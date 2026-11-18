from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from import_legacy_demo import ImportConflict, import_legacy
from knowledge_schema import approved_recipe_versions, initialize_database, open_database


class LegacyImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.source = root / "legacy.sqlite3"
        self.dest = root / "formal.sqlite3"
        c = sqlite3.connect(self.source)
        c.executescript("""
            CREATE TABLE cooking_categories(template_id INTEGER PRIMARY KEY, category TEXT NOT NULL, description TEXT NOT NULL);
            CREATE TABLE recipes(id INTEGER PRIMARY KEY, name TEXT NOT NULL, template_id INTEGER NOT NULL, description TEXT NOT NULL, summary_safety_tip TEXT NOT NULL, time_minutes INTEGER, image TEXT, user_id INTEGER, tools_list TEXT, ingredients_list TEXT);
            CREATE TABLE recipe_steps(id INTEGER PRIMARY KEY, recipe_id INTEGER NOT NULL, step_no INTEGER NOT NULL, title TEXT NOT NULL, action TEXT NOT NULL, tools TEXT NOT NULL, tool_usage TEXT NOT NULL, safety_tip TEXT NOT NULL);
        """)
        c.execute("INSERT INTO cooking_categories VALUES (1,'家常','分类说明')")
        c.execute("INSERT INTO recipes VALUES (1,'测试菜',1,'原始描述','注意安全',20,'should-not-be-read',NULL,'锅（大、深）、铲','盐（少量、可选）、葱')")
        c.execute("INSERT INTO recipes VALUES (2,'用户菜',1,'不应导入','',10,'private',7,'锅','盐')")
        c.execute("INSERT INTO recipes VALUES (3,'共享食材菜',1,'第二条菜','安全提示',15,'ignored',NULL,'锅（大、深）、砧板','盐（少量、可选）、蛋')")
        c.execute("INSERT INTO recipe_steps VALUES (11,1,1,'准备','切配、保留原文','锅（大、深）','原始用法','小心')")
        c.execute("INSERT INTO recipe_steps VALUES (12,2,1,'用户步骤','不应导入','锅','','')")
        c.execute("INSERT INTO recipe_steps VALUES (13,3,1,'共享用具','另一道菜','锅（大、深）','工具说明','注意')")
        c.commit(); c.close()

    def tearDown(self):
        self.tmp.cleanup()

    def _conn(self):
        return open_database(self.dest)

    def test_curated_only_unreviewed_and_structured(self):
        source_before = self.source.stat()
        result = import_legacy(self.source, self.dest)
        source_after = self.source.stat()
        self.assertEqual(result["recipes"], 2)
        self.assertEqual(result["steps"], 2)
        self.assertEqual((source_before.st_size, source_before.st_mtime_ns),
                         (source_after.st_size, source_after.st_mtime_ns))
        c = self._conn()
        try:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM Recipe").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM Recipe WHERE standard_name='用户菜'").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM RecipeStep").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM LegacyImportLedger").fetchone()[0], 5)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM RecipeVersion WHERE review_status='draft'").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM Experience WHERE review_status='pending_review'").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM RecipeCategory WHERE review_status='draft'").fetchone()[0], 1)
            self.assertTrue(all(r[0] == 'draft' for r in c.execute("SELECT review_status FROM Ingredient")))
            self.assertTrue(all(r[0] == 'draft' for r in c.execute("SELECT review_status FROM Cookware")))
            self.assertTrue(all(r[0] == 'draft' for r in c.execute("SELECT review_status FROM EvidenceLink")))
            self.assertEqual(tuple(c.execute("SELECT usage_policy,source_status,rights_review_status FROM KnowledgeSource").fetchone()), ("internal_only", "not_applicable", "pending_review"))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM Ingredient WHERE canonical_name='盐（少量、可选）'").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM Cookware WHERE canonical_name='锅（大、深）'").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM EvidenceLink WHERE target_type='experience'").fetchone()[0], 2)
            self.assertEqual(approved_recipe_versions(c), [])
            c.execute("PRAGMA foreign_key_check")
            self.assertFalse(c.execute("PRAGMA foreign_key_check").fetchall())
        finally:
            c.close()

    def test_repeat_is_idempotent_and_dry_run_rolls_back(self):
        initialize_database(self.dest)
        before = sqlite3.connect(self.dest)
        before_counts = before.execute("SELECT COUNT(*) FROM Recipe").fetchone()[0]
        before.close()
        dry = import_legacy(self.source, self.dest, dry_run=True)
        self.assertEqual(dry["recipes"], 2)
        c = self._conn(); self.assertEqual(c.execute("SELECT COUNT(*) FROM Recipe").fetchone()[0], before_counts); c.close()
        import_legacy(self.source, self.dest)
        c = self._conn()
        version_id = c.execute("SELECT recipe_version_id FROM RecipeVersion ORDER BY recipe_version_id LIMIT 1").fetchone()[0]
        c.execute("UPDATE RecipeVersion SET change_note='人工补充，保持本地修改' WHERE recipe_version_id=?", (version_id,))
        c.commit(); c.close()
        import_legacy(self.source, self.dest)
        c = self._conn()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM Recipe").fetchone()[0], 2)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM LegacyImportLedger").fetchone()[0], 5)
        self.assertIn("人工补充", c.execute("SELECT change_note FROM RecipeVersion WHERE recipe_version_id=?", (version_id,)).fetchone()[0])
        self.assertEqual(import_legacy(self.source, self.dest)["skipped"], 5)
        c.close()

    def test_source_drift_aborts_without_partial_changes(self):
        import_legacy(self.source, self.dest)
        c = sqlite3.connect(self.source)
        c.execute("UPDATE recipes SET description='漂移' WHERE id=1"); c.commit(); c.close()
        with self.assertRaises(ImportConflict):
            import_legacy(self.source, self.dest)
        c = self._conn()
        self.assertEqual(c.execute("SELECT COUNT(*) FROM Recipe").fetchone()[0], 2)
        self.assertEqual(c.execute("SELECT COUNT(*) FROM LegacyImportLedger").fetchone()[0], 5)
        c.close()


if __name__ == "__main__":
    unittest.main()
