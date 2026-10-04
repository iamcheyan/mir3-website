#!/usr/bin/env python3
"""从 Zircon System.db 导出的 maps_export.json 生成网站地图资料数据。

按「D+数字家族」把 627 张地图归组成可读的副本套系（祖玛神殿是一套、
潘夜石窟是一套…），并保留每条连接的两端地图与坐标，供页面标注
「从哪张图怎么走到哪张图」。
"""
import json
import re
import sys
from collections import defaultdict

EXPORT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/maps_export.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "data/maps.json"

# D 家族 -> (中文套系名, 兜底英文名)
# 依据 System.db 实际 Description 归纳；未列出的家族用首个成员的名字。
FAMILY_NAMES = {
    "D00": ("魔界与飞天武术馆", "Magic Realm"),
    "D01": ("天然洞穴", "Natural Cave"),
    "D02": ("沃玛神殿", "Uma Temple"),
    "D10": ("潘夜神殿", "Banya Temple"),
    "D11": ("祖玛神殿", "Zuma Temple"),
    "D12": ("罪孽洞穴", "Sin Cave"),
    "D13": ("黑宫与东部银杏废矿", "Black Palace"),
    "D14": ("幽灵船", "Phantom Ship"),
    "D20": ("比奇废矿与西沙漠", "Deserted Mine"),
    "D21": ("冰原地下", "Ice Field"),
    "D22": ("绝情塔", "Love Tower"),
    "D29": ("练级与 BOSS 集中营", "Training Ground"),
    "D30": ("龙穴", "Dragon Cave"),
    "D35": ("修罗密道与禁地", "Asura"),
    "D37": ("兵马俑", "Terracotta"),
    "D40": ("蚂蚁洞（南部）与尸王房", "Ant Cave South"),
    "D41": ("地下第一层", "Underground L1"),
    "D42": ("矿山", "Mine"),
    "D43": ("北部矿山", "North Mine"),
    "D44": ("北部地下", "North Underground"),
    "D45": ("南部矿山", "South Mine"),
    "D50": ("沃玛神殿（另一线）", "Uma Temple Alt"),
    "D51": ("祖玛教主宫廷", "Zuma King Court"),
    "D60": ("潘夜石窟与万年谷", "Banya Stone Cave"),
    "D61": ("潘夜石窟内层", "Banya Stone Cave Inner"),
    "D71": ("石阁", "Stone Pavilion"),
    "D80": ("绝望谷与南部蚂蚁洞", "Despair Valley"),
    "D81": ("北部蚂蚁洞穴", "Ant Cave North"),
    "D82": ("东部蚂蚁洞穴", "Ant Cave East"),
    "D90": ("神舰与赤月山谷", "Starship"),
}

# 城镇主城（官方 StartPoint.txt 12 座中已登记的 11 座）
TOWN_IDS = ["0", "01", "02", "1", "2", "4", "5", "8", "41", "74", "81"]

TOWN_ZH = {
    "0": "比奇县城", "01": "边境城市", "02": "银杏山谷", "1": "道馆",
    "2": "蛇谷", "4": "盟重土城", "5": "沙漠绿洲", "8": "潘夜岛",
    "41": "诺玛沙漠", "74": "盟重县", "81": "流放岛",
}


def family_of(fn):
    m = re.match(r"^[Dd](\d{3,4})", fn)
    return "D" + m.group(1)[:2] if m else None


def main():
    d = json.load(open(EXPORT, encoding="utf-8-sig"))
    maps = {m["id"]: m for m in d["maps"]}
    links = d["links"]
    zones = {z["map"]: z for z in d["zones"]}

    # 地图 -> 该图的出向连接（附目标与坐标）
    out_links = defaultdict(list)
    in_links = defaultdict(list)
    for l in links:
        out_links[l["from"]].append(l)
        in_links[l["to"]].append(l)

    def decorate(m):
        e = dict(m)
        e["links"] = out_links.get(m["id"], [])
        e["inbound"] = in_links.get(m["id"], [])
        e["linkCount"] = len(e["links"]) + len(e["inbound"])
        z = zones.get(m["id"])
        e["safeZone"] = bool(z)
        if z:
            e["bindPt"] = z["bindPt"]
            e["safeRadius"] = z["regionCount"]
        return e

    groups = []

    # 1) 城镇主城
    town_items = [decorate(maps[i]) for i in TOWN_IDS if i in maps]
    for t in town_items:
        t["nameZh"] = TOWN_ZH.get(t["id"], t["name"])
    groups.append({"id": "towns", "name": "城镇主城", "desc": "玩家主城与安全区，回城/复活点", "items": town_items})

    # 2) 城镇附属（0_ / 1_ / 02_ 等城内建筑与副图）
    sub_items = [decorate(m) for m in maps.values() if not family_of(m["id"]) and m["id"] not in TOWN_IDS
                 and re.match(r"^\d+_", m["id"])]
    if sub_items:
        sub_items.sort(key=lambda x: x["id"])
        groups.append({"id": "town-sub", "name": "城镇附属", "desc": "城内建筑、行会区域与城镇子图", "items": sub_items})

    # 3) 地下城/洞窟：按 D 家族成套
    fam = defaultdict(list)
    for fn in maps:
        f = family_of(fn)
        if f:
            fam[f].append(decorate(maps[fn]))
    dungeon_groups = []
    for f, items in sorted(fam.items(), key=lambda kv: -len(kv[1])):
        zh, en = FAMILY_NAMES.get(f, (items[0]["name"], f))
        items.sort(key=lambda x: x["id"])
        dungeon_groups.append({
            "id": f.lower(), "code": f, "name": zh, "nameEn": en,
            "desc": f"{items[0]['name']} 等 {len(items)} 张地图组成的成套副本",
            "items": items,
        })
    groups.append({"id": "dungeons", "name": "地下城与洞窟（按副本成套）",
                   "desc": "每套副本内部逐层连通，层间通道见各地图连接点", "suites": dungeon_groups})

    # 4) 特殊/其他
    special = [decorate(m) for m in maps.values()
               if not family_of(m["id"]) and m["id"] not in TOWN_IDS
               and not re.match(r"^\d+_", m["id"])]
    special.sort(key=lambda x: x["id"])
    if special:
        groups.append({"id": "special", "name": "特殊地图", "desc": "副本、活动与未归类地图", "items": special})

    total = sum(len(g.get("items", [])) for g in groups) + \
        sum(len(s["items"]) for g in groups if "suites" in g for s in g["suites"])

    out = {
        "id": "map-index",
        "title": "全服地图与连接点",
        "category": "地图",
        "exportedAt": d.get("exportedAt", ""),
        "stats": {
            "maps": d["mapCount"],
            "links": d["linkCount"],
            "safeZones": d["zoneCount"],
            "suites": len(dungeon_groups),
        },
        "groups": groups,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"写出 {OUT}: 地图 {total} / 套系 {len(dungeon_groups)} / 分组 {len(groups)}")
    for g in groups:
        if "suites" in g:
            print(f"  {g['name']}: {len(g['suites'])} 套 "
                  f"({sum(len(s['items']) for s in g['suites'])} 张)")
        else:
            print(f"  {g['name']}: {len(g['items'])} 张")


if __name__ == "__main__":
    main()
