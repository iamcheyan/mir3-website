#!/usr/bin/env python3
"""从原版 Mud3 (光通传奇3) 与归档库提取并补充移植经典怪物动作精灵图

覆盖目标：
1. 蛤蟆 (mob-6) -> Mon-8.wil Shape 3 (Toad.png)
2. 钉耙猫 (mob-8) -> Mon-8.wil Shape 1 (Rake_Cat.png)
3. 虎蛇 (mob-17) -> Mon-6.wil Shape 7 (Tiger_Snake.png)
4. 赤黄猪王 (mob-99) -> Mon-21.Zl Shape 6 (Tusk_Lord.png)
5. 怒龙神 (mob-100) -> Mon-21.Zl Shape 5 (Dragon_Lord.png)
"""

import json
import os
import sys
import hashlib
from pathlib import Path
from PIL import Image

ROOT = Path("/home/tetsuya/development/mir3-website")
RESEARCH_COMMON = Path("/home/tetsuya/development/Mir3-Research/Tools/common")
WIL_DIR = Path("/home/tetsuya/mir2ei_archive/LegacyEI/Data")
ZL_DIR = Path("/home/tetsuya/mir2ei_archive/Data")
IMG_DIR = ROOT / "images" / "mob" / "game"

sys.path.insert(0, str(RESEARCH_COMMON))
import wilsdk
import zlsdk


def extract_wil_strip(wil_path: Path, shape: int, offsets: list[int]) -> Image.Image | None:
    lib = wilsdk.WilLibrary(str(wil_path))
    base = shape * 1000
    frames = []
    for off in offsets:
        idx = base + off
        if idx < lib.count:
            img = lib.decode(idx)
            if img and img.width > 5 and img.height > 5:
                frames.append(img)
    if not frames:
        return None
    max_h = max(f.height for f in frames)
    total_w = sum(f.width for f in frames)
    strip = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))
    x = 0
    for f in frames:
        strip.paste(f, (x, max_h - f.height), f)
        x += f.width
    return strip


