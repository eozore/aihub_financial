import json
from pathlib import Path

MAP_FILE = Path(__file__).parent / "category_map.json"


def load_category_map():
    if not MAP_FILE.exists():
        return {}
    with MAP_FILE.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("mapping", {})


def get_category(normalized_desc: str, category_map: dict | None = None) -> str | None:
    if category_map is None:
        category_map = load_category_map()
    if not normalized_desc:
        return None
    value = category_map.get(normalized_desc)
    if value is None:
        return None
    if isinstance(value, str) and value.strip() == "":
        return None
    if isinstance(value, str) and value.strip().lower() in {"ambigua", "ambígua", "ambiguous"}:
        return None
    return value
