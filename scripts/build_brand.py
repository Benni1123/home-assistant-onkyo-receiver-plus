"""Render the original receiver artwork into Home Assistant's brand PNGs."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BRAND = (
    Path(__file__).resolve().parents[1] / "custom_components" / "onkyo_receiver_plus" / "brand"
)
NAVY = "#0b172b"
OUTLINE = "#294763"
SCREEN = "#081728"
LIGHT = "#7ae4f2"
MINT = "#9cf5c4"
WHITE = "#f2f7ff"


def receiver_icon():
    """Draw the tile and receiver at 2x, with transparency at the corners."""
    image = Image.new("RGBA", (512, 512))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 508, 508), 110, fill=NAVY, outline=OUTLINE, width=6)
    draw.rounded_rectangle((64, 173, 446, 353), 28, fill="#203653", outline="#426385", width=6)
    draw.rounded_rectangle((93, 207, 286, 284), 14, fill=SCREEN, outline="#3f667b", width=4)
    draw.line(
        [(111, 251), (138, 251), (152, 231), (169, 267), (187, 224),
         (202, 251), (263, 251)],
        fill=LIGHT,
        width=6,
        joint="curve",
    )
    for start in (101, 127, 153):
        draw.rounded_rectangle((start, 309, start + 14, 322), 6, fill="#87a6bb")
    draw.ellipse((320, 224, 412, 316), fill=NAVY, outline=LIGHT, width=5)
    draw.line((366, 268, 383, 249), fill=LIGHT, width=6)
    draw.ellipse((342, 89, 461, 208), fill=NAVY)
    draw.ellipse((351, 98, 452, 199), fill=MINT)
    draw.rounded_rectangle((394, 121, 409, 176), 6, fill=NAVY)
    draw.rounded_rectangle((374, 141, 429, 156), 6, fill=NAVY)
    return image


def font(size, bold=False):
    candidates = (
        ("segoeuib.ttf", "DejaVuSans-Bold.ttf")
        if bold else ("segoeui.ttf", "DejaVuSans.ttf")
    )
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def main():
    BRAND.mkdir(parents=True, exist_ok=True)
    icon = receiver_icon()
    logo = Image.new("RGBA", (1280, 384))
    draw = ImageDraw.Draw(logo)
    draw.rounded_rectangle((2, 2, 1277, 381), 84, fill=NAVY, outline=OUTLINE, width=5)
    logo.alpha_composite(icon.resize((272, 272), Image.Resampling.LANCZOS), (53, 56))
    draw.text((374, 105), "Onkyo Receiver", font=font(78, bold=True), fill=WHITE)
    draw.text((374, 205), "PLUS", font=font(75, bold=True), fill=MINT)
    draw.text((609, 233), "HOME ASSISTANT", font=font(36), fill=LIGHT)
    for name, image in (("icon", icon), ("logo", logo)):
        image.save(BRAND / f"{name}@2x.png", optimize=True)
        image.resize(
            (image.width // 2, image.height // 2), Image.Resampling.LANCZOS
        ).save(BRAND / f"{name}.png", optimize=True)


if __name__ == "__main__":
    main()
