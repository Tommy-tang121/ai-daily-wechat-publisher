from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def generate_cover(output_dir: Path, date: str, title: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (900, 500), "#efe0b4")
    draw = ImageDraw.Draw(image)
    font_path = Path(__file__).parents[2] / "fonts" / "ZCOOLKuaiLe-Regular.ttf"
    title_font = ImageFont.truetype(font_path, 58) if font_path.exists() else ImageFont.load_default()
    date_font = ImageFont.truetype(font_path, 36) if font_path.exists() else ImageFont.load_default()
    draw.rectangle((34, 16, 866, 22), fill="#29251f")
    draw.text((70, 150), title, fill="#29251f", font=title_font)
    draw.text((70, 270), date, fill="#d9473f", font=date_font)
    draw.rectangle((34, 468, 866, 474), fill="#29251f")
    path = output_dir / f"{date}.png"
    image.save(path)
    return path
