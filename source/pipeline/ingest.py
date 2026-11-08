"""Ingest step: hash PDF, simple fingerprint, update manifest."""
import hashlib
import json
from pathlib import Path
from typing import Dict, Any

MANIFEST_PATH = Path(__file__).parent.parent / "manifest.json"


def _location_tier(path: str) -> str:
    p = path.replace("\\", "/")
    if "/paid/" in p:
        return "paid"
    if "/extensive/" in p:
        return "extensive"
    if "/basic/" in p:
        return "basic"
    return "unknown"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def simple_fingerprint(path: Path) -> str:
    """Very lightweight fingerprint: size + first/last 4k hash. Placeholder for MinHash later."""
    size = path.stat().st_size
    h = hashlib.sha256()
    with open(path, "rb") as f:
        head = f.read(4096)
        h.update(head)
        if size > 8192:
            f.seek(-4096, 2)
            h.update(f.read(4096))
    return f"sz{size}-h{h.hexdigest()[:16]}"

def load_manifest() -> Dict[str, Any]:
    if MANIFEST_PATH.exists():
        with open(MANIFEST_PATH) as f:
            return json.load(f)
    return {"documents": {}, "version": 1}

def save_manifest(data: Dict[str, Any]):
    with open(MANIFEST_PATH, "w") as f:
        json.dump(data, f, indent=2)

def ingest_pdf(pdf_path: Path, category: str) -> Dict[str, Any]:
    """Ingest a single PDF, update manifest, return record."""
    pdf_path = Path(pdf_path).resolve()
    sha = sha256_file(pdf_path)
    fp = simple_fingerprint(pdf_path)
    rel = str(pdf_path.relative_to(Path(__file__).parent.parent.parent))  # relative to repo root roughly

    manifest = load_manifest()
    docs = manifest.setdefault("documents", {})

    # Dedup check
    for doc_id, rec in docs.items():
        if rec.get("sha256") == sha:
            # Same file. Honor a new category if the caller passed one.
            if category and rec.get("category") != category:
                rec["category"] = category
                save_manifest(manifest)
                print(f"Exact duplicate of {doc_id}; category updated to {category}")
            else:
                print(f"Exact duplicate of {doc_id}")
            return rec
        if rec.get("fingerprint") == fp:
            print(f"Near-duplicate fingerprint of {doc_id}")

    doc_id = f"{pdf_path.stem}-{sha[:8]}"
    record = {
        "id": doc_id,
        "path": str(pdf_path.relative_to(pdf_path.parents[3]) if len(pdf_path.parts) > 3 else pdf_path.name),
        "sha256": sha,
        "fingerprint": fp,
        "size": pdf_path.stat().st_size,
        "category": category,
        "location": _location_tier(str(pdf_path)),
        "title": pdf_path.stem,
        "status": "ingested",
        "canonical": True,
    }
    docs[doc_id] = record
    save_manifest(manifest)
    print(f"Ingested {doc_id}")
    return record
