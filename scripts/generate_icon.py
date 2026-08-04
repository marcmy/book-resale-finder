from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
RESOURCE_DIR = ROOT / "book_resale_finder" / "resources"
PNG_PATH = RESOURCE_DIR / "icon.png"
ICO_PATH = RESOURCE_DIR / "icon.ico"
CANVAS = 512


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\seguisb.ttf"),
        Path(r"C:\Windows\Fonts\arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def build_icon() -> Image.Image:
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Dollar bill.
    draw.rounded_rectangle(
        (48, 78, 405, 334),
        radius=36,
        fill="#dff3e6",
        outline="#105d38",
        width=18,
    )
    draw.line((90, 132, 363, 132), fill="#52b788", width=10)
    draw.line((90, 280, 363, 280), fill="#52b788", width=10)
    for x, y in ((90, 116), (363, 116), (90, 296), (363, 296)):
        draw.ellipse((x - 10, y - 10, x + 10, y + 10), fill="#167447")
    draw.ellipse((157, 135, 307, 285), fill="#f5fff8", outline="#167447", width=10)

    font = _font(112)
    text = "$"
    box = draw.textbbox((0, 0), text, font=font)
    width = box[2] - box[0]
    height = box[3] - box[1]
    draw.text((232 - width / 2, 210 - height / 2 - box[1]), text, font=font, fill="#167447")

    # Magnifying glass.
    draw.ellipse((210, 202, 432, 424), fill="#eef8ff", outline="#172033", width=20)
    draw.ellipse((247, 239, 395, 387), fill="#cfe7f4", outline="#7fb9d9", width=10)
    draw.line((393, 385, 474, 466), fill="#172033", width=48)
    draw.line((397, 389, 470, 462), fill="#607089", width=22)

    return image


def main() -> None:
    RESOURCE_DIR.mkdir(parents=True, exist_ok=True)
    image = build_icon()
    image.save(PNG_PATH, optimize=True)
    image.save(
        ICO_PATH,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"Generated {PNG_PATH.relative_to(ROOT)} and {ICO_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
