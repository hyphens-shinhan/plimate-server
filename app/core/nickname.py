import random
from typing import Tuple
from app.core.config import settings

# Korean adjective + noun combinations for fun, memorable nicknames
ADJECTIVES = [
    "행복한",
    "귀여운",
    "용감한",
    "똑똑한",
    "활발한",
    "차분한",
    "명랑한",
    "씩씩한",
    "재치있는",
    "다정한",
    "멋진",
    "따뜻한",
    "시원한",
    "즐거운",
    "밝은",
    "조용한",
    "활기찬",
    "상냥한",
    "당당한",
    "신나는",
    "슬기로운",
    "든든한",
    "침착한",
    "빛나는",
    "사랑스러운",
    "발랄한",
    "의젓한",
    "산뜻한",
    "튼튼한",
    "깜찍한",
    "착한",
    "영리한",
    "다재다능한",
    "친근한",
    "쾌활한",
    "낙천적인",
    "겸손한",
    "현명한",
    "성실한",
    "포용적인",
    "생기있는",
    "고결한",
    "정직한",
    "신뢰할",
    "단호한",
    "유능한",
    "열정적인",
    "섬세한",
    "겸손한",
    "주도적인",
]

NOUNS = [
    "쏠",
    "몰리",
    "리노",
    "슈",
    "도레미",
    "루루라라",
    "플리",
    "레이",
]

# Avatar identifiers (stored in database, URLs constructed on retrieval)
ANONYMOUS_AVATARS = [
    "anony_1",
    "anony_2",
    "anony_3",
    "anony_4",
    "anony_5",
    "anony_6",
    "anony_7",
    "anony_8",
]


def get_avatar_url(avatar_id: str) -> str:
    """
    Construct full avatar URL from identifier.

    Args:
        avatar_id: Avatar identifier like "anony_1"

    Returns:
        Full URL like "https://...supabase.co/storage/.../anony_1.png"
    """
    return f"{settings.AVATAR_BUCKET_URL}{avatar_id}.png"

# Optional: Block inappropriate combinations if needed
BLOCKED_COMBINATIONS = set()


def generate_nickname() -> Tuple[str, str]:
    """
    Generate random fun nickname with avatar identifier.

    Uses Korean adjective + noun combinations to create memorable,
    fun, and culturally appropriate nicknames.

    Returns:
        Tuple[str, str]: (nickname, avatar_identifier)
                        e.g., ("행복한 쏠", "anony_1")
    """
    max_attempts = 10
    for _ in range(max_attempts):
        adjective = random.choice(ADJECTIVES)
        noun = random.choice(NOUNS)

        if (adjective, noun) not in BLOCKED_COMBINATIONS:
            nickname = f"{adjective} {noun}"
            avatar = random.choice(ANONYMOUS_AVATARS)
            return nickname, avatar

    # Fallback if all attempts blocked (unlikely)
    return f"{random.choice(ADJECTIVES)} {random.choice(NOUNS)}", random.choice(
        ANONYMOUS_AVATARS
    )


def get_random_avatar() -> str:
    """
    Get random avatar identifier from the 8-avatar pool.

    Used for club join avatar assignment and other contexts
    where nickname is provided but avatar needs to be assigned.

    Returns:
        str: Avatar identifier like "anony_1" (full URL constructed via get_avatar_url)
    """
    return random.choice(ANONYMOUS_AVATARS)
