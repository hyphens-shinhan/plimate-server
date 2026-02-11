"""
Receipt OCR API. Same logic as hyphens-shinhan/hyphens-frontend:
extract text with Tesseract (kor+eng), parse into item name + price pairs.

System dependency: Tesseract OCR must be installed (e.g. macOS: brew install
tesseract tesseract-lang; Ubuntu: apt install tesseract-ocr tesseract-ocr-kor).

OCR runs in a thread pool so the first run (language data load, 1–2 min) does
not block the event loop.
"""

import asyncio
import re
from io import BytesIO

import pytesseract
from fastapi import APIRouter, File, HTTPException, UploadFile, status
from PIL import Image

from app.core.deps import AuthenticatedUser
from app.schemas.ocr import ReceiptOcrItem, ReceiptOcrResponse

router = APIRouter(prefix="/ocr", tags=["ocr"])

# Skip keywords (header/footer) - same as frontend
SKIP_KEYWORDS = [
    "영수증",
    "RECEIPT",
    "TOTAL",
    "합계",
    "소계",
    "SUBTOTAL",
    "TAX",
    "세금",
    "부가세",
    "VAT",
    "할인",
    "DISCOUNT",
    "거스름돈",
    "CHANGE",
    "받은금액",
    "지불금액",
    "PAID",
    "카드",
    "CARD",
    "현금",
    "CASH",
    "포인트",
    "POINT",
    "일시",
    "날짜",
    "DATE",
    "TIME",
    "시간",
    "주소",
    "ADDRESS",
    "전화",
    "PHONE",
    "사업자",
    "등록번호",
    "번호",
    "POS",
    "상품명",
    "단가",
    "수량",
    "금액",
    "품목",
    "품명",
]


def _clean_price(price_str: str) -> float:
    """Fix common OCR errors: ¢->9, O->0, l->1. Same as frontend cleanPrice."""
    cleaned = (
        price_str.replace("¢", "9")
        .replace("©", "9")
        .replace("O", "0")
        .replace("o", "0")
        .replace("l", "1")
        .replace("|", "1")
    )
    cleaned = re.sub(r"[,\s]", "", cleaned)
    cleaned = re.sub(r"[^\d]", "", cleaned)
    return float(cleaned) if cleaned else 0.0


def _has_korean(text: str) -> bool:
    return bool(re.search(r"[가-힣]", text))


def _parse_receipt_items(ocr_text: str) -> list[ReceiptOcrItem]:
    """
    Parse OCR text into item name + price pairs. Same logic as hyphens-shinhan
    utils/ocr.ts parseReceiptItems().
    """
    items: list[ReceiptOcrItem] = []
    lines = [
        line.strip()
        for line in ocr_text.split("\n")
        if line.strip()
    ]

    start_index = 0
    for i, line in enumerate(lines):
        if re.search(
            r"(상품명|품목|품명|ITEM|PRODUCT)",
            line,
            re.IGNORECASE,
        ) and re.search(
            r"(단가|수량|금액|가격|PRICE|AMOUNT)",
            line,
            re.IGNORECASE,
        ):
            start_index = i + 1
            break

    i = start_index
    while i < len(lines):
        line = lines[i]
        if len(line) < 3:
            i += 1
            continue
        if any(k in line for k in SKIP_KEYWORDS):
            i += 1
            continue
        if re.match(r"^[\d\s,.\-¢]+$", line):
            i += 1
            continue
        if re.search(r"\d{2,3}-\d{3,4}-\d{4}|\d{4}-\d{2}-\d{2}|\d{2}:\d{2}", line):
            i += 1
            continue

        item_name = ""
        price = 0.0

        # Pattern 1: item name and price on same line
        same_line = re.match(
            r"([가-힣\w\s()]+?)\s+([\d]{1,3}(?:[,\s]?[\d]{3})*)\s*(?:원|₩)?",
            line,
        )
        if same_line:
            item_name = same_line.group(1).strip()
            price = _clean_price(same_line.group(2))
            if (
                _has_korean(item_name)
                and 1000 <= price < 100_000_000
            ):
                items.append(ReceiptOcrItem(name=item_name, price=round(price)))
                i += 1
                continue

        # Pattern 2: item name on current line, price on next line
        if _has_korean(line) and i + 1 < len(lines):
            next_line = lines[i + 1]
            price_match = re.search(r"([\d]{1,3}(?:[,\s]?[\d]{3})*)", next_line)
            if price_match:
                potential_price = _clean_price(price_match.group(1))
                if (
                    1000 <= potential_price < 100_000_000
                    and not any(k in line for k in SKIP_KEYWORDS)
                    and len(line) > 2
                ):
                    items.append(
                        ReceiptOcrItem(name=line.strip(), price=round(potential_price))
                    )
                    i += 2
                    continue

        # Pattern 3: price at end of line
        price_at_end = re.match(
            r"(.+?)\s+([\d]{1,3}(?:[,\s]?[\d]{3})*)\s*(?:원|₩)?$",
            line,
        )
        if price_at_end:
            potential_name = price_at_end.group(1).strip()
            potential_price = _clean_price(price_at_end.group(2))
            if (
                _has_korean(potential_name)
                and 1000 <= potential_price < 100_000_000
            ):
                name = re.sub(r"\s+", " ", potential_name)
                name = re.sub(r"[^\w가-힣\s()]", "", name).strip()
                if len(name) >= 2:
                    items.append(ReceiptOcrItem(name=name, price=round(potential_price)))
            i += 1
            continue

        i += 1

    # Deduplicate and filter (same as frontend)
    def is_valid(item: ReceiptOcrItem, index: int, self: list[ReceiptOcrItem]) -> bool:
        if not _has_korean(item.name):
            return False
        if item.price < 1000 or item.price >= 100_000_000:
            return False
        first_idx = next(
            (
                j
                for j, other in enumerate(self)
                if other.name == item.name or abs(other.price - item.price) < 100
            ),
            len(self),
        )
        if index != first_idx:
            return False
        if re.match(r"^[\d\s,.\-]+$", item.name):
            return False
        return True

    unique = [item for i, item in enumerate(items) if is_valid(item, i, items)]
    return unique


