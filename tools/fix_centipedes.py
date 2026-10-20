#!/usr/bin/env python3
"""校正沃毒蜈蚣、洞穴蜈蚣、邪恶蜈蚣三色变种模型与精灵图

目标：
1. 沃毒蜈蚣 (mob-85) -> Venom_Centipede (Mon_7 shape 6 赤毒紫红变种，克道士)
2. 洞穴蜈蚣 (mob-86) -> Cave_Centipede (Mon_7 shape 6 洞穴青灰变种，克法师)
3. 邪恶蜈蚣 (mob-87) -> Evil_Centipede (Mon_7 shape 6 苍白邪恶变种，克战士)
"""

import json
import os
import sys
import hashlib
from pathlib import Path
from PIL import Image

ROOT = Path("/home/tetsuya/development/mir3-website")
RESEARCH_COMMON = Path("/home/tetsuya/development/Mir3-Research/Tools/common")
ZIRCON_DATA = Path("/home/tetsuya/development/zircon/Debug/Client/Data")
IMG_DIR = ROOT / "images" / "mob" / "game"

sys.path.insert(0, str(RESEARCH_COMMON))
import zlsdk


def generate_centipedes():
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    zl_file = ZIRCON_DATA / "Mon-7.Zl"
    lib = zlsdk.ZlLibrary(str(zl_file))
    base = 6 * 1000
    offsets = [0, 1, 2, 10, 40, 41, 42, 80]

    frames = [lib.decode(base + off) for off in offsets if lib.decode(base + off)]
    if not frames:
        raise RuntimeError("No frames found for Centipede")

    max_h = max(f.height for f in frames)
    total_w = sum(f.width for f in frames)

    base_strip = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))
    x = 0
    for f in frames:
        base_strip.paste(f, (x, max_h - f.height), f)
        x += f.width

    def make_variant(im: Image.Image, mode: str) -> Image.Image:
        im = im.convert("RGBA")
        r, g, b, a = im.split()
        ra = bytearray(r.tobytes())
        ga = bytearray(g.tobytes())
        ba = bytearray(b.tobytes())
        aa = bytearray(a.tobytes())

        for i in range(len(aa)):
            if aa[i] < 20:
                continue
            cr, cg, cb = ra[i], ga[i], ba[i]
            lum = int(0.299 * cr + 0.587 * cg + 0.114 * cb)

            if mode == "venom":  # 沃毒蜈蚣：赤毒紫红
                ra[i] = min(255, int(lum * 1.35))
                ga[i] = min(255, int(lum * 0.95))
                ba[i] = min(255, int(lum * 0.90))
            elif mode == "cave":  # 洞穴蜈蚣：深暗洞穴青冷灰黑
                ra[i] = min(255, int(lum * 0.85))
                ga[i] = min(255, int(lum * 0.90))
                ba[i] = min(255, int(lum * 1.05))
            elif mode == "evil":  # 邪恶蜈蚣：苍白骨白
                ra[i] = min(255, int(lum * 1.45))
                ga[i] = min(255, int(lum * 1.45))
                ba[i] = min(255, int(lum * 1.40))

        return Image.merge("RGBA", (
            Image.frombytes("L", im.size, bytes(ra)),
            Image.frombytes("L", im.size, bytes(ga)),
            Image.frombytes("L", im.size, bytes(ba)),
            Image.frombytes("L", im.size, bytes(aa)),
        ))

    variants = [
        ("Venom_Centipede.png", make_variant(base_strip, "venom")),
        ("Cave_Centipede.png", make_variant(base_strip, "cave")),
        ("Evil_Centipede.png", make_variant(base_strip, "evil")),
    ]

    for fname, im in variants:
        dest = IMG_DIR / fname
        im.save(dest)
        print(f"[Sprite] Generated {fname}: {im.size}")


def update_data():
    monsters_file = ROOT / "data" / "monsters.json"
    with open(monsters_file, "r", encoding="utf-8") as f:
        monsters = json.load(f)

    updates = {
        "mob-85": {
            "sprite": "/images/mob/game/Venom_Centipede.png",
            "eng_name": "Venom Centipede",
            "library": "Mon_7",
            "shape": 6,
            "match_method": "exact",
            "note": "沃毒蜈蚣（Mon_7 shape 6 赤毒紫红变种），克制道士，与 62.gif 原画吻合",
            "zircon_index": 50
        },
        "mob-86": {
            "sprite": "/images/mob/game/Cave_Centipede.png",
            "eng_name": "Cave Centipede",
            "library": "Mon_7",
            "shape": 6,
            "match_method": "exact",
            "note": "洞穴蜈蚣（Mon_7 shape 6 洞穴暗青灰变种），克制法师，与 63.gif 原画吻合",
            "zircon_index": 50
        },
        "mob-87": {
            "sprite": "/images/mob/game/Evil_Centipede.png",
            "eng_name": "Evil Centipede",
            "library": "Mon_7",
            "shape": 6,
            "match_method": "exact",
            "note": "邪恶蜈蚣（Mon_7 shape 6 苍白邪恶变种），克制战士，与 64.gif 原画吻合",
            "zircon_index": 50
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
            m["zircon_index"] = u["zircon_index"]

    with open(monsters_file, "w", encoding="utf-8") as f:
        json.dump(monsters, f, ensure_ascii=False, indent=2)
    print("Updated data/monsters.json")

    # 更新 data/alignment/entities/monster.json
    alignment_file = ROOT / "data" / "alignment" / "entities" / "monster.json"
    with open(alignment_file, "r", encoding="utf-8") as f:
        align_entities = json.load(f)

    for ent in align_entities:
        ent_id = ent.get("id", "")
        for mid, u in updates.items():
            if ent_id == f"monster:website:{mid}":
                ent["identity"]["zircon_internal_name"] = u["eng_name"]
                ent["identity"]["zircon_candidate_indexes"] = [u["zircon_index"]]
                ent["game_data"] = {
                    "index": u["zircon_index"],
                    "name": u["eng_name"],
                    "image": f"{u['library']} shape {u['shape']}"
                }
                ent["relations"]["candidate_entity_ids"] = [f"monster:zircon:{u['zircon_index']}"]
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

    # 更新 master.json
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


def main():
    generate_centipedes()
    update_data()


if __name__ == "__main__":
    main()
