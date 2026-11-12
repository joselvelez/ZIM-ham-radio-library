"""Category from the filename prefix.

The filename is the triage. `nav-comms_manual_yaesu_ft-857.pdf` is a manual.
The map is the single place a prefix becomes a taxonomy category.
Fail Fast if the prefix is not in the map.
"""
from __future__ import annotations
from pathlib import Path

# Prefix after `nav-comms_` and before the next `_`.
PREFIX_CATEGORY = {
    "manual": "manuals",
    "tutorial": "operating",
    "reference": "reference",
    "book": "reference",
    "article": "reference",
}


def category_from_filename(pdf_path: Path) -> str:
    """Taxonomy category for a file. Fail Fast if the prefix is unknown."""
    stem = pdf_path.stem
    parts = stem.split("_")
    if len(parts) < 3 or parts[0] != "nav-comms":
        raise SystemExit(
            f"{pdf_path.name} does not match nav-comms_<prefix>_…. "
            "Rename it or pass --category."
        )
    prefix = parts[1]
    category = PREFIX_CATEGORY.get(prefix)
    if category is None:
        known = ", ".join(sorted(PREFIX_CATEGORY))
        raise SystemExit(
            f"Unknown prefix {prefix!r} in {pdf_path.name}. Known: {known}."
        )
    return category