def _extract_total_from_receipt(ocr_text: str) -> int | None:
    """
    When no line items are found, try to extract a single total from lines
    containing 합계/총/Total/TOTAL etc. Returns price in won or None.
    """
    total_keywords = re.compile(
        r"(합계|총\s*금액|총\s*비용|총\s*결제|TOTAL|GRAND\s*TOTAL)",
        re.IGNORECASE,
    )
    for line in ocr_text.split("\n"):
        line = line.strip()
        if not total_keywords.search(line):
            continue
        # Look for price: digits with optional , or spaces (e.g. 12,000 or 12000)
        price_match = re.search(
            r"([\d]{1,3}(?:[,\s]?[\d]{3})*)\s*(?:원|₩|WON)?\s*$",
            line,
        )
        if price_match:
            price = _clean_price(price_match.group(1))
            if 100 <= price < 100_000_000:
                return round(price)
    return None


def _extract_text_from_image(image: Image.Image) -> str:
    """
    Run Tesseract OCR. Prefer kor+eng; fall back to eng if Korean data missing.
    Converts to RGB so Tesseract gets a compatible format (avoids empty text from RGBA/P).
    """
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    for lang in ("kor+eng", "eng"):
        try:
            return pytesseract.image_to_string(image, lang=lang) or ""
        except pytesseract.TesseractError:
            continue
    return ""


@router.post("/receipt", response_model=ReceiptOcrResponse)
async def receipt_ocr(
    _: AuthenticatedUser,
    file: UploadFile = File(..., description="Receipt image file"),
) -> ReceiptOcrResponse:
    """
    Upload a receipt image; returns extracted line items (name + price).
    Uses Tesseract OCR (kor+eng) and the same parsing rules as the frontend.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be an image (e.g. image/jpeg, image/png)",
        )
    try:
        contents = await file.read()
        image = Image.open(BytesIO(contents))
        image.load()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid image: {e!s}",
        ) from e

    try:
        ocr_text = await asyncio.to_thread(_extract_text_from_image, image)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OCR failed: {e!s}",
        ) from e

    # Return 200 with empty items when no text (so frontend shows "항목을 찾을 수 없습니다"
    # instead of treating 422 as error and falling back to client-side OCR).
    if not (ocr_text and ocr_text.strip()):
        return ReceiptOcrResponse(items=[])

    items = _parse_receipt_items(ocr_text)
    # 항목이 없으면 합계/총/Total 라인에서 총액만 추출해 "총 비용" 한 항목으로 반환
    if not items:
        total = _extract_total_from_receipt(ocr_text)
        if total is not None:
            items = [ReceiptOcrItem(name="총 비용", price=total)]
    return ReceiptOcrResponse(items=items)
