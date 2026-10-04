#!/usr/bin/env python3
"""为全服 627 张地图生成网页缩略图。

流程：
  1. 调 Mir3-Research 的 gen_static_maps.py 渲染全量 JPG（最小缩放）
  2. 后处理：缩到宽 400 + JPEG q60/optimize，把单张 1.7MB 压到 ~16KB
  3. 落到 mir3-website/images/mapgen/<编号>.jpg，供地图资料页引用

用法：
  python3 tools/gen_map_thumbs.py
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from PIL import Image

SITE_ROOT = Path(__file__).resolve().parent.parent
RESEARCH = Path("/home/tetsuya/development/Mir3-Research/Tools/maps")
IMAGES_DIR = SITE_ROOT / "images" / "mapgen"
EXPORT_JSON = SITE_ROOT / "data" / "maps.json"

RAW_DIR = Path("/tmp/mapgen_raw")
TARGET_W = 400
QUALITY = 60


def render_all(workers: int) -> Path:
    print(f"[1/3] 渲染全量地图 -> {RAW_DIR} (workers={workers})")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, "gen_static_maps.py", "--out", str(RAW_DIR), "--workers", str(workers)],
        cwd=str(RESEARCH), check=True,
    )
    return RAW_DIR


def compress(raw_dir: Path) -> dict[str, str]:
    print(f"[2/3] 压缩到宽 {TARGET_W}px / JPEG q{QUALITY} -> {IMAGES_DIR}")
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    sizes = {}
    files = sorted(raw_dir.glob("*.jpg"))
    for i, f in enumerate(files, 1):
        out = IMAGES_DIR / f.name
        try:
            with Image.open(f) as im:
                w, h = im.size
                nw = TARGET_W
                nh = max(1, int(h * nw / w))
                im.resize((nw, nh), Image.LANCZOS).convert("RGB").save(
                    out, "JPEG", quality=QUALITY, optimize=True)
            sizes[f.stem] = f"{out.stat().st_size // 1024}KB"
        except Exception as exc:                     # 单张失败不阻断全量
            print(f"  [失败] {f.name}: {exc}")
        if i % 100 == 0:
            print(f"  ...{i}/{len(files)}")
    print(f"  完成 {len(sizes)} 张")
    return sizes


def report(sizes: dict[str, str]) -> None:
    doc = json.loads(EXPORT_JSON.read_text(encoding="utf-8"))
    ids = [m["id"] for g in doc["groups"] for m in g.get("items", [])]
    ids += [m["id"] for g in doc["groups"] for s in g.get("suites", []) for m in s["items"]]
    have = {p.stem for p in IMAGES_DIR.glob("*.jpg")}
    missing = [i for i in ids if i not in have]
    total = sum(p.stat().st_size for p in IMAGES_DIR.glob("*.jpg"))
    print(f"[3/3] 页面需 {len(ids)} 张，已有 {len(have)} 张，缺 {len(missing)} 张")
    if missing:
        print(f"  缺图示例: {missing[:10]}")
    print(f"  图片目录总大小: {total / 1024 / 1024:.1f} MB")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    t0 = time.time()
    raw = render_all(args.workers)
    sizes = compress(raw)
    report(sizes)
    print(f"用时 {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
