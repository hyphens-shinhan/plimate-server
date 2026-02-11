from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status
from postgrest import CountMethod

from app.core.database import supabase
from app.core.deps import AuthenticatedUser
from app.schemas.grades import (
    LetterGrade,
    Semester,
    SemesterGradeCreate,
    SemesterGradeListResponse,
    SemesterGradeResponse,
    SemesterGradeUpdate,
    YearGPAResponse,
)

router = APIRouter(prefix="/grades", tags=["grades"])


def calculate_gpa(grades: list[SemesterGradeResponse]) -> dict:
    """Calculate weighted GPA from list of grades."""
    if not grades:
        return {"gpa": 0.0, "total_credits": 0.0, "semester_breakdown": []}

    # Overall calculation
    total_points = sum(
        LetterGrade(g.grade).gpa_value * g.credits for g in grades
    )
    total_credits = sum(g.credits for g in grades)
    overall_gpa = round(total_points / total_credits, 2) if total_credits > 0 else 0.0

    # Semester breakdown
    semester_data: dict[int, dict] = {}
    for grade in grades:
        key = grade.semester
        if key not in semester_data:
            semester_data[key] = {"credits": 0.0, "points": 0.0}
        semester_data[key]["credits"] += grade.credits
        semester_data[key]["points"] += (
            LetterGrade(grade.grade).gpa_value * grade.credits
        )

    semester_breakdown = [
        {
            "semester": sem,
            "credits": data["credits"],
            "gpa": round(data["points"] / data["credits"], 2)
            if data["credits"] > 0
            else 0.0,
        }
        for sem, data in sorted(semester_data.items())
    ]

    return {
        "gpa": overall_gpa,
        "total_credits": total_credits,
        "semester_breakdown": semester_breakdown,
    }


@router.post("/", response_model=SemesterGradeResponse, status_code=status.HTTP_201_CREATED)
async def create_grade(grade: SemesterGradeCreate, user: AuthenticatedUser):
    """Create a new semester grade. Prevents duplicate courses per semester."""
    try:
        # Check for duplicate course in same semester
        existing = (
            supabase.table("semester_grades")
            .select("id")
            .eq("user_id", str(user.id))
            .eq("year", grade.year)
            .eq("semester", grade.semester.value)
            .eq("course_name", grade.course_name)
            .execute()
        )

        if existing.data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Course already exists for this semester",
            )

        # Insert grade
        result = (
            supabase.table("semester_grades")
            .insert(
                {
                    "user_id": str(user.id),
                    "year": grade.year,
                    "semester": grade.semester.value,
                    "course_name": grade.course_name,
                    "grade": grade.grade.value,
                    "credits": grade.credits,
                }
            )
            .execute()
        )

        if not result.data:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return SemesterGradeResponse(**result.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/", response_model=SemesterGradeListResponse)
async def list_grades(
    user: AuthenticatedUser,
    year: int | None = None,
    semester: int | None = None,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """List all user's grades with optional year/semester filters."""
    try:
        query = (
            supabase.table("semester_grades")
            .select("*", count=CountMethod.exact)
            .eq("user_id", str(user.id))
        )

        if year:
            query = query.eq("year", year)
        if semester:
            query = query.eq("semester", semester)

        result = (
            query.order("year", desc=True)
            .order("semester", desc=True)
            .order("course_name")
            .range(offset, offset + limit - 1)
            .execute()
        )

        return SemesterGradeListResponse(
            grades=[SemesterGradeResponse(**g) for g in result.data or []],
            total=result.count or 0,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/{year}/gpa", response_model=YearGPAResponse)
async def get_year_gpa(year: int, user: AuthenticatedUser):
    """Calculate GPA for a specific year with semester breakdown."""
    try:
        # Get all grades for the year
        result = (
            supabase.table("semester_grades")
            .select("*")
            .eq("user_id", str(user.id))
            .eq("year", year)
            .execute()
        )

        grades = [SemesterGradeResponse(**g) for g in result.data or []]

        # Calculate GPA
        gpa_data = calculate_gpa(grades)

        return YearGPAResponse(
            year=year,
            total_credits=gpa_data["total_credits"],
            gpa=gpa_data["gpa"],
            semester_breakdown=gpa_data["semester_breakdown"],
            grades=grades,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.patch("/{grade_id}", response_model=SemesterGradeResponse)
async def update_grade(
    grade_id: UUID, grade_update: SemesterGradeUpdate, user: AuthenticatedUser
):
    """Update a specific grade (only own grades)."""
    update_data = grade_update.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )

    # If course_name is being updated, check for duplicates
    if "course_name" in update_data:
        # First get the existing grade to know year/semester
        existing = (
            supabase.table("semester_grades")
            .select("year, semester")
            .eq("id", str(grade_id))
            .eq("user_id", str(user.id))
            .single()
            .execute()
        )
        if existing.data:
            duplicate = (
                supabase.table("semester_grades")
                .select("id")
                .eq("user_id", str(user.id))
                .eq("year", existing.data["year"])
                .eq("semester", existing.data["semester"])
                .eq("course_name", update_data["course_name"])
                .neq("id", str(grade_id))
                .execute()
            )
            if duplicate.data:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Course already exists for this semester",
                )

    # Convert enums to values for Supabase
    if "grade" in update_data and update_data["grade"] is not None:
        update_data["grade"] = update_data["grade"].value

    try:
        result = (
            supabase.table("semester_grades")
            .update(update_data)
            .eq("id", str(grade_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Grade not found or unauthorized",
            )

        return SemesterGradeResponse(**result.data[0])
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.delete("/{grade_id}")
async def delete_grade(grade_id: UUID, user: AuthenticatedUser):
    """Delete a specific grade (only own grades)."""
    try:
        # Verify grade belongs to user and delete
        result = (
            supabase.table("semester_grades")
            .delete()
            .eq("id", str(grade_id))
            .eq("user_id", str(user.id))
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Grade not found or unauthorized",
            )

        return {"message": "Grade deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )
