import unittest

import app


class CatalogZirconMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = app.load_data()

    def test_every_public_catalog_entry_has_a_cross_reference_status(self):
        expected = {"monsters": 154, "items": 371, "skills": 61, "missions": 24, "maps": 3}
        for collection, count in expected.items():
            with self.subTest(collection=collection):
                self.assertEqual(len(self.data[collection]), count)
                self.assertTrue(all(isinstance(row.get("zircon_match"), dict)
                                    for row in self.data[collection]))

    def test_oma_translation_conflict_shows_game_index_and_internal_name(self):
        rows = {row["name"]: row for row in self.data["monsters"]
                if row["name"] in {"半兽人", "半兽战士"}}
        oma = rows["半兽人"]["zircon_match"]
        warrior = rows["半兽战士"]["zircon_match"]
        self.assertEqual(oma["state"], "conflict")
        self.assertIn("Index 22", oma["details"])
        self.assertIn("Oma", oma["details"])
        self.assertIn("游戏当前名：祖玛", oma["details"])
        self.assertEqual(warrior["state"], "conflict")
        self.assertIn("Oma Warrior", warrior["details"])
        self.assertIn("游戏当前名：祖玛卫士", warrior["details"])

    def test_pending_candidates_are_not_mislabeled_as_confirmed(self):
        match = next(row for row in self.data["items"] if row["name"] == "木剑")["zircon_match"]
        self.assertEqual(match["state"], "candidate")
        self.assertIn("Index 126", match["details"])
        self.assertNotEqual(match["label"], "已确认匹配")

    def test_missing_mapping_is_marked_as_not_yet_matched_not_proven_absent(self):
        match = app._match_badge(None)
        self.assertEqual(match["state"], "unreviewed")
        self.assertEqual(match["label"], "尚无对照记录")


if __name__ == "__main__":
    unittest.main()
