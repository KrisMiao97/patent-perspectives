"""Portable reuse exports use synthetic data only; no provider calls."""
import base64
from contextlib import closing
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("reuse_export_under_test", ROOT / "scripts" / "export_reuse.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ReuseExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="patent-reuse-test-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.sqlite"
        self.output = self.root / "export"
        with closing(sqlite3.connect(self.source)) as db, db:
            db.executescript("""
                CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE applications(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE documents(id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES applications(id), text TEXT NOT NULL, text_hash TEXT NOT NULL, data TEXT NOT NULL);
                CREATE TABLE population_reviews(application_id TEXT PRIMARY KEY REFERENCES applications(id), data TEXT NOT NULL);
                CREATE TABLE evidence(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id), data TEXT NOT NULL);
            """)
            db.execute("INSERT INTO meta VALUES (?,?)", ("run", json.dumps({"status": "incomplete", "as_of_date": "2026-01-10", "scope": {"synthetic": True}})))
            for index, state in enumerate(("included", "pending", "excluded"), start=1):
                appid = "APP" + str(index)
                db.execute("INSERT INTO applications VALUES (?,?)", (appid, json.dumps({"id": appid, "legal_status": "unknown", "title": "Synthetic " + str(index)})))
                db.execute("INSERT INTO population_reviews VALUES (?,?)", (appid, json.dumps({"status": state})))
            text = "1. A synthetic device with a valve."
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            db.execute("INSERT INTO documents VALUES (?,?,?,?,?)", ("DOC1", "APP1", text, text_hash, json.dumps({"version": "A", "qualified": False, "source_artifact": "missing/source.json"})))
            db.execute("INSERT INTO evidence VALUES (?,?,?)", ("EV1", "DOC1", json.dumps({"quote": "A synthetic device", "start": 3, "end": 21, "source_text_hash": text_hash})))

    def manifest(self, items):
        path = self.root / "materials.json"
        path.write_text(json.dumps({"root": "assets", "items": items}), encoding="utf-8")
        return path

    def read_manifest(self):
        return json.loads((self.output / "export-manifest.json").read_text(encoding="utf-8"))

    def test_all_records_states_ids_and_original_text_are_retained(self):
        before = self.source.read_bytes()
        result = exporter.export_bundle(self.source, self.output)
        self.assertEqual(before, self.source.read_bytes())
        self.assertEqual(result["rows"], 9)
        with closing(sqlite3.connect(self.output / "patent.sqlite")) as db:
            self.assertEqual(db.execute("SELECT id FROM applications ORDER BY id").fetchall(), [("APP1",), ("APP2",), ("APP3",)])
            statuses = [json.loads(row[0])["status"] for row in db.execute("SELECT data FROM population_reviews ORDER BY application_id")]
            self.assertEqual(statuses, ["included", "pending", "excluded"])
            text, text_hash, metadata = db.execute("SELECT text,text_hash,data FROM documents").fetchone()
            self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), text_hash)
            self.assertFalse(json.loads(metadata)["qualified"])
            self.assertEqual(db.execute("PRAGMA foreign_key_check").fetchall(), [])
        apps = [json.loads(line) for line in (self.output / "tables/applications.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertIsInstance(apps[0]["data"], dict)
        self.assertEqual(apps[1]["data"]["legal_status"], "unknown")
        manifest = self.read_manifest()
        self.assertFalse(manifest["materials_manifest_supplied"])
        self.assertFalse(manifest["original_gate_replay_ready"])
        self.assertTrue((self.output / "csv/applications.csv").is_file())
        self.assertEqual(manifest["transformations"]["unpackaged_local_reference"], 1)
        for entry in manifest["files"]:
            self.assertEqual(exporter.hash_file(self.output / entry["path"]), entry["sha256"])

    def test_consistent_backup_includes_committed_wal(self):
        db = sqlite3.connect(self.source)
        self.addCleanup(db.close)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("INSERT INTO applications VALUES (?,?)", ("WAL1", '{"legal_status":"unknown"}'))
        db.commit()
        self.assertTrue(Path(str(self.source) + "-wal").is_file())
        exporter.export_bundle(self.source, self.output)
        with closing(sqlite3.connect(self.output / "patent.sqlite")) as exported:
            self.assertEqual(exported.execute("SELECT count(*) FROM applications WHERE id='WAL1'").fetchone()[0], 1)

    def test_redacts_nested_receipts_queries_inline_secrets_paths_and_blobs(self):
        sentinels = ["NESTED_SECRET_739", "SIGNED_SECRET_830", "PASSWORD_SECRET_945", "INLINE_SECRET_983", "OPAQUE_SECRET_521", "ACCOUNT_SECRET_472", "VALUE_SECRET_610", "user-private-token"]
        value = {"authorization": sentinels[0], "url": "https://name:" + sentinels[2] + "@example.test/p?a=1&X-Amz-Signature=" + sentinels[1], "machine": "C:/Users/user-private-token/raw.json", "unix": "/home/user-private-token/private.json", "note": "api_key=" + sentinels[3], "nested": json.dumps({"account_id": sentinels[5]})}
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("INSERT INTO meta VALUES (?,?)", ("source-receipt", json.dumps(value)))
            db.execute("INSERT INTO meta VALUES (?,?)", ("api_key", sentinels[6]))
            db.execute("CREATE TABLE binary_receipts(id TEXT PRIMARY KEY, body BLOB NOT NULL)")
            db.execute("INSERT INTO binary_receipts VALUES (?,?)", ("RECEIPT1", sentinels[4].encode()))
        before = self.source.read_bytes()
        exporter.export_bundle(self.source, self.output)
        self.assertEqual(before, self.source.read_bytes())
        for path in self.output.rglob("*"):
            if path.is_file():
                for secret in sentinels:
                    self.assertNotIn(secret.encode(), path.read_bytes(), path.name)
        with closing(sqlite3.connect(self.output / "patent.sqlite")) as db:
            self.assertEqual(db.execute("SELECT body FROM binary_receipts").fetchone()[0], b"")
            cleaned = json.loads(db.execute("SELECT value FROM meta WHERE key='source-receipt'").fetchone()[0])
            self.assertEqual(cleaned["url"], "https://example.test/p?a=1")
        self.assertNotEqual(self.read_manifest()["source_backup_sha256"], self.read_manifest()["exported_database_sha256"])

    def test_explicit_materials_are_relative_and_portable(self):
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "market.json").write_text(json.dumps({"source_id": "M1", "model": "Synthetic product", "api_key": "MARKET_SECRET", "evidence": ["public statement"]}), encoding="utf-8")
        (assets / "analysis.json").write_text(json.dumps({"application_id": "APP1", "source_ids": ["M1"], "source_artifact": "market.json"}), encoding="utf-8")
        png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZMsAAAAASUVORK5CYII=")
        (assets / "figure.png").write_bytes(png)
        materials = self.manifest([{"id": "market-source", "category": "market", "path": "market.json", "source_ids": ["M1"]}, {"id": "analysis-source", "category": "analysis", "path": "analysis.json"}, {"id": "figure", "category": "patent", "path": "figure.png", "binary_reviewed": True}])
        exporter.export_bundle(self.source, self.output, materials)
        moved = self.root / "moved"
        shutil.move(self.output, moved)
        analysis = json.loads((moved / "materials/analysis/analysis-source.json").read_text(encoding="utf-8"))
        self.assertEqual(analysis["source_artifact"], "materials/market/market-source.json")
        self.assertTrue((moved / analysis["source_artifact"]).is_file())
        self.assertEqual((moved / "materials/patent/figure.png").read_bytes(), png)
        manifest = json.loads((moved / "export-manifest.json").read_text(encoding="utf-8"))
        for item in manifest["materials"]:
            self.assertEqual(exporter.hash_file(moved / item["path"]), item["exported_sha256"])
        self.assertTrue(next(item for item in manifest["materials"] if item["id"] == "market-source")["transformed"])

    def test_optional_invalid_material_is_omitted_before_link_rewrite(self):
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "linked.json").write_text('{"source_artifact":"broken.json"}', encoding="utf-8")
        (assets / "broken.json").write_text("not json", encoding="utf-8")
        materials = self.manifest([{"id": "linked", "category": "analysis", "path": "linked.json"}, {"id": "broken", "category": "records", "path": "broken.json", "required": False}])
        result = exporter.export_bundle(self.source, self.output, materials)
        self.assertEqual(result["omitted_materials"], 1)
        content = json.loads((self.output / "materials/analysis/linked.json").read_text(encoding="utf-8"))
        self.assertEqual(content["source_artifact"], "[UNPACKAGED_LOCAL_REFERENCE]")

    def test_required_failure_leaves_no_output_or_temporary_folder(self):
        (self.root / "assets").mkdir()
        materials = self.manifest([{"id": "missing", "category": "market", "path": "missing.json"}])
        with self.assertRaises(exporter.ExportError):
            exporter.export_bundle(self.source, self.output, materials)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".reuse-export-*")))

    def test_material_escape_rejected(self):
        (self.root / "assets").mkdir()
        materials = self.manifest([{"id": "escape", "category": "market", "path": "../source.sqlite"}])
        with self.assertRaises(exporter.ExportError):
            exporter.export_bundle(self.source, self.output, materials)
        self.assertFalse(self.output.exists())

    def test_binary_requires_actual_review_flag(self):
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "document.pdf").write_bytes(b"%PDF-1.7\nsynthetic fixture\n%%EOF")
        materials = self.manifest([{"id": "pdf", "category": "patent", "path": "document.pdf"}])
        with self.assertRaises(exporter.ExportError):
            exporter.export_bundle(self.source, self.output, materials)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        (self.output / "existing.txt").write_text("keep", encoding="utf-8")
        with self.assertRaises(exporter.ExportError):
            exporter.export_bundle(self.source, self.output)
        self.assertEqual((self.output / "existing.txt").read_text(), "keep")

    def test_html_material_is_delivered_as_inert_source_text(self):
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "source.html").write_text('<html><script>alert("untrusted source")</script><p>Public fact</p></html>', encoding="utf-8")
        materials = self.manifest([{"id": "webpage", "category": "market", "path": "source.html"}])
        exporter.export_bundle(self.source, self.output, materials)
        material = self.read_manifest()["materials"][0]
        self.assertTrue(material["path"].endswith(".html.txt"))
        self.assertEqual(material["delivery_mode"], "inert_source_text")
        self.assertIn("Public fact", (self.output / material["path"]).read_text(encoding="utf-8"))

    def test_current_engine_database_schema_exports_all_user_tables(self):
        import test_integrity as fixtures
        case = fixtures.IntegrityTests(methodName="test_missing_fulltext_never_completes_or_renders")
        case.setUp()
        try:
            case.seed()
            case.document()
            case.db.commit()
            expected = {row[0]: case.db.execute('SELECT count(*) FROM "' + row[0] + '"').fetchone()[0] for row in case.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            exporter.export_bundle(case.dbpath, self.output)
            actual = {entry["table"]: entry["rows"] for entry in self.read_manifest()["tables"]}
            self.assertEqual(actual, expected)
            self.assertGreaterEqual(len(actual), 20)
        finally:
            case.doCleanups()

    def test_sensitive_primary_key_is_rejected_without_partial_output(self):
        with closing(sqlite3.connect(self.source)) as db, db:
            db.execute("INSERT INTO applications VALUES (?,?)", ("C:/Users/private/identity.json", "{}"))
        with self.assertRaises(exporter.ExportError):
            exporter.export_bundle(self.source, self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".reuse-export-*")))

    def test_invalid_database_leaves_no_output_or_open_file(self):
        invalid = self.root / "invalid.sqlite"
        invalid.write_bytes(b"not a sqlite database")
        with self.assertRaises(sqlite3.DatabaseError):
            exporter.export_bundle(invalid, self.output)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".reuse-export-*")))

    def test_markdown_links_images_and_reference_definitions_survive_move(self):
        assets = self.root / "assets"
        for child in ("records", "market", "figures"):
            (assets / child).mkdir(parents=True)
        source = assets / "records/note.md"
        original = ('# Notes\n'
                    '[Market source](../market/source.json#facts)\n'
                    '![Figure](../figures/figure.png?download=1#view "Original figure")\n'
                    '[Reference][market]\n\n[market]: <../market/source.json> "Source title"\n'
                    '[Public website](https://example.test/catalog?a=1#part) and [Here](#notes)\n'
                    '`[Code example](not-a-material.json)`\n'
                    '```md\n[Code block](not-a-material.json)\n```\n')
        source.write_text(original, encoding="utf-8")
        (assets / "market/source.json").write_text('{"source_id":"M1"}', encoding="utf-8")
        (assets / "figures/figure.png").write_bytes(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZMsAAAAASUVORK5CYII="))
        materials = self.manifest([
            {"id": "analysis-records", "category": "records", "path": "records/note.md"},
            {"id": "market-01", "category": "market", "path": "market/source.json"},
            {"id": "figure-01", "category": "patent", "path": "figures/figure.png", "binary_reviewed": True},
        ])
        exporter.export_bundle(self.source, self.output, materials)
        moved = self.root / "relocated-reuse"
        shutil.move(self.output, moved)
        note = moved / "materials/records/analysis-records.md"
        actual = note.read_text(encoding="utf-8")
        self.assertIn('[Market source](../market/market-01.json#facts)', actual)
        self.assertIn('![Figure](../patent/figure-01.png?download=1#view "Original figure")', actual)
        self.assertIn('[market]: <../market/market-01.json> "Source title"', actual)
        for relative in ("../market/market-01.json", "../patent/figure-01.png"):
            self.assertTrue((note.parent / relative).resolve().is_file())
        self.assertIn('[Public website](https://example.test/catalog?a=1#part)', actual)
        self.assertIn('[Here](#notes)', actual)
        self.assertIn('`[Code example](not-a-material.json)`', actual)
        self.assertIn('```md\n[Code block](not-a-material.json)\n```', actual)
        self.assertEqual(source.read_text(encoding="utf-8"), original)
        manifest = json.loads((moved / "export-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["transformations"]["markdown_asset_reference_relocated"], 3)
        self.assertNotIn("markdown_local_reference_unavailable", manifest["transformations"])

    def test_unlisted_or_outside_markdown_targets_are_marked_without_reading(self):
        assets = self.root / "assets"
        assets.mkdir()
        (assets / "note.md").write_text('[Missing](unlisted.json)\n![Missing figure](image.png)\n[Outside](../outside.json)\n', encoding="utf-8")
        (assets / "unlisted.json").write_text('{"private":"UNLISTED_MATERIAL_SENTINEL"}', encoding="utf-8")
        (self.root / "outside.json").write_text('{"private":"OUTSIDE_MATERIAL_SENTINEL"}', encoding="utf-8")
        materials = self.manifest([{"id": "analysis-records", "category": "records", "path": "note.md"}])
        exporter.export_bundle(self.source, self.output, materials)
        note = (self.output / "materials/records/analysis-records.md").read_text(encoding="utf-8")
        self.assertEqual(note.count("关联材料未打包"), 3)
        self.assertNotIn("](unlisted.json)", note)
        self.assertNotIn("](../outside.json)", note)
        manifest = self.read_manifest()
        self.assertEqual(manifest["transformations"]["markdown_local_reference_unavailable"], 3)
        for path in self.output.rglob("*"):
            if path.is_file():
                self.assertNotIn(b"UNLISTED_MATERIAL_SENTINEL", path.read_bytes())
                self.assertNotIn(b"OUTSIDE_MATERIAL_SENTINEL", path.read_bytes())


if __name__ == "__main__":
    unittest.main()
