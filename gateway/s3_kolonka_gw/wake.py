import re

# Whisper often hears «колонка» as тонко / колонна / голонка.
_WAKE = re.compile(
    r"(?:эй|hey|hi)\s+|"
    r"(?:колонк[ауиеы]|калонк[ауиеы]|коленк[ауиеы]|каленк[ауиеы]|"
    r"колонн[ауиеы]|голонк[ауиеы]|полонк[ауиеы]|толонк[ауиеы]|клонка|"
    r"коломк[ауиеы]|тонк[аоуиеы]|"
    r"kolonka|coloka|слушай(?:те)?|проснись|очнись)",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"[\s,!.:;?-]+")
_FUZZY = ("колонка", "kolonka", "слушай")


def _norm(token: str) -> str:
    return token.lower().replace("ё", "е")


def _lev(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 2:
        return 99
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def match_wake(text: str) -> tuple[bool, str]:
    raw = (text or "").strip()
    if not raw:
        return False, ""
    if _WAKE.search(raw):
        rest = _WAKE.sub(" ", raw)
        rest = _SPLIT.sub(" ", rest).strip()
        return True, rest
    parts = _SPLIT.split(raw, maxsplit=1)
    token = _norm(parts[0]) if parts else ""
    if token and len(token) >= 5 and any(_lev(token, word) <= 2 for word in _FUZZY):
        rest = parts[1] if len(parts) > 1 else ""
        rest = _SPLIT.sub(" ", rest).strip()
        return True, rest
    return False, raw
