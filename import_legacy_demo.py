"""Explicit, transactional import of curated records from the legacy demo DB.

Importing this module has no side effects. The source is always opened read-only;
images and user/profile data are intentionally ignored.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from knowledge_schema import DEFAULT_DB_PATH, initialize_database, open_database

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCE = BASE_DIR / "厨房数据库.sqlite3"
SOURCE_SYSTEM = "legacy_demo"
SOURCE_ID = "legacy-source-public-demo"


class ImportConflict(RuntimeError):
    """Source drift or a deterministic target collision requires human review."""


def _id(kind: str, value: Any) -> str:
    return f"legacy-{kind}-{hashlib.sha256(str(value).encode('utf-8')).hexdigest()[:24]}"


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _tokens(value: Any) -> list[str]:
    """Split top-level Chinese enumeration commas, preserving free text exactly."""
    text = _text(value).strip()
    if not text:
        return []
    result: list[str] = []
    buf: list[str] = []
    depth = 0
    pairs = {"(": ")", "（": "）", "[": "]", "【": "】", "{": "}"}
    closing = set(pairs.values())
    for char in text:
        if char in pairs:
            depth += 1
        elif char in closing:
            depth = max(0, depth - 1)
        if char == "、" and depth == 0:
            token = "".join(buf).strip()
            if token:
                result.append(token)
            buf = []
        else:
            buf.append(char)
    token = "".join(buf).strip()
    if token:
        result.append(token)
    return list(dict.fromkeys(result))


def _json_hash(record: dict[str, Any]) -> str:
    raw = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _row_hash(row: sqlite3.Row, fields: tuple[str, ...]) -> str:
    return _json_hash({field: row[field] for field in fields})


def _source(path: Path) -> sqlite3.Connection:
    source_uri = path.expanduser().resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(source_uri, uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def _ledger(conn: sqlite3.Connection, record_id: str):
    return conn.execute(
        "SELECT * FROM LegacyImportLedger WHERE source_system=? AND source_record_id=?",
        (SOURCE_SYSTEM, record_id),
    ).fetchone()


def _flatten_target_ids(value: Any) -> set[str]:
    if isinstance(value, dict):
        result: set[str] = set()
        for child in value.values():
            result.update(_flatten_target_ids(child))
        return result
    if isinstance(value, (list, tuple, set)):
        result: set[str] = set()
        for child in value:
            result.update(_flatten_target_ids(child))
        return result
    if isinstance(value, str):
        return {value}
    return set()


def _known_targets(conn: sqlite3.Connection) -> set[str]:
    known: set[str] = set()
    for row in conn.execute("SELECT target_ids_json FROM LegacyImportLedger WHERE source_system=?", (SOURCE_SYSTEM,)):
        try:
            known.update(_flatten_target_ids(json.loads(row[0])))
        except (TypeError, json.JSONDecodeError):
            raise ImportConflict("import ledger contains invalid target_ids_json")
    return known


def _ensure_entity(
    conn: sqlite3.Connection,
    table: str,
    key_column: str,
    entity_id: str,
    name_column: str,
    name: str,
    known_targets: set[str],
    created_entities: set[str],
    insert_sql: str,
    insert_values: tuple[Any, ...],
) -> None:
    existing = conn.execute(
        f"SELECT {name_column} FROM {table} WHERE {key_column}=?", (entity_id,)
    ).fetchone()
    if existing:
        if entity_id not in known_targets and entity_id not in created_entities:
            raise ImportConflict(f"deterministic target collision without ledger: {table}.{key_column}={entity_id}")
        if existing[0] != name:
            raise ImportConflict(f"imported master data changed locally: {table}.{key_column}={entity_id}")
        return
    name_collision = conn.execute(
        f"SELECT {key_column} FROM {table} WHERE {name_column}=? COLLATE NOCASE", (name,)
    ).fetchone()
    if name_collision:
        raise ImportConflict(f"canonical name already exists under another ID: {table}.{name_column}={name}")
    conn.execute(insert_sql, insert_values)
    created_entities.add(entity_id)


def _insert_ledger(conn: sqlite3.Connection, record_id: str, digest: str, targets: dict[str, Any]) -> None:
    conn.execute("""
        INSERT INTO LegacyImportLedger
            (source_system, source_record_id, source_content_sha256, target_ids_json)
        VALUES (?, ?, ?, ?)
    """, (SOURCE_SYSTEM, record_id, digest,
          json.dumps(targets, ensure_ascii=False, sort_keys=True, separators=(",", ":"))))


def _insert_source_if_needed(conn: sqlite3.Connection, known_targets: set[str]) -> None:
    existing = conn.execute("SELECT source_id FROM KnowledgeSource WHERE source_id=?", (SOURCE_ID,)).fetchone()
    if existing:
        if SOURCE_ID not in known_targets:
            raise ImportConflict(f"deterministic target collision without import ledger: KnowledgeSource={SOURCE_ID}")
        return
    conn.execute("""
        INSERT INTO KnowledgeSource
            (source_id, source_type, title, publisher, url, usage_policy, rights_basis,
             rights_note, source_status, review_status, rights_review_status)
        VALUES (?, 'legacy_demo', 'Legacy demo SQLite', 'Wenchu demo', NULL,
                'internal_only', '', 'Legacy demo import; not externally licensed or reviewed',
                'not_applicable', 'draft', 'pending_review')
    """, (SOURCE_ID,))


def _insert_evidence(conn: sqlite3.Connection, evidence_id: str, target_type: str, target_id: str) -> None:
    conn.execute("""
        INSERT INTO EvidenceLink
            (evidence_id, source_id, target_type, target_id, our_summary, evidence_note, review_status)
        VALUES (?, ?, ?, ?, ?, ?, 'draft')
    """, (evidence_id, SOURCE_ID, target_type, target_id,
          "Local demo content imported for human review; not independently verified",
          "Internal-only legacy source; no external rights or approval claimed"))


def import_legacy(
    source: str | Path = DEFAULT_SOURCE,
    db: str | Path = DEFAULT_DB_PATH,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Import curated demo records only; identical reruns skip and source drift aborts."""
    initialize_database(db)
    dest = open_database(db)
    src = _source(Path(source))
    counts = {
        "recipes": 0, "categories": 0, "steps": 0, "experiences": 0,
        "ingredients": 0, "tools": 0, "evidence": 0, "skipped": 0,
    }
    try:
        categories = src.execute(
            "SELECT template_id,category,description FROM cooking_categories ORDER BY template_id"
        ).fetchall()
        recipes = src.execute("""
            SELECT id,name,template_id,description,summary_safety_tip,time_minutes,
                   tools_list,ingredients_list,user_id
            FROM recipes WHERE user_id IS NULL ORDER BY id
        """).fetchall()
        recipe_ids = [row["id"] for row in recipes]
        if recipe_ids:
            marks = ",".join("?" for _ in recipe_ids)
            steps = src.execute(f"""
                SELECT id,recipe_id,step_no,title,action,tools,tool_usage,safety_tip
                FROM recipe_steps WHERE recipe_id IN ({marks}) ORDER BY recipe_id,step_no,id
            """, recipe_ids).fetchall()
        else:
            steps = []

        items: list[tuple[str, str, dict[str, Any]]] = []
        for row in categories:
            record_id = f"category:{row['template_id']}"
            items.append((record_id, _row_hash(row, ("template_id", "category", "description")),
                          {"kind": "category", "row": row}))
        recipe_fields = (
            "id", "name", "template_id", "description", "summary_safety_tip",
            "time_minutes", "tools_list", "ingredients_list", "user_id",
        )
        for row in recipes:
            record_id = f"recipe:{row['id']}"
            items.append((record_id, _row_hash(row, recipe_fields), {"kind": "recipe", "row": row}))
        step_fields = ("id", "recipe_id", "step_no", "title", "action", "tools", "tool_usage", "safety_tip")
        for row in steps:
            record_id = f"step:{row['id']}"
            items.append((record_id, _row_hash(row, step_fields), {"kind": "step", "row": row}))

        for record_id, digest, _ in items:
            old = _ledger(dest, record_id)
            if old and old["source_content_sha256"] != digest:
                raise ImportConflict(f"source content drift for {record_id}; refusing to overwrite")

        dest.execute("BEGIN IMMEDIATE")
        known_targets = _known_targets(dest)
        known_record_ids = {
            row[0] for row in dest.execute(
                "SELECT source_record_id FROM LegacyImportLedger WHERE source_system=?", (SOURCE_SYSTEM,)
            )
        }
        has_new_content_rows = any(
            data["kind"] != "category" and _ledger(dest, record_id) is None
            for record_id, _, data in items
        )
        if has_new_content_rows:
            _insert_source_if_needed(dest, known_targets)
        created_entities: set[str] = set()
        cat_by_template: dict[Any, str] = {}
        for record_id, digest, data in items:
            old = _ledger(dest, record_id)
            if old:
                counts["skipped"] += 1
                targets = json.loads(old["target_ids_json"])
                if data["kind"] == "category":
                    cat_by_template[data["row"]["template_id"]] = targets["category_id"]
                continue
            row = data["row"]
            targets: dict[str, Any] = {}
            if data["kind"] == "category":
                category_id = _id("category", row["template_id"])
                targets["category_id"] = category_id
                _ensure_entity(
                    dest, "RecipeCategory", "category_id", category_id, "name", _text(row["category"]),
                    known_targets, created_entities,
                    "INSERT INTO RecipeCategory(category_id,name,parent_category_id,review_status) VALUES (?,?,NULL,'draft')",
                    (category_id, _text(row["category"])),
                )
                cat_by_template[row["template_id"]] = category_id
                counts["categories"] += 1
            elif data["kind"] == "recipe":
                recipe_id = _id("recipe", row["id"])
                version_id = _id("version", row["id"])
                targets.update(recipe_id=recipe_id, recipe_version_id=version_id, source_id=SOURCE_ID)
                targets["ingredient_ids"] = []
                targets["tool_ids"] = []
                category_id = cat_by_template.get(row["template_id"])
                if row["template_id"] is not None and category_id is None:
                    raise ImportConflict(f"recipe {row['id']} references missing legacy category {row['template_id']}")
                _ensure_entity(
                    dest, "Recipe", "recipe_id", recipe_id, "standard_name", _text(row["name"]),
                    known_targets, created_entities,
                    "INSERT INTO Recipe(recipe_id,standard_name,category_id,description,record_status) VALUES (?,?,?,?, 'active')",
                    (recipe_id, _text(row["name"]), category_id, _text(row["description"])),
                )
                if not dest.execute("SELECT 1 FROM RecipeVersion WHERE recipe_version_id=?", (version_id,)).fetchone():
                    if version_id not in known_targets:
                        if dest.execute("SELECT 1 FROM RecipeVersion WHERE recipe_version_id=?", (version_id,)).fetchone():
                            raise ImportConflict(f"deterministic target collision without ledger: RecipeVersion={version_id}")
                    dest.execute("""
                        INSERT INTO RecipeVersion
                            (recipe_version_id,recipe_id,version_no,prep_time_minutes,cook_time_minutes,
                             change_note,review_status)
                        VALUES (?,?,1,NULL,?,?, 'draft')
                    """, (version_id, recipe_id, row["time_minutes"],
                          f"Imported from legacy demo recipe {row['id']}; review before use"))
                else:
                    raise ImportConflict(f"untracked RecipeVersion target already exists: {version_id}")

                ingredient_tokens = _tokens(row["ingredients_list"])
                for index, token in enumerate(ingredient_tokens):
                    ingredient_id = _id("ingredient", token)
                    was_known = ingredient_id in known_targets or ingredient_id in created_entities
                    _ensure_entity(
                        dest, "Ingredient", "ingredient_id", ingredient_id, "canonical_name", token,
                        known_targets, created_entities,
                        "INSERT INTO Ingredient(ingredient_id,canonical_name,category_id,default_unit,review_status) VALUES (?,?,NULL,NULL,'draft')",
                        (ingredient_id, token),
                    )
                    if not was_known:
                        counts["ingredients"] += 1
                    targets["ingredient_ids"].append(ingredient_id)
                    dest.execute("""
                        INSERT INTO RecipeIngredient
                            (recipe_ingredient_id,recipe_version_id,ingredient_id,amount,unit,role,prep_note)
                        VALUES (?,?,?,NULL,NULL,'unclassified','Original free-text token; amount and role not inferred')
                    """, (_id("recipe-ingredient", f"{row['id']}:{index}"), version_id, ingredient_id))
                tool_tokens = _tokens(row["tools_list"])
                for index, token in enumerate(tool_tokens):
                    tool_id = _id("tool", token)
                    was_known = tool_id in known_targets or tool_id in created_entities
                    _ensure_entity(
                        dest, "Cookware", "cookware_id", tool_id, "canonical_name", token,
                        known_targets, created_entities,
                        "INSERT INTO Cookware(cookware_id,canonical_name,cookware_type,review_status) VALUES (?,?, 'legacy_unclassified','draft')",
                        (tool_id, token),
                    )
                    if not was_known:
                        counts["tools"] += 1
                    targets["tool_ids"].append(tool_id)
                    dest.execute("""
                        INSERT INTO RecipeCookware
                            (recipe_cookware_id,recipe_version_id,cookware_id,use_role,use_stage,conditions)
                        VALUES (?,?,?,'optional','',?)
                    """, (_id("recipe-tool", f"{row['id']}:{index}"), version_id, tool_id,
                          "Unreviewed placeholder: source did not state requiredness; do not treat optional as fact"))
                self_evidence_id = _id("evidence", f"recipe:{row['id']}")
                targets["recipe_evidence_id"] = self_evidence_id
                _insert_evidence(dest, self_evidence_id, "recipe_version", version_id)
                counts["evidence"] += 1

                tip = _text(row["summary_safety_tip"]).strip()
                if tip:
                    experience_id = _id("experience", f"summary:{row['id']}")
                    experience_evidence_id = _id("evidence", f"experience:{row['id']}")
                    targets["summary_experience_id"] = experience_id
                    targets["experience_evidence_id"] = experience_evidence_id
                    dest.execute("""
                        INSERT INTO Experience
                            (experience_id,title,claim,conditions,review_status,safety_impact)
                        VALUES (?,?,?,?, 'pending_review','important')
                    """, (experience_id, f"{row['name']} safety summary", tip,
                          "Imported verbatim from the legacy demo; safety content requires human review"))
                    dest.execute("""
                        INSERT INTO ExperienceRecipe
                            (experience_recipe_id,experience_id,recipe_id,recipe_version_id,applicability_note)
                        VALUES (?,?,?,?,?)
                    """, (_id("experience-recipe", experience_id), experience_id, recipe_id, version_id,
                          "Imported from the legacy demo's recipe-specific summary"))
                    _insert_evidence(dest, experience_evidence_id, "experience", experience_id)
                    counts["experiences"] += 1
                    counts["evidence"] += 1
                counts["recipes"] += 1
            else:
                version_id = _id("version", row["recipe_id"])
                step_id = _id("step", row["id"])
                targets["step_id"] = step_id
                targets["tool_ids"] = []
                if not dest.execute("SELECT 1 FROM RecipeVersion WHERE recipe_version_id=?", (version_id,)).fetchone():
                    raise ImportConflict(f"step {row['id']} has no imported recipe version {version_id}")
                instruction = (_text(row["title"]) + "：" + _text(row["action"])).strip("：")
                tool_usage = _text(row["tool_usage"]).strip()
                if tool_usage and tool_usage not in instruction:
                    instruction += "；工具用法：" + tool_usage
                dest.execute("""
                    INSERT INTO RecipeStep(step_id,recipe_version_id,step_no,instruction,safety_reminder)
                    VALUES (?,?,?,?,?)
                """, (step_id, version_id, row["step_no"], instruction, _text(row["safety_tip"])))
                for index, token in enumerate(_tokens(row["tools"])):
                    tool_id = _id("tool", token)
                    was_known = tool_id in known_targets or tool_id in created_entities
                    _ensure_entity(
                        dest, "Cookware", "cookware_id", tool_id, "canonical_name", token,
                        known_targets, created_entities,
                        "INSERT INTO Cookware(cookware_id,canonical_name,cookware_type,review_status) VALUES (?,?, 'legacy_unclassified','draft')",
                        (tool_id, token),
                    )
                    if not was_known:
                        counts["tools"] += 1
                    targets["tool_ids"].append(tool_id)
                    dest.execute("INSERT INTO StepCookware(step_id,cookware_id) VALUES (?,?)", (step_id, tool_id))
                step_evidence_id = _id("evidence", f"step:{row['id']}")
                targets["evidence_id"] = step_evidence_id
                _insert_evidence(dest, step_evidence_id, "recipe_step", step_id)
                counts["evidence"] += 1
                counts["steps"] += 1

            _insert_ledger(dest, record_id, digest, targets)
            known_record_ids.add(record_id)
            known_targets.update(_flatten_target_ids(targets))

        if dry_run:
            dest.rollback()
        else:
            dest.commit()
        return counts
    except Exception:
        dest.rollback()
        raise
    finally:
        src.close()
        dest.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读导入旧 demo 菜谱到正式知识库")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = import_legacy(args.source, args.db, dry_run=args.dry_run)
        print(json.dumps({**result, "dry_run": args.dry_run}, ensure_ascii=False, sort_keys=True))
        return 0
    except (sqlite3.Error, OSError, ImportConflict, ValueError) as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
