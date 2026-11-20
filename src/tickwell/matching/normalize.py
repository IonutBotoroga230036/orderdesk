import re
import unicodedata

POT_SIZES_P = {9, 10, 11, 12, 13, 14, 15, 17, 19, 21, 23}


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation: 'Fächerahorn  ROT!' -> 'facherahorn rot'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"[^a-z0-9\-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_pot(text: str) -> str | None:
    """Read a pot or container size from free text.

    P13, P15 ... are pot diameters in cm; C3, C5 ... are container litres.
    '5 liter', '5L', '3 ltr' -> C5/C3. A bare 'buxus 15' is read as P15.
    """
    t = normalize(text)
    if m := re.search(r"\bp\s?(\d{1,2})\b", t):
        return f"P{int(m.group(1))}"
    if m := re.search(r"\bc\s?(\d{1,2})\b", t):
        return f"C{int(m.group(1))}"
    if m := re.search(r"\b(\d{1,2})\s?(l|lt|ltr|liter|litre|liters|litres)\b", t):
        return f"C{int(m.group(1))}"
    nums = re.findall(r"(?<![\w-])(\d{1,2})(?![\w-])", t)
    if len(nums) == 1 and int(nums[0]) in POT_SIZES_P:
        return f"P{int(nums[0])}"
    return None


def strip_sizes(text: str) -> str:
    t = normalize(text)
    t = re.sub(r"\b[pc]\s?\d{1,2}\b", " ", t)
    t = re.sub(r"\b\d{1,2}\s?(l|lt|ltr|liter|litre|liters|litres)\b", " ", t)
    t = re.sub(r"(?<![\w-])\d+(?![\w-])", " ", t)
    return re.sub(r"\s+", " ", t).strip()
