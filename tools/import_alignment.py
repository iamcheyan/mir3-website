#!/usr/bin/env python3
"""Build a sanitized, versioned alignment master from the current local snapshots."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlsplit
import ipaddress

ROOT = Path(__file__).resolve().parents[1]
DB_SECTIONS = {
    "monster": ("MonsterInfo", "MonsterName", "monsters"),
    "item": ("ItemInfo", "ItemName", "items"),
    "skill": ("MagicInfo", "Name", "magics"),
    "npc": ("NPCInfo", "NPCName", "npcs"),
    "map": ("MapInfo", "Description", "maps"),
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def commit(repo: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def ref(source_id: str, record: str, field: str | None = None) -> dict:
    out = {"source_id": source_id, "record": record}
    if field:
        out["field"] = field
    return out


def public_url(value: str) -> str | None:
    try:
        parsed = urlsplit(value.strip())
        host = parsed.hostname
        parsed.port
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        return None
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and not address.is_global:
        return None
    if not address and (host.casefold() in {"localhost", "localhost.localdomain"} or host.casefold().endswith((".local", ".lan", ".internal", ".home"))):
        return None
    if parsed.query and re.search(r"token|secret|key|password|auth", parsed.query, re.I):
        return None
    return value.strip()
def safe_filename(value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    return Path(value).name if Path(value).is_absolute() else value


def web_image(image: str | dict | None, evidence: dict | None) -> dict | None:
    if isinstance(image, dict):
        evidence = image
        image = image.get("path")
    if not image:
        return None
    raw_path = Path(image)
    if raw_path.is_absolute():
        try:
            path = raw_path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            path = None
    else:
        path = image.removeprefix("../")
    result = {"path": path}
    file = ROOT / path if path else None
    if file and file.is_file():
        result.update({"exists": True, "bytes": file.stat().st_size, "sha256": sha256(file)})
    else:
        result["exists"] = bool(evidence and evidence.get("present"))
    if evidence:
        for key in ("width", "height", "format", "frames", "mode"):
            if evidence.get(key) is not None:
                result[key] = evidence[key]
    return result


def candidate_summary(candidate: dict) -> dict:
    resource = candidate.get("resource") or {}
    out = {
        "zircon_index": candidate.get("index"),
        "internal_name": candidate.get("internal_name") or candidate.get("name"),
        "resource_name": candidate.get("image"),
        "shape": candidate.get("shape"),
    }
    if resource:
        out["resource_evidence"] = {
            k: resource[k] for k in ("status", "library", "library_number", "shape", "nonblank_probe_frames_0_99", "body_frame_formula") if k in resource
        }
        frames = resource.get("sample_frames") or []
        if frames:
            out["resource_evidence"]["sample_frames"] = [
                {k: frame[k] for k in ("draw_frame", "index", "width", "height", "offsetX", "offsetY") if k in frame}
                for frame in frames[:8]
            ]
    return {k: v for k, v in out.items() if v is not None}


def assessment(status: str = "pending_review", reason: str = "未完成人工复核；来源事实保留，不自动修正。") -> dict:
    pending = {"status": "pending_review", "reason": reason}
    return {
        "overall_status": status,
        "fields": {
            "identity_mapping": dict(pending),
            "display_name": dict(pending),
            "resource_identity": {"status": "pending_evidence", "reason": "资源身份必须由可视/索引证据确认。"},
            "game_data": dict(pending),
            "relations": dict(pending),
        },
        "reason": reason,
        "reviewer": None,
        "reviewed_at": None,
        "suggested_action": "人工复核；保持当前游戏翻译与实体索引不变。",
        "export_enabled": False,
    }


def compact_row(row: dict, excluded: set[str]) -> dict:
    """Retain source-backed scalar/structured game fields, not redundant reverse lists."""
    return {k: v for k, v in row.items() if k not in excluded and k != "_Identity"}


def source_entry(source_id: str, path: Path, relative: str, repository: str, revision: str, version: str | None = None) -> dict:
    return {
        "source_id": source_id,
        "repository": repository,
        "path": relative,
        "revision": revision,
        "version": version,
        "sha256": sha256(path),
    }


def build(args) -> dict:
    research = args.research.resolve()
    export = args.system_snapshot.resolve()
    root = ROOT
    research_commit = commit(research)
    zircon_commit = commit(args.zircon.resolve())
    website_commit = commit(root)
    research_base = research / "docs/research/ei-ui-layout/artifacts"
    align_base = research_base / "website-alignment-2026-09-26"
    web_base = research_base / "web-entity-audit-2026-09-26"
    old_base = research_base / "npc-monster-alignment-2026-09-25"
    db_names_path = args.db_names.resolve()
    translations = read_json(db_names_path)
    records: dict[str, dict] = {}
    by_type_index: dict[tuple[str, int], dict] = {}
    by_site_id: dict[tuple[str, str], dict] = {}
    used_website_sources: set[tuple[str, str]] = set()
    provenance = []

    def add_provenance(source_id: str, path: Path, repo: str, revision: str, relative: str, version: str | None = None):
        provenance.append(source_entry(source_id, path, relative, repo, revision, version))

    # Commit-pinned, hashed source files. Source paths are repository-relative only.
    site_inputs = ["data/monsters.json", "data/items.json", "data/skills.json", "data/maps.json", "data/missions.json"]
    for rel in site_inputs:
        add_provenance("website-data", root / rel, "iamcheyan/mir3-website", website_commit, rel)
    add_provenance("game-translations", db_names_path, "iamcheyan/Zircon", zircon_commit, "GodotClient/translations/db_names.json")
    research_inputs = [
        ("website-alignment-manifest", "website-alignment-2026-09-26/manifest.json"),
        ("website-alignment-production-targets", "website-alignment-2026-09-26/final-production-targets-20260926.json"),
        ("website-alignment-production-evidence", "website-alignment-2026-09-26/production-apply-evidence-20260926.json"),
        ("website-alignment-verification", "website-alignment-2026-09-26/verification.json"),
        ("website-alignment-extension", "website-alignment-2026-09-26/extension-manifest.json"),
        ("website-alignment-extension-verification", "website-alignment-2026-09-26/extension-verification.json"),
        ("website-alignment-item", "website-alignment-2026-09-26/item-manifest.json"),
        ("website-alignment-skill-detail", "website-alignment-2026-09-26/skill-detail-manifest.json"),
        ("website-alignment-map-ecology", "website-alignment-2026-09-26/map-ecology-manifest.json"),
        ("website-alignment-mission-crossref", "website-alignment-2026-09-26/mission-cross-reference.json"),
        ("website-alignment-npc", "website-alignment-2026-09-26/npc-manifest.json"),
        ("website-alignment-respawn", "website-alignment-2026-09-26/respawn-manifest.json"),
        ("website-alignment-map-family", "website-alignment-2026-09-26/map-family-manifest.json"),
        ("web-audit-summary", "web-entity-audit-2026-09-26/audit_summary.json"),
        ("web-audit-verification", "web-entity-audit-2026-09-26/verification.json"),
        ("web-audit-sources", "web-entity-audit-2026-09-26/external_sources.json"),
        ("web-audit-queries", "web-entity-audit-2026-09-26/search_queries.json"),
        ("web-audit-ledger", "web-entity-audit-2026-09-26/audit_ledger.tsv"),
        ("npc-monster-2025", "npc-monster-alignment-2026-09-25/manifest.json"),
        ("npc-monster-2025-plan", "npc-monster-alignment-2026-09-25/approved-offline-plan.json"),
        ("npc-monster-2025-review", "npc-monster-alignment-2026-09-25/manual-review-summary.json"),
        ("npc-monster-2025-production-history", "npc-monster-alignment-2026-09-25/production-respawn-apply.json"),
    ]
    for source_id, rel in research_inputs:
        add_provenance(source_id, research_base / rel, "iamcheyan/Mir3-Research", research_commit,
                       f"docs/research/ei-ui-layout/artifacts/{rel}")

    # Read live SystemDbProbe output generated read-only from System.db.
    raw_tables = {p.stem: read_json(p)["rows"] for p in export.glob("*.json") if p.name != "meta.json"}
    counts = {name: len(rows) for name, rows in raw_tables.items()}
    info_rows = raw_tables.get("SystemDatabaseInfo", [])
    db_version = str(info_rows[0].get("Version", "unknown")) if info_rows else "unknown"
    for table, rows in raw_tables.items():
        p = export / f"{table}.json"
        add_provenance(f"zircon-table-{table}", p, "read-only SystemDbProbe export", zircon_commit,
                       f"system-db-export/{table}.json", db_version)

    # Load web source entities and current Zircon entity records.
    alignment = read_json(align_base / "manifest.json")
    extension = read_json(align_base / "extension-manifest.json")
    website_data = {name: read_json(root / f"data/{name}.json") for name in ("monsters", "items", "skills", "maps", "missions")}
    npc_alignment_rows = read_json(align_base / "npc-manifest.json")
    respawn_alignment_rows = read_json(align_base / "respawn-manifest.json")
    map_family_rows = read_json(align_base / "map-family-manifest.json")
    map_ecology = read_json(align_base / "map-ecology-manifest.json")
    item_alignment_rows = read_json(align_base / "item-manifest.json")
    skill_detail_rows = read_json(align_base / "skill-detail-manifest.json")
    mission_crossrefs = read_json(align_base / "mission-cross-reference.json")

    def game_record(entity_type: str, row: dict) -> dict:
        index = int(row["Index"])
        table, name_key, trans_section = DB_SECTIONS[entity_type]
        internal_name = str(row.get(name_key, ""))
        current = translations.get(trans_section, {}).get(internal_name, {})
        current_zh = current.get("zh") if isinstance(current, dict) else None
        current_ja = current.get("ja") if isinstance(current, dict) else None
        display = current_zh if isinstance(current_zh, str) and current_zh.strip() else internal_name
        identifier = f"{entity_type}:zircon:{index}"
        excluded = {
            "Respawns", "Drops", "MonsterInfoStats", "Regions", "Guards", "SafeZones", "NPCs",
            "NPCs", "StartQuests", "FinishQuests", "Requirements", "Rewards", "Tasks", "DropItems",
        }
        rec = {
            "id": identifier,
            "entity_type": entity_type,
            "identity": {
                "entity_type": entity_type,
                "zircon_index": index,
                "zircon_internal_name": internal_name,
                "current_game_name": display,
                "current_translation": {k: v for k, v in {"zh": current_zh, "ja": current_ja}.items() if isinstance(v, str)},
                "website_source_id": None,
                "website_source_ids": [],
                "website_name": None,
                "standard_name_zh": None,
                "standard_name_ja": None,
                "candidate_website_names": [],
                "aliases": [],
                "version": db_version,
            },
            "resources": {
                "website": None,
                "zircon": {
                    "resource_name": row.get("Image") or row.get("Icon"),
                    "library": None,
                    "shape": row.get("Shape"),
                    "frame": row.get("Image") if entity_type == "item" else row.get("Icon"),
                    "face": row.get("FaceImage"),
                    "icon": row.get("Icon"),
                    "exists": None,
                    "verification": "not-verified-by-resource-probe",
                    "evidence_refs": [],
                },
            },
            "game_data": compact_row(row, excluded | {name_key, "Index", "_Identity"}),
            "relations": {
                "map_region_ids": [], "respawn_ids": [], "drop_ids": [], "quest_ids": [],
                "store_entry_ids": [], "conflict_counterparts": [],
            },
            "assessment": assessment(),
            "evidence": [ref(f"zircon-table-{table}", f"{table}.Index={index}")],
            "source_findings": [],
        }
        records[identifier] = rec
        by_type_index[(entity_type, index)] = rec
        return rec

    for entity_type, (table, _, _) in DB_SECTIONS.items():
        for row in raw_tables.get(table, []):
            game_record(entity_type, row)

    # Full Index-keyed relation tables. Their endpoints never resolve by name alone.
    map_regions = raw_tables.get("MapRegion", [])
    region_by_index = {int(row["Index"]): row for row in map_regions}
    map_by_index = {int(row["Index"]): row for row in raw_tables.get("MapInfo", [])}
    npc_by_index = {int(row["Index"]): row for row in raw_tables.get("NPCInfo", [])}
    quest_by_index = {int(row["Index"]): row for row in raw_tables.get("QuestInfo", [])}
    monster_by_index = {int(row["Index"]): row for row in raw_tables.get("MonsterInfo", [])}
    item_by_index = {int(row["Index"]): row for row in raw_tables.get("ItemInfo", [])}
    for row in map_regions:
        idx = int(row["Index"]); map_ref = row.get("Map") or {}; map_idx = map_ref.get("Index")
        pt = row.get("PointRegion") or {}
        ident = f"map_region:zircon:{idx}"
        records[ident] = {
            "id": ident, "entity_type": "map_region",
            "identity": {"entity_type": "map_region", "zircon_index": idx, "zircon_internal_name": row.get("Description"), "current_game_name": None, "website_source_id": None, "website_source_ids": [], "website_name": None, "standard_name_zh": None, "standard_name_ja": None, "candidate_website_names": [], "aliases": [], "version": db_version},
            "resources": {"website": None, "zircon": {"resource_name": None, "library": None, "shape": None, "frame": None, "face": None, "icon": None, "exists": None, "verification": "not-applicable", "evidence_refs": []}},
            "game_data": {k: v for k, v in row.items() if k not in {"Index", "_Identity", "Map", "PointRegion"}},
            "relations": {"map_id": f"map:zircon:{map_idx}" if map_idx is not None else None, "npc_ids": [], "respawn_ids": [], "conflict_counterparts": []},
            "assessment": assessment(), "evidence": [ref("zircon-table-MapRegion", f"MapRegion.Index={idx}")], "source_findings": [],
        }
    for table, kind, source_field in (("RespawnInfo", "respawn", "Monster"), ("DropInfo", "drop", "Monster")):
        for row in raw_tables.get(table, []):
            idx = int(row["Index"]); monster_ref = row.get("Monster") or {}; monster_idx = monster_ref.get("Index")
            ident = f"{kind}:zircon:{idx}"
            if kind == "respawn":
                region_ref = row.get("Region") or {}; region_idx = region_ref.get("Index")
                rels = {"monster_id": f"monster:zircon:{monster_idx}" if monster_idx is not None else None,
                        "map_region_id": f"map_region:zircon:{region_idx}" if region_idx is not None else None,
                        "map_id": None, "drop_ids": [], "conflict_counterparts": []}
                if region_idx in region_by_index:
                    map_idx = (region_by_index[region_idx].get("Map") or {}).get("Index")
                    rels["map_id"] = f"map:zircon:{map_idx}" if map_idx is not None else None
                game_fields = {k: v for k, v in row.items() if k not in {"Index", "_Identity", "Monster", "Region"}}
                type_label = "respawn"
            else:
                item_ref = row.get("Item") or {}; item_idx = item_ref.get("Index")
                rels = {"monster_id": f"monster:zircon:{monster_idx}" if monster_idx is not None else None,
                        "item_id": f"item:zircon:{item_idx}" if item_idx is not None else None,
                        "conflict_counterparts": []}
                game_fields = {k: v for k, v in row.items() if k not in {"Index", "_Identity", "Monster", "Item"}}
                type_label = "drop"
            records[ident] = {
                "id": ident, "entity_type": type_label,
                "identity": {"entity_type": type_label, "zircon_index": idx, "zircon_internal_name": row.get("_Identity"), "current_game_name": None, "website_source_id": None, "website_source_ids": [], "website_name": None, "standard_name_zh": None, "standard_name_ja": None, "candidate_website_names": [], "aliases": [], "version": db_version},
                "resources": {"website": None, "zircon": {"resource_name": None, "library": None, "shape": None, "frame": None, "face": None, "icon": None, "exists": None, "verification": "not-applicable", "evidence_refs": []}},
                "game_data": game_fields, "relations": rels, "assessment": assessment(),
                "evidence": [ref(f"zircon-table-{table}", f"{table}.Index={idx}")], "source_findings": [],
            }
            if kind == "respawn" and monster_idx in by_type_index:
                by_type_index[("monster", int(monster_idx))]["relations"]["respawn_ids"].append(ident)
            if kind == "drop" and monster_idx in by_type_index:
                by_type_index[("monster", int(monster_idx))]["relations"]["drop_ids"].append(ident)
            if kind == "drop" and item_idx in by_type_index:
                by_type_index[("item", int(item_idx))]["relations"]["drop_ids"].append(ident)
            if kind == "respawn" and region_idx in records:
                records[f"map_region:zircon:{region_idx}"]["relations"]["respawn_ids"].append(ident)
    for row in raw_tables.get("NPCInfo", []):
        idx = int(row["Index"]); region_idx = (row.get("Region") or {}).get("Index")
        rec = by_type_index[("npc", idx)]
        if region_idx is not None:
            rec["relations"]["map_region_ids"].append(f"map_region:zircon:{region_idx}")
            region = records.get(f"map_region:zircon:{region_idx}")
            if region:
                region["relations"]["npc_ids"].append(rec["id"])
        for q in row.get("StartQuests", []) + row.get("FinishQuests", []):
            qid = f"quest:zircon:{q.get('Index')}"
            if qid in records and qid not in rec["relations"]["quest_ids"]:
                rec["relations"]["quest_ids"].append(qid)
    # Quest definitions/tasks/rewards remain separate, typed records with Index references.
    for row in raw_tables.get("QuestInfo", []):
        idx = int(row["Index"]); ident = f"quest:zircon:{idx}"
        rels = {"npc_ids": [], "item_ids": [], "monster_ids": [], "task_ids": [], "reward_ids": [], "requirement_ids": [], "conflict_counterparts": []}
        for key in ("StartNPC", "FinishNPC"):
            target = (row.get(key) or {}).get("Index")
            if target is not None: rels["npc_ids"].append(f"npc:zircon:{target}")
        for field, relation, prefix in (
            ("Requirements", "requirement_ids", "quest_requirement"),
            ("Rewards", "reward_ids", "quest_reward"),
            ("Tasks", "task_ids", "quest_task"),
        ):
            for item in row.get(field, []) or []:
                rels[relation].append(f"{prefix}:zircon:{item.get('Index')}")
        records[ident] = {
            "id": ident, "entity_type": "quest", "identity": {"entity_type": "quest", "zircon_index": idx, "zircon_internal_name": row.get("QuestName"), "current_game_name": None, "website_source_id": None, "website_source_ids": [], "website_name": None, "standard_name_zh": None, "standard_name_ja": None, "candidate_website_names": [], "aliases": [], "version": db_version},
            "resources": {"website": None, "zircon": {"resource_name": None, "library": None, "shape": None, "frame": None, "face": None, "icon": None, "exists": None, "verification": "not-applicable", "evidence_refs": []}},
            "game_data": {k: v for k, v in row.items() if k not in {"Index", "_Identity", "StartNPC", "FinishNPC", "Tasks", "Rewards", "Requirements"}},
            "relations": rels, "assessment": assessment(), "evidence": [ref("zircon-table-QuestInfo", f"QuestInfo.Index={idx}")], "source_findings": [],
        }
    table_kinds = {
        "QuestTask": "quest_task", "QuestReward": "quest_reward",
        "QuestRequirement": "quest_requirement", "QuestTaskMonsterDetails": "quest_task_monster_detail",
        "NPCGood": "store_entry", "StoreInfo": "store_item",
    }
    for table, kind in table_kinds.items():
        for row in raw_tables.get(table, []):
            idx = int(row["Index"])
            ident = f"{kind}:zircon:{idx}"
            rels = {"conflict_counterparts": []}
            relation_fields = [("Quest", "quest_id", "quest"), ("Item", "item_id", "item"), ("Monster", "monster_id", "monster")]
            if table == "QuestTaskMonsterDetails":
                relation_fields.append(("Task", "task_id", "quest_task"))
            for field, target, prefix in relation_fields:
                value = row.get(field)
                idx_ref = value.get("Index") if isinstance(value, dict) else None
                if idx_ref is not None:
                    rels[target] = f"{prefix}:zircon:{idx_ref}"
            if table == "NPCGood":
                rels["shop_page_id"] = (row.get("Page") or {}).get("Index")
            exclusions = {"Index", "_Identity", "Quest", "Item", "Page", "Monster", "MonsterDetails"}
            if table == "QuestTaskMonsterDetails":
                exclusions.add("Task")
            records[ident] = {
                "id": ident, "entity_type": kind,
                "identity": {"entity_type": kind, "zircon_index": idx, "zircon_internal_name": row.get("_Identity") or row.get("GoodsIndex")},
                "resources": {"website": None, "zircon": {"resource_name": None, "library": None, "shape": None, "frame": None, "face": None, "icon": None, "exists": None, "verification": "not-applicable", "evidence_refs": []}},
                "game_data": {k: v for k, v in row.items() if k not in exclusions},
                "relations": rels, "assessment": assessment(),
                "evidence": [ref(f"zircon-table-{table}", f"{table}.Index={idx}")],
                "source_findings": [],
            }
            quest_id = rels.get("quest_id")
            if kind in {"quest_task", "quest_reward", "quest_requirement"} and quest_id in records:
                relation_key = {"quest_task": "task_ids", "quest_reward": "reward_ids", "quest_requirement": "requirement_ids"}[kind]
                records[quest_id]["relations"][relation_key].append(ident)
            task_id = rels.get("task_id")
            if kind == "quest_task_monster_detail" and task_id in records:
                records[task_id]["relations"].setdefault("monster_detail_ids", []).append(ident)
                monster_id = rels.get("monster_id")
                if monster_id in records:
                    records[task_id]["relations"].setdefault("monster_ids", []).append(monster_id)
            if kind == "store_entry" and rels.get("item_id") in records:
                records[rels["item_id"]]["relations"].setdefault("store_entry_ids", []).append(ident)

    # Explicit website monster/skill identity research; status is evidence, never export approval.
    web_rows = {}
    for row in alignment.get("monster_identity", []):
        web_rows[("monster", row["website_monster_id"])] = row
    for row in alignment.get("skills", []):
        web_rows[("skill", row["website_skill_id"])] = row
    for row in extension.get("items", []):
        key = (row.get("website_name", ""), row.get("website_category", ""))
        web_rows.setdefault(("item_name", "\u0000".join(key)), row)

    def attach_website(entity_type: str, source_id: str, source_name: str, category: str, image: str | None, image_evidence: dict | None,
                       candidate_indexes: list[int], evidence_ref: dict, source_status: str, match_internal_names: dict[int, str] | None = None):
        source_key = (entity_type, source_id)
        candidates = sorted(set(int(x) for x in candidate_indexes if x is not None))
        valid = []
        for idx in candidates:
            rec = by_type_index.get((entity_type, idx))
            candidate_name = (match_internal_names or {}).get(idx)
            if rec and (not candidate_name or rec["identity"]["zircon_internal_name"] == candidate_name):
                valid.append(rec)
        is_single_source_confirmed = source_status in {"confirmed", "confirmed-name"} and len(valid) == 1 and len(candidates) == 1
        site = {"source_id": source_id, "name": source_name, "standard_name_zh": source_name, "category": category,
                "image": web_image(image, image_evidence), "source_status": source_status, "source_ref": evidence_ref,
                "candidate_indexes": candidates}
        if is_single_source_confirmed:
            rec = valid[0]
            rec["identity"]["website_source_ids"].append(source_id)
            rec["identity"]["candidate_website_names"].append({
                key: site[key] for key in ("source_id", "name", "source_status", "candidate_indexes")
            })
            if len(rec["identity"]["website_source_ids"]) == 1:
                rec["identity"]["website_source_id"] = source_id
                rec["identity"]["website_name"] = source_name
                rec["identity"]["standard_name_zh"] = source_name
            elif rec["identity"]["website_name"] != source_name:
                rec["identity"]["standard_name_zh"] = None
                rec["assessment"]["overall_status"] = "conflict"
            rec["resources"]["website"] = site["image"]
            rec["evidence"].append(evidence_ref)
            rec["assessment"]["fields"]["identity_mapping"] = {"status": "source_confirmed", "reason": f"来源状态 {source_status}，Index 与内部名在当前 Zircon 快照逐项相符；尚非翻译导出批准。"}
            current = rec["identity"].get("current_game_name")
            if current and current != source_name:
                rec["assessment"]["fields"]["display_name"] = {"status": "conflict", "reason": "网站标准名与当前中文显示值不同；除明确标记的冲突示例外，不将不同自动判为错误。"}
            used_website_sources.add(source_key)
            by_site_id[source_key] = rec
            return rec
        ident = f"{entity_type}:website:{source_id}"
        status = "conflict" if len(candidates) > 1 else "pending_review"
        rec = {
            "id": ident, "entity_type": entity_type,
            "identity": {"entity_type": entity_type, "zircon_index": None, "zircon_internal_name": None,
                         "current_game_name": None, "website_source_id": source_id, "website_source_ids": [source_id],
                         "website_name": source_name, "standard_name_zh": source_name, "standard_name_ja": None,
                         "candidate_website_names": [], "zircon_candidate_indexes": candidates, "aliases": [],
                         "version": "website-source"},
            "resources": {"website": site["image"], "zircon": {"resource_name": None, "library": None, "shape": None, "frame": None, "face": None, "icon": None, "exists": None, "verification": "pending", "evidence_refs": []}},
            "game_data": {},
            "relations": {"candidate_entity_ids": [f"{entity_type}:zircon:{x}" for x in candidates], "map_region_ids": [], "respawn_ids": [], "drop_ids": [], "quest_ids": [], "store_entry_ids": [], "conflict_counterparts": []},
            "assessment": assessment(status, "来源没有唯一闭合到当前 Zircon Index；保留候选并等待人工复核。"),
            "evidence": [evidence_ref], "source_findings": [],
        }
        records[ident] = rec
        by_site_id[source_key] = rec
        used_website_sources.add(source_key)
        for candidate in candidates:
            target = by_type_index.get((entity_type, candidate))
            if target:
                target["identity"]["candidate_website_names"].append(site)
                target["relations"]["conflict_counterparts"].append(ident)
        return rec

    # Monsters: status and candidate identity come from the dated detailed alignment manifest.
    for row in alignment.get("monster_identity", []):
        source_id = row["website_monster_id"]
        website = next((r for r in website_data["monsters"] if r.get("id") == source_id), {})
        candidates = row.get("zircon_candidates", [])
        attach_website("monster", source_id, row.get("website_monster_name", website.get("name", "")),
                       row.get("website_category", website.get("category", "")), row.get("website_image", website.get("image")),
                       row.get("website_image_evidence"), [c.get("index") for c in candidates] or ([row.get("zircon_index")] if row.get("zircon_index") is not None else []),
                       ref("website-alignment-manifest", f"manifest.json#monster_identity/{source_id}"), row.get("status", "pending"),
                       {int(c["index"]): c.get("internal_name") for c in candidates if c.get("index") is not None})
    for row in alignment.get("skills", []):
        source_id = row["website_skill_id"]
        website = next((r for r in website_data["skills"] if r.get("id") == source_id), {})
        idx = row.get("zircon_index")
        attach_website("skill", source_id, row.get("website_skill_name", website.get("name", "")),
                       row.get("website_class", website.get("class", "")), row.get("website_image", website.get("image")),
                       row.get("website_image_evidence"), [idx] if idx is not None else [],
                       ref("website-alignment-manifest", f"manifest.json#skills/{source_id}"), row.get("status", "pending"),
                       {int(idx): row.get("zircon_name")} if idx is not None else {})
    # Items: a single candidate is only linked when the research source explicitly confirmed it and current name agrees.
    item_id_by_name = defaultdict(list)
    for website in website_data["items"]:
        item_id_by_name[website.get("name", "")].append(website)
    for row in extension.get("items", []):
        name = row.get("website_name", "")
        matching_sites = item_id_by_name.get(name, [])
        website = matching_sites[0] if matching_sites else {}
        candidates = row.get("zircon_candidates", [])
        indexes = [c.get("index") for c in candidates]
        names = {int(c["index"]): c.get("name") for c in candidates if c.get("index") is not None}
        source_id = website.get("id") or f"item-{row.get('website_category','')}-{name}"
        attach_website("item", source_id, name, row.get("website_category", ""), row.get("website_image") or website.get("image"),
                       row.get("website_image") or {}, indexes, ref("website-alignment-extension", f"extension-manifest.json#items/{name}"),
                       row.get("status", "pending"), names)

    # Website guide records and map-family records remain explicit when no stable Zircon identity exists.
    for website in website_data["missions"]:
        ident = f"mission:website:{website.get('id')}"
        records[ident] = {
            "id": ident, "entity_type": "mission", "identity": {"entity_type": "mission", "zircon_index": None, "zircon_internal_name": None, "current_game_name": None, "website_source_id": website.get("id"), "website_source_ids": [website.get("id")], "website_name": website.get("title"), "standard_name_zh": website.get("title"), "standard_name_ja": None, "candidate_website_names": [], "aliases": [], "version": "website-source"},
            "resources": {"website": None, "zircon": {"resource_name": None, "library": None, "shape": None, "frame": None, "face": None, "icon": None, "exists": None, "verification": "not-applicable", "evidence_refs": []}},
            "game_data": {k: v for k, v in website.items() if k not in {"id", "title"}},
            "relations": {"candidate_entity_ids": [], "npc_ids": [], "skill_ids": [], "item_ids": [], "monster_ids": [], "conflict_counterparts": []},
            "assessment": assessment("pending_evidence", "17173 任务攻略与 QuestInfo 定义是不同数据形态；交叉引用仅作候选，等待逐条复核。"),
            "evidence": [ref("website-data", f"missions.json#{website.get('id')}")], "source_findings": [],
        }
    for group in website_data["maps"]:
        group_id = group.get("id")
        ident = f"map_group:website:{group_id}"
        records[ident] = {
            "id": ident, "entity_type": "map_group", "identity": {"entity_type": "map_group", "zircon_index": None, "zircon_internal_name": None, "current_game_name": None, "website_source_id": group_id, "website_source_ids": [group_id], "website_name": group.get("title"), "standard_name_zh": group.get("title"), "standard_name_ja": None, "candidate_website_names": [], "aliases": [], "version": "website-source"},
            "resources": {"website": None, "zircon": {"resource_name": None, "library": None, "shape": None, "frame": None, "face": None, "icon": None, "exists": None, "verification": "not-applicable", "evidence_refs": []}},
            "game_data": {"area_count": len(group.get("areas", []))}, "relations": {"area_ids": [], "conflict_counterparts": []},
            "assessment": assessment("pending_review", "网站地图是区域家族索引，不等同于 Zircon 的逐张 MapInfo。"),
            "evidence": [ref("website-data", f"maps.json#{group_id}")], "source_findings": [],
        }
    family_by_area = {(r.get("website_group"), r.get("website_area")): r for r in map_family_rows}
    ecology_by_group = {r.get("website_group"): r for r in map_ecology.get("families", [])}
    for group in website_data["maps"]:
        group_id = group.get("id")
        group_id_ref = f"map_group:website:{group_id}"
        family = ecology_by_group.get(group_id, {})
        for area_number, area in enumerate(group.get("areas", []), start=1):
            name = area.get("name", "")
            family_row = family_by_area.get((group_id, name), {})
            candidates = family_row.get("zircon_mapinfo_candidates", [])
            candidate_indexes = sorted({int(c["index"]) for c in candidates if c.get("index") is not None})
            ecology_area = next((a for a in family.get("areas", []) if a.get("website_area") == name), {})
            ecology_candidates = [candidate for family_candidate in ecology_area.get("zircon_family_candidates", [])
                                  for candidate in family_candidate.get("zircon_mapinfo_candidates", [])]
            ecology_indexes = sorted({int(c["index"]) for c in ecology_candidates if c.get("index") is not None})
            candidate_indexes = sorted(set(candidate_indexes) | set(ecology_indexes))
            ident = f"map_area:website:{group_id}:{area_number:02d}"
            image = web_image(area.get("image"), family_row.get("image_evidence"))
            records[ident] = {
                "id": ident, "entity_type": "map_area",
                "identity": {"entity_type": "map_area", "website_source_id": ident, "website_name": name, "standard_name_zh": name, "zircon_candidate_indexes": candidate_indexes},
                "resources": {"website": image},
                "game_data": {"category": group.get("category"), "group_title": group.get("title"), "area_order": area_number,
                              "ecology_candidate_details": [{"index": c.get("index"), "file": c.get("file"), "description": c.get("description")} for c in ecology_candidates]},
                "relations": {"map_group_id": group_id_ref, "candidate_entity_ids": [f"map:zircon:{i}" for i in candidate_indexes], "conflict_counterparts": []},
                "assessment": assessment("pending_evidence", "地图图片和名称来自网站；候选 MapInfo 来自地图族清单，粒度、别名与资源尚未逐项复核。"),
                "evidence": [ref("website-data", f"maps.json#{group_id}/areas/{area_number-1}"),
                             ref("website-alignment-map-family", f"map-family-manifest.json#{group_id}/{name}")],
                "source_findings": [],
            }
            records[group_id_ref]["relations"]["area_ids"].append(ident)
            for candidate in candidate_indexes:
                target = records.get(f"map:zircon:{candidate}")
                if target:
                    target["relations"]["conflict_counterparts"].append(ident)

    # Detailed imported evidence summaries and safe source references.
    source_registry = []
    source_ids_by_url = {}
    for source_id, item in read_json(web_base / "external_sources.json").items():
        source_url = public_url(item.get("url", ""))
        entry = {
            "id": source_id, "url": source_url, "title": item.get("title"),
            "publisher": item.get("publisher"), "accessed_at": item.get("accessed_at"),
            "bytes": item.get("bytes"), "sha256": item.get("sha256"),
            "used_for": item.get("used_for", []),
        }
        source_registry.append(entry)
        if source_url:
            source_ids_by_url[source_url] = source_id
    search_queries = []
    query_ids = {}
    for number, item in enumerate(read_json(web_base / "search_queries.json"), start=1):
        query_id = f"web-query:{number:02d}"
        query_ids[item["q"]] = query_id
        query_sources = sorted({source_ids_by_url[url] for raw in item.get("sources", [])
                                if (url := public_url(raw)) in source_ids_by_url})
        search_queries.append({"id": query_id, "query": item["q"], "outcome": item.get("outcome"),
                               "source_refs": query_sources})
    findings = []
    ledger_path = web_base / "audit_ledger.tsv"
    with ledger_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for line, row in enumerate(reader, start=2):
            kind = row["kind"]
            mapped_type = {"monster": "monster", "item": "item", "skill": "skill", "npc": "npc", "map": "map", "respawn": "respawn", "quest": "quest"}.get(kind, kind)
            refs = []
            rec_id = row.get("record_id", "")
            if rec_id.startswith("website:"):
                source_id = rec_id.split(":", 1)[1]
                target = by_site_id.get((mapped_type, source_id))
                if target: refs.append(target["id"])
            if rec_id.startswith("zircon:") and row.get("zircon_index", "").isdigit():
                target = records.get(f"{mapped_type}:zircon:{int(row['zircon_index'])}")
                if target: refs.append(target["id"])
            if not refs and row.get("zircon_index", "").isdigit():
                target = records.get(f"{mapped_type}:zircon:{int(row['zircon_index'])}")
                if target: refs.append(target["id"])
            urls = sorted({safe for value in (row.get("external_sources", "") or "").split(";") if (safe := public_url(value))})
            query_refs = sorted({query_ids[query.strip()] for query in (row.get("search_queries", "") or "").split(";")
                                 if query.strip() in query_ids})
            finding = {
                "id": f"web-audit:{kind}:{line}", "entity_type": kind, "source_record_id": rec_id,
                "entity_refs": sorted(set(refs)), "direction": row.get("direction"),
                "direction_before_audit": row.get("direction_before_audit"), "source_status": row.get("status"),
                "previous_status": row.get("previous_status"), "web_search_status": row.get("web_search_status"),
                "confidence": row.get("confidence"), "review_required": str(row.get("review_required", "")).lower() == "true",
                "zircon_index": int(row["zircon_index"]) if row.get("zircon_index", "").isdigit() else None,
                "zircon_internal_name": row.get("zircon_name") or None,
                "website_name": row.get("mir2ei_name") or None,
                "public_sources": urls,
                "external_source_refs": sorted({source_ids_by_url[url] for url in urls if url in source_ids_by_url}),
                "search_query_refs": query_refs,
                "evidence_refs": [ref("web-audit-ledger", f"audit_ledger.tsv:L{line}")],
            }
            findings.append(finding)
            for target_id in finding["entity_refs"]:
                records[target_id]["source_findings"].append(finding["id"])

    # Include source-manifest per-record status snapshots, without private paths or operational logs.
    observations = []
    for row in alignment.get("monster_identity", []):
        observations.append({"id": f"website-alignment:monster:{row['website_monster_id']}", "entity_refs": [by_site_id[("monster", row["website_monster_id"])]["id"]], "source_status": row.get("status"), "apply_status": row.get("apply_status"), "confidence": row.get("confidence"), "match_method": row.get("match_method"), "candidate_count": row.get("candidate_count"), "candidate_indexes": [c.get("index") for c in row.get("zircon_candidates", [])], "candidate_resources": [candidate_summary(c) for c in row.get("zircon_candidates", [])], "evidence_refs": [ref("website-alignment-manifest", f"manifest.json#monster_identity/{row['website_monster_id']}")]})
    for row in alignment.get("skills", []):
        observations.append({"id": f"website-alignment:skill:{row['website_skill_id']}", "entity_refs": [by_site_id[("skill", row["website_skill_id"])]["id"]], "source_status": row.get("status"), "apply_status": row.get("apply_status"), "confidence": row.get("confidence"), "match_method": row.get("match_method"), "candidate_indexes": [row.get("zircon_index")] if row.get("zircon_index") is not None else [], "icon_evidence": row.get("icon_evidence"), "catalog_evidence": row.get("catalog_evidence"), "evidence_refs": [ref("website-alignment-manifest", f"manifest.json#skills/{row['website_skill_id']}")]})
    for row in extension.get("missions", []):
        ident = f"mission:website:{row.get('website_id')}"
        if ident in records:
            observations.append({"id": f"website-extension:mission:{row.get('website_id')}", "entity_refs": [ident], "source_status": "pending-evidence", "step_count": row.get("raw_step_count"), "subtask_count": row.get("raw_quest_count"), "references": row.get("references", {}), "evidence_refs": [ref("website-alignment-extension", f"extension-manifest.json#missions/{row.get('website_id')}")]})
    website_skill_by_name = {(r.get("name"), r.get("class")): r for r in website_data["skills"]}
    for row_number, row in enumerate(item_alignment_rows, start=1):
        source = next((x for x in website_data["items"] if x.get("name") == row.get("website_name")), {})
        target = by_site_id.get(("item", source.get("id")))
        observations.append({
            "id": f"website-item-manifest:{row_number:03d}:{source.get('id', row.get('website_name'))}",
            "entity_refs": [target["id"]] if target else [],
            "source_status": row.get("status"), "skip_reason": row.get("skip_reason"),
            "candidate_indexes": [c.get("index") for c in row.get("zircon_candidates", [])],
            "candidate_resources": [candidate_summary(c) for c in row.get("zircon_candidates", [])],
            "category_candidate_indexes": [c.get("index") for c in row.get("category_compatible_candidates", [])],
            "legacy_candidate_count": len(row.get("legacy_source_candidates", [])),
            "icon_evidence": row.get("icon_evidence"), "attribute_evidence": row.get("attribute_evidence"),
            "evidence_refs": [ref("website-alignment-item", f"item-manifest.json#{row.get('website_name')}")],
        })
    for row in skill_detail_rows:
        site = website_skill_by_name.get((row.get("website_name"), row.get("website_class")), {})
        target = by_site_id.get(("skill", site.get("id")))
        observations.append({
            "id": f"website-skill-detail:{site.get('id', row.get('website_name'))}",
            "entity_refs": [target["id"]] if target else [],
            "source_status": row.get("status"), "skip_reason": row.get("skip_reason"),
            "candidate_indexes": [c.get("index") for c in row.get("zircon_candidates", [])],
            "candidate_resources": [candidate_summary(c) for c in row.get("zircon_candidates", [])],
            "icon_evidence": row.get("icon_evidence"), "legacy_alignment_evidence": row.get("legacy_alignment_evidence"),
            "evidence_refs": [ref("website-alignment-skill-detail", f"skill-detail-manifest.json#{row.get('website_name')}")],
        })
    for row in npc_alignment_rows:
        idx = row.get("npc_index")
        target = records.get(f"npc:zircon:{idx}")
        observations.append({
            "id": f"website-npc-manifest:{idx}", "entity_refs": [target["id"]] if target else [],
            "source_status": row.get("apply_status"), "current_name": row.get("current_name"),
            "current_map": row.get("current_map"), "current_xy": row.get("current_xy"),
            "website_name": row.get("website_name"), "website_page": public_url(row.get("website_page", "")) if row.get("website_page") else None,
            "matched_identity": row.get("matched_identity"), "map_match": row.get("map_match"),
            "coordinate_evidence": row.get("coordinate_evidence"), "walkable": row.get("walkable"),
            "overlap": row.get("overlap"), "confidence": row.get("confidence"), "skip_reason": row.get("skip_reason"),
            "evidence_refs": [ref("website-alignment-npc", f"npc-manifest.json#NPCInfo.Index={idx}")],
        })
    for row in respawn_alignment_rows:
        idx = row.get("respawn_index")
        target = records.get(f"respawn:zircon:{idx}")
        observations.append({
            "id": f"website-respawn-manifest:{idx}", "entity_refs": [target["id"]] if target else [],
            "source_status": row.get("apply_status"), "match_status": row.get("match_status"),
            "monster_index": row.get("monster_index"), "monster_name": row.get("monster_name"),
            "old_respawn": row.get("old_respawn"), "new_respawn": row.get("new_respawn"),
            "hero_kill": row.get("hero_kill"), "confidence": row.get("confidence"),
            "walkable": row.get("walkable"), "overlap": row.get("overlap"),
            "evidence_refs": [ref("website-alignment-respawn", f"respawn-manifest.json#RespawnInfo.Index={idx}")],
        })
    for area in map_family_rows:
        group = area.get("website_group")
        name = area.get("website_area")
        area_id = next((r["id"] for r in records.values() if r["entity_type"] == "map_area"
                        and r["identity"].get("website_name") == name
                        and r["identity"].get("website_source_id", "").startswith(f"map_area:website:{group}:")), None)
        indexes = [c.get("index") for c in area.get("zircon_mapinfo_candidates", [])]
        observations.append({
            "id": f"website-map-family:{group}:{name}", "entity_refs": [area_id] if area_id else [],
            "candidate_indexes": indexes, "coordinate_policy": area.get("coordinate_policy"),
            "image_evidence": web_image(area.get("image"), area.get("image_evidence")),
            "candidate_details": [{"index": c.get("index"), "file": c.get("file"), "description": c.get("description")} for c in area.get("zircon_mapinfo_candidates", [])],
            "evidence_refs": [ref("website-alignment-map-family", f"map-family-manifest.json#{group}/{name}")],
        })
    for row in mission_crossrefs:
        ident = f"mission:website:{row.get('website_id')}"
        observations.append({
            "id": f"website-mission-crossref:{row.get('website_id')}",
            "entity_refs": [ident] if ident in records else [],
            "references": row.get("references"), "explicit_step_npcs": row.get("explicit_step_npcs"),
            "current_quest_start_name_hits": row.get("current_quest_start_name_hits"),
            "raw_step_count": row.get("raw_step_count"), "raw_quest_count": row.get("raw_quest_count"),
            "evidence_refs": [ref("website-alignment-mission-crossref", f"mission-cross-reference.json#{row.get('website_id')}")],
        })

    # Explicit cross-entity dispute fixture from user-specified case and independently cited source records.
    def add_counterpart(left: str, right: str):
        if left in records and right in records:
            for a, b in ((left, right), (right, left)):
                rel = records[a]["relations"].setdefault("conflict_counterparts", [])
                if b not in rel: rel.append(b)
    oma = records.get("monster:zircon:22")
    oma_warrior = records.get("monster:zircon:18")
    zuma_guard_site = records.get("monster:website:mob-119")
    for index in (78, 80):
        add_counterpart(f"monster:zircon:{index}", "monster:website:mob-119")
    add_counterpart("monster:zircon:18", "monster:website:mob-119")
    if oma:
        oma["assessment"]["overall_status"] = "cross_entity_conflict"
        oma["assessment"]["fields"]["display_name"] = {"status": "display_name_error", "reason": "Goal 指定的半兽人示例：当前映射值为祖玛；网站标准名为半兽人。仅暴露冲突，不改写翻译。"}
        oma["assessment"]["fields"]["identity_mapping"] = {"status": "source_confirmed", "reason": "2026-09-26 网站对齐 manifest 将 mob-12 映射至 Zircon MonsterInfo.Index=22 / Oma；当前快照 Index 和内部名吻合。"}
        oma["assessment"]["reason"] = "半兽人与 Oma 身份已由快照证据对应；当前中文显示名存在目标明确指出的交叉翻译冲突。禁止自动修正。"
    if oma_warrior:
        oma_warrior["assessment"]["overall_status"] = "cross_entity_conflict"
        oma_warrior["assessment"]["fields"]["display_name"] = {"status": "display_name_error", "reason": "Goal 指定的半兽战士示例：Oma Warrior 当前显示祖玛卫士；网站标准名为半兽战士，另有独立祖玛卫士候选实体。仅暴露冲突，不改写翻译。"}
        oma_warrior["assessment"]["fields"]["identity_mapping"] = {"status": "source_confirmed", "reason": "2026-09-26 网站对齐 manifest 将 mob-13 映射至 Zircon MonsterInfo.Index=18 / Oma Warrior；当前快照 Index 和内部名吻合。"}
        oma_warrior["assessment"]["reason"] = "半兽战士与 Oma Warrior 身份已对应；当前中文显示名与网站标准名冲突。mob-119 祖玛卫士的候选 Index 78/80 保留待人工确认。"
    if zuma_guard_site:
        zuma_guard_site["assessment"]["overall_status"] = "conflict"
        zuma_guard_site["assessment"]["reason"] = "网站祖玛卫士候选同时涉及 Zircon Index 78 Zuma Guardian 与 80 Zuma Keeper；网络台账与资源候选结论并不一致，保留双方证据，不自动选 Index。"

    # Cross-link current relations and add 2025 review provenance without collapsing source statuses.
    npc_old = read_json(old_base / "manifest.json")
    for row in npc_old.get("npcs", []):
        idx = row.get("current_npc_index")
        target = records.get(f"npc:zircon:{idx}") if idx is not None else None
        if target:
            target["evidence"].append(ref("npc-monster-2025", f"manifest.json#npcs/{idx}"))
            observations.append({"id": f"npc-monster-2025:npc:{idx}", "entity_refs": [target["id"]], "source_status": row.get("apply_status"), "map_relation": row.get("map_relation"), "match_method": row.get("match_method"), "confidence": row.get("confidence"), "walkable": row.get("walkable"), "evidence_refs": [ref("npc-monster-2025", f"manifest.json#npcs/{idx}")]})
    for row in npc_old.get("monster_identity", []):
        idx = row.get("mapped_zircon_monster_index")
        target = records.get(f"monster:zircon:{idx}") if idx is not None else None
        observations.append({"id": f"npc-monster-2025:monster:{row.get('hero_kill_monster_id')}", "entity_refs": [target["id"]] if target else [], "source_status": row.get("status"), "confidence": row.get("confidence"), "mapped_zircon_index": idx, "evidence_status": (row.get("four_way_evidence") or {}).get("evidence_status"), "evidence_refs": [ref("npc-monster-2025", f"manifest.json#monster_identity/{row.get('hero_kill_monster_id')}")]})
    for row in npc_old.get("monster_respawns", []):
        old = row.get("old_respawn") or {}
        idx = old.get("Index") or row.get("zircon_respawn_index")
        target = records.get(f"respawn:zircon:{idx}") if idx is not None else None
        observations.append({"id": f"npc-monster-2025:respawn:{idx or len(observations)}", "entity_refs": [target["id"]] if target else [], "source_status": row.get("apply_status"), "match_status": row.get("match_status"), "confidence": row.get("confidence"), "mapped_monster_index": row.get("mapped_zircon_monster_index"), "evidence_refs": [ref("npc-monster-2025", f"manifest.json#monster_respawns/{idx}")]})

    for row in npc_old.get("maps", []):
        info = row.get("zircon_map_info") or {}
        idx = info.get("index")
        target = records.get(f"map:zircon:{idx}") if idx is not None else None
        observations.append({
            "id": f"npc-monster-2025:map:{idx if idx is not None else row.get('original_map')}",
            "entity_refs": [target["id"]] if target else [],
            "map_relation": row.get("relation"), "map_file": safe_filename(row.get("map_file")),
            "legacy_map_file": safe_filename(row.get("hero_kill_file")), "map_size": row.get("size"),
            "landmarks": row.get("city_town_safe_zone_landmarks"),
            "hero_kill_walkable": row.get("hero_kill_walkable"),
            "zircon_walkable": row.get("zircon_walkable"),
            "coordinate_transform": row.get("coordinate_transform"),
            "coordinate_reuse": row.get("coordinate_reuse"),
            "confidence": row.get("confidence"),
            "evidence_refs": [ref("npc-monster-2025", f"manifest.json#maps/{idx}")],
        })
    for collection in ("hero_kill_refreshes", "yxs_only_refresh", "refresh_conflicts", "missing_yxs_refresh"):
        for row_number, row in enumerate(npc_old.get(collection, []), start=1):
            monster_index = row.get("mapped_zircon_monster_index")
            respawn_ids = [f"respawn:zircon:{idx}" for idx in row.get("current_respawn_indices", [])
                           if f"respawn:zircon:{idx}" in records]
            monster_id = f"monster:zircon:{monster_index}" if f"monster:zircon:{monster_index}" in records else None
            observations.append({
                "id": f"npc-monster-2025:{collection}:{row_number}",
                "entity_refs": ([monster_id] if monster_id else []) + respawn_ids,
                "source_status": row.get("status"), "map": row.get("hero_kill_map"),
                "coordinates": row.get("hero_kill_xy"), "range": row.get("hero_kill_range"),
                "count": row.get("hero_kill_count"), "interval": row.get("hero_kill_interval"),
                "monster_name": row.get("hero_kill_monster_name"), "mapped_monster_index": monster_index,
                "mapped_monster_name": row.get("mapped_zircon_monster_name"),
                "current_respawn_indexes": row.get("current_respawn_indices", []),
                "confidence": row.get("confidence"), "range_note": row.get("range_note"),
                "source_line": row.get("source_line"), "parse_warning": row.get("parse_warning"),
                "evidence_refs": [ref("npc-monster-2025", f"manifest.json#{collection}/{row_number-1}")],
            })
    for collection in ("zircon_only_refresh",):
        for row_number, row in enumerate(npc_old.get(collection, []), start=1):
            idx = row.get("zircon_respawn_index")
            respawn_id = f"respawn:zircon:{idx}"
            observations.append({
                "id": f"npc-monster-2025:{collection}:{row_number}",
                "entity_refs": [respawn_id] if respawn_id in records else [],
                "map": row.get("map"), "coordinates": row.get("xy"),
                "monster_name": row.get("monster"), "source_reason": row.get("reason"),
                "evidence_refs": [ref("npc-monster-2025", f"manifest.json#{collection}/{row_number-1}")],
            })
    for collection in ("monster_conflicts", "zircon_only_monsters"):
        for row_number, row in enumerate(npc_old.get(collection, []), start=1):
            idx = row.get("zircon_monster_index")
            monster_id = f"monster:zircon:{idx}"
            observations.append({
                "id": f"npc-monster-2025:{collection}:{row_number}",
                "entity_refs": [monster_id] if monster_id in records else [],
                "source_status": row.get("status"), "monster_name": row.get("zircon_monster_name"),
                "legacy_names": row.get("hero_kill_names"), "source_reason": row.get("reason"),
                "evidence_refs": [ref("npc-monster-2025", f"manifest.json#{collection}/{row_number-1}")],
            })
    # Carry current snapshot relationships from parent map and quest records.
    for row in raw_tables.get("MapInfo", []):
        idx = int(row["Index"]); rec = by_type_index[("map", idx)]
        rec["relations"]["map_region_ids"] = [f"map_region:zircon:{r.get('Index')}" for r in row.get("Regions", []) if r.get("Index") is not None]
    for row in raw_tables.get("QuestTask", []):
        task_id = f"quest_task:zircon:{row['Index']}"
        quest_id = (row.get("Quest") or {}).get("Index")
        target = records.get(f"quest:zircon:{quest_id}")
        if target and task_id not in target["relations"]["task_ids"]: target["relations"]["task_ids"].append(task_id)
    # All collection order is fixed before serializing.
    for rec in records.values():
        for value in rec.get("relations", {}).values():
            if isinstance(value, list):
                value[:] = sorted(set(value), key=str)
        rec["source_findings"] = sorted(set(rec.get("source_findings", [])))
        rec["relations"] = {
            key: value for key, value in rec["relations"].items()
            if value not in (None, [], {})
        }
        rec.pop("source_findings", None) if not rec["source_findings"] else None
        identity = rec["identity"]
        identity.pop("entity_type", None)
        identity.pop("version", None)
        for key in ("zircon_index", "zircon_internal_name", "current_game_name", "current_translation",
                    "website_source_id", "website_source_ids", "website_name", "standard_name_zh",
                    "standard_name_ja", "candidate_website_names", "aliases", "zircon_candidate_indexes"):
            value = identity.get(key)
            if value in (None, [], {}):
                identity.pop(key, None)
        if "website_source_ids" in identity and len(identity["website_source_ids"]) == 1:
            identity.pop("website_source_ids")
        resource = rec["resources"].get("zircon", {})
        for key in list(resource):
            if resource[key] is None:
                resource.pop(key)
        if resource.get("verification") == "not-applicable" and len(resource) == 1:
            resource.clear()
        website_resource = rec["resources"].get("website")
        if not website_resource and not resource:
            rec.pop("resources")
        elif not website_resource:
            rec["resources"]["zircon"] = resource
            rec["resources"].pop("website")
        default_assessment = assessment()
        if rec["assessment"] == default_assessment:
            rec.pop("assessment")
    
    source_counts = {
        "website": {**{k: len(v) for k, v in website_data.items()},
                    "map_areas": sum(len(group.get("areas", [])) for group in website_data["maps"])},
        "zircon": counts,
        "web_audit": {"total": len(findings)},
        "website_alignment": {"monsters": len(alignment.get("monster_identity", [])), "skills": len(alignment.get("skills", [])), "map_areas": len(map_family_rows)},
        "website_extension": {"items": len(extension.get("items", [])), "skills": len(extension.get("skills", [])), "missions": len(extension.get("missions", []))},
        "npc_monster_2025": {"maps": len(npc_old.get("maps", [])), "npcs": len(npc_old.get("npcs", [])), "monsters": len(npc_old.get("monster_identity", [])), "respawns": len(npc_old.get("monster_respawns", []))},
        "web_audit_context": {"external_sources": len(source_registry), "search_queries": len(search_queries)},
    }
    return {
        "schema_version": 1,
        "captured_at": "2026-09-27",
        "source_counts": source_counts,
        "translation_baseline": translations,
        "external_sources": sorted(source_registry, key=lambda source: source["id"]),
        "search_queries": search_queries,
        "provenance": {
            "repositories": {"website": {"name": "iamcheyan/mir3-website", "commit": website_commit}, "zircon": {"name": "iamcheyan/Zircon", "commit": zircon_commit, "system_database_version": db_version}, "research": {"name": "iamcheyan/Mir3-Research", "commit": research_commit}},
            "inputs": sorted(provenance, key=lambda x: (x["source_id"], x["path"])),
            "policy": "Dated snapshots are source observations, not current truth. Live Zircon tables came from a read-only SystemDbProbe export. Names are never inferred from similarity. No translation is export-approved by default.",
        },
        "entities": sorted(records.values(), key=lambda r: r["id"]),
        "research_findings": sorted(findings, key=lambda f: f["id"]),
        "source_observations": sorted(observations, key=lambda x: x["id"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-snapshot", type=Path, required=True, help="SystemDbProbe --json output directory (read-only source).")
    parser.add_argument("--research", type=Path, required=True, help="Mir3-Research checkout (read-only source).")
    parser.add_argument("--zircon", type=Path, default=Path("[本地路径已脱敏]"))
    parser.add_argument("--db-names", type=Path, default=Path("[本地路径已脱敏]"))
    parser.add_argument("--output", type=Path, default=ROOT / "data/alignment/master.json")
    args = parser.parse_args()
    master = build(args)
    arrays = {
        "entities": master.pop("entities"),
        "research_findings": master.pop("research_findings"),
        "source_observations": master.pop("source_observations"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    shards = {}
    total_bytes = 0
    for collection, rows in arrays.items():
        grouped = defaultdict(list)
        if collection == "entities":
            for row in rows:
                grouped[row["entity_type"]].append(row)
        else:
            grouped[collection].extend(rows)
        shards[collection] = []
        for shard_name, shard_rows in sorted(grouped.items()):
            relative = (Path("entities") / f"{shard_name}.json") if collection == "entities" else Path(f"{collection}.json")
            shard_path = args.output.parent / relative
            text = json.dumps(shard_rows, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            encoded = text.encode("utf-8")
            if len(encoded) > 25 * 1024 * 1024:
                raise ValueError(f"alignment shard exceeds the 25 MiB static-asset limit: {relative.as_posix()}")
            shard_path.parent.mkdir(parents=True, exist_ok=True)
            shard_path.write_bytes(encoded)
            digest = hashlib.sha256(encoded).hexdigest()
            shards[collection].append({"path": relative.as_posix(), "count": len(shard_rows), "sha256": digest})
            total_bytes += len(encoded)
    master["shards"] = shards
    manifest_text = json.dumps(master, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    args.output.write_text(manifest_text, encoding="utf-8")
    total_bytes += len(manifest_text.encode("utf-8"))
    counts = {key: sum(part["count"] for part in parts) for key, parts in shards.items()}
    print(f"wrote {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}: {counts['entities']} entities, {counts['research_findings']} audit findings, {counts['source_observations']} observations, {total_bytes} total bytes in {sum(map(len, shards.values())) + 1} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
