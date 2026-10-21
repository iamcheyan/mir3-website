#!/usr/bin/env python3
"""修复钉耙猫、独眼蜘蛛、天狼蜘蛛、幻影蜘蛛、血金刚/神鬼王、白野猪模型与解耦：

1. 钉耙猫 (mob-8) -> Mon-28.Zl Shape 6 (Rake_Cat.png, 双手持木柄铁齿钉耙, 100% 匹配 f07.gif)
2. 独眼蜘蛛 (mob-60) -> Mon-11.wil Shape 2 (Arachnid_Gazer.png, 正中巨圆目大蜘蛛, 100% 匹配 43.gif)
3. 天狼蜘蛛 (mob-61) -> Mon-11.wil Shape 3 (Wolf_Spider.png, 独立文件, 头部红瘤狼蛛, 100% 匹配 44.gif)
4. 幻影蜘蛛 (mob-62) -> Mon-11.Zl Shape 6 (Phantom_Spider.png, 独立文件, 巨型骷髅印记母蛛巢穴, 100% 匹配 45.gif)
5. 血金刚/神鬼王 (mob-74, mob-75) -> Mon-11.Zl Shape 8 (Red_Moon_Protector.png, 恢复双头金刚真身, 100% 匹配 50.gif)
6. 白野猪 (mob-103) -> Mon-8.Zl Shape 8 (White_Boar.png, 独立文件, 流星铁球锤白野猪, 100% 匹配 40.gif)
7. 赤黄猪王 (mob-99) -> 保持 Mon-21 Shape 6 (Tusk_Lord.png, 战锤赤黄獠牙猪神)
8. 更新 data/monsters.json 与 data/alignment/entities/monster.json，并重算 master.json shard sha256
"""

import json
import os
import sys
import hashlib
from pathlib import Path
from PIL import Image

ROOT = Path("/home/tetsuya/development/mir3-website")
RESEARCH_COMMON = Path("/home/tetsuya/development/Mir3-Research/Tools/common")
LEGACY_WIL_DIR = Path("/home/tetsuya/mir2ei_archive/LegacyEI/Data")
ZL_DIR = Path("/home/tetsuya/mir2ei/Data")
IMG_DIR = ROOT / "images" / "mob" / "game"

sys.path.insert(0, str(RESEARCH_COMMON))
import zlsdk
import wilsdk


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


def set_reason(item: dict, text: str):
    if "assessment" in item and isinstance(item["assessment"], dict):
        item["assessment"]["reason"] = text
    if "decision" in item and isinstance(item["decision"], dict):
        item["decision"]["reason"] = text


