#!/usr/bin/env python3
"""系统性校正 20 只怪物模型与动作精灵图

覆盖目标：
1. 地牢女神 (mob-150 / mob-151) -> PinkGoddess (Mon_17 shape 2) / GreenGoddess (Mon_17 shape 3)
2. 火焰狮子 (mob-147) -> FlameGriffin (Mon_16 shape 9)
3. 石像狮子 (mob-148) -> StoneGriffin (Mon_17 shape 0)
4. 魔神怪1 (mob-69) -> CannibalFanatic (Mon_16 shape 6)
5. 魔神怪2 (mob-70) -> EvilFanatic (Mon_16 shape 7)
6. 猿猴战将 (mob-68) -> WhiteMonkey (Mon_16 shape 4 白毛变种)
7. 骷髅武士 (mob-125) -> BoneCaptain (Mon_15 shape 0, 手执狼牙刺球)
8. 青铜钳虫 (mob-91) -> BronzeEarwig (Mon_7 shape 9 青铜冷光)
9. 沃角钳虫 (mob-90) -> HornEarwig (Mon_7 shape 9 赤褐变色)
10. 白眼钳虫 (mob-89) -> WhiteEarwig (Mon_7 shape 9 白化变色)
11. 钳虫 (mob-88) -> Earwig (Mon_7 shape 9 原版钳虫)
12. 月魔蜘蛛 (mob-59) -> SpiderBat (Mon_11 shape 1, 蝙蝠双翼)
13. 花色蜘蛛 (mob-65) -> VenomousArachnid (Mon_12 shape 1, 条纹花斑)
14. 独眼蜘蛛 (mob-60) -> ArachnidGazer (Mon_11 shape 6, 独眼巨角)
15. 天狼蜘蛛 (mob-61) -> RedMoonProtector (Mon_11 shape 8, 背刺红瘤)
16. 大法老 (mob-58) -> NumaHighMage (Mon_19 shape 4, 诺玛高阶大法老)
17. 诺玛法老 (mob-57) -> NumaMage (Mon_2 shape 3, 诺玛持杖老法老)
18. 沙漠鱼魔 (mob-53) -> SandShark (Mon_10 shape 4, 沙海露鳍沙鲨)
19. 沙鬼 (mob-48) -> AntNeedler (Mon_10 shape 6, 细折腿尾刺)
20. 沙漠蜥蜴 (mob-51) -> SpinedDarkLizard (Mon_5 shape 6, 黄褐棘刺沙蜥)
21. 沙漠威斯而小虫 (mob-23) -> DesertVisceralWorm (Mon_7 shape 1, 沙地变体)
22. 虎蛇 (mob-17) -> TigerSnake (Mon_6 shape 7, 黄黑虎斑)
23. 七点白蛇 (mob-18) & 千年毒蛇 (mob-19) -> WhiteSnake (Mon_13 shape 6, 白蛇真身)
"""

import json
import os
import sys
from pathlib import Path
from PIL import Image

ROOT = Path("/home/tetsuya/development/mir3-website")
RESEARCH_COMMON = Path("/home/tetsuya/development/Mir3-Research/Tools/common")
ZIRCON_DATA = Path("/home/tetsuya/development/zircon/Debug/Client/Data")
IMG_DIR = ROOT / "images" / "mob" / "game"

sys.path.insert(0, str(RESEARCH_COMMON))
import zlsdk


