import math
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


FONT_DIR = Path(__file__).parents[2] / "fonts"
BG_TOP = (237, 221, 176)
BG_MID = (242, 228, 189)
BG_BOT = (237, 221, 176)
INK = (42, 38, 32)
RED = (230, 57, 70)
W, H = 900, 500
MARGIN = 36
WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _load_font(name: str, size: int, bold: bool = False):
    path = FONT_DIR / name
    if not path.exists():
        return ImageFont.load_default()
    font = ImageFont.truetype(path, size)
    if bold:
        try:
            font.set_variation_by_name("Bold")
        except Exception:
            pass
    return font


def _wavy(draw: ImageDraw.ImageDraw, x1: int, y: int, x2: int,
          color: tuple[int, int, int], amp: int = 4, period: int = 24, width: int = 3) -> None:
    points = []
    for x in range(x1, x2 + 1):
        dy = amp * math.sin(2 * math.pi * (x - x1) / period)
        points.append((x, y + dy))
    for index in range(len(points) - 1):
        draw.line([points[index], points[index + 1]], fill=color, width=width)


def generate_cover(output_dir: Path, date: str, title: str, author: str = "Tommy") -> Path:
    """Generate the original 900×500 hand-drawn daily cover."""
    del title  # The original design intentionally uses a fixed masthead headline.
    output_dir.mkdir(parents=True, exist_ok=True)
    weekday = WEEKDAY[datetime.strptime(date, "%Y-%m-%d").weekday()]

    heading_font = _load_font("Caveat[wght].ttf", 88, bold=True)
    chinese_heading_font = _load_font("ZCOOLKuaiLe-Regular.ttf", 88)
    masthead_font = _load_font("Caveat[wght].ttf", 56, bold=True)
    date_font = _load_font("ZCOOLKuaiLe-Regular.ttf", 62)
    weekday_font = _load_font("ZCOOLKuaiLe-Regular.ttf", 36)
    author_font = _load_font("Caveat[wght].ttf", 36, bold=True)

    image = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(image)
    for y in range(H):
        ratio = y / H
        if ratio < 0.5:
            start, end, progress = BG_TOP, BG_MID, ratio * 2
        else:
            start, end, progress = BG_MID, BG_BOT, (ratio - 0.5) * 2
        color = tuple(int(start[index] + (end[index] - start[index]) * progress) for index in range(3))
        draw.line([(0, y), (W, y)], fill=color)

    draw.rectangle([(MARGIN, 12), (W - MARGIN, 15)], fill=INK)
    draw.rectangle([(MARGIN, 22), (W - MARGIN, 23)], fill=INK)

    mast_ai, mast_daily = "AI", " Daily"
    mast_ai_width = masthead_font.getbbox(mast_ai)[2] - masthead_font.getbbox(mast_ai)[0]
    mast_daily_width = masthead_font.getbbox(mast_daily)[2] - masthead_font.getbbox(mast_daily)[0]
    mast_x = (W - mast_ai_width - mast_daily_width) / 2
    draw.text((mast_x, 80), mast_ai, fill=RED, font=masthead_font)
    draw.text((mast_x + mast_ai_width, 80), mast_daily, fill=INK, font=masthead_font)

    headline_ai, headline_cn = "AI", " 行业热点新闻"
    headline_ai_width = heading_font.getbbox(headline_ai)[2] - heading_font.getbbox(headline_ai)[0]
    headline_cn_width = chinese_heading_font.getbbox(headline_cn)[2] - chinese_heading_font.getbbox(headline_cn)[0]
    headline_x = (W - headline_ai_width - headline_cn_width) / 2
    draw.text((headline_x, 158), headline_ai, fill=INK, font=heading_font)
    draw.text((headline_x + headline_ai_width, 158), headline_cn, fill=INK, font=chinese_heading_font)
    draw.line([((W - 240) / 2, 258), ((W + 240) / 2, 258)], fill=INK, width=3)

    date_bbox = date_font.getbbox(date)
    date_width = date_bbox[2] - date_bbox[0]
    date_x, date_y = (W - date_width) / 2, 279
    draw.text((date_x + 3, date_y + 3), date, fill=INK, font=date_font)
    draw.text((date_x, date_y), date, fill=RED, font=date_font)
    _wavy(draw, int(date_x), date_y + (date_bbox[3] - date_bbox[1]) + 10, int(date_x + date_width), RED)

    author_text = f" · {author}"
    weekday_width = weekday_font.getbbox(weekday)[2] - weekday_font.getbbox(weekday)[0]
    author_width = author_font.getbbox(author_text)[2] - author_font.getbbox(author_text)[0]
    byline_width = weekday_width + author_width
    byline_height, byline_padding, byline_border = 36, 8, 2
    byline_box_height = byline_height + byline_padding * 2 + byline_border * 2
    byline_box_width = byline_width + 80
    byline_top = int(430 - byline_box_height)
    byline_left = (W - byline_box_width) / 2
    draw.rectangle([(byline_left, byline_top), (byline_left + byline_box_width, byline_top + byline_box_height)], fill=BG_TOP)
    draw.line([(byline_left, byline_top), (byline_left + byline_box_width, byline_top)], fill=INK, width=byline_border)
    draw.line([(byline_left, byline_top + byline_box_height - 1), (byline_left + byline_box_width, byline_top + byline_box_height - 1)], fill=INK, width=byline_border)
    byline_x, byline_y = (W - byline_width) / 2, byline_top + byline_padding + 2
    draw.text((byline_x, byline_y), weekday, fill=INK, font=weekday_font)
    draw.text((byline_x + weekday_width, byline_y), author_text, fill=INK, font=author_font)

    bordered = Image.new("RGB", (W, H), INK)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle([(4, 4), (W - 5, H - 5)], radius=8, fill=255)
    bordered.paste(image, (0, 0), mask)

    path = output_dir / f"{date}.png"
    bordered.save(path)
    return path
