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

def score_document(extracted: Dict[str, Any], figures_ok: bool) -> Dict[str, Any]:
    """Score from pymupdf4llm chunks and whether figures were produced."""
    chunks = extracted.get("chunks") or []
    page_count = len(chunks) or 1
    body_chars = sum(len(c.get("text", "")) for c in chunks)
    chars_per_page = body_chars / page_count
    text_score = min(1.0, chars_per_page / 150)
    figure_score = 1.0 if figures_ok or body_chars > 0 else 0.0
    total = round(min(1.0, 0.6 * text_score + 0.4 * figure_score), 2)
    return {
        "score": total,
        "text_score": round(text_score, 2),
        "figure_score": figure_score,
        "body_chars": body_chars,
        "chars_per_page": round(chars_per_page, 1),
        "page_count": page_count,
        "figures_ok": figures_ok,
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
