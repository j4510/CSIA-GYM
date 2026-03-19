import hashlib
import os
from PIL import Image, ImageDraw

AVATAR_DIR = os.path.join(os.path.dirname(__file__), 'static', 'avatars')
GRID = 5
SIZE = 500
CELL = SIZE // GRID
PADDING = SIZE // 10


def _color_from_hash(h):
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    # Ensure it's not too dark or too light
    r = max(50, min(200, r))
    g = max(50, min(200, g))
    b = max(50, min(200, b))
    return (r, g, b)


def generate_identicon(username: str) -> str:
    """Generate a 500x500 WebP identicon for the given username.
    Returns the filename (not full path)."""
    os.makedirs(AVATAR_DIR, exist_ok=True)

    h = hashlib.md5(username.lower().encode()).hexdigest()
    color = _color_from_hash(h)
    bg = (15, 15, 15)

    img = Image.new('RGB', (SIZE, SIZE), bg)
    draw = ImageDraw.Draw(img)

    # 5x5 grid, mirrored horizontally — use first 15 bits of hash
    for row in range(GRID):
        for col in range(GRID // 2 + 1):
            idx = row * 3 + col
            bit = int(h[idx % len(h)], 16) % 2
            if bit:
                x0 = PADDING + col * CELL
                y0 = PADDING + row * CELL
                x1 = x0 + CELL - 2
                y1 = y0 + CELL - 2
                draw.rectangle([x0, y0, x1, y1], fill=color)
                # Mirror
                mirror_col = GRID - 1 - col
                if mirror_col != col:
                    mx0 = PADDING + mirror_col * CELL
                    draw.rectangle([mx0, y0, mx0 + CELL - 2, y1], fill=color)

    filename = f'avatar_{username}.webp'
    img.save(os.path.join(AVATAR_DIR, filename), 'WEBP', quality=85)
    return filename
