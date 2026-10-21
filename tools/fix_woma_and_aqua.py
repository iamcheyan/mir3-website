#!/usr/bin/env python3
"""修复沃玛勇士、沃玛战将、恶性怪真模型与解耦：

1. 沃玛勇士 (mob-111) -> Mon-28.Zl Shape 7 (Uma_Warrior.png, 双手持长柄红杆金叉三叉戟, 100% 匹配 11.gif)
2. 沃玛战将 (mob-112) -> Mon-27.Zl Shape 8 (Uma_Warlord.png, 手持金刺带钩大骨锤, 100% 匹配 12.gif)
3. 恶性怪 (mob-139) -> Mon-10.Zl Shape 2 (Aqua_Lizard.png, 头顶白尖刺绿色双足蜥魔, 100% 匹配 image026.gif / 用户截图)
4. 更新 data/monsters.json 与 data/alignment/entities/monster.json，并重算 master.json shard sha256
"""

import json
import os
import sys
import hashlib
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


def set_reason(item: dict, text: str):
    if "assessment" in item and isinstance(item["assessment"], dict):
        item["assessment"]["reason"] = text
    if "decision" in item and isinstance(item["decision"], dict):
        item["decision"]["reason"] = text


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    std_offsets = [40, 41, 42, 43, 120, 121, 122, 123, 200, 201, 202, 203, 360, 361, 362, 363]

    # 1. 导出 3 个怪物独立精灵图
    # A. 沃玛勇士 (Mon-28.Zl Shape 7, 双手持长柄红杆金叉三叉戟)
    strip_uma_warrior = extract_zl_strip(ZL_DIR / "Mon-28.Zl", 7, std_offsets)
    if strip_uma_warrior:
        strip_uma_warrior.save(IMG_DIR / "Uma_Warrior.png")
        print(f"[Sprite] Exported Uma_Warrior.png (Mon-28 shape 7): {strip_uma_warrior.size}")

    # B. 沃玛战将 (Mon-27.Zl Shape 8, 手持金刺带钩大骨锤)
    strip_uma_warlord = extract_zl_strip(ZL_DIR / "Mon-27.Zl", 8, std_offsets)
    if strip_uma_warlord:
        strip_uma_warlord.save(IMG_DIR / "Uma_Warlord.png")
        print(f"[Sprite] Exported Uma_Warlord.png (Mon-27 shape 8): {strip_uma_warlord.size}")

    # C. 恶性怪 (Mon-10.Zl Shape 2, 水蜥蜴/恶形鬼真身，头顶白尖刺绿色蜥魔)
    strip_aqua_lizard = extract_zl_strip(ZL_DIR / "Mon-10.Zl", 2, std_offsets)
    if strip_aqua_lizard:
        strip_aqua_lizard.save(IMG_DIR / "Aqua_Lizard.png")
        print(f"[Sprite] Exported Aqua_Lizard.png (Mon-10 shape 2): {strip_aqua_lizard.size}")

    # 2. 更新 data/monsters.json
    with open(ROOT / "data" / "monsters.json", "r", encoding="utf-8") as f:
        monsters = json.load(f)

    for m in monsters:
        mid = m.get("id")
        if mid == "mob-111":
            m["game"] = {
                "sprite": "/images/mob/game/Uma_Warrior.png",
                "eng_name": "Uma Trident Infidel",
                "library": "Mon_28",
                "shape": 7,
                "match_method": "exact",
                "note": "Zircon 原生 Mon_28 shape 7 沃玛勇士真身（双手持长柄红杆金叉三叉戟），与 11.gif 原画 100% 吻合"
            }
        elif mid == "mob-112":
            m["game"] = {
                "sprite": "/images/mob/game/Uma_Warlord.png",
                "eng_name": "Uma Mace Infidel",
                "library": "Mon_27",
                "shape": 8,
                "match_method": "exact",
                "note": "Zircon 原生 Mon_27 shape 8 沃玛战将真身（手持带钩金刺大骨锤），与 12.gif 原画 100% 吻合"
            }
        elif mid == "mob-139":
            m["game"] = {
                "sprite": "/images/mob/game/Aqua_Lizard.png",
                "eng_name": "Aqua Lizard",
                "library": "Mon_10",
                "shape": 2,
                "match_method": "exact",
                "note": "Mon-10 shape 2 水蜥蜴/恶形鬼真身（头顶白尖刺绿色双足长爪蜥魔），与 image026.gif 原画 100% 吻合"
            }
            m["zircon_index"] = 156

    with open(ROOT / "data" / "monsters.json", "w", encoding="utf-8") as f:
        json.dump(monsters, f, ensure_ascii=False, indent=2)
    print("Updated data/monsters.json")

    # 3. 更新 data/alignment/entities/monster.json
    monster_align_path = ROOT / "data" / "alignment" / "entities" / "monster.json"
    with open(monster_align_path, "r", encoding="utf-8") as f:
        align_entities = json.load(f)

    for item in align_entities:
        eid = item.get("id")
        if eid == "monster:website:mob-139":
            item["game_data"] = {
                "image": "Mon_10 shape 2",
                "index": 156,
                "name": "Aqua Lizard"
            }
            if "identity" in item:
                item["identity"]["zircon_candidate_indexes"] = [156]
                item["identity"]["zircon_internal_name"] = "Aqua Lizard"
            if "relations" in item:
                item["relations"]["candidate_entity_ids"] = ["monster:zircon:156"]
            if "resources" in item and "zircon" in item["resources"]:
                item["resources"]["zircon"]["path"] = "/images/mob/game/Aqua_Lizard.png"
            set_reason(item, "Mon-10 shape 2 水蜥蜴/恶形鬼真身（头顶白尖刺绿色双足长爪蜥魔），与 image026.gif 原画 100% 吻合")

    with open(monster_align_path, "w", encoding="utf-8") as f:
        json.dump(align_entities, f, ensure_ascii=False, indent=2)
    print("Updated data/alignment/entities/monster.json")

    # 4. 更新 master.json shard sha256
    master_path = ROOT / "data" / "alignment" / "master.json"
    with open(master_path, "r", encoding="utf-8") as f:
        master = json.load(f)

    with open(monster_align_path, "rb") as f:
        monster_content = f.read()

    monster_sha = hashlib.sha256(monster_content).hexdigest()
    found = False
    for shard in master.get("shards", {}).get("entities", []):
        if shard.get("path") == "entities/monster.json":
            shard["sha256"] = monster_sha
            shard["count"] = len(align_entities)
            found = True
            break

    if found:
        with open(master_path, "w", encoding="utf-8") as f:
            json.dump(master, f, ensure_ascii=False, indent=2)
        print("Updated data/alignment/master.json shards entities/monster.json sha256 & count")
    else:
        print("WARNING: entities/monster.json not found in master shards!")


if __name__ == "__main__":
    main()