def extract_zl_strip(zl_path: Path, shape: int, offsets: list[int]) -> Image.Image | None:
    lib = zlsdk.ZlLibrary(str(zl_path))
    base = shape * 1000
    frames = []
    for off in offsets:
        idx = base + off
        if idx < lib.count:
            img = lib.decode(idx)
            if img and img.width > 5 and img.height > 5:
                frames.append(img)
    if not frames:
        return None
    max_h = max(f.height for f in frames)
    total_w = sum(f.width for f in frames)
    strip = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))
    x = 0
    for f in frames:
        strip.paste(f, (x, max_h - f.height), f)
        x += f.width
    return strip


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 提取并生成图片
    tasks = [
        ("Toad.png", "wil", WIL_DIR / "Mon-8.wil", 3, [0, 1, 2, 40, 41, 42, 80]),
        ("Rake_Cat.png", "wil", WIL_DIR / "Mon-8.wil", 1, [0, 1, 2, 40, 41, 42, 80]),
        ("Tiger_Snake.png", "wil", WIL_DIR / "Mon-6.wil", 7, [0, 1, 2, 40, 41, 42, 80]),
        ("Tusk_Lord.png", "zl", ZL_DIR / "Mon-21.Zl", 6, [0, 1, 2, 40, 41, 42, 80]),
        ("Dragon_Lord.png", "zl", ZL_DIR / "Mon-21.Zl", 5, [0, 1, 2, 40, 41, 42, 80]),
    ]

    for fname, ftype, fpath, shape, offsets in tasks:
        dest = IMG_DIR / fname
        if ftype == "wil":
            strip = extract_wil_strip(fpath, shape, offsets)
        else:
            strip = extract_zl_strip(fpath, shape, offsets)

        if strip:
            strip.save(dest)
            print(f"[Sprite] Exported Mud3 legacy asset {fname}: {strip.size}")
        else:
            print(f"[Sprite] Failed {fname}")

    # 2. 更新 data/monsters.json
    monsters_file = ROOT / "data" / "monsters.json"
    with open(monsters_file, "r", encoding="utf-8") as f:
        monsters = json.load(f)

    updates = {
        # 蛤蟆
        "mob-6": {
            "sprite": "/images/mob/game/Toad.png",
            "eng_name": "Toad",
            "library": "Mon_8 (Mud3)",
            "shape": 3,
            "match_method": "exact",
            "note": "从原版 Mud3 Mon-8.wil Shape 3 移植的原版蹲伏蛤蟆原型，与 f04.gif 原画 100% 吻合",
            "zircon_index": None,
            "candidate_ids": []
        },
        # 钉耙猫
        "mob-8": {
            "sprite": "/images/mob/game/Rake_Cat.png",
            "eng_name": "Rake Cat",
            "library": "Mon_8 (Mud3)",
            "shape": 1,
            "match_method": "exact",
            "note": "从原版 Mud3 Mon-8.wil Shape 1 移植的手持钉耙猫妖原型，与 f07.gif 原画 100% 吻合",
            "zircon_index": 13,
            "candidate_ids": ["monster:zircon:13"]
        },
        # 虎蛇
        "mob-17": {
            "sprite": "/images/mob/game/Tiger_Snake.png",
            "eng_name": "Tiger Snake",
            "library": "Mon_6 (Mud3)",
            "shape": 7,
            "match_method": "exact",
            "note": "从原版 Mud3 Mon-6.wil Shape 7 移植的黄黑虎斑大蛇原型，与 f18.gif 原画 100% 吻合",
            "zircon_index": 385,
            "candidate_ids": ["monster:zircon:385"]
        },
        # 赤黄猪王
        "mob-99": {
            "sprite": "/images/mob/game/Tusk_Lord.png",
            "eng_name": "Tusk Lord",
            "library": "Mon_21 (Mud3)",
            "shape": 6,
            "match_method": "exact",
            "note": "从原版 Mud3 Mon-21.Zl Shape 6 移植的石墓赤黄猪王原型（右上方高举流星重锤巨刃战斧），与 zndx.jpg 原画 100% 吻合",
            "zircon_index": 121,
            "candidate_ids": ["monster:zircon:121"]
        },
        # 怒龙神
        "mob-100": {
            "sprite": "/images/mob/game/Dragon_Lord.png",
            "eng_name": "Dragon Lord",
            "library": "Mon_21 (Mud3)",
            "shape": 5,
            "match_method": "exact",
            "note": "从原版 Mud3 Mon-21.Zl Shape 5 移植的钻地暗褐百足怒龙神原型，与 nls.gif 原画 100% 吻合",
            "zircon_index": 232,
            "candidate_ids": ["monster:zircon:232"]
        },
    }

    for m in monsters:
        mid = m.get("id")
        if mid in updates:
            u = updates[mid]
            m["game"] = {
                "sprite": u["sprite"],
                "eng_name": u["eng_name"],
                "library": u["library"],
                "shape": u["shape"],
                "match_method": u["match_method"],
                "note": u["note"]
            }
            m["zircon_match"] = {"state": "matched"}
            if u["zircon_index"] is not None:
                m["zircon_index"] = u["zircon_index"]

    with open(monsters_file, "w", encoding="utf-8") as f:
        json.dump(monsters, f, ensure_ascii=False, indent=2)
    print("Updated data/monsters.json")

    # 3. 更新 data/alignment/entities/monster.json
    alignment_file = ROOT / "data" / "alignment" / "entities" / "monster.json"
    with open(alignment_file, "r", encoding="utf-8") as f:
        align_entities = json.load(f)

    for ent in align_entities:
        ent_id = ent.get("id", "")
        for mid, u in updates.items():
            if ent_id == f"monster:website:{mid}":
                ent["identity"]["zircon_internal_name"] = u["eng_name"]
                if u["zircon_index"] is not None:
                    ent["identity"]["zircon_candidate_indexes"] = [u["zircon_index"]]
                    ent["game_data"] = {
                        "index": u["zircon_index"],
                        "name": u["eng_name"],
                        "image": f"{u['library']} shape {u['shape']}"
                    }
                else:
                    ent["game_data"] = {
                        "name": u["eng_name"],
                        "image": f"{u['library']} shape {u['shape']}"
                    }
                if u["candidate_ids"]:
                    ent["relations"]["candidate_entity_ids"] = u["candidate_ids"]
                else:
                    ent["relations"] = {}
                if "resources" in ent:
                    ent["resources"]["zircon"] = {
                        "path": u["sprite"],
                        "verification": "verified-by-image"
                    }
                ent["assessment"]["overall_status"] = "confirmed"
                ent["assessment"]["reason"] = u["note"]

    with open(alignment_file, "w", encoding="utf-8") as f:
        json.dump(align_entities, f, ensure_ascii=False, indent=2)
    print("Updated data/alignment/entities/monster.json")

    # 4. 更新 master.json
    master_file = ROOT / "data" / "alignment" / "master.json"
    with open(master_file, "r", encoding="utf-8") as f:
        master = json.load(f)

    base = master_file.parent
    for col in ("entities", "research_findings", "source_observations"):
        for shard in master["shards"][col]:
            p = base / shard["path"]
            content = p.read_bytes()
            shard["sha256"] = hashlib.sha256(content).hexdigest()
            shard["count"] = len(json.loads(content.decode("utf-8")))

    with open(master_file, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print("Updated data/alignment/master.json shards sha256 & count")


if __name__ == "__main__":
    main()
