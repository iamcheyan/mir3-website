#!/usr/bin/env python3
"""修复 mob-122 骷髅士兵模型配置，彻底区分骷髅士兵与骷髅弓箭手：

1. 骷髅士兵 (mob-122) -> Mon-15.Zl Shape 2 (Bone_Soldier.png, 手持带旗长枪, 100% 匹配 67.gif 原画)
2. 骷髅弓箭手 (mob-124) -> 保持 Mon-15.Zl Shape 4 (Bone_Archer.png, 手持弓箭远距离进攻, 100% 匹配 69.gif 原画)
3. 更新 data/monsters.json 与 data/alignment/entities/monster.json，并重算 master.json sha256
"""

import json
import hashlib
import sys
from pathlib import Path
from PIL import Image

ROOT = Path("/home/tetsuya/development/mir3-website")
RESEARCH_COMMON = Path("/home/tetsuya/development/Mir3-Research/Tools/common")
ZL_DIR = Path("/home/tetsuya/mir2ei/Data")
IMG_DIR = ROOT / "images" / "mob" / "game"

sys.path.insert(0, str(RESEARCH_COMMON))
import zlsdk


def extract_zl_strip(zl_path: Path, shape: int, offsets: list[int]) -> Image.Image | None:
    zl = zlsdk.ZlLibrary(str(zl_path))
    base = shape * 1000
    frames = []
    for off in offsets:
        idx = base + off
        if idx < zl.count:
            img = zl.decode(idx)
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
    std_offsets = [40, 41, 42, 43, 120, 121, 122, 123, 200, 201, 202, 203, 360, 361, 362, 363]

    # 1. 提取/更新 Bone_Soldier.png 精灵图 (Mon-15.Zl Shape 2)
    strip_soldier = extract_zl_strip(ZL_DIR / "Mon-15.Zl", 2, std_offsets)
    if strip_soldier:
        strip_soldier.save(IMG_DIR / "Bone_Soldier.png")
        print(f"[Sprite] Exported Bone_Soldier.png (Mon-15 shape 2): {strip_soldier.size}")

    # 2. 更新 data/monsters.json
    monsters_path = ROOT / "data" / "monsters.json"
    with open(monsters_path, "r", encoding="utf-8") as f:
        monsters = json.load(f)

    for m in monsters:
        if m.get("id") == "mob-122":
            m["game"] = {
                "sprite": "/images/mob/game/Bone_Soldier.png",
                "eng_name": "Bone Soldier",
                "library": "Mon_15",
                "shape": 2,
                "match_method": "exact",
                "note": "潘夜石窟骷髅士兵真身（Mon_15 shape 2），手持带旗长枪，与 67.gif 原画 100% 吻合"
            }
            m["zircon_index"] = 119
            print("Updated data/monsters.json: mob-122 -> Bone Soldier (shape 2, index 119)")
            break

    with open(monsters_path, "w", encoding="utf-8") as f:
        json.dump(monsters, f, ensure_ascii=False, indent=2)

    # 3. 更新 data/alignment/entities/monster.json
    entities_path = ROOT / "data" / "alignment" / "entities" / "monster.json"
    with open(entities_path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    for item in entities:
        eid = item.get("id")
        if eid == "monster:website:mob-122":
            item["game_data"] = {
                "image": "Mon_15 shape 2",
                "index": 119,
                "name": "Bone Soldier"
            }
            item["identity"]["zircon_candidate_indexes"] = [119]
            item["identity"]["zircon_internal_name"] = "Bone Soldier"
            item["relations"]["candidate_entity_ids"] = ["monster:zircon:119"]
            item["resources"]["zircon"] = {
                "path": "/images/mob/game/Bone_Soldier.png",
                "verification": "verified-by-image"
            }
            if "assessment" in item and isinstance(item["assessment"], dict):
                item["assessment"]["reason"] = "潘夜石窟骷髅士兵真身（Mon_15 shape 2），手持带旗长枪，与 67.gif 原画 100% 吻合"
        elif eid == "monster:zircon:116":
            if "relations" in item and "conflict_counterparts" in item["relations"]:
                item["relations"]["conflict_counterparts"] = [
                    c for c in item["relations"]["conflict_counterparts"]
                    if c != "monster:website:mob-122"
                ]

    with open(entities_path, "w", encoding="utf-8") as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)
    print("Updated data/alignment/entities/monster.json")

    # 4. 更新 data/alignment/research_findings.json
    rf_path = ROOT / "data" / "alignment" / "research_findings.json"
    with open(rf_path, "r", encoding="utf-8") as f:
        rf = json.load(f)

    for item in rf:
        if item.get("id") == "web-audit:monster:124" or item.get("source_record_id") == "website:mob-122":
            item["zircon_index"] = 119
            item["zircon_internal_name"] = "Bone Soldier"
            print("Updated research_findings item for mob-122 -> Bone Soldier")

    with open(rf_path, "w", encoding="utf-8") as f:
        json.dump(rf, f, ensure_ascii=False, indent=2)

    # 5. 更新 data/alignment/master.json shards sha256 & count
    master_path = ROOT / "data" / "alignment" / "master.json"
    with open(master_path, "r", encoding="utf-8") as f:
        master = json.load(f)

    with open(entities_path, "rb") as f:
        entities_sha = hashlib.sha256(f.read()).hexdigest()

    with open(rf_path, "rb") as f:
        rf_sha = hashlib.sha256(f.read()).hexdigest()

    for shard in master.get("shards", {}).get("entities", []):
        if shard.get("path") == "entities/monster.json":
            shard["sha256"] = entities_sha
            shard["count"] = len(entities)
            print("Updated master.json entities/monster.json sha256")

    for shard in master.get("shards", {}).get("research_findings", []):
        if shard.get("path") == "research_findings.json":
            shard["sha256"] = rf_sha
            shard["count"] = len(rf)
            print("Updated master.json research_findings.json sha256")

    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print("Updated data/alignment/master.json")


if __name__ == "__main__":
    main()
