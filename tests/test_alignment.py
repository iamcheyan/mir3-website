import unittest

import hashlib
import json
import tempfile
from pathlib import Path

from tools.import_alignment import public_url, public_publisher, public_metadata_text
from tools.alignment import AlignmentError, build_translation_export, load_master, validate_master



class PublicEvidenceUrlTests(unittest.TestCase):
    def test_accepts_public_dns_urls_and_rejects_private_or_credentialed_urls(self):
        self.assertEqual(public_url("https://example.org/source?page=2"), "https://example.org/source?page=2")
        self.assertIsNone(public_url("http://192.168.1.4/internal"))
        self.assertIsNone(public_url("https://user:pass@example.org/source"))
        self.assertIsNone(public_url("https://example.org/source?api_key=private"))

    def test_public_publisher_sanitizes_local_paths(self):
        self.assertEqual(public_publisher("本地客户端副本 /mnt/test-client/Data"),
                         "本地研究来源（路径已脱敏）")
        self.assertEqual(public_publisher("mir2ei.iamcheyan.com"), "mir2ei.iamcheyan.com")
        self.assertEqual(public_metadata_text("本地文献 /data/archive/source.json"),
                         "本地文献 [本地路径已脱敏]")
        self.assertEqual(public_metadata_text("客户端 Data/ 图库"), "客户端 资源 图库")

class MasterShardTests(unittest.TestCase):
    def test_sharded_master_loads_in_manifest_order_and_checks_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            values = {
                "entities/monster.json": [{"id": "monster:zircon:1"}],
                "research_findings.json": [],
                "source_observations.json": [],
            }
            shards = {}
            for name, rows in values.items():
                content = (json.dumps(rows) + "\n").encode()
                path = base / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
                collection = "entities" if name.startswith("entities/") else name.removesuffix(".json")
                shards.setdefault(collection, []).append({
                    "path": name, "count": len(rows), "sha256": hashlib.sha256(content).hexdigest()
                })
            manifest = {"schema_version": 1, "shards": shards}
            (base / "master.json").write_text(json.dumps(manifest), encoding="utf-8")

            loaded = load_master(base / "master.json")

            self.assertEqual(loaded["entities"], values["entities/monster.json"])
            self.assertEqual(loaded["research_findings"], [])
            self.assertEqual(loaded["source_observations"], [])
            (base / "entities/monster.json").write_text("[]\n", encoding="utf-8")
            with self.assertRaisesRegex(AlignmentError, "digest mismatch"):
                load_master(base / "master.json")

class SourceConflictFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        master_path = Path(__file__).resolve().parents[1] / "data/alignment/master.json"
        cls.master = load_master(master_path)
        cls.records = {record["id"]: record for record in cls.master["entities"]}

    def test_oma_and_oma_warrior_remain_distinct_with_display_conflicts(self):
        oma = self.records["monster:zircon:22"]
        warrior = self.records["monster:zircon:18"]
        self.assertNotEqual(oma["id"], warrior["id"])
        self.assertEqual((oma["identity"]["zircon_internal_name"], oma["identity"]["website_name"],
                          oma["identity"]["current_translation"]["zh"]), ("Oma", "半兽人", "祖玛"))
        self.assertEqual((warrior["identity"]["zircon_internal_name"], warrior["identity"]["website_name"],
                          warrior["identity"]["current_translation"]["zh"]), ("Oma Warrior", "半兽战士", "祖玛卫士"))
        self.assertEqual(oma["assessment"]["overall_status"], "cross_entity_conflict")
        self.assertEqual(warrior["assessment"]["fields"]["display_name"]["status"], "display_name_error")

    def test_website_zuma_guard_retains_two_candidates_and_ledger_disagreement(self):
        website = self.records["monster:website:mob-119"]
        self.assertEqual(website["identity"]["zircon_candidate_indexes"], [78, 80])
        self.assertEqual(website["relations"]["candidate_entity_ids"],
                         ["monster:zircon:78", "monster:zircon:80"])
        candidate_names = {self.records[target]["identity"]["zircon_internal_name"]
                           for target in website["relations"]["candidate_entity_ids"]}
        self.assertEqual(candidate_names, {"Zuma Guardian", "Zuma Keeper"})
        ledger_rows = [finding for finding in self.master["research_findings"]
                       if website["id"] in finding.get("entity_refs", [])]
        self.assertEqual([(finding["zircon_index"], finding["direction"]) for finding in ledger_rows], [(78, "both")])

