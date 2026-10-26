"""按 manifest 逐份抽取全班作业（pdf + docx 全覆盖），杜绝漏抽。

用法：
    python batch_extract.py <manifest.json> <输出根目录>

输出：
    <输出根目录>/<序号>_<姓名>/content.md 和 images/
    序号与姓名取自 manifest 中的文件名，保证一份不漏。

说明：本脚本只遍历 manifest 里的全部文件并按扩展名分流调用 extract 的抽取逻辑，
    与 extract.py 共用同一套 docx/pdf 抽取实现，避免重复代码。
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract import extract_docx, extract_pdf

sys.stdout.reconfigure(encoding="utf-8")


def pick_label(filename):
    """从文件名抽一个可读标签作为目录名：优先学号-姓名，否则去扩展名的原名。"""
    stem = os.path.splitext(filename)[0]
    m = re.search(r"(\d{6,})[-_\s]*(.+?)(?:[-_\s]*(实验|报告|作业).*)?$", stem)
    if m and m.group(1) and m.group(2):
        return f"{m.group(1)}_{m.group(2).strip()}"
    return stem


def main(manifest_path, out_root):
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    files = manifest.get("submissions", [])
    if not files:
        print("清单里没有可批改文件")
        return

    os.makedirs(out_root, exist_ok=True)
    used = set()
    ok = fail = 0

    for i, sub in enumerate(files, start=1):
        src = sub["path"]
        ext = sub["ext"].lower()
        if not os.path.exists(src):
            print(f"  缺失原件，跳过：{sub['rel']}")
            fail += 1
            continue

        label = pick_label(sub["name"])
        base = label
        k = 1
        while base in used:
            k += 1
            base = f"{label}_{k}"
        used.add(base)
        outdir = os.path.join(out_root, f"{i:02d}_{base}")

        if ext == ".docx":
            md, failures = extract_docx(src, outdir)
        elif ext == ".pdf":
            md, failures = extract_pdf(src, outdir)
        else:
            print(f"  跳过（不支持的格式）：{sub['rel']}")
            fail += 1
            continue

        with open(os.path.join(outdir, "content.md"), "w", encoding="utf-8") as f:
            f.write(md)

        n_img = len(os.listdir(os.path.join(outdir, "images")))
        print(f"  [{i:02d}] {sub['rel']} → {outdir}（文本 {len(md)} 字，图片 {n_img} 张）")
        if failures:
            print(f"        特殊图片可能无法查看：{', '.join(failures)}")
        ok += 1

    print(f"\n抽取完成：成功 {ok} 份，失败/跳过 {fail} 份")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
