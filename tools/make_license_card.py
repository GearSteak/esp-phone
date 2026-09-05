#!/usr/bin/env python3
"""Generate a printable Digivice demo paper-cart PNG (+ QR).

Usage (from repo root):
  pip install qrcode pillow
  python tools/make_license_card.py
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "docs" / "assets"
OUT_PNG = OUT_DIR / "digivice_demo_paper_cart.png"

DEMO_ID = "demo-hello"
DEMO_SECRET = "digivice-demo-secret"
PAYLOAD = (
    f"DIGIVICE-CARD:1:{DEMO_ID}:"
    + hashlib.sha256(f"{DEMO_SECRET}:{DEMO_ID}".encode()).hexdigest()[:10]
)


def main() -> int:
    try:
        import qrcode
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("Install: pip install qrcode pillow", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Trading-card-ish print at ~300 DPI (2.5" x 3.5")
    w, h = 750, 1050
    img = Image.new("RGB", (w, h), (245, 240, 230))
    draw = ImageDraw.Draw(img)

    # Outer frame
    draw.rectangle([18, 18, w - 19, h - 19], outline=(20, 20, 20), width=8)
    draw.rectangle([36, 36, w - 37, h - 37], outline=(180, 40, 40), width=4)

    try:
        font_title = ImageFont.truetype("arial.ttf", 54)
        font_body = ImageFont.truetype("arial.ttf", 28)
        font_small = ImageFont.truetype("arial.ttf", 22)
        font_mono = ImageFont.truetype("consola.ttf", 20)
    except OSError:
        font_title = ImageFont.load_default()
        font_body = font_title
        font_small = font_title
        font_mono = font_title

    draw.text((w // 2, 70), "DIGIVICE", fill=(20, 20, 20), font=font_title, anchor="mt")
    draw.text(
        (w // 2, 130),
        "PAPER CART",
        fill=(180, 40, 40),
        font=font_body,
        anchor="mt",
    )
    draw.text(
        (w // 2, 175),
        "Hello Digivice  ·  demo-hello",
        fill=(60, 60, 60),
        font=font_small,
        anchor="mt",
    )

    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(PAYLOAD)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    qr_img = qr_img.resize((420, 420), Image.NEAREST)
    qx, qy = (w - 420) // 2, 230
    img.paste(qr_img, (qx, qy))
    draw.rectangle([qx - 6, qy - 6, qx + 420 + 5, qy + 420 + 5], outline=(20, 20, 20), width=3)

    draw.text(
        (w // 2, 680),
        "Scan with Digivice → Games → Paper Cart",
        fill=(30, 30, 30),
        font=font_small,
        anchor="mt",
    )
    draw.text(
        (w // 2, 720),
        "Or type this code (Confirm Scan / Insert):",
        fill=(80, 80, 80),
        font=font_small,
        anchor="mt",
    )

    # Wrap payload
    y = 770
    for i in range(0, len(PAYLOAD), 28):
        chunk = PAYLOAD[i : i + 28]
        draw.text((w // 2, y), chunk, fill=(20, 20, 20), font=font_mono, anchor="mt")
        y += 28

    draw.text(
        (w // 2, 920),
        "Eject before inserting another card.",
        fill=(100, 60, 60),
        font=font_small,
        anchor="mt",
    )
    draw.text(
        (w // 2, 970),
        "USB carts still plug into the case for movies.",
        fill=(90, 90, 90),
        font=font_small,
        anchor="mt",
    )

    img.save(OUT_PNG, "PNG")
    print(f"Wrote {OUT_PNG}")
    print(f"Payload: {PAYLOAD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
