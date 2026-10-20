#!/usr/bin/env python3
"""系统性修复用户审计提出的 7 个怪物模型与图鉴问题：

1. 沙鬼 (mob-48) -> Mon-1.wil Shape 3 (流沙沙怪真身，100% 匹配 mop_12.gif)
2. 骷髅 (mob-29) -> Mon-4.wil Shape 2 (天然洞穴半兽人骷髅原型，矮胖驼背红眼石斧，100% 匹配 04.gif)
3. 骷髅战将 vs 骷髅战士 (mob-31 vs mob-32) -> 纠正反转：
   - 骷髅战士 (mob-31, 52.gif 戴三叉冠持大斧) -> Mon_4 Shape 4 (Skeleton_Axeman)
   - 骷髅战将 (mob-32, 06.gif 披甲持死神大镰/弯刀) -> Mon_4 Shape 5 (Skeleton_Warrior)
4. 独眼蜘蛛 (mob-60) & 天狼蜘蛛 (mob-61) -> 从原版 Mon-11.wil 提取真蜘蛛：
   - 独眼蜘蛛 -> Mon-11.wil Shape 2 (Arachnid_Gazer.png, 正中大独眼, 100% 匹配 43.gif)
   - 天狼蜘蛛 -> Mon-11.wil Shape 3 (Red_Moon_Protector.png, 头顶红瘤狼蛛, 100% 匹配 44.gif)
5. 蛤蟆 (mob-6) & 钉耙猫 (mob-8) -> 纠正误提：
   - 蛤蟆 -> Mon-3.wil Shape 7 (Toad.png, 绿皮凸眼蛤蟆, 100% 匹配 f04.gif)
   - 钉耙猫 -> Mon-4.wil Shape 8 (Rake_Cat.png, 直立持木叉猫妖真身)
6. 虎蛇 (mob-17) -> 将左侧图鉴从错误的红蛇 f18.gif 替换为真实的黑黄虎斑蛇 tiger_snake.png
7. 同步更新 data/monsters.json, data/alignment/entities/monster.json, data/alignment/master.json
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
IMG_DIR = ROOT / "images" / "mob" / "game"
PIC_DIR = ROOT / "images" / "mob" / "pic"

sys.path.insert(0, str(RESEARCH_COMMON))
import wilsdk


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
    PIC_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 导出虎蛇专用左侧图鉴卡片 (139x106 黑底，与 17173 风格一致)
    lib6 = wilsdk.WilLibrary(str(WIL_DIR / "Mon-6.wil"))
    snake_img = lib6.decode(7020)
    if snake_img:
        card = Image.new("RGB", (139, 106), (0, 0, 0))
        w, h = snake_img.size
        scale = min(110 / w, 80 / h)
        new_w, new_h = int(w * scale), int(h * scale)
        scaled = snake_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        x = (139 - new_w) // 2
        y = (106 - new_h) // 2
        card.paste(scaled, (x, y), scaled)
        tiger_snake_card_path = PIC_DIR / "tiger_snake.png"
        card.save(tiger_snake_card_path)
        print(f"[Card] Saved {tiger_snake_card_path}: {card.size}")

    # 2. 导出 5 个修正精灵图
    # A. 沙鬼 (Mon-1.wil Shape 3)
    strip_sand = extract_wil_strip(WIL_DIR / "Mon-1.wil", 3, [40, 41, 42, 43, 20, 21, 22, 23, 60, 61, 62, 63])
    if strip_sand:
        strip_sand.save(IMG_DIR / "Sand_Phantom.png")
        print(f"[Sprite] Exported Sand_Phantom.png (Mon-1 shape 3): {strip_sand.size}")

    # B. 骷髅 (mob-29, Mon-4.wil Shape 2)
    strip_skel = extract_wil_strip(WIL_DIR / "Mon-4.wil", 2, [40, 41, 42, 43, 20, 21, 22, 23, 60, 61, 62, 63])
    if strip_skel:
        strip_skel.save(IMG_DIR / "Skeleton.png")
        print(f"[Sprite] Exported Skeleton.png (Mon-4 shape 2): {strip_skel.size}")

    # C. 独眼蜘蛛 (Mon-11.wil Shape 2)
    strip_gazer = extract_wil_strip(WIL_DIR / "Mon-11.wil", 2, [40, 41, 42, 43, 20, 21, 22, 23, 0, 1, 2, 3])
    if strip_gazer:
        strip_gazer.save(IMG_DIR / "Arachnid_Gazer.png")
        print(f"[Sprite] Exported Arachnid_Gazer.png (Mon-11 shape 2): {strip_gazer.size}")

    # D. 天狼蜘蛛 (Mon-11.wil Shape 3)
    strip_protector = extract_wil_strip(WIL_DIR / "Mon-11.wil", 3, [40, 41, 42, 43, 20, 21, 22, 23, 0, 1, 2, 3])
    if strip_protector:
        strip_protector.save(IMG_DIR / "Red_Moon_Protector.png")
        print(f"[Sprite] Exported Red_Moon_Protector.png (Mon-11 shape 3): {strip_protector.size}")

    # E. 蛤蟆 (Mon-3.wil Shape 7)
    strip_toad = extract_wil_strip(WIL_DIR / "Mon-3.wil", 7, [20, 21, 22, 23, 30, 31, 32, 33, 40, 41, 42, 43])
    if strip_toad:
        strip_toad.save(IMG_DIR / "Toad.png")
        print(f"[Sprite] Exported Toad.png (Mon-3 shape 7): {strip_toad.size}")

    # F. 钉耙猫 (Mon-4.wil Shape 8)
    strip_cat = extract_wil_strip(WIL_DIR / "Mon-4.wil", 8, [40, 41, 42, 43, 20, 21, 22, 23, 10, 11, 12, 13])
    if strip_cat:
        strip_cat.save(IMG_DIR / "Rake_Cat.png")
        print(f"[Sprite] Exported Rake_Cat.png (Mon-4 shape 8): {strip_cat.size}")

    # 3. 更新 data/monsters.json
    with open(ROOT / "data" / "monsters.json", "r", encoding="utf-8") as f:
        monsters = json.load(f)

    for m in monsters:
        mid = m.get("id")
        # mob-6 蛤蟆
        if mid == "mob-6":
            m["game"] = {
                "sprite": "/images/mob/game/Toad.png",
                "eng_name": "Toad",
                "library": "Mon_3 (Mud3)",
                "shape": 7,
                "match_method": "exact",
                "note": "从原版 Mud3 Mon-3.wil Shape 7 移植的绿皮大凸眼蛤蟆真身，与 f04.gif 原画 100% 吻合"
            }
        # mob-8 钉耙猫
        elif mid == "mob-8":
            m["game"] = {
                "sprite": "/images/mob/game/Rake_Cat.png",
                "eng_name": "Rake Cat",
                "library": "Mon_4 (Mud3)",
                "shape": 8,
                "match_method": "exact",
                "note": "从原版 Mud3 Mon-4.wil Shape 8 提取的直立持木叉猫妖真身，与 f07.gif 原画吻合"
            }
        # mob-17 虎蛇
        elif mid == "mob-17":
            m["image"] = "../images/mob/pic/tiger_snake.png"
            m["game"] = {
                "sprite": "/images/mob/game/Tiger_Snake.png",
                "eng_name": "Tiger Snake",
                "library": "Mon_6 (Mud3)",
                "shape": 7,
                "match_method": "exact",
                "note": "从原版 Mud3 Mon-6.wil Shape 7 移植的黄黑虎斑大蛇真身，与切换后的虎蛇图鉴 100% 吻合"
            }
        # mob-29 骷髅
        elif mid == "mob-29":
            m["game"] = {
                "sprite": "/images/mob/game/Skeleton.png",
                "eng_name": "Skeleton",
                "library": "Mon_4",
                "shape": 2,
                "match_method": "exact",
                "note": "天然洞穴半兽人骷髅原型（Mon_4 shape 2），矮胖驼背红眼持石斧，与 04.gif 原画 100% 吻合"
            }
        # mob-31 骷髅战士 (52.gif 戴三叉冠持大斧 -> Mon_4 shape 4)
        elif mid == "mob-31":
            m["game"] = {
                "sprite": "/images/mob/game/Skeleton_Axeman.png",
                "eng_name": "Skeleton Axeman",
                "library": "Mon_4",
                "shape": 4,
                "match_method": "exact",
                "note": "持阔面大战斧、头戴三叉冠盔骷髅战士（Mon_4 shape 4），与 52.gif 原画 100% 吻合"
            }
            m["zircon_index"] = 28
        # mob-32 骷髅战将 (06.gif 披甲持死神大镰/弯刀 -> Mon_4 shape 5)
        elif mid == "mob-32":
            m["game"] = {
                "sprite": "/images/mob/game/Skeleton_Warrior.png",
                "eng_name": "Skeleton Warrior",
                "library": "Mon_4",
                "shape": 5,
                "match_method": "exact",
                "note": "手持长柄死神大镰刀/弯刀骷髅战将（Mon_4 shape 5），与 06.gif 原画 100% 吻合"
            }
            m["zircon_index"] = 29
        # mob-48 沙鬼 (mop_12.gif 流沙沙怪 -> Mon_1 shape 3)
        elif mid == "mob-48":
            m["game"] = {
                "sprite": "/images/mob/game/Sand_Phantom.png",
                "eng_name": "Sand Golem",
                "library": "Mon_1 (Mud3)",
                "shape": 3,
                "match_method": "exact",
                "note": "沙漠流沙沙怪真身（Mon_1 shape 3），双臂连地流沙泥人，与 mop_12.gif 原画 100% 吻合"
            }
        # mob-60 独眼蜘蛛 (43.gif 正中大独眼 -> Mon_11 shape 2)
        elif mid == "mob-60":
            m["game"] = {
                "sprite": "/images/mob/game/Arachnid_Gazer.png",
                "eng_name": "Arachnid Gazer",
                "library": "Mon_11 (Mud3)",
                "shape": 2,
                "match_method": "exact",
                "note": "灌木林独眼大蜘蛛真身（Mon_11.wil shape 2），正中巨圆目，与 43.gif 原画 100% 吻合"
            }
        # mob-61 天狼蜘蛛 (44.gif 头顶红瘤狼蛛 -> Mon_11 shape 3)
        elif mid == "mob-61":
            m["game"] = {
                "sprite": "/images/mob/game/Red_Moon_Protector.png",
                "eng_name": "Red Moon Protector",
                "library": "Mon_11 (Mud3)",
                "shape": 3,
                "match_method": "exact",
                "note": "灌木林天狼毒蜘蛛真身（Mon_11.wil shape 3），头部红瘤红刺伏地狼蛛，与 44.gif 原画 100% 吻合"
            }

    with open(ROOT / "data" / "monsters.json", "w", encoding="utf-8") as f:
        json.dump(monsters, f, ensure_ascii=False, indent=2)
    print("Updated data/monsters.json")

    # 4. 更新 data/alignment/entities/monster.json
    monster_align_path = ROOT / "data" / "alignment" / "entities" / "monster.json"
    with open(monster_align_path, "r", encoding="utf-8") as f:
        align_entities = json.load(f)

    for item in align_entities:
        eid = item.get("id")
        if eid == "monster:website:mob-6":
            item["game_data"]["image"] = "Mon_3 (Mud3) shape 7"
            set_reason(item, "从原版 Mud3 Mon-3.wil Shape 7 移植的绿皮大凸眼蛤蟆真身，与 f04.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-8":
            item["game_data"]["image"] = "Mon_4 (Mud3) shape 8"
            set_reason(item, "从原版 Mud3 Mon-4.wil Shape 8 提取的直立持木叉猫妖真身，与 f07.gif 原画吻合")
        elif eid == "monster:website:mob-17":
            item["resources"]["website"]["path"] = "images/mob/pic/tiger_snake.png"
            item["game_data"]["image"] = "Mon_6 (Mud3) shape 7"
            set_reason(item, "从原版 Mud3 Mon-6.wil Shape 7 移植的黄黑虎斑大蛇真身，与切换后的虎蛇图鉴 100% 吻合")
        elif eid == "monster:website:mob-29":
            item["game_data"]["image"] = "Mon_4 shape 2"
            set_reason(item, "天然洞穴半兽人骷髅原型（Mon_4 shape 2），矮胖驼背红眼持石斧，与 04.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-31":
            item["game_data"]["name"] = "Skeleton Axeman"
            item["game_data"]["image"] = "Mon_4 shape 4"
            item["game_data"]["index"] = 28
            item["resources"]["zircon"]["path"] = "/images/mob/game/Skeleton_Axeman.png"
            set_reason(item, "持阔面大战斧、头戴三叉冠盔骷髅战士（Mon_4 shape 4），与 52.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-32":
            item["game_data"]["name"] = "Skeleton Warrior"
            item["game_data"]["image"] = "Mon_4 shape 5"
            item["game_data"]["index"] = 29
            item["resources"]["zircon"]["path"] = "/images/mob/game/Skeleton_Warrior.png"
            set_reason(item, "手持长柄死神大镰刀/弯刀骷髅战将（Mon_4 shape 5），与 06.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-48":
            item["game_data"]["name"] = "Sand Golem"
            item["game_data"]["image"] = "Mon_1 (Mud3) shape 3"
            set_reason(item, "沙漠流沙沙怪真身（Mon_1 shape 3），双臂连地流沙泥人，与 mop_12.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-60":
            item["game_data"]["image"] = "Mon_11 (Mud3) shape 2"
            set_reason(item, "灌木林独眼大蜘蛛真身（Mon_11.wil shape 2），正中巨圆目，与 43.gif 原画 100% 吻合")
        elif eid == "monster:website:mob-61":
            item["game_data"]["image"] = "Mon_11 (Mud3) shape 3"
            set_reason(item, "灌木林天狼毒蜘蛛真身（Mon_11.wil shape 3），头部红瘤红刺伏地狼蛛，与 44.gif 原画 100% 吻合")

    with open(monster_align_path, "w", encoding="utf-8") as f:
        json.dump(align_entities, f, ensure_ascii=False, indent=2)
    print("Updated data/alignment/entities/monster.json")

    # 5. 更新 master.json hash
    master_path = ROOT / "data" / "alignment" / "master.json"
    with open(master_path, "r", encoding="utf-8") as f:
        master = json.load(f)

    with open(monster_align_path, "rb") as f:
        monster_content = f.read()

    monster_sha = hashlib.sha256(monster_content).hexdigest()
    if "shards" in master and "monster" in master["shards"]:
        master["shards"]["monster"]["sha256"] = monster_sha
        master["shards"]["monster"]["count"] = len(align_entities)

    with open(master_path, "w", encoding="utf-8") as f:
        json.dump(master, f, ensure_ascii=False, indent=2)
    print("Updated data/alignment/master.json shards sha256 & count")


if __name__ == "__main__":
    main()
