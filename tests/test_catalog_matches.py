import unittest

import app


class CatalogZirconMatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = app.load_data()

    def test_every_public_catalog_entry_has_a_cross_reference_status(self):
        # maps 已从「3 个图集卡片」改为按 Zircon System.db 导出的全服地图文档，
        # 不再走候选推断，因此单独断言其规模与完整性。
        expected = {"monsters": 154, "items": 371, "skills": 61, "missions": 24}
        for collection, count in expected.items():
            with self.subTest(collection=collection):
                self.assertEqual(len(self.data[collection]), count)
                self.assertTrue(all(isinstance(row.get("zircon_match"), dict)
                                    for row in self.data[collection]))

    def test_map_index_lists_every_registered_map_with_its_channels(self):
        doc = self.data["maps"]
        self.assertIsInstance(doc, dict)
        stats = doc["stats"]
        self.assertEqual(stats["maps"], 627)

        maps = [m for g in doc["groups"] for m in g.get("items", [])]
        maps += [m for g in doc["groups"] for s in g.get("suites", []) for m in s["items"]]
        self.assertEqual(len(maps), stats["maps"], "地图条目数必须与 stats.maps 一致")
        self.assertEqual(len({m["id"] for m in maps}), stats["maps"], "地图编号不得重复")

        # 每条通道的两端都必须能在页面里定位到，否则「怎么走」无法点开。
        # 一个门口的多个可行走格会被折叠成一条通道，fromPts 保留全部出发点，
        # 因此这里校验的是「折叠后的条数」与「出发点总数」两个维度。
        ids = {m["id"] for m in maps}
        links = [l for m in maps for l in m["links"]]
        self.assertEqual(len(links), sum(m["linkCount"] - len(m["inbound"]) for m in maps),
                         "折叠后的通道条数必须与各地图出向条数之和一致")
        for m in maps:
            # 同一张源图内，指向同一落点的行必须已被折叠成一条
            seen = set()
            for link in m["links"]:
                with self.subTest(link=f"{m['id']}->{link['to']}@{link['toPt']}"):
                    self.assertIn(link["to"], ids)
                    self.assertRegex(link["toPt"], r"^\d+,\d+$")
                    self.assertTrue(link["fromPts"], "通道必须记录至少一个出发点")
                    for pt in link["fromPts"]:
                        self.assertRegex(pt, r"^\d+,\d+$")
                    key = (link["to"], link["toPt"])
                    self.assertNotIn(key, seen, "同一源图内出现重复落点的通道行")
                    seen.add(key)
        self.assertEqual(len(links), stats["linksShown"],
                         "页面渲染的通道条数必须等于 linksShown")
        # 折叠只会减少条数，不会凭空多出通道
        self.assertLessEqual(stats["linksShown"], stats["links"])


    def test_towns_and_safe_zones_are_kept_together(self):
        towns = next(g for g in self.data["maps"]["groups"] if g["id"] == "towns")
        safe = {m["id"] for m in towns["items"] if m.get("safeZone")}
        self.assertTrue(safe, "主城分组必须标出安全区")
        for m in towns["items"]:
            if m.get("safeZone"):
                self.assertRegex(m["bindPt"], r"^\d+,\d+$")

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