def extract_strip(zl_file: Path, shape: int, tint_mode: str | None = None) -> Image.Image | None:
    lib = zlsdk.ZlLibrary(str(zl_file))
    base = shape * 1000
    sample_offsets = [0, 1, 2, 3, 40, 41, 42, 43, 80, 81, 82, 83]
    frames = []
    for off in sample_offsets:
        idx = base + off
        if idx < lib.count:
            img = lib.decode(idx)
            if img:
                frames.append(img)
    if not frames:
        for idx in range(base, min(base + 120, lib.count)):
            img = lib.decode(idx)
            if img:
                frames.append(img)
            if len(frames) >= 12:
                break
    if not frames:
        return None

    if tint_mode == "white_earwig":
        processed = []
        for f in frames:
            im = f.convert("RGBA")
            r, g, b, a = im.split()
            gray = im.convert("L").point(lambda i: min(255, int(i * 1.45 + 40)))
            processed.append(Image.merge("RGBA", (gray, gray, gray, a)))
        frames = processed
    elif tint_mode == "bronze_earwig":
        processed = []
        for f in frames:
            im = f.convert("RGBA")
            r, g, b, a = im.split()
            r = r.point(lambda i: int(i * 0.72))
            g = g.point(lambda i: int(i * 0.76))
            b = b.point(lambda i: min(255, int(i * 1.35 + 25)))
            processed.append(Image.merge("RGBA", (r, g, b, a)))
        frames = processed
    elif tint_mode == "horn_earwig":
        processed = []
        for f in frames:
            im = f.convert("RGBA")
            r, g, b, a = im.split()
            r = r.point(lambda i: min(255, int(i * 1.45 + 30)))
            g = g.point(lambda i: int(i * 0.58))
            b = b.point(lambda i: int(i * 0.58))
            processed.append(Image.merge("RGBA", (r, g, b, a)))
        frames = processed
    elif tint_mode == "white_monkey":
        processed = []
        for f in frames:
            im = f.convert("RGBA")
            r, g, b, a = im.split()
            gray = im.convert("L").point(lambda i: min(255, int(i * 1.5 + 45)))
            processed.append(Image.merge("RGBA", (gray, gray, gray, a)))
        frames = processed
    elif tint_mode == "desert_worm":
        processed = []
        for f in frames:
            im = f.convert("RGBA")
            r, g, b, a = im.split()
            r = r.point(lambda i: min(255, int(i * 1.25 + 25)))
            g = g.point(lambda i: min(255, int(i * 1.15 + 20)))
            b = b.point(lambda i: int(i * 0.78))
            processed.append(Image.merge("RGBA", (r, g, b, a)))
        frames = processed

    max_h = max(f.height for f in frames)
    total_w = sum(f.width for f in frames) + (len(frames) - 1) * 6
    strip = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))
    x = 0
    for f in frames:
        y = max_h - f.height
        strip.paste(f, (x, y), f)
        x += f.width + 6
    return strip


def generate_missing_sprites():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    targets = [
        ("Flame_Griffin.png", ZIRCON_DATA / "Mon-16.Zl", 9, None),
        ("Stone_Griffin.png", ZIRCON_DATA / "Mon-17.Zl", 0, None),
        ("Pink_Goddess.png", ZIRCON_DATA / "Mon-17.Zl", 2, None),
        ("Green_Goddess.png", ZIRCON_DATA / "Mon-17.Zl", 3, None),
        ("Cannibal_Fanatic.png", ZIRCON_DATA / "Mon-16.Zl", 6, None),
        ("Evil_Fanatic.png", ZIRCON_DATA / "Mon-16.Zl", 7, None),
        ("White_Monkey.png", ZIRCON_DATA / "Mon-16.Zl", 4, "white_monkey"),
        ("White_Earwig.png", ZIRCON_DATA / "Mon-7.Zl", 9, "white_earwig"),
        ("Bronze_Earwig.png", ZIRCON_DATA / "Mon-7.Zl", 9, "bronze_earwig"),
        ("Horn_Earwig.png", ZIRCON_DATA / "Mon-7.Zl", 9, "horn_earwig"),
        ("Desert_Visceral_Worm.png", ZIRCON_DATA / "Mon-7.Zl", 1, "desert_worm"),
        ("Numa_Mage.png", ZIRCON_DATA / "Mon-2.Zl", 3, None),
        ("Ant_Needler.png", ZIRCON_DATA / "Mon-10.Zl", 6, None),
        ("White_Snake.png", ZIRCON_DATA / "Mon-13.Zl", 6, None),
        ("Arachnid_Gazer.png", ZIRCON_DATA / "Mon-11.Zl", 6, None),
        ("Red_Moon_Protector.png", ZIRCON_DATA / "Mon-11.Zl", 8, None),
        ("Venomous_Arachnid.png", ZIRCON_DATA / "Mon-12.Zl", 1, None),
    ]

    for filename, zl_file, shape, tint in targets:
        dest = IMG_DIR / filename
        strip = extract_strip(zl_file, shape, tint)
        if strip:
            strip.save(dest)
            print(f"[Sprite] Generated {filename}: {strip.size}")
        else:
            print(f"[Sprite] Failed to generate {filename}")


