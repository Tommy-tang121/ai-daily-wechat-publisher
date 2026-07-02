import os, math
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

BG_TOP = (237, 221, 176)
BG_MID = (242, 228, 189)
BG_BOT = (237, 221, 176)
INK = (42, 38, 32)
INK_SOFT = (90, 82, 73)
RED = (230, 57, 70)
ORANGE = (247, 127, 0)
WHITE = (255, 255, 255)

W, H = 900, 500
M = 36

WEEKDAY = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


def _load_font(name, size, bold=False):
    path = os.path.join(FONT_DIR, name)
    if not os.path.exists(path):
        return ImageFont.load_default()
    font = ImageFont.truetype(path, size)
    if bold:
        try:
            font.set_variation_by_name("Bold")
        except Exception:
            pass
    return font


def _wavy(draw, x1, y, x2, color, amp=4, period=24, width=3):
    pts = []
    for x in range(x1, x2 + 1):
        dy = amp * math.sin(2 * math.pi * (x - x1) / period)
        pts.append((x, y + dy))
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=color, width=width)


def generate_cover(date_str, title="AI 行业热点新闻", author="Tommy"):
    dt_obj = datetime.strptime(date_str, "%Y-%m-%d")
    weekday = WEEKDAY[dt_obj.weekday()]

    f_head = _load_font("Caveat[wght].ttf", 88, bold=True)
    f_zcool_88 = _load_font("ZCOOLKuaiLe-Regular.ttf", 88)
    f_mast = _load_font("Caveat[wght].ttf", 56, bold=True)
    f_date = _load_font("ZCOOLKuaiLe-Regular.ttf", 62)
    f_by_cn = _load_font("ZCOOLKuaiLe-Regular.ttf", 36)
    f_by_en = _load_font("Caveat[wght].ttf", 36, bold=True)

    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    for y in range(H):
        r = y / H
        if r < 0.5:
            t = r * 2
            cr = int(BG_TOP[0] + (BG_MID[0] - BG_TOP[0]) * t)
            cg = int(BG_TOP[1] + (BG_MID[1] - BG_TOP[1]) * t)
            cb = int(BG_TOP[2] + (BG_MID[2] - BG_TOP[2]) * t)
        else:
            t = (r - 0.5) * 2
            cr = int(BG_MID[0] + (BG_BOT[0] - BG_MID[0]) * t)
            cg = int(BG_MID[1] + (BG_BOT[1] - BG_MID[1]) * t)
            cb = int(BG_MID[2] + (BG_BOT[2] - BG_MID[2]) * t)
        draw.line([(0, y), (W, y)], fill=(cr, cg, cb))

    # === TOP RULES ===
    draw.rectangle([(M, 12), (W - M, 15)], fill=INK)
    draw.rectangle([(M, 22), (W - M, 23)], fill=INK)

    # === CENTER GROUP: masthead + headline + date (vertically centered) ===
    mast_y = 80

    # Masthead "AI Daily" centered
    mast_ai = "AI"
    mast_daily = " Daily"
    mw = f_mast.getbbox(mast_ai)[2] - f_mast.getbbox(mast_ai)[0]
    dw = f_mast.getbbox(mast_daily)[2] - f_mast.getbbox(mast_daily)[0]
    mx = (W - mw - dw) / 2
    draw.text((mx, mast_y), mast_ai, fill=RED, font=f_mast)
    draw.text((mx + mw, mast_y), mast_daily, fill=INK, font=f_mast)

    # Headline
    head_y = 158
    h1 = "AI"
    h2 = " 行业热点新闻"
    h1_w = f_head.getbbox(h1)[2] - f_head.getbbox(h1)[0]
    h2_w = f_zcool_88.getbbox(h2)[2] - f_zcool_88.getbbox(h2)[0]
    hx = (W - h1_w - h2_w) / 2
    draw.text((hx, head_y), h1, fill=INK, font=f_head)
    draw.text((hx + h1_w, head_y), h2, fill=INK, font=f_zcool_88)

    # Underline
    ul_y = 258
    ul_w = 240
    draw.line([((W - ul_w) / 2, ul_y), ((W + ul_w) / 2, ul_y)], fill=INK, width=3)

    # Date
    date_bbox = f_date.getbbox(date_str)
    dt_w = date_bbox[2] - date_bbox[0]
    dt_y = 279
    dt_x = (W - dt_w) / 2
    draw.text((dt_x + 3, dt_y + 3), date_str, fill=INK, font=f_date)
    draw.text((dt_x, dt_y), date_str, fill=RED, font=f_date)

    # Wavy underline
    wavy_y = dt_y + (date_bbox[3] - date_bbox[1]) + 10
    _wavy(draw, int(dt_x), wavy_y, int(dt_x + dt_w), RED, amp=4, period=24, width=3)

    # === BYLINE (safe zone, away from bottom crop) ===
    weekday_text = weekday
    author_text = f" · {author}"
    ww = f_by_cn.getbbox(weekday_text)[2] - f_by_cn.getbbox(weekday_text)[0]
    aw = f_by_en.getbbox(author_text)[2] - f_by_en.getbbox(author_text)[0]
    by_w = ww + aw
    by_pad = 8
    by_border = 2
    by_bh = 36 + by_pad * 2 + by_border * 2
    by_bw = by_w + 80
    by_bottom = 430
    by_top = int(by_bottom - by_bh)
    by_left = (W - by_bw) / 2
    draw.rectangle([(by_left, by_top), (by_left + by_bw, by_top + by_bh)], fill=BG_TOP)
    draw.line([(by_left, by_top), (by_left + by_bw, by_top)], fill=INK, width=by_border)
    draw.line([(by_left, by_top + by_bh - 1), (by_left + by_bw, by_top + by_bh - 1)], fill=INK, width=by_border)
    tx = (W - by_w) / 2
    ty = by_top + by_pad + 2
    draw.text((tx, ty), weekday_text, fill=INK, font=f_by_cn)
    draw.text((tx + ww, ty), author_text, fill=INK, font=f_by_en)

    # === BORDER (4px INK with rounded corners) ===
    border_img = Image.new("RGB", (W, H), INK)
    mask = Image.new("L", (W, H), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([(4, 4), (W - 5, H - 5)], radius=8, fill=255)
    border_img.paste(img, (0, 0), mask)
    img = border_img

    out_dir = os.path.join(os.path.dirname(__file__), "static", "covers")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"{date_str}.png")
    img.save(out_path)
    return f"static/covers/{date_str}.png"
