"""在 PDF 作业上落笔：按评分点在题号左侧空白处写红色手写分数，末页写总分。

用法：
    python annotate_pdf.py <成绩json> <原PDF> <输出PDF>

成绩 json 结构见 SKILL.md「评分结果格式」。
"""

import json
import os
import sys
import tempfile

import pymupdf
from PIL import Image, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding="utf-8")

INK = (235, 60, 66)          # 红笔颜色
CJK_FONT = r"C:\Windows\Fonts\STXINGKA.TTF"   # 华文行楷：中文批注
LATIN_FONT = r"C:\Windows\Fonts\Inkfree.ttf"  # Inkfree：手写数字
DPI = 4          # 渲染倍率，保证放大不糊
ANGLE = -5       # 手写倾斜角


def _font_path(text):
    """纯数字/符号用手写数字体，含中文时用行楷。"""
    if text.isascii() and os.path.exists(LATIN_FONT):
        return LATIN_FONT
    if os.path.exists(CJK_FONT):
        return CJK_FONT
    raise SystemExit("找不到可用的手写字体（华文行楷/Inkfree）")


def render(text, size_pt, angle=ANGLE, color=INK, stroke=0):
    """把手写文字渲染成透明背景 PNG，返回 (图片路径, 宽pt, 高pt)。"""
    px = max(8, int(size_pt * DPI))
    if not text.isascii():
        px = int(px * 0.9)  # 行楷同字号视觉偏大，收一点
    font = ImageFont.truetype(_font_path(text), px)
    x0, y0, x1, y1 = font.getbbox(text)
    pad = px // 3
    img = Image.new("RGBA", (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(img).text((pad - x0, pad - y0), text, font=font, fill=color + (255,),
                             stroke_width=stroke, stroke_fill=color + (255,))
    if angle:
        img = img.rotate(angle, expand=True, resample=Image.BICUBIC)
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    img.save(path)
    return path, img.width / DPI, img.height / DPI


def search_loose(page, needle):
    """忽略空格与换行的定位：把页面字符流压掉空白后匹配，避免「（2） 实现代码」这类空格差异。"""
    chars = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                for ch in span.get("chars", []):
                    chars.append((ch["c"], ch["bbox"]))

    compact = "".join(c for c, _ in chars if not c.isspace())
    target = "".join(c for c in needle if not c.isspace())
    if not target:
        return None
    pos = compact.find(target)
    if pos < 0:
        return None

    keep = [bbox for c, bbox in chars if not c.isspace()]
    picked = keep[pos:pos + len(target)]
    return pymupdf.Rect(
        min(b[0] for b in picked), min(b[1] for b in picked),
        max(b[2] for b in picked), max(b[3] for b in picked),
    )


def find_anchor(doc, text):
    """在全文按顺序找锚点文本，返回 (页码, Rect)。允许锚点被换行拆开时截断重试。"""
    text = text.strip()
    probes = [text, text[:10], text[:6]]
    for probe in probes:
        if not probe.strip():
            continue
        for pno in range(len(doc)):
            rect = search_loose(doc[pno], probe)
            if rect:
                return pno, rect
    return None, None


def place(page, rect, w, h):
    """分数统一写在页面左侧页边、与题目行齐平；左侧被正文占满时退到右侧页边。"""
    mid = (rect.y0 + rect.y1) / 2 - h / 2
    margin = 22
    if rect.x0 - margin >= w + 6:
        return pymupdf.Rect(margin, mid, margin + w, mid + h)
    right = page.rect.width - margin - w
    if right > rect.x1 + 6:
        return pymupdf.Rect(right, mid, right + w, mid + h)
    return pymupdf.Rect(max(margin, rect.x0 - w - 4), mid, max(margin, rect.x0 - w - 4) + w, mid + h)


def overlaps(page, rect):
    return any(pymupdf.Rect(b[:4]).intersects(rect) for b in page.get_text("blocks"))


def main(grades_path, src, dst):
    with open(grades_path, encoding="utf-8") as f:
        data = json.load(f)

    doc = pymupdf.open(src)
    size = doc[0].rect.width * 0.036      # 分数字号随页面大小缩放
    missed, temps = [], []

    for item in data.get("items", []):
        score = item.get("score")
        if score is None:
            continue
        anchor = item.get("anchor") or item.get("title") or ""
        pno, rect = find_anchor(doc, anchor)
        if pno is None:
            missed.append(anchor)
            continue
        page = doc[pno]
        img, w, h = render(f"{score}", size)
        temps.append(img)
        page.insert_image(place(page, rect, w, h), filename=img)

        comment = (item.get("comment") or "").strip()
        if comment and len(comment) <= 14:
            # 批注写在分数正下方，宽度不够时按比例缩字号，避免压到正文
            avail = max(60, rect.x0 - 26)
            csize = size * 0.6
            cimg, cw, ch = render(comment, csize, stroke=1)
            if cw > avail:
                csize *= avail / cw
                os.remove(cimg)
                cimg, cw, ch = render(comment, csize, stroke=1)
            temps.append(cimg)
            box = pymupdf.Rect(22, rect.y1 + 2, 22 + cw, rect.y1 + 2 + ch)
            if box.y1 < page.rect.height - 20:
                page.insert_image(box, filename=cimg)

    total = data.get("total")
    if total:
        last = doc[-1]
        text = f"{total['score']}/{total['max']}" if total.get("max") else f"{total['score']}"
        img, w, h = render(text, size * 1.15)
        temps.append(img)
        box = pymupdf.Rect(last.rect.width - w - 46, last.rect.height - h - 52,
                           last.rect.width - 46, last.rect.height - 52)
        for _ in range(3):
            if not overlaps(last, box):
                break
            box = box + (0, -h - 10, 0, -h - 10)
        last.insert_image(box, filename=img)

    os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
    doc.save(dst, garbage=3, deflate=True)
    doc.close()
    for t in temps:
        try:
            os.remove(t)
        except OSError:
            pass

    print(f"已生成：{dst}")
    if missed:
        print(f"  以下评分点未在文中定位，未落笔：{', '.join(missed)}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2], sys.argv[3])
