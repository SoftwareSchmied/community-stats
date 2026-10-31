"""Render the project's geometric mark at Home Assistant icon sizes."""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    destination = ROOT / "custom_components" / "community_stats" / "brand"
    destination.mkdir(parents=True, exist_ok=True)
    scale = 4
    image = Image.new("RGBA", (512 * scale, 512 * scale))
    draw = ImageDraw.Draw(image)

    def rectangle(box, radius, color):
        draw.rounded_rectangle(tuple(v * scale for v in box), radius * scale, fill=color)

    rectangle((8, 8, 504, 504), 112, "#103348")
    for left, top, color in ((106, 294, "#6CE5D4"), (216, 222, "#37BFC8"), (326, 146, "#F5CE72")):
        rectangle((left, top, left + 80, 402), 20, color)
        center = left + 40
        draw.ellipse(
            tuple(v * scale for v in (center - 26, top - 88, center + 26, top - 36)),
            fill=color,
        )
    for size, name in ((256, "icon.png"), (512, "icon@2x.png")):
        image.resize((size, size), Image.Resampling.LANCZOS).save(destination / name)


if __name__ == "__main__":
    main()
