"""Exercise the real receipt subprocess on the developer and CI platforms."""

import hashlib
import io

import pytest
from PIL import Image
from unloop.evidence import bounded_validation
from unloop.evidence_validation import InvalidDocument


def test_receipt_subprocess_accepts_png_and_rejects_corrupt_bytes():
    stream = io.BytesIO()
    Image.new("RGB", (32, 32), "white").save(stream, format="PNG")
    content = stream.getvalue()
    assert bounded_validation(content, "image/png") == {
        "mime_type": "image/png",
        "page_count": 1,
        "sha256": hashlib.sha256(content).hexdigest(),
    }
    with pytest.raises(InvalidDocument, match="invalid_document"):
        bounded_validation(b"\x89PNG\r\n\x1a\ncorrupt", "image/png")
