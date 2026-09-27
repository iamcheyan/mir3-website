#!/usr/bin/env python3
"""Validate the alignment master and produce approval-gated translation candidates."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TYPE_TO_SECTION = {
    "monster": "monsters", "item": "items", "skill": "magics",
    "npc": "npcs", "map": "maps",
}
STATUS_VALUES = {
    "pending_review", "pending_evidence", "source_confirmed", "confirmed",
    "candidate", "conflict", "cross_entity_conflict", "ambiguous",
    "display_name_error", "approved", "corrected", "rejected", "not_applicable",
}
RELATION_ID_KEYS = {
    "candidate_entity_ids", "conflict_counterparts", "area_ids", "map_region_ids",
    "respawn_ids", "drop_ids", "quest_ids", "store_entry_ids", "npc_ids",
    "item_ids", "monster_ids", "skill_ids", "task_ids", "reward_ids", "requirement_ids",
    "monster_detail_ids", "candidate_map_ids", "map_id", "map_group_id", "map_region_id",
    "monster_id", "item_id", "quest_id", "npc_id", "task_id",
}


class AlignmentError(ValueError):
    """Invalid master or unsafe translation export request."""


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _iter_relation_targets(relations):
    if not isinstance(relations, dict):
        return
    for key, value in relations.items():
        if key not in RELATION_ID_KEYS:
            continue
        values = value if isinstance(value, list) else [value]
        for target in values:
            if isinstance(target, str) and ":" in target:
                yield key, target


def _scan_public_strings(value, location="$"):
    errors = []
    if isinstance(value, dict):
        for key, child in value.items():
            errors.extend(_scan_public_strings(child, f"{location}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_scan_public_strings(child, f"{location}[{index}]"))
    elif isinstance(value, str):
        if re.search(r"(?<![A-Za-z0-9])/(?:home|tmp|Users|private|mnt|var/tmp)/", value):
            errors.append(f"{location}: absolute path must not be published")
        if re.search(r"(?<!\d)(?:10\.\d{1,3}\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?!\d)", value):
            errors.append(f"{location}: private/local IP address must not be published")
    return errors


def validate_master(master: dict) -> list[str]:
    """Return deterministic structural, provenance, privacy, and reference errors."""
    errors = []
    if not isinstance(master, dict):
        return ["master must be a JSON object"]
    if master.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    provenance = master.get("provenance", {})
    inputs = provenance.get("inputs", []) if isinstance(provenance, dict) else []
    if not isinstance(inputs, list):
        inputs = []
    source_ids = {item.get("source_id") for item in inputs if isinstance(item, dict) and isinstance(item.get("source_id"), str)}
    external_sources = master.get("external_sources", [])
    if not isinstance(external_sources, list):
        errors.append("external_sources must be an array")
        external_sources = []
    external_source_ids = {row.get("id") for row in external_sources if isinstance(row, dict) and isinstance(row.get("id"), str)}
    if len(external_source_ids) != len(external_sources):
        errors.append("external_sources has missing or duplicate ids")
    queries = master.get("search_queries", [])
    if not isinstance(queries, list):
        errors.append("search_queries must be an array")
        queries = []
    query_ids = {row.get("id") for row in queries if isinstance(row, dict) and isinstance(row.get("id"), str)}
    if len(query_ids) != len(queries):
        errors.append("search_queries has missing or duplicate ids")
    for query in queries:
        if not isinstance(query, dict):
            continue
        for source_id in query.get("source_refs", []):
            if source_id not in external_source_ids:
                errors.append(f"search query {query.get('id')}: unknown external source {source_id}")
    for pos, source in enumerate(inputs):
        if not isinstance(source, dict):
            errors.append(f"provenance.inputs[{pos}] must be an object")
            continue
        path = source.get("path")
        if not isinstance(path, str) or path.startswith("/") or ".." in Path(path).parts:
            errors.append(f"provenance.inputs[{pos}] path must be repository-relative")
        digest = source.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append(f"provenance.inputs[{pos}] has invalid sha256")
    entities = master.get("entities")
    if not isinstance(entities, list):
        return errors + ["entities must be an array"]
    ids = set()
    duplicates = set()
    by_id = {}
    for pos, entity in enumerate(entities):
        label = f"entities[{pos}]"
        if not isinstance(entity, dict):
            errors.append(f"{label} must be an object")
            continue
        identifier = entity.get("id")
        if not isinstance(identifier, str) or not identifier:
            errors.append(f"{label} has no stable id")
            continue
        if identifier in ids:
            duplicates.add(identifier)
        ids.add(identifier)
        by_id[identifier] = entity
        if not isinstance(entity.get("entity_type"), str):
            errors.append(f"{identifier}: entity_type must be a string")
        for required in ("identity", "game_data", "relations", "evidence"):
            if required not in entity:
                errors.append(f"{identifier}: missing {required}")
        if not isinstance(entity.get("identity"), dict):
            errors.append(f"{identifier}: identity must be an object")
        if not isinstance(entity.get("relations"), dict):
            errors.append(f"{identifier}: relations must be an object")
        if not isinstance(entity.get("evidence"), list):
            errors.append(f"{identifier}: evidence must be an array")
        else:
            for evidence in entity["evidence"]:
                if not isinstance(evidence, dict):
                    errors.append(f"{identifier}: evidence entries must be objects")
                    continue
                if evidence.get("source_id") not in source_ids:
                    errors.append(f"{identifier}: unregistered evidence source {evidence.get('source_id')!r}")
        assessment = entity.get("assessment")
        if assessment is not None:
            if not isinstance(assessment, dict):
                errors.append(f"{identifier}: assessment must be an object")
                continue
            status = assessment.get("overall_status", "pending_review")
            if status not in STATUS_VALUES:
                errors.append(f"{identifier}: unknown status {status!r}")
            fields = assessment.get("fields", {})
            if not isinstance(fields, dict):
                errors.append(f"{identifier}: assessment.fields must be an object")
            else:
                for field_name, field in fields.items():
                    if not isinstance(field, dict):
                        errors.append(f"{identifier}: assessment.fields.{field_name} must be an object")
                        continue
                    field_status = field.get("status", "pending_review")
                    if field_status not in STATUS_VALUES:
                        errors.append(f"{identifier}: unknown status {field_status!r} at {field_name}")
            if assessment.get("export_enabled") and status not in {"approved", "corrected"}:
                errors.append(f"{identifier}: export_enabled requires approved or corrected status")
    for identifier in sorted(duplicates):
        errors.append(f"duplicate entity id {identifier}")
    valid_ids = set(by_id)
    for entity in entities:
        if not isinstance(entity, dict) or not isinstance(entity.get("relations"), dict):
            continue
        for relation_key, target in _iter_relation_targets(entity["relations"]):
            if target not in valid_ids:
                msg = f"{entity.get('id')}: dangling relation {relation_key} -> {target}"
                if msg not in errors:
                    errors.append(msg)
    for collection_name in ("source_observations", "research_findings"):
        collection = master.get(collection_name, [])
        if not isinstance(collection, list):
            errors.append(f"{collection_name} must be an array")
            continue
        collection_ids = set()
        for row in collection:
            if not isinstance(row, dict):
                errors.append(f"{collection_name} entries must be objects")
                continue
            row_id = row.get("id")
            if not isinstance(row_id, str) or not row_id:
                errors.append(f"{collection_name} entry has no stable id")
            elif row_id in collection_ids:
                errors.append(f"duplicate {collection_name.removesuffix('s')} id {row_id}")
            collection_ids.add(row_id)
            for target in row.get("entity_refs", []) or []:
                if target not in valid_ids:
                    errors.append(f"{collection_name} {row.get('id')}: dangling entity ref {target}")
            for evidence in row.get("evidence_refs", []) or []:
                if not isinstance(evidence, dict) or evidence.get("source_id") not in source_ids:
                    errors.append(f"{collection_name} {row.get('id')}: unregistered evidence source")
            if collection_name == "research_findings":
                for source_id in row.get("external_source_refs", []) or []:
                    if source_id not in external_source_ids:
                        errors.append(f"{collection_name} {row_id}: unknown external source {source_id}")
                for query_id in row.get("search_query_refs", []) or []:
                    if query_id not in query_ids:
                        errors.append(f"{collection_name} {row_id}: unknown search query {query_id}")
    errors.extend(_scan_public_strings(master))
    return sorted(set(errors))


def _eligible(entity: dict) -> bool:
    assessment = entity.get("assessment", {})
    if not isinstance(assessment, dict) or not assessment.get("export_enabled"):
        return False
    if assessment.get("overall_status") not in {"approved", "corrected"}:
        return False
    fields = assessment.get("fields", {})
    mapping = fields.get("identity_mapping", {}) if isinstance(fields, dict) else {}
    display = fields.get("display_name", {}) if isinstance(fields, dict) else {}
    if mapping.get("status") not in {"confirmed", "source_confirmed"}:
        return False
    if display.get("status") not in {"approved", "corrected"}:
        return False
    identity = entity.get("identity", {})
    return (entity.get("entity_type") in TYPE_TO_SECTION
            and isinstance(identity, dict)
            and isinstance(identity.get("zircon_index"), int)
            and isinstance(identity.get("zircon_internal_name"), str)
            and isinstance(identity.get("standard_name_zh"), str)
            and bool(identity["standard_name_zh"].strip()))


def build_translation_export(master: dict, base: dict) -> dict:
    """Return a compatible full translation candidate and reversible changed-key report."""
    errors = validate_master(master)
    if errors:
        raise AlignmentError("Invalid master: " + "; ".join(errors[:20]))
    if not isinstance(base, dict) or any(not isinstance(base.get(section, {}), dict) for section in TYPE_TO_SECTION.values()):
        raise AlignmentError("translation baseline sections must be JSON objects")
    output = copy.deepcopy(base)
    buckets = defaultdict(list)
    for entity in master["entities"]:
        entity_type = entity.get("entity_type")
        identity = entity.get("identity", {})
        if entity_type in TYPE_TO_SECTION and isinstance(identity, dict):
            name = identity.get("zircon_internal_name")
            if isinstance(name, str) and name:
                buckets[(entity_type, name)].append(entity)
    approved = [entity for entity in master["entities"] if _eligible(entity)]
    approved_groups = defaultdict(list)
    for entity in approved:
        key = (entity["entity_type"], entity["identity"]["zircon_internal_name"])
        approved_groups[key].append(entity)
    changes = []
    for (entity_type, name), chosen in sorted(approved_groups.items()):
        all_records = buckets[(entity_type, name)]
        missing = [e for e in all_records if not _eligible(e)]
        if missing:
            indexes = sorted(e.get("identity", {}).get("zircon_index") for e in all_records
                             if isinstance(e.get("identity", {}).get("zircon_index"), int))
            raise AlignmentError(f"name-key collision for {name!r} at Index {indexes}: every record sharing this runtime key must be approved")
        values = {e["identity"]["standard_name_zh"].strip() for e in chosen}
        if len(values) != 1:
            indexes = sorted(e["identity"]["zircon_index"] for e in chosen)
            raise AlignmentError(f"approved records sharing {name!r} have different names at Index {indexes}")
        value = values.pop()
        section = TYPE_TO_SECTION[entity_type]
        output.setdefault(section, {})
        old = output[section].get(name)
        old_zh = old.get("zh") if isinstance(old, dict) else None
        if old_zh == value:
            continue
        localized = copy.deepcopy(old) if isinstance(old, dict) else {}
        localized["zh"] = value
        output[section][name] = localized
        for entity in chosen:
            changes.append({"entity_id": entity["id"], "section": section, "internal_name": name,
                            "previous_zh": old_zh, "next_zh": value})
    canonical = (json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    base_bytes = (json.dumps(base, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return {
        "translation": output,
        "changes": sorted(changes, key=lambda item: (item["section"], item["internal_name"], item["entity_id"])),
        "rollback": [{"section": c["section"], "internal_name": c["internal_name"], "restore_zh": c["previous_zh"]} for c in changes],
        "base_sha256": _digest(base_bytes),
        "candidate_sha256": _digest(canonical),
        "exported_entity_count": len(approved),
    }


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))



def load_master(path: Path) -> dict:
    """Load and verify an inline master or its content-addressed JSON shards."""
    master = _load_json(path)
    shards = master.get("shards")
    if shards is None:
        return master
    if not isinstance(shards, dict):
        raise AlignmentError("master shards must be an object")
    base = path.resolve().parent
    for collection_name in ("entities", "research_findings", "source_observations"):
        if collection_name in master or not isinstance(shards.get(collection_name), list):
            raise AlignmentError(f"master shard manifest is invalid for {collection_name}")
        rows = []
        for part in shards[collection_name]:
            if not isinstance(part, dict) or not isinstance(part.get("path"), str):
                raise AlignmentError(f"invalid {collection_name} shard descriptor")
            relative = Path(part["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise AlignmentError(f"unsafe {collection_name} shard path")
            shard_path = (base / relative).resolve()
            if not shard_path.is_relative_to(base):
                raise AlignmentError(f"unsafe {collection_name} shard path")
            content = shard_path.read_bytes()
            if _digest(content) != part.get("sha256"):
                raise AlignmentError(f"{collection_name} shard digest mismatch: {relative.as_posix()}")
            shard_rows = json.loads(content.decode("utf-8"))
            if not isinstance(shard_rows, list) or len(shard_rows) != part.get("count"):
                raise AlignmentError(f"{collection_name} shard count mismatch: {relative.as_posix()}")
            rows.extend(shard_rows)
        master[collection_name] = rows
    return master

def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _is_in_zircon(path: Path) -> bool:
    return any(part.casefold() == "zircon" for part in path.parts)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="validate a canonical alignment master")
    validate.add_argument("master", type=Path)
    export = commands.add_parser("export", help="produce a dry-run game translation candidate")
    export.add_argument("--master", type=Path, required=True)
    export.add_argument("--base", type=Path, required=True, help="read-only db_names.json baseline")
    export.add_argument("--output", type=Path, required=True, help="candidate output outside Zircon; never a game file")
    export.add_argument("--report", type=Path, help="optional reversible diff report")
    args = parser.parse_args(argv)
    try:
        master = load_master(args.master)
        if args.command == "validate":
            errors = validate_master(master)
            if errors:
                print("\n".join(errors), file=sys.stderr)
                return 1
            print(f"valid: {len(master['entities'])} entities")
            return 0
        base = _load_json(args.base)
        result = build_translation_export(master, base)
        output_path = args.output.resolve()
        if output_path in {args.base.resolve(), args.master.resolve()} or _is_in_zircon(output_path) or output_path.is_relative_to(ROOT):
            raise AlignmentError("refusing to overwrite inputs or write a translation candidate inside a source repository")
        _write_json(output_path, result["translation"])
        report = {key: value for key, value in result.items() if key != "translation"}
        report["candidate_output"] = str(output_path)
        if args.report:
            report_path = args.report.resolve()
            if report_path in {args.base.resolve(), args.master.resolve(), output_path} or _is_in_zircon(report_path) or report_path.is_relative_to(ROOT):
                raise AlignmentError("refusing to overwrite inputs or write an export report inside a source repository")
            _write_json(report_path, report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, AlignmentError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
