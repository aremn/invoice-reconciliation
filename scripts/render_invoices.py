"""Render fictional invoice images from a JSON file that has an "invoices" list.

This is the starter pack's tasks/invoices/render_invoices.py with two changes:
  1. the input file and the output folder are command-line arguments, so the added
     invoices are rendered without touching the supplied seed images;
  2. an invoice record may carry "blur_radius": the finished image is then blurred,
     which gives the deliberately unreadable document.
Canvas, fonts, labels and positions are the same as in the starter script.

Usage:  python scripts/render_invoices.py data/additions.json data/images
Requires Pillow.
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


def render(inv: dict) -> Image.Image:
    font = ImageFont.load_default(size=22)
    title = ImageFont.load_default(size=32)
    im = Image.new("RGB", (950, 650), "#ffffff")
    d = ImageDraw.Draw(im)
    b = inv["layout"] == "b"
    d.rectangle((0, 0, 950, 100), fill="#e4edf5" if b else "#edf0e6")
    d.text((40, 30), "FICTIONAL INVOICE - " + inv["invoice_number"], font=title, fill="black")
    fields = [
        ("Supplier", inv["supplier_id"]),
        ("Purchase order", inv["po_id"] or "(missing)"),
        ("Item / SKU", inv["sku"]),
        ("Quantity", str(inv["quantity"])),
        ("Unit price (USD)", f"{inv['unit_cents'] / 100:.2f}"),
        ("Total (USD)", f"{inv['total_cents'] / 100:.2f}"),
    ]
    for i, (key, value) in enumerate(fields):
        x, y = (60, 145 + i * 66) if not b else (480 if i % 2 else 40, 155 + (i // 2) * 125)
        d.text((x, y), f"{key}: {value}", font=font, fill="black")
    if inv.get("blur_radius"):
        im = im.filter(ImageFilter.GaussianBlur(inv["blur_radius"]))
    return im


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("usage: python scripts/render_invoices.py <invoices.json> <output-folder>")
    source, out_dir = Path(sys.argv[1]), Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)
    for inv in json.loads(source.read_text(encoding="utf-8"))["invoices"]:
        target = out_dir / (inv["file_id"] + ".png")
        render(inv).save(target)
        print("rendered", target.as_posix())


if __name__ == "__main__":
    main()
