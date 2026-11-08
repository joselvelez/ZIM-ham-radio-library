"""Conservative SVG optimizer — SVGO safe subset.

Pure function. Implements only the transformations that SVGO's default
preset treats as safe for static diagrams:

- remove XML declaration and comments
- remove <metadata>, editor namespaces (inkscape, sodipodi, etc.)
- remove empty groups and empty attributes
- round numeric values in path data and attributes to 2 decimal places
- preserve viewBox and clipPath elements (required for correct clipping)

Fail Fast: raises ValueError if the input is not well-formed SVG or the
result is empty.
"""
from __future__ import annotations
import re
from xml.etree import ElementTree as ET


_EDITOR_NS = (
    "inkscape",
    "sodipodi",
    "adobe",
    "illustrator",
    "sketch",
)
_NUMERIC = re.compile(r"-?\d+\.\d{3,}")


class BadSVG(ValueError):
    """Raised when an SVG cannot be optimized safely."""


def _round_numbers(text: str) -> str:
    def repl(m: re.Match) -> str:
        try:
            return f"{float(m.group(0)):.2f}".rstrip("0").rstrip(".")
        except ValueError:
            return m.group(0)
    return _NUMERIC.sub(repl, text)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _strip_editor_attrs(elem: ET.Element) -> None:
    to_drop = []
    for key in list(elem.attrib):
        low = key.lower()
        if any(ns in low for ns in _EDITOR_NS) or (
            low.startswith("{") and any(ns in low for ns in _EDITOR_NS)
        ):
            to_drop.append(key)
        elif elem.attrib[key] == "":
            to_drop.append(key)
    for key in to_drop:
        del elem.attrib[key]
    for child in list(elem):
        local = _local(child.tag).lower()
        if local == "metadata" or any(ns in local for ns in _EDITOR_NS):
            elem.remove(child)
            continue
        _strip_editor_attrs(child)
        # Remove empty groups that have no attributes and no children
        if _local(child.tag) == "g" and not child.attrib and len(child) == 0:
            elem.remove(child)


def optimize_svg(svg: str) -> str:
    """Return a cleaned SVG. Raises BadSVG on malformed input."""
    if not svg or not svg.strip():
        raise BadSVG("empty SVG")
    # Drop XML declaration and comments before parsing
    cleaned = re.sub(r"<\?xml[^?]*\?>", "", svg)
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)
    cleaned = cleaned.strip()
    if not cleaned.startswith("<svg"):
        # Allow a leading newline or whitespace already stripped
        if "<svg" not in cleaned[:200]:
            raise BadSVG("input is not an SVG")
    try:
        root = ET.fromstring(cleaned)
    except ET.ParseError as exc:
        raise BadSVG(f"malformed SVG: {exc}") from exc
    if not root.tag.endswith("svg") and _local(root.tag) != "svg":
        raise BadSVG("root element is not <svg>")

    _strip_editor_attrs(root)

    # Round numbers in path d attributes and numeric attrs
    for elem in root.iter():
        if "d" in elem.attrib:
            elem.attrib["d"] = _round_numbers(elem.attrib["d"])
        for key in list(elem.attrib):
            val = elem.attrib[key]
            if any(c.isdigit() for c in val) and "." in val:
                elem.attrib[key] = _round_numbers(val)

    # Ensure viewBox is preserved (do not remove it)
    # Serialize
    try:
        out = ET.tostring(root, encoding="unicode", method="xml")
    except Exception as exc:
        raise BadSVG(f"could not serialize SVG: {exc}") from exc
    if not out or "svg" not in out.lower():
        raise BadSVG("optimizer produced empty output")
    return out
