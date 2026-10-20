"""解压全班作业压缩包，生成可批改的作业清单。

用法：
    python prepare.py <压缩包路径> <工作目录>

输出：
    <工作目录>/submissions/   解压后的作业原件
    <工作目录>/manifest.json  作业清单
"""

import json
import os
import shutil
import sys
import zipfile

sys.stdout.reconfigure(encoding="utf-8")

SUPPORTED = {".docx", ".pdf"}
IGNORE_DIRS = {"__MACOSX", ".git"}
IGNORE_FILES = {".DS_Store", "Thumbs.db"}


def decode_name(info):
    """修复 Windows 压缩包中文文件名乱码（未打 UTF-8 标记的按 GBK 还原）。"""
    name = info.filename
    if info.flag_bits & 0x800:
        return name
    try:
        raw = name.encode("cp437")
    except UnicodeEncodeError:
        return name
    for enc in ("gbk", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return name


def safe_target(root, name):
    """防目录穿越，同时去掉压缩包自带的顶层目录层级判断。"""
    parts = [p for p in name.replace("\\", "/").split("/") if p not in ("", ".")]
    parts = [p for p in parts if p != ".."]
    return os.path.join(root, *parts) if parts else None


def extract(archive, workdir):
    subs = os.path.join(workdir, "submissions")
    os.makedirs(subs, exist_ok=True)
    skipped = []

    with zipfile.ZipFile(archive) as zf:
        members = [i for i in zf.infolist() if not i.is_dir()]
        for info in members:
            name = decode_name(info)
            parts = name.replace("\\", "/").split("/")
            if any(p in IGNORE_DIRS for p in parts) or parts[-1] in IGNORE_FILES:
                continue
            if parts[-1].startswith("~$"):
                continue

            target = safe_target(subs, name)
            if not target:
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    # 压缩包可能自带一层全班目录，若所有文件都在同一子目录下则上提一层
    entries = os.listdir(subs)
    if len(entries) == 1 and os.path.isdir(os.path.join(subs, entries[0])):
        inner = os.path.join(subs, entries[0])
        for item in os.listdir(inner):
            shutil.move(os.path.join(inner, item), os.path.join(subs, item))
        os.rmdir(inner)

    files = []
    for root, _, names in os.walk(subs):
        for n in sorted(names):
            path = os.path.join(root, n)
            ext = os.path.splitext(n)[1].lower()
            rel = os.path.relpath(path, subs).replace("\\", "/")
            if ext in SUPPORTED:
                files.append({"name": n, "rel": rel, "path": path.replace("\\", "/"), "ext": ext})
            else:
                skipped.append({"name": n, "rel": rel, "reason": f"不支持的格式 {ext or '(无扩展名)'}"})

    files.sort(key=lambda x: x["rel"])
    manifest = {"count": len(files), "submissions": files, "skipped": skipped}
    with open(os.path.join(workdir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"解压完成：可批改 {len(files)} 份，跳过 {len(skipped)} 个文件")
    for s in skipped:
        print(f"  跳过 {s['rel']}（{s['reason']}）")
    return manifest


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    extract(sys.argv[1], sys.argv[2])
