"""
image_utils.py — PIL image processing helpers.

All PIL Image objects are created and destroyed entirely within each
function. Callers only deal with plain bytes, so no Image resource
can leak into the calling module.
"""

import io
from PIL import Image


def encode_avatar(raw_bytes: bytes, size: int = 500) -> bytes:
    """
    Accept raw image bytes, return WebP-encoded bytes at size x size.
    No PIL Image object is ever returned or assigned outside this function.
    """
    out = io.BytesIO()
    src_buf = io.BytesIO(raw_bytes)
    try:
        with Image.open(src_buf) as img:
            img.draft('RGB', (size, size))
            with img.convert('RGB') as rgb:
                with rgb.resize((size, size), Image.LANCZOS) as resized:
                    resized.save(out, format='WEBP', quality=85)
    finally:
        src_buf.close()
    return out.getvalue()
