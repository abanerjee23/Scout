"""Bounded structural file checks. No OCR, extraction or policy decision."""

import hashlib
import io
import json
import sys
import warnings

from PIL import Image
from pypdf import PdfReader

MAX_BYTES = 10 * 1024 * 1024
MAX_PAGES = 10
MAX_FILES = 10
MAX_REQUEST_BYTES = MAX_BYTES * MAX_FILES + 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000


class InvalidDocument(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def validate_bytes(content, declared_mime):
    if not 0 < len(content) <= MAX_BYTES:
        raise InvalidDocument("document_size")
    mime = (
        "image/png"
        if content.startswith(b"\x89PNG\r\n\x1a\n")
        else "image/jpeg"
        if content.startswith(b"\xff\xd8\xff")
        else "application/pdf"
        if content.startswith(b"%PDF-")
        else None
    )
    if mime is None or declared_mime != mime:
        raise InvalidDocument("document_type")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            if mime == "application/pdf":
                pdf = PdfReader(io.BytesIO(content), strict=True)
                if pdf.is_encrypted:
                    raise InvalidDocument("encrypted_pdf")
                pages = len(pdf.pages)
                if not 1 <= pages <= MAX_PAGES:
                    raise InvalidDocument("document_pages")
                for page in pdf.pages:
                    if page.mediabox.width <= 0 or page.mediabox.height <= 0:
                        raise InvalidDocument("invalid_document")
                    # Validate referenced content streams, not merely the page tree.
                    contents = page.get_contents()
                    if contents is not None:
                        contents.get_data()
            else:
                with Image.open(io.BytesIO(content)) as image:
                    if image.format != {"image/png": "PNG", "image/jpeg": "JPEG"}[mime]:
                        raise InvalidDocument("document_type")
                    if getattr(image, "n_frames", 1) != 1:
                        raise InvalidDocument("document_pages")
                    image.verify()
                with Image.open(io.BytesIO(content)) as image:
                    image.load()
                pages = 1
    except InvalidDocument:
        raise
    except Exception:
        raise InvalidDocument("invalid_document") from None
    return {"mime_type": mime, "page_count": pages, "sha256": hashlib.sha256(content).hexdigest()}


def main():
    # Child receives synthetic/private bytes via stdin only; output is fixed fields.
    import logging
    import resource

    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 10))

    logging.disable(logging.CRITICAL)
    try:
        result = validate_bytes(sys.stdin.buffer.read(MAX_BYTES + 1), sys.argv[1])
        print(json.dumps(result))
    except InvalidDocument as error:
        print(json.dumps({"error": error.code}))
        sys.exit(1)


if __name__ == "__main__":
    main()
