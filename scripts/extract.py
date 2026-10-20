"""把一份作业（docx/pdf）拆成「可读文本 + 可看图」两部分，交给大模型批改。

用法：
    python extract.py <作业路径> <输出目录>

输出：
    <输出目录>/content.md   正文文本，图片位置以 ![](images/xx.png) 标记
    <输出目录>/images/      正文中出现的图片（含实验结果截图）

说明：本脚本只做抽取，不做任何识别。图片由大模型直接看图判断。
"""

import os
import sys

import pymupdf

sys.stdout.reconfigure(encoding="utf-8")

MIN_PIXELS = 100  # 小于此边长视为图标/装饰，不抽


# ---------------- Word ----------------

def _docx_images_order(el):
    """返回段落 XML 中图片的 rId 顺序。"""
    from docx.oxml.ns import qn

    ids = []
    for blip in el.iter(qn("a:blip")):
        rid = blip.get(qn("r:embed"))
        if rid:
            ids.append(rid)
    return ids


def extract_docx(path, outdir):
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    imgdir = os.path.join(outdir, "images")
    os.makedirs(imgdir, exist_ok=True)

    lines, idx, failures = [], 0, []

    def emit_images(el):
        nonlocal idx
        for rid in _docx_images_order(el):
            try:
                part = doc.part.related_parts[rid]
            except KeyError:
                continue
            ext = os.path.splitext(part.partname)[1].lower() or ".bin"
            idx += 1
            fname = f"img_{idx:03d}{ext}"
            with open(os.path.join(imgdir, fname), "wb") as f:
                f.write(part.blob)
            lines.append(f"![](images/{fname})")
            if ext not in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"):
                failures.append(fname)

    def walk(parent):
        for child in parent.iterchildren():
            if child.tag == qn("w:p"):
                p = Paragraph(child, doc)
                text = p.text.strip()
                has_img = bool(_docx_images_order(child))
                if text:
                    style = (p.style.name or "").lower()
                    prefix = "## " if "heading" in style or "标题" in style else ""
                    lines.append(prefix + text)
                if has_img:
                    emit_images(child)
            elif child.tag == qn("w:tbl"):
                table = Table(child, doc)
                lines.append("")
                for row in table.rows:
                    cells = [c.text.strip().replace("\n", " ") for c in row.cells]
                    lines.append("| " + " | ".join(cells) + " |")
                lines.append("")

    walk(doc.element.body)

    md = "\n".join(lines)
    return md, failures


# ---------------- PDF ----------------

def extract_pdf(path, outdir):
    doc = pymupdf.open(path)
    imgdir = os.path.join(outdir, "images")
    os.makedirs(imgdir, exist_ok=True)

    lines, failures = [], []
    for pno, page in enumerate(doc, start=1):
        lines.append(f"\n<!-- 第{pno}页 -->\n")

        infos = [i for i in page.get_image_info(xrefs=True) if i.get("xref")]
        kept = []
        for info in infos:
            w, h = info["bbox"][2] - info["bbox"][0], info["bbox"][3] - info["bbox"][1]
            if w < MIN_PIXELS and h < MIN_PIXELS:
                continue
            kept.append(info)
        kept.sort(key=lambda i: i["bbox"][1])

        # 按图片的纵向位置，把标记插回文本流的对应行附近
        text_lines = page.get_text("text").splitlines()
        page_h = page.rect.height or 1
        marks = []
        for k, info in enumerate(kept, start=1):
            fname = f"p{pno:02d}_img{k}.png"
            try:
                pix = pymupdf.Pixmap(doc, info["xref"])
                if pix.n - pix.alpha >= 4:
                    pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
                pix.save(os.path.join(imgdir, fname))
            except Exception:
                failures.append(fname)
                continue
            at = min(len(text_lines), int(info["bbox"][1] / page_h * len(text_lines)))
            marks.append((at, fname))
        marks.sort()

        mi = 0
        for i, line in enumerate(text_lines):
            while mi < len(marks) and marks[mi][0] <= i:
                lines.append(f"![](images/{marks[mi][1]})")
                mi += 1
            lines.append(line)
        while mi < len(marks):
            lines.append(f"![](images/{marks[mi][1]})")
            mi += 1

    return "\n".join(lines), failures


def main(src, outdir):
    os.makedirs(outdir, exist_ok=True)
    ext = os.path.splitext(src)[1].lower()
    if ext == ".docx":
        md, failures = extract_docx(src, outdir)
    elif ext == ".pdf":
        md, failures = extract_pdf(src, outdir)
    else:
        raise SystemExit(f"不支持的格式：{ext}")

    with open(os.path.join(outdir, "content.md"), "w", encoding="utf-8") as f:
        f.write(md)

    n_img = len(os.listdir(os.path.join(outdir, "images")))
    print(f"已抽取：{os.path.basename(src)}")
    print(f"  文本 {len(md)} 字符，图片 {n_img} 张 → {outdir}")
    if failures:
        print(f"  以下图片格式特殊，可能无法直接查看：{', '.join(failures)}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
