import json
import unittest
from pathlib import Path

from tools.alignment import load_master  # pyright: ignore[reportMissingImports]

ROOT = Path(__file__).resolve().parents[1]
TYPE_CONFIG = {"monster", "item", "skill", "mission", "map_group"}


class MatchPreviewCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.master = load_master(ROOT / "data" / "alignment" / "master.json")
        cls.records = {record["id"]: record for record in cls.master["entities"]}
        cls.preview_index = json.loads((ROOT / "data" / "alignment" / "match-preview-index.json").read_text(encoding="utf-8"))

    def test_unmatched_website_queue_excludes_already_linked_zircon_rows(self):
        source_rows = [
            record for record in self.master["entities"]
            if record.get("entity_type") in TYPE_CONFIG
            and (record.get("identity") or {}).get("website_source_id")
            and not isinstance((record.get("identity") or {}).get("zircon_index"), int)
        ]
        self.assertEqual(len(source_rows), 438)
        self.assertEqual({record["entity_type"] for record in source_rows}, TYPE_CONFIG)
        linked_rows = [
            record for record in self.master["entities"]
            if record.get("entity_type") in TYPE_CONFIG
            and (record.get("identity") or {}).get("website_source_id")
            and isinstance((record.get("identity") or {}).get("zircon_index"), int)
        ]
        self.assertEqual(len(linked_rows), 167)

    def test_candidate_preview_index_is_local_safe_and_assets_exist(self):
        index = self.preview_index
        self.assertEqual(index.get("schema_version"), 1)
        assets = index.get("assets")
        self.assertIsInstance(assets, dict)
        self.assertGreater(len(assets), 1800)
        for entity_id, relpath in assets.items():
            self.assertIn(entity_id, self.records)
            self.assertTrue(relpath.startswith("images/zircon-match/"))
            self.assertNotIn("..", Path(relpath).parts)
            self.assertNotIn("/home/", relpath)
            asset = ROOT / relpath
            self.assertTrue(asset.is_file(), relpath)
            with asset.open("rb") as image:
                header = image.read(12)
            self.assertEqual(header[:4], b"RIFF", relpath)
            self.assertEqual(header[8:12], b"WEBP", relpath)

    def test_preview_targets_are_game_side_rows(self):
        for entity_id in self.preview_index["assets"]:
            record = self.records[entity_id]
            self.assertIn(record.get("entity_type"), {"monster", "item", "skill", "map"})
            self.assertIsInstance((record.get("identity") or {}).get("zircon_index"), int)


if __name__ == "__main__":
    unittest.main()
