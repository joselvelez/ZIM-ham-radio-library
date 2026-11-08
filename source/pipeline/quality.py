"""Quality score and review queue.

Score is derived only from data the extractor already produced.
Low scores are written to a review list; nothing is re-implemented here.
"""
from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
import json
from datetime import datetime

REVIEW_DIR = Path("source/notes/review")

def score_document(extracted: Dict[str, Any], svg_ok: bool) -> Dict[str, Any]:
    """Simple, explainable score from extraction results.
    - text: enough body text present
    - figures: native vectors found and SVG produced when expected
    """
    pages = extracted.get("pages", [])
    page_count = len(pages) or 1
    body_chars = sum(len(b["text"]) for p in pages for b in p.get("text_blocks", []))
    chars_per_page = body_chars / page_count
    has_vectors = any(p.get("has_native_vectors") for p in pages)
    label_count = sum(len(p.get("label_blocks", [])) for p in pages)

    # text density: 150+ chars/page is full marks; empty pages hurt the score
    text_score = min(1.0, chars_per_page / 150)
    figure_score = 1.0 if (not has_vectors or svg_ok) else 0.0
    label_bonus = 0.1 if label_count else 0.0

    total = round(0.6 * text_score + 0.4 * figure_score + label_bonus, 2)
    total = min(1.0, total)

    return {
        "score": total,
        "text_score": round(text_score, 2),
        "figure_score": figure_score,
        "body_chars": body_chars,
        "chars_per_page": round(chars_per_page, 1),
        "page_count": page_count,
        "has_vectors": has_vectors,
        "svg_ok": svg_ok,
        "label_count": label_count,
    }

def enqueue_if_low(record: Dict[str, Any], quality: Dict[str, Any], threshold: float = 0.6) -> Path | None:
    """Write a review entry when score is below threshold. Returns the path or None."""
    if quality["score"] >= threshold:
        return None
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "id": record.get("id"),
        "path": record.get("path"),
        "score": quality["score"],
        "quality": quality,
        "queued_at": datetime.utcnow().isoformat() + "Z",
        "reason": "score below threshold",
    }
    out = REVIEW_DIR / f"{record.get('id', 'unknown')}.json"
    out.write_text(json.dumps(entry, indent=2))
    return out
