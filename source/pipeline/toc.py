"""TOC leader-line parser — single source of truth.

Used only when the PDF has no outline (get_toc() is empty). Detects lines
with dot leaders and a trailing page number, and turns them into a list.
Everything that is not a leader line is left untouched.

Fail Fast: a line that looks like a TOC entry but has no page number raises.
"""
from __future__ import annotations
import re
from typing import List, Tuple


# Title .... 12   or   Title ..... **12**
_LEADER = re.compile(
    r"^\**\s*(?P<title>.+?)\s*\**\s*\.{3,}\s*[\*\s]*(?P<page>\d{1,3})\s*\**\s*$"
)


class BadTocLine(ValueError):
    """Raised when a leader line has no usable page number."""


def is_toc_line(line: str) -> bool:
    return bool(_LEADER.match(line.strip().strip("*").strip()))


def parse_toc_line(line: str) -> Tuple[str, str]:
    """Return (title, page). Fail Fast if the page number is missing."""
    m = _LEADER.match(line.strip().strip("*").strip())
    if not m or not m.group("page"):
        raise BadTocLine(f"TOC line has no page number: {line!r}")
    title = re.sub(r"\*+", "", m.group("title"))
    title = re.sub(r"\s+", " ", title).strip()
    if not title:
        raise BadTocLine(f"TOC line has no title: {line!r}")
    return title, m.group("page")


def toc_to_markdown(text: str) -> str:
    """Rewrite a block of leader-dot lines as a markdown list.

    Non-leader lines are preserved. A run of leader lines becomes one list.
    """
    out: List[str] = []
    in_list = False
    for raw in text.splitlines():
        line = raw.strip()
        if is_toc_line(line):
            title, page = parse_toc_line(line)
            if not in_list:
                if out and out[-1] != "":
                    out.append("")
                in_list = True
            out.append(f"- {title} — {page}")
        else:
            if in_list and line:
                out.append("")
                in_list = False
            out.append(raw)
    return "\n".join(out)