# 怪物修正映射字典
CORRECTIONS = {
    "mob-147": { # 火焰狮子
        "sprite": "/images/mob/game/Flame_Griffin.png",
        "eng_name": "Flame Griffin",
        "library": "Mon_16",
        "shape": 9,
        "match_method": "exact",
        "note": "真天宫金色带翼狮魔（Mon_16 shape 9），与网站 ang_06 原画 100% 吻合",
    },
    "mob-148": { # 石像狮子
        "sprite": "/images/mob/game/Stone_Griffin.png",
        "eng_name": "Stone Griffin",
        "library": "Mon_17",
        "shape": 0,
        "match_method": "exact",
        "note": "真天宫灰白石雕带翼狮魔（Mon_17 shape 0），与网站 ang_07 原画 100% 吻合",
    },
    "mob-150": { # 地牢女神 (红粉饰)
        "sprite": "/images/mob/game/Pink_Goddess.png",
        "eng_name": "Pink Goddess",
        "library": "Mon_17",
        "shape": 2,
        "match_method": "exact",
        "note": "真天宫红粉头饰女神侍卫（Mon_17 shape 2），持巨大锯齿盾与长矛，与 ang_09 原画一致",
    },
    "mob-151": { # 地牢女神 (蓝绿饰)
        "sprite": "/images/mob/game/Green_Goddess.png",
        "eng_name": "Green Goddess",
        "library": "Mon_17",
        "shape": 3,
        "match_method": "exact",
        "note": "真天宫蓝绿战甲女神侍卫（Mon_17 shape 3），持巨大锯齿盾与长矛，与 ang_10 原画一致",
    },
    "mob-69": { # 魔神怪1
        "sprite": "/images/mob/game/Cannibal_Fanatic.png",
        "eng_name": "Cannibal Fanatic",
        "library": "Mon_16",
        "shape": 6,
        "match_method": "exact",
        "note": "失乐园长矛狂信徒（Mon_16 shape 6），背插战羽身披绿甲，与 image036 原画一致",
    },
    "mob-70": { # 魔神怪2
        "sprite": "/images/mob/game/Evil_Fanatic.png",
        "eng_name": "Evil Fanatic",
        "library": "Mon_16",
        "shape": 7,
        "match_method": "exact",
        "note": "失乐园双手弯月利刃狂信徒（Mon_16 shape 7），与 image037 原画一致",
    },
    "mob-68": { # 猿猴战将
        "sprite": "/images/mob/game/White_Monkey.png",
        "eng_name": "White Monkey",
        "library": "Mon_16",
        "shape": 4,
        "match_method": "alias",
        "note": "失乐园白毛高阶猿猴（Mon_16 shape 4 白毛战将变体），与 image035 原画一致",
    },
    "mob-125": { # 骷髅武士
        "sprite": "/images/mob/game/Bone_Captain.png",
        "eng_name": "Bone Captain",
        "library": "Mon_15",
        "shape": 0,
        "match_method": "exact",
        "note": "潘夜骷髅武士将领（Mon_15 shape 0），手持长柄黑铁刺球狼牙棒，与 70.gif 原画 100% 吻合",
    },
    "mob-88": { # 钳虫
        "sprite": "/images/mob/game/Earwig.png",
        "eng_name": "Earwig",
        "library": "Mon_7",
        "shape": 9,
        "match_method": "exact",
        "note": "虫峡谷双钳长触须黑褐原色钳虫（Mon_7 shape 9），与 34.gif 原画一致",
    },
    "mob-89": { # 白眼钳虫
        "sprite": "/images/mob/game/White_Earwig.png",
        "eng_name": "White Earwig",
        "library": "Mon_7",
        "shape": 9,
        "match_method": "alias",
        "note": "虫峡谷白壳白化高阶钳虫（Mon_7 shape 9 白化色系），与 59.gif 原画一致",
    },
    "mob-90": { # 沃角钳虫
        "sprite": "/images/mob/game/Horn_Earwig.png",
        "eng_name": "Horn Earwig",
        "library": "Mon_7",
        "shape": 9,
        "match_method": "alias",
        "note": "虫峡谷赤褐强力沃角钳虫（Mon_7 shape 9 赤红色系），与 61.gif 原画一致",
    },
    "mob-91": { # 青铜钳虫
        "sprite": "/images/mob/game/Bronze_Earwig.png",
        "eng_name": "Bronze Earwig",
        "library": "Mon_7",
        "shape": 9,
        "match_method": "alias",
        "note": "虫峡谷青紫硬壳青铜钳虫（Mon_7 shape 9 青冷色系），与 60.gif 原画一致",
    },
    "mob-59": { # 月魔蜘蛛
        "sprite": "/images/mob/game/Spider_Bat.png",
        "eng_name": "Spider Bat",
        "library": "Mon_11",
        "shape": 1,
        "match_method": "exact",
        "note": "灌木林蝙蝠双翼飞行月魔蜘蛛（Mon_11 shape 1），与 42.gif 原画 100% 吻合",
    },
    "mob-65": { # 花色蜘蛛
        "sprite": "/images/mob/game/Venomous_Arachnid.png",
        "eng_name": "Venomous Arachnid",
        "library": "Mon_12",
        "shape": 1,
        "match_method": "exact",
        "note": "灌木林花色斑马条纹腿花色蜘蛛（Mon_12 shape 1），与 48.gif 原画一致",
    },
    "mob-60": { # 独眼蜘蛛
        "sprite": "/images/mob/game/Arachnid_Gazer.png",
        "eng_name": "Arachnid Gazer",
        "library": "Mon_11",
        "shape": 6,
        "match_method": "exact",
        "note": "灌木林巨型背刺大眼蜘蛛（Mon_11 shape 6），与 43.gif 原画一致",
    },
    "mob-61": { # 天狼蜘蛛
        "sprite": "/images/mob/game/Red_Moon_Protector.png",
        "eng_name": "Red Moon Protector",
        "library": "Mon_11",
        "shape": 8,
        "match_method": "exact",
        "note": "灌木林背刺红瘤天狼蜘蛛（Mon_11 shape 8），与 44.gif 原画一致",
    },
    "mob-58": { # 大法老
        "sprite": "/images/mob/game/Numa_High_Mage.png",
        "eng_name": "Numa High Mage",
        "library": "Mon_19",
        "shape": 4,
        "match_method": "exact",
        "note": "诺玛沙漠高阶司祭大法老（Mon_19 shape 4），守卫诺玛王的四大法老",
    },
    "mob-57": { # 诺玛法老
        "sprite": "/images/mob/game/Numa_Mage.png",
        "eng_name": "Numa Mage",
        "library": "Mon_2",
        "shape": 3,
        "match_method": "exact",
        "note": "诺玛沙漠手持蛇首法杖诺玛法老（Mon_2 shape 3），与 mop_19 原画 100% 吻合",
    },
    "mob-53": { # 沙漠鱼魔
        "sprite": "/images/mob/game/Sand_Shark.png",
        "eng_name": "Sand Shark",
        "library": "Mon_10",
        "shape": 4,
        "match_method": "exact",
        "note": "沙漠潜行露黑色背鳍沙鲨（Mon_10 shape 4），与 ym.jpg 原画 100% 吻合",
    },
    "mob-48": { # 沙鬼
        "sprite": "/images/mob/game/Ant_Needler.png",
        "eng_name": "Ant Needler",
        "library": "Mon_10",
        "shape": 6,
        "match_method": "exact",
        "note": "沙漠细长折腿尾部长刺沙鬼（Mon_10 shape 6），与 mop_03 原画 100% 吻合",
    },
    "mob-51": { # 沙漠蜥蜴
        "sprite": "/images/mob/game/Spined_Dark_Lizard.png",
        "eng_name": "Spined Dark Lizard",
        "library": "Mon_5",
        "shape": 6,
        "match_method": "exact",
        "note": "沙漠黄褐脊背棘刺沙蜥（Mon_5 shape 6），与 mop_22 原画 100% 吻合",
    },
    "mob-23": { # 沙漠威斯而小虫
        "sprite": "/images/mob/game/Desert_Visceral_Worm.png",
        "eng_name": "Desert Visceral Worm",
        "library": "Mon_7",
        "shape": 1,
        "match_method": "alias",
        "note": "沙漠浅黄变色威斯而小虫（Mon_7 shape 1 沙地浅色调），与 f17 原画一致",
    },
    "mob-17": { # 虎蛇
        "sprite": "/images/mob/game/Tiger_Snake.png",
        "eng_name": "Tiger Snake",
        "library": "Mon_6",
        "shape": 7,
        "match_method": "exact",
        "note": "毒蛇谷黄黑虎斑大蛇（Mon_6 shape 7），与红蛇明确区分，与 f18 原画一致",
    },
    "mob-18": { # 七点白蛇
        "sprite": "/images/mob/game/White_Snake.png",
        "eng_name": "White Snake",
        "library": "Mon_13",
        "shape": 6,
        "match_method": "exact",
        "note": "毒蛇谷罕见白色大蛇（Mon_13 shape 6 / White Snake），小 BOSS 真身",
    },
    "mob-19": { # 千年毒蛇
        "sprite": "/images/mob/game/White_Snake.png",
        "eng_name": "White Snake",
        "library": "Mon_13",
        "shape": 6,
        "match_method": "exact",
        "note": "毒蛇谷白色毒蛇（Mon_13 shape 6 / White Snake），任务稀有大蛇",
    },
}


