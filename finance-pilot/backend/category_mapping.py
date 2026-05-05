"""Category mapping backed by DEFAULT_CATEGORIES from categories.py.

Replaces the old category_map.json (496 personal entries) with the
standard SaaS category system.  Keeps the same public API so existing
callers (classification_service.py, etc.) continue to work.
"""

from typing import Optional

from categories import DEFAULT_CATEGORIES


def load_category_map() -> dict[str, str]:
    """Build a keyword → category lookup from DEFAULT_CATEGORIES.

    Returns a dict where each key is a lowercase keyword and the value
    is the category name.  This mirrors the old JSON-based map so that
    ``get_category()`` can do a simple substring search.
    """
    mapping: dict[str, str] = {}
    for category, keywords in DEFAULT_CATEGORIES.items():
        for kw in keywords:
            mapping[kw.lower()] = category
    return mapping


def get_category(normalized_desc: str, category_map: dict | None = None) -> str | None:
    """Return the category for *normalized_desc* using keyword matching.

    Uses partial, case-insensitive matching against the keyword map
    built from ``DEFAULT_CATEGORIES``.  Returns ``None`` when no keyword
    matches (the caller is expected to fall back to "Outros").
    """
    if category_map is None:
        category_map = load_category_map()
    if not normalized_desc:
        return None

    desc_lower = normalized_desc.strip().lower()
    if not desc_lower:
        return None

    for keyword, category in category_map.items():
        if keyword in desc_lower:
            return category

    return None