def entity(index, internal_name, *, status="pending_review", export_enabled=False, standard_name=None):
    return {
        "id": f"monster:zircon:{index}",
        "entity_type": "monster",
        "identity": {
            "zircon_index": index,
            "zircon_internal_name": internal_name,
            "standard_name_zh": standard_name,
        },
        "game_data": {},
        "assessment": {
            "overall_status": status,
            "fields": {
                "identity_mapping": {"status": "source_confirmed"},
                "display_name": {"status": status},
            },
            "export_enabled": export_enabled,
        },
        "evidence": [],
        "relations": {},
    }
class TranslationExportTests(unittest.TestCase):
    def test_only_explicitly_approved_names_change_and_all_other_locales_survive(self):
        master = {"schema_version": 1, "entities": [
            entity(1, "Oma", status="approved", export_enabled=True, standard_name="半兽人"),
            entity(2, "Oma Warrior", standard_name="半兽战士"),
        ]}
        base = {"monsters": {"Oma": {"zh": "祖玛", "ja": "オーマ"},
                             "Unreviewed": {"zh": "旧名", "ja": "保持"}}, "items": {}}

        result = build_translation_export(master, base)

        self.assertEqual(result["translation"]["monsters"]["Oma"], {"zh": "半兽人", "ja": "オーマ"})
        self.assertEqual(result["translation"]["monsters"]["Unreviewed"], base["monsters"]["Unreviewed"])
        self.assertEqual(result["changes"], [{"entity_id": "monster:zircon:1", "section": "monsters",
                                                "internal_name": "Oma", "previous_zh": "祖玛",
                                                "next_zh": "半兽人"}])

    def test_name_key_collision_requires_approval_for_every_index(self):
        master = {"schema_version": 1, "entities": [
            entity(9, "Jack", status="approved", export_enabled=True, standard_name="杰克"),
            entity(106, "Jack", status="pending_review", standard_name="杰克"),
        ]}

        with self.assertRaisesRegex(AlignmentError, "Jack.*Index"):
            build_translation_export(master, {"npcs": {"Jack": {"zh": "杰克"}}})

    def test_validator_rejects_duplicate_ids_dangling_relations_and_unknown_status(self):
        first = entity(1, "Oma")
        first["relations"] = {"candidate_entity_ids": ["monster:zircon:999"]}
        invalid = {"schema_version": 1, "entities": [first, dict(first)]}
        invalid["entities"][1]["assessment"] = {"overall_status": "greenlit", "fields": {}, "export_enabled": False}

        errors = validate_master(invalid)

        self.assertTrue(any("duplicate entity id" in error for error in errors))
        self.assertTrue(any("unknown status" in error for error in errors))
        self.assertTrue(any("dangling relation" in error for error in errors))

    def test_validator_rejects_unregistered_and_absolute_evidence_sources(self):
        record = entity(1, "Oma")
        record["evidence"] = [{"source_id": "unregistered", "record": "/data/research-snapshot/input.json"}]
        master = {"schema_version": 1, "entities": [record], "provenance": {"inputs": []}}

        errors = validate_master(master)

        self.assertTrue(any("unregistered evidence source" in error for error in errors))
        self.assertTrue(any("absolute path" in error for error in errors))


    def test_validator_rejects_duplicate_observation_ids(self):
        master = {"schema_version": 1, "entities": [], "source_observations": [
            {"id": "source-row:1", "entity_refs": []},
            {"id": "source-row:1", "entity_refs": []},
        ]}

        errors = validate_master(master)

        self.assertTrue(any("duplicate source_observation id" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
