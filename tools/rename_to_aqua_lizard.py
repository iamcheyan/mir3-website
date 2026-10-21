#!/usr/bin/env python3
"""将恶性怪统一重命名为水蜥蜴：

1. data/monsters.json: mob-139 name 改为 水蜥蜴，game note 同步
2. data/maps.json: mob-139 / 恶性怪 刷新记录更新为 水蜥蜴 (Aqua Lizard)
3. data/map_viewer_data.json: 同步更新为 水蜥蜴 (Aqua Lizard)
4. data/alignment/entities/monster.json:
   - monster:website:mob-139 standard_name_zh / website_name 改为 水蜥蜴
   - monster:zircon:106, 375 的 candidate_website_names 中的 恶性怪 改为 水蜥蜴
5. data/alignment/research_findings.json: web-audit:monster:141 的 website_name 改为 水蜥蜴
6. data/alignment/master.json: 重新计算各 shard 的 sha256 与 count
"""

import json
import hashlib
from pathlib import Path

ROOT = Path("/home/tetsuya/development/mir3-website")


def update_spawns(spawns: list):
    for sp in spawns:
        if isinstance(sp, dict):
            if sp.get("webId") == "mob-139" or sp.get("name") == "恶性怪":
                sp["name"] = "水蜥蜴"
                sp["nameEn"] = "Aqua Lizard"


def main():
    # 1. 更新 data/monsters.json
    monsters_path = ROOT / "data" / "monsters.json"
    with open(monsters_path, "r", encoding="utf-8") as f:
        monsters = json.load(f)

    for m in monsters:
        if m.get("id") == "mob-139":
            m["name"] = "水蜥蜴"
            if "game" in m:
                m["game"]["eng_name"] = "Aqua Lizard"
                m["game"]["note"] = "Mon-10 shape 2 水蜥蜴真身（头顶白尖刺绿色双足长爪蜥魔），与 image026.gif 原画 100% 吻合"
            print("Updated data/monsters.json: mob-139 -> 水蜥蜴")
            break

    with open(monsters_path, "w", encoding="utf-8") as f:
        json.dump(monsters, f, ensure_ascii=False, indent=2)

    # 2. 更新 data/maps.json
    maps_path = ROOT / "data" / "maps.json"
    with open(maps_path, "r", encoding="utf-8") as f:
        maps_data = json.load(f)

    def scan_maps(obj):
        if isinstance(obj, dict):
            if "spawns" in obj and isinstance(obj["spawns"], list):
                update_spawns(obj["spawns"])
            for v in obj.values():
                scan_maps(v)
        elif isinstance(obj, list):
            for item in obj:
                scan_maps(item)

    scan_maps(maps_data)
    with open(maps_path, "w", encoding="utf-8") as f:
        json.dump(maps_data, f, ensure_ascii=False, indent=1)
    print("Updated data/maps.json spawns")

    # 3. 更新 data/map_viewer_data.json
    mv_path = ROOT / "data" / "map_viewer_data.json"
    if mv_path.exists():
        with open(mv_path, "r", encoding="utf-8") as f:
            mv_data = json.load(f)
        scan_maps(mv_data)
        with open(mv_path, "w", encoding="utf-8") as f:
            json.dump(mv_data, f, ensure_ascii=False)
        print("Updated data/map_viewer_data.json spawns")

    # 4. 更新 data/alignment/entities/monster.json
    monster_entities_path = ROOT / "data" / "alignment" / "entities" / "monster.json"
    with open(monster_entities_path, "r", encoding="utf-8") as f:
        entities = json.load(f)

    for item in entities:
        eid = item.get("id")
        if eid == "monster:website:mob-139":
            item["identity"]["standard_name_zh"] = "水蜥蜴"
            item["identity"]["website_name"] = "水蜥蜴"
            item["identity"]["zircon_internal_name"] = "Aqua Lizard"
            item["identity"]["zircon_candidate_indexes"] = [156]
            item["game_data"] = {
                "image": "Mon_10 shape 2",
                "index": 156,
                "name": "Aqua Lizard"
            }
            item["relations"] = {
                "candidate_entity_ids": ["monster:zircon:156"]
            }
            item["resources"]["zircon"] = {
                "path": "/images/mob/game/Aqua_Lizard.png",
                "verification": "verified-by-image"
            }
            if "assessment" in item and isinstance(item["assessment"], dict):
                item["assessment"]["reason"] = "Mon-10 shape 2 水蜥蜴真身（头顶白尖刺绿色双足长爪蜥魔），与 image026.gif 原画 100% 吻合"
        elif eid in ["monster:zircon:106", "monster:zircon:375"]:
            candidates = item.get("identity", {}).get("candidate_website_names", [])
            for cand in candidates:
                if cand.get("source_id") == "mob-139":
                    cand["name"] = "水蜥蜴"
                    cand["standard_name_zh"] = "水蜥蜴"

    with open(monster_entities_path, "w", encoding="utf-8") as f:
        json.dump(entities, f, ensure_ascii=False, indent=2)
    print("Updated data/alignment/entities/monster.json")

    # 5. 更新 data/alignment/research_findings.json
    rf_path = ROOT / "data" / "alignment" / "research_findings.json"
    with open(rf_path, "r", encoding="utf-8") as f:
        rf = json.load(f)

    for item in rf:
        if item.get("id") == "web-audit:monster:141" or item.get("source_record_id") == "website:mob-139":
            item["website_name"] = "水蜥蜴"
            item["zircon_index"] = 156
            item["zircon_internal_name"] = "Aqua Lizard"
            print("Updated research_findings item for mob-139 -> 水蜥蜴")

    with open(rf_path, "w", encoding="utf-8") as f:
        json.dump(rf, f, ensure_ascii=False, indent=2)

    # 6. 更新 data/alignment/master.json shards sha256 & count
    master_path = ROOT / "data" / "alignment" / "master.json"
    with open(master_path, "r", encoding="utf-8") as f:
        master = json.load(f)

    with open(monster_entities_path, "rb") as f:
        monster_sha = hashlib.sha256(f.read()).hexdigest()

    with open(rf_path, "rb") as f:
        rf_sha = hashlib.sha256(f.read()).hexdigest()

    for shard in master.get("shards", {}).get("entities", []):
        if shard.get("path") == "entities/monster.json":
            shard["sha256"] = monster_sha
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
