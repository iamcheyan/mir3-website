#!/usr/bin/env python3
"""Generate lightweight, static Zircon candidate thumbnails for the website matcher.

Inputs are read-only local Zircon client resources and the website's alignment master.
Only small WebP previews and a website-relative index are written under this repository.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "alignment"
OUT_DIR = ROOT / "images" / "zircon-match"
INDEX_PATH = DATA_DIR / "match-preview-index.json"


def library_map(source: str) -> dict[str, str]:
    return {key: value.replace("\\", "/") for key, value in re.findall(
        r'\[LibraryFile\.([A-Za-z0-9_]+)\]\s*=\s*@"([^\"]+)"', source
    )}


def monster_map(source: str) -> dict[str, tuple[str, int]]:
    result = {}
    for name, library, shape in re.findall(
        r'\{\s*MonsterImage\.([A-Za-z0-9_]+),\s*\(LibraryFile\.([A-Za-z0-9_]+),\s*(\d+)\)\s*\}', source
    ):
        result[name] = (library, int(shape))
    return result


def safe_slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")
    return value[:70] or "frame"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zircon-root", type=Path, default=Path(os.environ.get("MIR3_ZIRCON_ROOT", ROOT.parent / "zircon")))
    parser.add_argument("--research-common", type=Path, default=ROOT.parent / "Mir3-Research" / "Tools" / "common")
    args = parser.parse_args()

    if not args.zircon_root.is_dir():
        parser.error(f"Zircon client source not found: {args.zircon_root}")
    sys.path.insert(0, str(ROOT))
    from tools.alignment import load_master
    sys.path.insert(0, str(args.research_common))
    try:
        import zlsdk
    except ImportError as exc:
        parser.error(f"Cannot import the existing Tools/common/zlsdk.py reader: {exc}")

    client_root = args.zircon_root / "GodotClient"
    data_root = args.zircon_root / "Debug" / "Client" / "Data"
    for required in (client_root / "Formats" / "MonsterLookup.cs", args.zircon_root / "LibraryCore" / "Libraries.cs"):
        if not required.is_file():
            parser.error(f"Required read-only Zircon mapping file not found: {required}")
    library_files = library_map((args.zircon_root / "LibraryCore" / "Libraries.cs").read_text(encoding="utf-8"))
    # GodotClient item cells resolve LibraryFile.StoreItem through this legacy
    # backpack/shop icon set (not the similarly named Storeitem.Zl library).
    library_files["StoreItem"] = "Data/Storeitems.Zl"
    monster_lookup = monster_map((client_root / "Formats" / "MonsterLookup.cs").read_text(encoding="utf-8"))
    master = load_master(DATA_DIR / "master.json")

    specs: dict[str, tuple[Path, int, str]] = {}
    assets: dict[str, str] = {}
    misses: list[dict[str, str]] = []
    for record in master["entities"]:
        identity = record.get("identity") or {}
        index = identity.get("zircon_index")
        if not isinstance(index, int):
            continue
        entity_type = record.get("entity_type")
        data = record.get("game_data") or {}
        library_enum = frame = None
        folder = entity_type
        if entity_type == "item" and isinstance(data.get("Image"), int):
            library_enum, frame, folder = "StoreItem", data["Image"], "item"
        elif entity_type == "skill" and isinstance(data.get("Icon"), int):
            library_enum, frame, folder = "MagicIcon", data["Icon"], "skill"
        elif entity_type == "map" and isinstance(data.get("MiniMap"), int):
            library_enum, frame, folder = "MiniMap", data["MiniMap"], "map"
        elif entity_type == "monster" and isinstance(data.get("Image"), str):
            mapping = monster_lookup.get(data["Image"])
            if mapping:
                library_enum, shape = mapping
                frame, folder = shape * 1000 + 40, "monster"
        if library_enum is None or frame is None:
            continue
        library_rel = library_files.get(library_enum)
        if not library_rel:
            misses.append({"entity_id": record["id"], "reason": f"No library path for {library_enum}"})
            continue
        library_path = data_root / Path(library_rel.replace("Data/", "", 1))
        if not library_path.is_file():
            misses.append({"entity_id": record["id"], "reason": f"Resource library unavailable: {Path(library_rel).name}"})
            continue
        internal = str(identity.get("zircon_internal_name") or identity.get("current_game_name") or record["id"])
        if folder == "monster":
            filename = f"{safe_slug(internal)}-{frame}.webp"
        else:
            filename = f"{frame}.webp"
        rel = Path(folder) / filename
        specs[str(rel)] = (library_path, frame, record["id"])
        assets[record["id"]] = f"images/zircon-match/{rel.as_posix()}"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    libraries = {}
    failures = []
    for rel, (library_path, frame, entity_id) in sorted(specs.items()):
        try:
            lib = libraries.get(library_path)
            if lib is None:
                lib = zlsdk.ZlLibrary(str(library_path))
                libraries[library_path] = lib
            image = lib.decode(frame)
            if image is None:
                failures.append({"entity_id": entity_id, "frame": str(frame), "library": library_path.name, "reason": "frame has no decodable image"})
                assets.pop(entity_id, None)
                continue
            image.thumbnail((112, 112))
            output = OUT_DIR / rel
            output.parent.mkdir(parents=True, exist_ok=True)
            image.save(output, "WEBP", quality=82, method=4)
        except Exception as exc:  # preserve the rest of the catalog if one resource is corrupt
            failures.append({"entity_id": entity_id, "frame": str(frame), "library": library_path.name, "reason": type(exc).__name__})
            assets.pop(entity_id, None)

    for lib in libraries.values():
        try:
            lib.data.close()
            lib._fh.close()
        except Exception:
            pass
    missing_previews = [
        {"entity_id": entity_id, "reason": f"Preview file missing: {relpath}"}
        for entity_id, relpath in assets.items() if not (ROOT / relpath).is_file()
    ]
    for preview in missing_previews:
        assets.pop(preview["entity_id"])

    index = {
        "schema_version": 1,
        "source": "Read-only Zircon client resource preview; thumbnails are visual aids, not identity proof.",
        "assets": dict(sorted(assets.items())),
        "unavailable_count": len(failures) + len(misses) + len(missing_previews),
    }
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "candidate_preview_count": len(assets),
        "unique_preview_files": len(specs),
        "unavailable_count": len(failures) + len(misses) + len(missing_previews),
        "written_bytes": sum(p.stat().st_size for p in OUT_DIR.rglob("*.webp")),
        "index": str(INDEX_PATH.relative_to(ROOT)),
        "sample_unavailable": (failures + misses + missing_previews)[:12],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
