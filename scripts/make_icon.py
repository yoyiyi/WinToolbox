"""生成应用图标（仅开发时需要 Pillow）。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    assets = root / "assets"
    assets.mkdir(exist_ok=True)

    size = 1024
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (size, size))
    pixels = gradient.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size)
            r = int(41 + (34 - 41) * t)
            g = int(98 + (211 - 98) * t)
            b = int(215 + (238 - 215) * t)
            pixels[x, y] = (r, g, b, 255)
    image.paste(gradient, (0, 0), rounded_mask(size, 190))

    draw = ImageDraw.Draw(image)
    # 细微的左上高光
    draw.ellipse((-300, -500, 900, 500), fill=(255, 255, 255, 24))
    font_path = Path(r"C:\Windows\Fonts\segoeuib.ttf")
    try:
        font = ImageFont.truetype(str(font_path), 560)
    except OSError:
        font = ImageFont.load_default()
    text = "W"
    box = draw.textbbox((0, 0), text, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1] - 20
    draw.text((x + 8, y + 12), text, font=font, fill=(5, 22, 48, 90))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))

    image.resize((512, 512), Image.LANCZOS).save(assets / "logo.png")
    image.save(
        assets / "app.ico",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    print(assets / "app.ico")


if __name__ == "__main__":
    main()
