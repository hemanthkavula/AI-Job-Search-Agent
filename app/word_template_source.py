from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMAT_RECORD = ROOT / "data" / "master_word_format.json"
TEMPLATE_PATH = ROOT / "data" / "Hemanth_Kavula_Senior_Data_Engineer_Resume.docx"
CHUNK_DIR = ROOT / "data" / "master_word_template_b64"


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def ensure_master_word_template() -> Path:
    """Materialize the exact user-uploaded DOCX from checksum-verified base64 chunks.

    The checked-in binary is only a convenience copy. The base64 chunk set is the
    canonical byte transport because GitHub text files preserve it exactly. Every
    materialization is verified against the SHA-256 recorded from the user's upload.
    """
    record = json.loads(FORMAT_RECORD.read_text(encoding="utf-8"))
    expected = (record.get("source") or {}).get("sha256")
    if not expected:
        raise RuntimeError("Master Word format record is missing the uploaded DOCX SHA-256")

    if TEMPLATE_PATH.exists():
        current = TEMPLATE_PATH.read_bytes()
        if _sha256_bytes(current) == expected:
            return TEMPLATE_PATH

    parts = sorted(CHUNK_DIR.glob("part*.txt"))
    if not parts:
        raise RuntimeError("Exact uploaded Word template chunks are missing")
    encoded = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    try:
        data = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise RuntimeError(f"Exact Word template chunks could not be decoded: {exc}") from exc

    actual = _sha256_bytes(data)
    if actual != expected:
        raise RuntimeError(
            f"Reconstructed Word template checksum mismatch: expected {expected}, got {actual}"
        )

    TEMPLATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    TEMPLATE_PATH.write_bytes(data)
    if _sha256_bytes(TEMPLATE_PATH.read_bytes()) != expected:
        raise RuntimeError("Exact Word template could not be materialized without byte drift")
    return TEMPLATE_PATH