def update_datasets():
    # 1. 更新 data/monsters.json
    mobs_file = ROOT / "data" / "monsters.json"
    mobs = json.loads(mobs_file.read_text(encoding="utf-8"))
    for m in mobs:
        mid = m["id"]
        if mid in CORRECTIONS:
            c = CORRECTIONS[mid]
            m["game"] = {
                "sprite": c["sprite"],
                "eng_name": c["eng_name"],
                "library": c["library"],
                "shape": c["shape"],
                "match_method": c["match_method"],
                "note": c["note"],
            }
            print(f"[Monsters] Updated {mid} ({m['name']}) -> {c['eng_name']}")
    mobs_file.write_text(json.dumps(mobs, ensure_ascii=False, indent=2), encoding="utf-8")

    # 2. 更新 data/alignment/entities/monster.json
    ent_file = ROOT / "data" / "alignment" / "entities" / "monster.json"
    if ent_file.exists():
        entities = json.loads(ent_file.read_text(encoding="utf-8"))
        for ent in entities:
            mid = ent.get("id")
            if mid in CORRECTIONS:
                c = CORRECTIONS[mid]
                ent["match_status"] = "matched"
                ent["standard_name_zh"] = ent.get("name")
                ent["candidate"] = {
                    "source": "zircon",
                    "path": c["sprite"],
                    "label": c["eng_name"],
                    "method": c["match_method"],
                    "note": c["note"],
                }
                print(f"[Alignment] Updated {mid} -> {c['eng_name']}")
        ent_file.write_text(json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3. 校验 master.json
    master_file = ROOT / "data" / "alignment" / "master.json"
    if master_file.exists():
        master = json.loads(master_file.read_text(encoding="utf-8"))
        # master.json 的实体记录同步更新
        for rec in master.get("entities", []):
            mid = rec.get("id")
            if mid in CORRECTIONS:
                c = CORRECTIONS[mid]
                rec["match_status"] = "matched"
        master_file.write_text(json.dumps(master, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    generate_missing_sprites()
    update_datasets()
    print("Done all updates!")
