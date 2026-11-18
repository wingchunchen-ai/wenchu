from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from knowledge_schema import (
    ExistingDatabaseError,
    approved_aliases,
    approved_experiences,
    approved_recipe_versions,
    format_relevant_knowledge,
    initialize_database,
    mark_recipe_version_changed,
    open_database,
    retrieve_relevant_knowledge,
    record_experience_review,
    record_recipe_version_review,
    record_source_link_check,
    record_source_rights_review,
)

NOW = "2026-11-18T15:00:00Z"
FUTURE = "2027-01-01T00:00:00Z"
PAST = "2026-11-17T00:00:00Z"


class KnowledgeSchemaTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tempdir.name) / "prototype.sqlite3"
        self.applied = initialize_database(self.db_path)
        self.conn = open_database(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.tempdir.cleanup()

    def add_recipe(self, recipe_id="r1", version_id="rv1", review_status="approved", next_review=FUTURE):
        self.conn.execute(
            "INSERT INTO Recipe(recipe_id, standard_name) VALUES (?, ?)",
            (recipe_id, "测试菜"),
        )
        self.conn.execute("""
            INSERT INTO RecipeVersion
                (recipe_version_id, recipe_id, version_no, review_status, reviewed_at, next_review_at)
            VALUES (?, ?, 1, ?, ?, ?)
        """, (version_id, recipe_id, review_status, NOW, next_review))

    def add_source_and_evidence(self, source_id, target_type, target_id, *, url="https://example.test/source",
                                source_status="accessible", next_link=FUTURE,
                                rights_status="approved", usage_policy="summary_only"):
        self.conn.execute("""
            INSERT INTO KnowledgeSource
                (source_id, source_type, title, url, usage_policy, rights_basis,
                 source_status, link_checked_at, next_link_check_at,
                 review_status, reviewed_at, next_review_at,
                 rights_review_status, rights_reviewed_at, next_rights_review_at)
            VALUES (?, 'web', 'Test source', ?, ?, 'verified basis', ?, ?, ?,
                    'approved', ?, ?, ?, ?, ?)
        """, (source_id, url, usage_policy,
              source_status, NOW if url else None, next_link if url else None,
              NOW, FUTURE, rights_status, NOW, FUTURE))
        self.conn.execute("""
            INSERT INTO EvidenceLink
                (evidence_id, source_id, target_type, target_id, locator, our_summary, review_status, reviewed_at)
            VALUES (?, ?, ?, ?, 'section-1', 'Our independently written summary', 'approved', ?)
        """, (f"e-{source_id}", source_id, target_type, target_id, NOW))

    def test_initialization_is_idempotent_and_does_not_seed_examples(self):
        self.assertEqual(len(self.applied), 3)
        self.assertEqual(initialize_database(self.db_path), [])
        count = self.conn.execute("SELECT COUNT(*) FROM Recipe").fetchone()[0]
        self.assertEqual(count, 0)
        migrations = self.conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        self.assertEqual(migrations, 3)
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_nonempty_unmanaged_database_is_left_untouched(self):
        legacy_path = Path(self.tempdir.name) / "legacy.sqlite3"
        legacy = sqlite3.connect(legacy_path)
        legacy.execute("CREATE TABLE recipes(id INTEGER PRIMARY KEY, name TEXT)")
        legacy.execute("INSERT INTO recipes VALUES (1, 'keep me')")
        legacy.commit()
        legacy.close()

        with self.assertRaises(ExistingDatabaseError):
            initialize_database(legacy_path)

        legacy = sqlite3.connect(legacy_path)
        self.assertEqual(legacy.execute("SELECT name FROM recipes").fetchone()[0], "keep me")
        self.assertIsNone(legacy.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone())
        legacy.close()

    def test_foreign_keys_and_recipe_relationships(self):
        self.add_recipe(review_status="draft", next_review=None)
        self.conn.execute("INSERT INTO Ingredient(ingredient_id, canonical_name) VALUES ('i1', '测试食材')")
        self.conn.execute("""
            INSERT INTO RecipeIngredient(recipe_ingredient_id, recipe_version_id, ingredient_id, amount, unit)
            VALUES ('ri1', 'rv1', 'i1', 25, 'g')
        """)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM RecipeIngredient WHERE recipe_version_id='rv1'").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("""
                INSERT INTO RecipeIngredient(recipe_ingredient_id, recipe_version_id, ingredient_id)
                VALUES ('ri-missing', 'no-such-version', 'i1')
            """)

    def test_recipe_retrieval_requires_approved_package_and_valid_source(self):
        self.add_recipe()
        self.add_source_and_evidence("s1", "recipe_version", "rv1")
        self.assertEqual([row["recipe_version_id"] for row in approved_recipe_versions(self.conn, NOW)], ["rv1"])

        self.conn.execute("UPDATE KnowledgeSource SET next_link_check_at=? WHERE source_id='s1'", (PAST,))
        self.assertEqual(approved_recipe_versions(self.conn, NOW), [])
        self.conn.execute("UPDATE KnowledgeSource SET next_link_check_at=? WHERE source_id='s1'", (FUTURE,))
        self.conn.execute("UPDATE KnowledgeSource SET rights_review_status='revoked' WHERE source_id='s1'")
        self.assertEqual(approved_recipe_versions(self.conn, NOW), [])
        self.conn.execute("UPDATE KnowledgeSource SET rights_review_status='approved' WHERE source_id='s1'")
        self.conn.execute("UPDATE RecipeVersion SET next_review_at=? WHERE recipe_version_id='rv1'", (PAST,))
        self.assertEqual(approved_recipe_versions(self.conn, NOW), [])

    def test_internal_only_and_unreviewed_evidence_are_not_returned(self):
        self.add_recipe()
        self.add_source_and_evidence("s1", "recipe_version", "rv1", usage_policy="internal_only")
        self.assertEqual(approved_recipe_versions(self.conn, NOW), [])
        self.conn.execute("UPDATE KnowledgeSource SET usage_policy='summary_only' WHERE source_id='s1'")
        self.conn.execute("UPDATE EvidenceLink SET review_status='pending_review' WHERE evidence_id='e-s1'")
        self.assertEqual(approved_recipe_versions(self.conn, NOW), [])

    def test_aliases_must_be_separately_approved_and_live(self):
        self.conn.execute("INSERT INTO Recipe(recipe_id, standard_name) VALUES ('r1', '测试菜')")
        self.conn.execute("""
            INSERT INTO RecipeAlias(alias_id, recipe_id, alias_text, normalized_alias_text, next_review_at)
            VALUES ('a1', 'r1', '测试叫法', '测试叫法', ?)
        """, (FUTURE,))
        self.assertEqual(approved_aliases(self.conn, NOW), [])
        self.conn.execute("UPDATE RecipeAlias SET review_status='approved' WHERE alias_id='a1'")
        self.assertEqual(approved_aliases(self.conn, NOW)[0]["alias_text"], "测试叫法")
        self.conn.execute("UPDATE RecipeAlias SET next_review_at=? WHERE alias_id='a1'", (PAST,))
        self.assertEqual(approved_aliases(self.conn, NOW), [])

    def test_experience_retrieval_uses_its_own_review_and_evidence(self):
        self.conn.execute("""
            INSERT INTO Experience
                (experience_id, title, claim, review_status, reviewed_at, next_review_at)
            VALUES ('x1', '经验', '待核验主张', 'approved', ?, ?)
        """, (NOW, FUTURE))
        self.add_source_and_evidence("sx", "experience", "x1")
        self.assertEqual([x["experience_id"] for x in approved_experiences(self.conn, NOW)], ["x1"])
        self.conn.execute("UPDATE EvidenceLink SET review_status='needs_update' WHERE evidence_id='e-sx'")
        self.assertEqual(approved_experiences(self.conn, NOW), [])

    def test_relevant_retrieval_is_exact_and_requires_approved_master_data(self):
        self.add_recipe(review_status="draft", next_review=None)
        self.conn.execute("""
            INSERT INTO Ingredient(ingredient_id, canonical_name, review_status, next_review_at)
            VALUES ('i1', '盐', 'draft', ?)
        """, (FUTURE,))
        self.conn.execute("""
            INSERT INTO RecipeIngredient(recipe_ingredient_id, recipe_version_id, ingredient_id, amount, unit, role)
            VALUES ('ri1', 'rv1', 'i1', 2, 'g', '调味')
        """)
        self.add_source_and_evidence("s1", "recipe_version", "rv1")
        record_recipe_version_review(self.conn, "rv1", "approved", reviewer_id="r1", reviewed_at=NOW)

        # A package approval does not approve its reusable ingredient master record.
        self.assertEqual(approved_recipe_versions(self.conn, NOW), [])
        self.assertEqual(retrieve_relevant_knowledge(self.conn, "测试菜", now=NOW), {})
        self.conn.execute("UPDATE Ingredient SET review_status='approved' WHERE ingredient_id='i1'")
        knowledge = retrieve_relevant_knowledge(self.conn, "测试菜", now=NOW)
        self.assertEqual(knowledge["recipe"]["standard_name"], "测试菜")
        self.assertEqual(knowledge["recipe"]["ingredients"][0]["canonical_name"], "盐")
        self.assertIn("审核有效", format_relevant_knowledge(knowledge))
        self.assertEqual(retrieve_relevant_knowledge(self.conn, "别的菜", now=NOW), {})

        self.conn.execute("""
            INSERT INTO RecipeAlias
                (alias_id, recipe_id, alias_text, normalized_alias_text, review_status, next_review_at)
            VALUES ('a1', 'r1', '测试别名', '测试别名', 'approved', ?)
        """, (FUTURE,))
        self.assertEqual(
            retrieve_relevant_knowledge(self.conn, "测试别名", now=NOW)["recipe"]["recipe_version_id"],
            "rv1",
        )

    def test_approved_package_can_be_reopened_and_audited(self):
        self.add_recipe(review_status="draft", next_review=None)
        self.assertTrue(record_recipe_version_review(
            self.conn, "rv1", "approved", reviewer_id="reviewer-1", reason="source checked", reviewed_at=NOW
        ))
        row = self.conn.execute(
            "SELECT review_status, next_review_at FROM RecipeVersion WHERE recipe_version_id='rv1'"
        ).fetchone()
        self.assertEqual(row["review_status"], "approved")
        self.assertEqual(row["next_review_at"], "2027-02-16T15:00:00Z")

        self.assertTrue(mark_recipe_version_changed(self.conn, "rv1", "ingredient amount changed", changed_at=NOW))
        self.assertEqual(self.conn.execute(
            "SELECT review_status FROM RecipeVersion WHERE recipe_version_id='rv1'"
        ).fetchone()[0], "needs_update")
        records = self.conn.execute(
            "SELECT decision, previous_status, new_status FROM ReviewRecord ORDER BY review_id"
        ).fetchall()
        self.assertEqual([row["decision"] for row in records], ["approved", "reopened"])
        self.assertEqual(records[-1]["previous_status"], "approved")
        self.assertEqual(records[-1]["new_status"], "needs_update")
        self.assertFalse(mark_recipe_version_changed(self.conn, "rv1", "another edit", changed_at=NOW))

    def test_database_trigger_reopens_package_after_relation_edit(self):
        self.add_recipe(review_status="draft", next_review=None)
        self.conn.execute("INSERT INTO Ingredient(ingredient_id, canonical_name) VALUES ('i1', '测试食材')")
        self.assertTrue(record_recipe_version_review(
            self.conn, "rv1", "approved", reviewer_id="reviewer-1", reason="checked", reviewed_at=NOW
        ))
        self.conn.execute("""
            INSERT INTO RecipeIngredient(recipe_ingredient_id, recipe_version_id, ingredient_id, amount, unit)
            VALUES ('ri1', 'rv1', 'i1', 25, 'g')
        """)
        self.assertEqual(self.conn.execute(
            "SELECT review_status FROM RecipeVersion WHERE recipe_version_id='rv1'"
        ).fetchone()[0], "needs_update")
        row = self.conn.execute("""
            SELECT decision, previous_status, new_status FROM ReviewRecord
            WHERE target_type='recipe_version' ORDER BY review_id DESC LIMIT 1
        """).fetchone()
        self.assertEqual(tuple(row), ("reopened", "approved", "needs_update"))

    def test_database_trigger_reopens_experience_after_applicability_edit(self):
        self.conn.execute("""
            INSERT INTO Experience
                (experience_id, title, claim, review_status, reviewed_at, next_review_at)
            VALUES ('x1', '经验', '主张', 'approved', ?, ?)
        """, (NOW, FUTURE))
        self.conn.execute("INSERT INTO Cookware(cookware_id, canonical_name) VALUES ('cw1', '测试锅')")
        self.conn.execute("""
            INSERT INTO ExperienceCookware(experience_cookware_id, experience_id, cookware_id)
            VALUES ('xc1', 'x1', 'cw1')
        """)
        self.assertEqual(self.conn.execute(
            "SELECT review_status FROM Experience WHERE experience_id='x1'"
        ).fetchone()[0], "needs_update")

    def test_database_trigger_reopens_package_when_header_changes(self):
        self.add_recipe()
        self.conn.execute("UPDATE RecipeVersion SET servings=3 WHERE recipe_version_id='rv1'")
        self.assertEqual(self.conn.execute(
            "SELECT review_status FROM RecipeVersion WHERE recipe_version_id='rv1'"
        ).fetchone()[0], "needs_update")

    def test_manual_reopen_rolls_back_if_audit_write_fails(self):
        self.add_recipe()
        self.conn.execute("""
            CREATE TRIGGER fail_review_audit BEFORE INSERT ON ReviewRecord
            WHEN NEW.target_type='recipe_version'
            BEGIN SELECT RAISE(ABORT, 'simulated audit failure'); END
        """)
        with self.assertRaises(sqlite3.IntegrityError):
            mark_recipe_version_changed(self.conn, "rv1", "change", changed_at=NOW)
        status = self.conn.execute(
            "SELECT review_status FROM RecipeVersion WHERE recipe_version_id='rv1'"
        ).fetchone()[0]
        self.assertEqual(status, "approved")

    def test_experience_review_sets_90_day_expiry_and_content_edit_reopens(self):
        self.conn.execute("""
            INSERT INTO Experience(experience_id, title, claim)
            VALUES ('x1', '经验', '草稿主张')
        """)
        self.assertTrue(record_experience_review(
            self.conn, "x1", "approved", reviewer_id="reviewer-1", reason="checked", reviewed_at=NOW
        ))
        row = self.conn.execute(
            "SELECT review_status, next_review_at FROM Experience WHERE experience_id='x1'"
        ).fetchone()
        self.assertEqual(row["review_status"], "approved")
        self.assertEqual(row["next_review_at"], "2027-02-16T15:00:00Z")
        self.conn.execute("UPDATE Experience SET claim='主张有实质更新' WHERE experience_id='x1'")
        self.assertEqual(self.conn.execute(
            "SELECT review_status FROM Experience WHERE experience_id='x1'"
        ).fetchone()[0], "needs_update")

    def test_source_link_and_rights_reviews_are_separate(self):
        self.add_recipe()
        self.add_source_and_evidence("s1", "recipe_version", "rv1")
        self.assertTrue(record_source_link_check(self.conn, "s1", False, reviewer_id="reviewer-1", checked_at=NOW))
        row = self.conn.execute("""
            SELECT source_status, next_link_check_at, review_status, rights_review_status
            FROM KnowledgeSource WHERE source_id='s1'
        """).fetchone()
        self.assertEqual(row["source_status"], "inaccessible")
        self.assertEqual(row["next_link_check_at"], "2026-12-18T15:00:00Z")
        self.assertEqual(row["review_status"], "approved")
        self.assertEqual(row["rights_review_status"], "approved")

        self.assertTrue(record_source_rights_review(
            self.conn, "s1", "revoked", reviewer_id="reviewer-2", reason="permission withdrawn", reviewed_at=NOW
        ))
        row = self.conn.execute("""
            SELECT source_status, review_status, rights_review_status
            FROM KnowledgeSource WHERE source_id='s1'
        """).fetchone()
        self.assertEqual(tuple(row), ("inaccessible", "approved", "revoked"))
        self.assertEqual(approved_recipe_versions(self.conn, NOW), [])

    def test_unconsented_analysis_cannot_store_reusable_content(self):
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute("""
                INSERT INTO AnalysisRecord(analysis_id, analysis_json, consent_to_share)
                VALUES ('a1', '{"steps":[]}', 0)
            """)
        self.conn.execute("INSERT INTO AnalysisRecord(analysis_id) VALUES ('a2')")
        row = self.conn.execute(
            "SELECT consent_to_share, review_status, analysis_json FROM AnalysisRecord WHERE analysis_id='a2'"
        ).fetchone()
        self.assertEqual(tuple(row), (0, "pending_review", None))


if __name__ == "__main__":
    unittest.main()