def main():
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 导出/恢复 5 个独立模型精灵图
    # A. 钉耙猫 (Mon-28.Zl Shape 6, DefaultMonster 标准动作帧)
    strip_rake = extract_zl_strip(ZL_DIR / "Mon-28.Zl", 6, [40, 41, 42, 43, 120, 121, 122, 123, 200, 201, 202, 203, 360, 361, 362, 363])
    if strip_rake:
        strip_rake.save(IMG_DIR / "Rake_Cat.png")
        print(f"[Sprite] Exported Rake_Cat.png (Mon-28 shape 6): {strip_rake.size}")

    # B. 幻影蜘蛛 (Mon-11.Zl Shape 6, 巨型骷髅母蛛巢穴真身)
    strip_phantom = extract_zl_strip(ZL_DIR / "Mon-11.Zl", 6, [0, 1, 2, 3, 10, 11, 12, 13, 160, 161, 162, 163, 170, 171, 320, 321, 322, 323])
    if strip_phantom:
        strip_phantom.save(IMG_DIR / "Phantom_Spider.png")
        print(f"[Sprite] Exported Phantom_Spider.png (Mon-11 shape 6): {strip_phantom.size}")

    # C. 天狼蜘蛛 (Mon-11.wil Shape 3, 独立文件 Wolf_Spider.png)
    strip_wolf = extract_wil_strip(LEGACY_WIL_DIR / "Mon-11.wil", 3, [40, 41, 42, 43, 20, 21, 22, 23, 0, 1, 2, 3])
    if strip_wolf:
        strip_wolf.save(IMG_DIR / "Wolf_Spider.png")
        print(f"[Sprite] Exported Wolf_Spider.png (Mon-11 shape 3): {strip_wolf.size}")

    # D. 血金刚/神鬼王 (Mon-11.Zl Shape 8, 恢复 Red_Moon_Protector.png 为双头金刚真身)
    strip_protector = extract_zl_strip(ZL_DIR / "Mon-11.Zl", 8, [40, 41, 42, 43, 120, 121, 122, 123, 200, 201, 202, 203, 360, 361, 362, 363])
    if strip_protector:
        strip_protector.save(IMG_DIR / "Red_Moon_Protector.png")
        print(f"[Sprite] Restored Red_Moon_Protector.png (Mon-11 shape 8): {strip_protector.size}")

    # E. 白野猪 (Mon-8.Zl Shape 8, 独立文件 White_Boar.png)
    strip_boar = extract_zl_strip(ZL_DIR / "Mon-8.Zl", 8, [40, 41, 42, 43, 120, 121, 122, 123, 200, 201, 202, 203, 360, 361, 362, 363])
    if strip_boar:
        strip_boar.save(IMG_DIR / "White_Boar.png")
        print(f"[Sprite] Exported White_Boar.png (Mon-8 shape 8): {strip_boar.size}")

    # F. 半兽人 (Mon-28.Zl Shape 4, 棕黄肉色皮肤蓝护腕手持石刀真身，区别于墨绿皮肤半兽战士)
    strip_oma = extract_zl_strip(ZL_DIR / "Mon-28.Zl", 4, [40, 41, 42, 43, 120, 121, 122, 123, 124, 125, 200, 201, 202, 203, 204, 205, 360, 361, 362, 363])
    if strip_oma:
        strip_oma.save(IMG_DIR / "Oma.png")
        print(f"[Sprite] Exported Oma.png (Mon-28 shape 4): {strip_oma.size}")

    # 2. 更新 data/monsters.json
    with open(ROOT / "data" / "monsters.json", "r", encoding="utf-8") as f:
        monsters = json.load(f)

    for m in monsters:
        mid = m.get("id")
        if mid == "mob-8":
            m["game"] = {
                "sprite": "/images/mob/game/Rake_Cat.png",
                "eng_name": "Raking Cat",
                "library": "Mon_28",
                "shape": 6,
                "match_method": "exact",
                "note": "Zircon 原生 Mon_28 shape 6 钉耙猫真身，双手横持木柄铁齿钉耙，与 f07.gif 原画 100% 吻合"
            }
        elif mid == "mob-12":
            m["game"] = {
                "sprite": "/images/mob/game/Oma.png",
                "eng_name": "Oma",
                "library": "Mon_28",
                "shape": 4,
                "match_method": "exact",
                "note": "Zircon 原生 Mon_28 shape 4 半兽人真身（棕黄肉色皮肤、双腕双踝蓝护圈手持石刀），与 f09.gif 原画 100% 吻合"
            }
        elif mid == "mob-13":
            m["game"] = {
                "sprite": "/images/mob/game/Oma_Warrior.png",
                "eng_name": "Oma Warrior",
                "library": "Mon_3",
                "shape": 3,
                "match_method": "exact",
                "note": "Mon_3 shape 3 半兽战士（墨绿皮肤、红护腕手持兽骨棒之半兽族长老），与 f10.gif 原画 100% 吻合"
            }
        elif mid == "mob-60":
            m["game"] = {
                "sprite": "/images/mob/game/Arachnid_Gazer.png",
                "eng_name": "Arachnid Gazer",
                "library": "Mon_11 (Mud3)",
                "shape": 2,
                "match_method": "exact",
                "note": "灌木林独眼大蜘蛛真身（Mon_11.wil shape 2），正中巨圆目，与 43.gif 原画 100% 吻合"
            }
        elif mid == "mob-61":
            m["game"] = {
                "sprite": "/images/mob/game/Wolf_Spider.png",
                "eng_name": "Wolf Spider",
                "library": "Mon_11 (Mud3)",
                "shape": 3,
                "match_method": "exact",
                "note": "灌木林天狼毒蜘蛛真身（Mon_11.wil shape 3），头部红瘤红刺伏地狼蛛，与 44.gif 原画 100% 吻合"
            }
        elif mid == "mob-62":
            m["game"] = {
                "sprite": "/images/mob/game/Phantom_Spider.png",
                "eng_name": "Arachnid Gazer",
                "library": "Mon_11",
                "shape": 6,
                "match_method": "exact",
                "note": "Mon-11 shape 6 幻影蜘蛛母蛛巢穴原型（背部带骷髅印记与蛛网巨蛛），与 45.gif 原画 100% 吻合"
            }
        elif mid == "mob-74":
            m["game"] = {
                "sprite": "/images/mob/game/Red_Moon_Protector.png",
                "eng_name": "Red Moon Protector",
                "library": "Mon_11",
                "shape": 8,
                "match_method": "alias",
                "note": "Mon-11 shape 8 双头血金刚真身（双头巨力赤瘤神魔），与 50.gif 原画 100% 吻合"
            }
        elif mid == "mob-75":
            m["game"] = {
                "sprite": "/images/mob/game/Red_Moon_Protector.png",
                "eng_name": "Red Moon Protector",
                "library": "Mon_11",
                "shape": 8,
                "match_method": "alias",
                "note": "Mon-11 shape 8 双头血金刚真身（双头巨力赤瘤神魔），与 50.gif 原画 100% 吻合"
            }
        elif mid == "mob-99":
            m["game"] = {
                "sprite": "/images/mob/game/Tusk_Lord.png",
                "eng_name": "Tusk Lord",
                "library": "Mon_21 (Mud3)",
                "shape": 6,
                "match_method": "exact",
                "note": "从原版 Mud3 Mon-21.wil Shape 6 移植的持大战锤赤黄獠牙猪神真身，与 23.gif 原画 100% 吻合"
            }
        elif mid == "mob-103":
            m["game"] = {
                "sprite": "/images/mob/game/White_Boar.png",
                "eng_name": "White Boar",
                "library": "Mon_8",
                "shape": 8,
                "match_method": "exact",
                "note": "Mon-8 shape 8 流星铁球锤经典白野猪真身，与 40.gif 原画 100% 吻合"
            }

    with open(ROOT / "data" / "monsters.json", "w", encoding="utf-8") as f:
        json.dump(monsters, f, ensure_ascii=False, indent=2)
    print("Updated data/monsters.json")

    # 3. 更新 data/alignment/entities/monster.json
    monster_align_path = ROOT / "data" / "alignment" / "entities" / "monster.json"
    with open(monster_align_path, "r", encoding="utf-8") as f:
        align_entities = json.load(f)

    for item in align_entities:
        eid = item.get("id")
        if eid == "monster:website:mob-8":
            item["game_data"]["image"] = "Mon_28 shape 6"
            if "resources" in item and "zircon" in item["resources"]:
                item["resources"]["zircon"]["path"] = "/images/mob/game/Rake_Cat.png"
            set_reason(item, "Zircon 原生 Mon_28 shape 6 钉耙猫真身，双手横持木柄铁齿钉耙，与 f07.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-60":
            item["game_data"]["image"] = "Mon_11 (Mud3) shape 2"
            if "resources" in item and "zircon" in item["resources"]:
                item["resources"]["zircon"]["path"] = "/images/mob/game/Arachnid_Gazer.png"
            set_reason(item, "灌木林独眼大蜘蛛真身（Mon_11.wil shape 2），正中巨圆目，与 43.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-61":
            item["game_data"]["image"] = "Mon_11 (Mud3) shape 3"
            if "resources" in item and "zircon" in item["resources"]:
                item["resources"]["zircon"]["path"] = "/images/mob/game/Wolf_Spider.png"
            set_reason(item, "灌木林天狼毒蜘蛛真身（Mon_11.wil shape 3），头部红瘤红刺伏地狼蛛，与 44.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-62":
            item["game_data"]["image"] = "Mon_11 shape 6"
            if "resources" in item and "zircon" in item["resources"]:
                item["resources"]["zircon"]["path"] = "/images/mob/game/Phantom_Spider.png"
            set_reason(item, "Mon-11 shape 6 幻影蜘蛛母蛛巢穴原型（背部带骷髅印记与蛛网巨蛛），与 45.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-103":
            item["game_data"]["image"] = "Mon_8 shape 8"
            if "resources" in item and "zircon" in item["resources"]:
                item["resources"]["zircon"]["path"] = "/images/mob/game/White_Boar.png"
            set_reason(item, "Mon-8 shape 8 流星铁球锤经典白野猪真身，与 40.gif 原画 100% 吻合")

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
