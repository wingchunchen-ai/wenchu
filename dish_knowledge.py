"""Persistent, image-free history and review queue for the Wenchu demo."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import sqlite3
import unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
KNOWLEDGE_DB_PATH = Path(os.environ.get(
    'WENCHU_KNOWLEDGE_DB', str(BASE_DIR / 'dish_knowledge.sqlite3'))).expanduser()
REVIEW_INTERVAL_DAYS = max(7, int(os.environ.get('WENCHU_KNOWLEDGE_REVIEW_DAYS', '7')))
logger = logging.getLogger(__name__)


def _digest(value: bytes) -> str:
    """Use a keyed fingerprint in deployed environments; never persist raw request inputs."""
    secret = (os.environ.get('WENCHU_KNOWLEDGE_HASH_KEY') or
              os.environ.get('WENCHU_SECRET_KEY') or '').strip()
    if secret:
        return hmac.new(secret.encode('utf-8'), value, hashlib.sha256).hexdigest()
    return hashlib.sha256(value).hexdigest()


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def iso_utc(value: datetime | None = None) -> str:
    return (value or now_utc()).isoformat()


def normalize_text(value: str | None) -> str:
    value = unicodedata.normalize('NFKC', str(value or '')).casefold()
    return ' '.join(value.split())


def normalize_dish_name(value: str | None) -> str:
    value = normalize_text(value)
    return ''.join(ch for ch in value if not ch.isspace() and not unicodedata.category(ch).startswith('P'))


def cookware_signature(cookware_list: list[str] | None) -> str:
    normalized = sorted({normalize_dish_name(item) for item in (cookware_list or []) if normalize_dish_name(item)})
    payload = json.dumps(normalized, ensure_ascii=False, separators=(',', ':'))
    return _digest(payload.encode('utf-8'))


def make_cache_key(dish_name: str, notes: str, cookware_list: list[str], image_bytes: bytes | None = None):
    """Return a keyed exact-request fingerprint; notes and image bytes are never persisted."""
    normalized_name = normalize_dish_name(dish_name)
    identity = {}
    if normalized_name:
        identity['dish_name'] = normalized_name
    if image_bytes is not None:
        identity['image_fingerprint'] = _digest(image_bytes)
    if not identity:
        return None, cookware_signature(cookware_list)
    signature = cookware_signature(cookware_list)
    key_data = {
        'version': 2,
        'identity': identity,
        'notes': normalize_text(notes),
        'cookware_signature': signature,
    }
    encoded = json.dumps(key_data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return _digest(encoded.encode('utf-8')), signature


class DishKnowledgeStore:
    def __init__(self, path: Path = KNOWLEDGE_DB_PATH):
        self.path = Path(path)

    def _connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA busy_timeout = 10000')
        conn.execute('''CREATE TABLE IF NOT EXISTS dish_analysis_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cache_key TEXT NOT NULL UNIQUE,
            dish_name TEXT NOT NULL,
            analysis_json TEXT NOT NULL,
            cookware_signature TEXT NOT NULL,
            review_status TEXT NOT NULL DEFAULT 'pending_review'
                CHECK (review_status IN ('pending_review', 'reviewed', 'needs_update')),
            review_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_used_at TEXT NOT NULL,
            reviewed_at TEXT,
            next_review_at TEXT NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS dish_knowledge_meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS dish_aliases (
            alias_key TEXT PRIMARY KEY,
            alias_text TEXT NOT NULL,
            recipe_id INTEGER NOT NULL,
            source_record_id INTEGER,
            review_status TEXT NOT NULL DEFAULT 'pending_review'
                CHECK (review_status IN ('pending_review', 'reviewed', 'needs_update')),
            review_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT,
            next_review_at TEXT
        )''')
        alias_columns = {row['name'] for row in conn.execute('PRAGMA table_info(dish_aliases)')}
        alias_migrations = {
            'review_status': "ALTER TABLE dish_aliases ADD COLUMN review_status TEXT NOT NULL DEFAULT 'pending_review'",
            'review_note': "ALTER TABLE dish_aliases ADD COLUMN review_note TEXT NOT NULL DEFAULT ''",
            'updated_at': "ALTER TABLE dish_aliases ADD COLUMN updated_at TEXT NOT NULL DEFAULT ''",
            'reviewed_at': 'ALTER TABLE dish_aliases ADD COLUMN reviewed_at TEXT',
            'next_review_at': 'ALTER TABLE dish_aliases ADD COLUMN next_review_at TEXT',
        }
        for column, statement in alias_migrations.items():
            if column not in alias_columns:
                conn.execute(statement)
        conn.execute('''UPDATE dish_aliases SET review_status = 'reviewed'
                        WHERE source_record_id IS NULL AND review_status = 'pending_review' ''')
        conn.execute('''UPDATE dish_aliases SET updated_at = created_at
                        WHERE updated_at = '' ''')
        conn.execute('''UPDATE dish_aliases SET next_review_at = (
                            SELECT next_review_at FROM dish_analysis_records
                            WHERE dish_analysis_records.id = dish_aliases.source_record_id)
                        WHERE source_record_id IS NOT NULL AND next_review_at IS NULL ''')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_dish_alias_source ON dish_aliases(source_record_id)')
        interval_value = str(REVIEW_INTERVAL_DAYS)
        stored_interval = conn.execute(
            "SELECT value FROM dish_knowledge_meta WHERE key = 'review_interval_days'"
        ).fetchone()
        if not stored_interval or stored_interval['value'] != interval_value:
            rows = conn.execute('''SELECT id, reviewed_at, updated_at
                                  FROM dish_analysis_records
                                  WHERE review_status = 'reviewed' ''').fetchall()
            for row in rows:
                try:
                    reviewed_at = datetime.fromisoformat(row['reviewed_at'] or row['updated_at'])
                    if reviewed_at.tzinfo is None:
                        reviewed_at = reviewed_at.replace(tzinfo=timezone.utc)
                    next_review_at = iso_utc(reviewed_at + timedelta(days=REVIEW_INTERVAL_DAYS))
                    conn.execute('UPDATE dish_analysis_records SET next_review_at = ? WHERE id = ?',
                                 (next_review_at, row['id']))
                except (TypeError, ValueError):
                    logger.warning('Could not migrate review date for dish record %s', row['id'])
            conn.execute('''INSERT INTO dish_knowledge_meta (key, value)
                            VALUES ('review_interval_days', ?)
                            ON CONFLICT(key) DO UPDATE SET value = excluded.value''', (interval_value,))
        conn.commit()
        return conn

    def get_cached(self, cache_key: str | None):
        if not cache_key:
            return None
        now = iso_utc()
        try:
            conn = self._connect()
            row = conn.execute('''SELECT id, dish_name, analysis_json, review_status,
                                         review_note, next_review_at, hit_count
                                  FROM dish_analysis_records
                                  WHERE cache_key = ? AND review_status = 'reviewed'
                                    AND next_review_at > ?''', (cache_key, now)).fetchone()
            if not row:
                conn.close()
                return None
            try:
                analysis = json.loads(row['analysis_json'])
            except (TypeError, json.JSONDecodeError):
                conn.execute("UPDATE dish_analysis_records SET review_status = 'needs_update' WHERE id = ?", (row['id'],))
                conn.commit()
                conn.close()
                logger.warning('Dish knowledge record %s contains invalid JSON and needs review', row['id'])
                return None
            conn.execute('''UPDATE dish_analysis_records
                            SET last_used_at = ?, hit_count = hit_count + 1
                            WHERE id = ?''', (now, row['id']))
            conn.commit()
            result = dict(row)
            result['analysis'] = analysis
            result['hit_count'] += 1
            conn.close()
            return result
        except (sqlite3.Error, OSError):
            logger.exception('Dish knowledge cache could not be read')
            return None

    def save_analysis(self, cache_key: str | None, dish_name: str, analysis: dict,
                      cookware_signature_value: str):
        if not cache_key:
            return None
        now_dt = now_utc()
        now = iso_utc(now_dt)
        next_review = iso_utc(now_dt + timedelta(days=REVIEW_INTERVAL_DAYS))
        try:
            conn = self._connect()
            conn.execute('''INSERT INTO dish_analysis_records
                (cache_key, dish_name, analysis_json, cookware_signature, review_status,
                 review_note, created_at, updated_at, last_used_at, reviewed_at,
                 next_review_at, hit_count)
                VALUES (?, ?, ?, ?, 'pending_review', '', ?, ?, ?, NULL, ?, 0)
                ON CONFLICT(cache_key) DO UPDATE SET
                    dish_name = excluded.dish_name,
                    analysis_json = excluded.analysis_json,
                    cookware_signature = excluded.cookware_signature,
                    review_status = 'pending_review',
                    review_note = '',
                    updated_at = excluded.updated_at,
                    last_used_at = excluded.last_used_at,
                    reviewed_at = NULL,
                    next_review_at = excluded.next_review_at,
                    hit_count = 0''', (
                    cache_key, (dish_name or analysis.get('dish_name') or '待确认菜品')[:100],
                    json.dumps(analysis, ensure_ascii=False, separators=(',', ':')),
                    cookware_signature_value, now, now, now, next_review))
            row = conn.execute('SELECT id FROM dish_analysis_records WHERE cache_key = ?', (cache_key,)).fetchone()
            conn.commit()
            conn.close()
            return row['id'] if row else None
        except (sqlite3.Error, OSError, TypeError, ValueError):
            logger.exception('Dish analysis could not be saved to the knowledge history')
            return None

    def add_curated_alias(self, alias_text: str, recipe_id: int) -> bool:
        """Add a project-reviewed alias that does not need a user analysis record."""
        alias_text = str(alias_text or '').strip()[:120]
        alias_key = normalize_dish_name(alias_text)
        if not alias_key or not isinstance(recipe_id, int) or recipe_id < 1:
            return False
        try:
            conn = self._connect()
            existing = conn.execute('SELECT recipe_id, source_record_id, review_status FROM dish_aliases WHERE alias_key = ?',
                                    (alias_key,)).fetchone()
            if existing:
                conn.close()
                return (existing['recipe_id'] == recipe_id and existing['source_record_id'] is None
                        and existing['review_status'] == 'reviewed')
            now = iso_utc()
            conn.execute('''INSERT INTO dish_aliases
                (alias_key, alias_text, recipe_id, source_record_id, review_status,
                 created_at, updated_at, reviewed_at, next_review_at)
                VALUES (?, ?, ?, NULL, 'reviewed', ?, ?, ?, NULL)''',
                (alias_key, alias_text, recipe_id, now, now, now))
            conn.commit()
            conn.close()
            return True
        except (sqlite3.Error, OSError, TypeError, ValueError):
            logger.exception('Curated dish alias could not be saved')
            return False

    def save_alias_candidate(self, alias_text: str, recipe_id: int, source_record_id: int) -> bool:
        """Save an AI-suggested alias as pending; it is never active solely because its source is reviewed."""
        alias_text = str(alias_text or '').strip()[:120]
        alias_key = normalize_dish_name(alias_text)
        if not alias_key or not isinstance(recipe_id, int) or recipe_id < 1:
            return False
        try:
            conn = self._connect()
            source = conn.execute('SELECT id, next_review_at FROM dish_analysis_records WHERE id = ?',
                                  (source_record_id,)).fetchone()
            if not source:
                conn.close()
                return False
            now = iso_utc()
            existing = conn.execute('''SELECT recipe_id, source_record_id, review_status, next_review_at
                                       FROM dish_aliases WHERE alias_key = ?''', (alias_key,)).fetchone()
            if existing:
                if existing['recipe_id'] != recipe_id:
                    conn.close()
                    logger.warning('Conflicting dish alias candidate was rejected')
                    return False
                if existing['source_record_id'] is None:
                    conn.close()
                    return True
                if (existing['review_status'] == 'reviewed'
                        and (not existing['next_review_at'] or existing['next_review_at'] > now)):
                    conn.close()
                    return True
                conn.execute('''UPDATE dish_aliases
                                SET alias_text = ?, source_record_id = ?, review_status = 'pending_review',
                                    review_note = '', updated_at = ?, reviewed_at = NULL, next_review_at = ?
                                WHERE alias_key = ?''',
                             (alias_text, source_record_id, now, source['next_review_at'], alias_key))
            else:
                conn.execute('''INSERT INTO dish_aliases
                    (alias_key, alias_text, recipe_id, source_record_id, review_status,
                     created_at, updated_at, reviewed_at, next_review_at)
                    VALUES (?, ?, ?, ?, 'pending_review', ?, ?, NULL, ?)''',
                    (alias_key, alias_text, recipe_id, source_record_id, now, now, source['next_review_at']))
            conn.commit()
            conn.close()
            return True
        except (sqlite3.Error, OSError, TypeError, ValueError):
            logger.exception('Dish alias candidate could not be saved')
            return False

    def approved_aliases(self) -> list[dict]:
        """Return curated or separately approved aliases with a still-valid source analysis."""
        try:
            conn = self._connect()
            rows = conn.execute('''SELECT a.alias_text, a.recipe_id
                FROM dish_aliases a
                LEFT JOIN dish_analysis_records r ON r.id = a.source_record_id
                WHERE a.review_status = 'reviewed'
                  AND (a.next_review_at IS NULL OR a.next_review_at > ?)
                  AND (a.source_record_id IS NULL
                       OR (r.review_status = 'reviewed' AND r.next_review_at > ?))
                ORDER BY a.alias_text COLLATE NOCASE''', (iso_utc(), iso_utc())).fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except (sqlite3.Error, OSError):
            logger.exception('Approved dish aliases could not be read')
            return []

    def alias_review_queue(self, limit: int = 100):
        """Aliases are reviewed separately when their source analysis is already approved."""
        now = iso_utc()
        try:
            conn = self._connect()
            rows = conn.execute('''SELECT a.alias_key, a.alias_text, a.recipe_id,
                                         a.source_record_id, a.review_status, a.review_note,
                                         a.created_at, a.updated_at, a.next_review_at,
                                         r.review_status AS source_review_status
                                  FROM dish_aliases a
                                  LEFT JOIN dish_analysis_records r ON r.id = a.source_record_id
                                  WHERE (a.review_status IN ('pending_review', 'needs_update')
                                         OR (a.next_review_at IS NOT NULL AND a.next_review_at <= ?))
                                    AND (a.source_record_id IS NULL OR r.id IS NULL
                                         OR (r.review_status = 'reviewed' AND r.next_review_at > ?))
                                  ORDER BY CASE a.review_status WHEN 'needs_update' THEN 0
                                       WHEN 'pending_review' THEN 1 ELSE 2 END,
                                       a.updated_at ASC LIMIT ?''',
                                (now, now, max(1, min(limit, 200)))).fetchall()
            conn.close()
            result = []
            for row in rows:
                item = dict(row)
                item['overdue'] = bool(item['next_review_at'] and item['next_review_at'] <= now)
                result.append(item)
            return result
        except (sqlite3.Error, OSError):
            logger.exception('Dish alias review queue could not be read')
            return []

    def review_queue(self, limit: int = 100):
        now = iso_utc()
        try:
            conn = self._connect()
            rows = conn.execute('''SELECT id, dish_name, analysis_json, review_status,
                                         review_note, created_at, updated_at, reviewed_at,
                                         next_review_at, hit_count
                                  FROM dish_analysis_records
                                  WHERE review_status IN ('pending_review', 'needs_update')
                                     OR next_review_at <= ?
                ORDER BY CASE review_status
                                      WHEN 'needs_update' THEN 0
                                      WHEN 'pending_review' THEN 1 ELSE 2 END,
                                      next_review_at ASC
                                  LIMIT ?''', (now, max(1, min(limit, 200)))).fetchall()
            aliases_by_record = {}
            if rows:
                ids = [int(row['id']) for row in rows]
                placeholders = ','.join('?' for _ in ids)
                aliases = conn.execute(
                    f'''SELECT source_record_id, alias_text FROM dish_aliases
                        WHERE source_record_id IN ({placeholders})
                          AND (review_status IN ('pending_review', 'needs_update')
                               OR (next_review_at IS NOT NULL AND next_review_at <= ?))
                        ORDER BY alias_text''', [*ids, now]).fetchall()
                for alias in aliases:
                    aliases_by_record.setdefault(alias['source_record_id'], []).append(alias['alias_text'])
            conn.close()
            result = []
            for row in rows:
                item = dict(row)
                try:
                    item['analysis'] = json.loads(item.pop('analysis_json'))
                except (TypeError, json.JSONDecodeError):
                    item['analysis'] = {'summary': '记录格式异常，请重新分析。', 'cookware': [], 'ingredients': [], 'tips': [], 'steps': []}
                    item['review_status'] = 'needs_update'
                item['overdue'] = item['next_review_at'] <= now
                item['alias_candidates'] = aliases_by_record.get(item['id'], [])
                result.append(item)
            return result
        except (sqlite3.Error, OSError):
            logger.exception('Dish knowledge review queue could not be read')
            return []

    def pending_count(self) -> int:
        now = iso_utc()
        try:
            conn = self._connect()
            count = conn.execute('''SELECT COUNT(*) FROM dish_analysis_records
                                    WHERE review_status IN ('pending_review', 'needs_update')
                                       OR next_review_at <= ?''', (now,)).fetchone()[0]
            alias_count = conn.execute('''SELECT COUNT(*) FROM dish_aliases a
                LEFT JOIN dish_analysis_records r ON r.id = a.source_record_id
                WHERE (a.review_status IN ('pending_review', 'needs_update')
                       OR (a.next_review_at IS NOT NULL AND a.next_review_at <= ?))
                  AND (a.source_record_id IS NULL OR r.id IS NULL
                       OR (r.review_status = 'reviewed' AND r.next_review_at > ?))''',
                                       (now, now)).fetchone()[0]
            conn.close()
            return int(count) + int(alias_count)
        except (sqlite3.Error, OSError):
            logger.exception('Dish knowledge review count could not be read')
            return 0

    def mark_review(self, record_id: int, outcome: str, note: str = '') -> bool:
        if outcome not in {'reviewed', 'needs_update'}:
            return False
        now_dt = now_utc()
        now = iso_utc(now_dt)
        next_review = iso_utc(now_dt + timedelta(days=REVIEW_INTERVAL_DAYS)) if outcome == 'reviewed' else now
        try:
            conn = self._connect()
            cursor = conn.execute('''UPDATE dish_analysis_records
                SET review_status = ?, review_note = ?, updated_at = ?, reviewed_at = ?, next_review_at = ?
                WHERE id = ?''', (outcome, str(note or '').strip()[:1000], now, now, next_review, record_id))
            if cursor.rowcount == 1:
                conn.execute('''UPDATE dish_aliases
                    SET review_status = ?, review_note = ?, updated_at = ?, reviewed_at = ?, next_review_at = ?
                    WHERE source_record_id = ?''',
                             (outcome, str(note or '').strip()[:1000], now, now, next_review, record_id))
            conn.commit()
            changed = cursor.rowcount == 1
            conn.close()
            return changed
        except (sqlite3.Error, OSError):
            logger.exception('Dish knowledge review update failed')
            return False

    def mark_alias_review(self, alias_key: str, outcome: str, note: str = '') -> bool:
        if outcome not in {'reviewed', 'needs_update'}:
            return False
        now_dt = now_utc()
        now = iso_utc(now_dt)
        next_review = iso_utc(now_dt + timedelta(days=REVIEW_INTERVAL_DAYS)) if outcome == 'reviewed' else now
        try:
            conn = self._connect()
            cursor = conn.execute('''UPDATE dish_aliases
                SET review_status = ?, review_note = ?, updated_at = ?, reviewed_at = ?, next_review_at = ?
                WHERE alias_key = ? AND (source_record_id IS NULL OR source_record_id IN (
                    SELECT id FROM dish_analysis_records
                    WHERE review_status = 'reviewed' AND next_review_at > ?))''',
                (outcome, str(note or '').strip()[:1000], now, now, next_review,
                 normalize_dish_name(alias_key), now))
            conn.commit()
            changed = cursor.rowcount == 1
            conn.close()
            return changed
        except (sqlite3.Error, OSError, TypeError, ValueError):
            logger.exception('Dish alias review update failed')
            return False

    def reviewed_experience_context(self, cookware_list: list[str], limit: int = 3) -> str:
        signature = cookware_signature(cookware_list)
        now = iso_utc()
        try:
            conn = self._connect()
            rows = conn.execute('''SELECT dish_name, analysis_json, review_note
                                  FROM dish_analysis_records
                                  WHERE review_status = 'reviewed'
                                    AND next_review_at > ?
                                    AND cookware_signature = ?
                                  ORDER BY reviewed_at DESC LIMIT ?''',
                                (now, signature, max(1, min(limit, 5)))).fetchall()
            conn.close()
        except (sqlite3.Error, OSError):
            logger.exception('Reviewed dish knowledge could not be loaded')
            return ''
        examples = []
        for row in rows:
            try:
                analysis = json.loads(row['analysis_json'])
            except (TypeError, json.JSONDecodeError):
                continue
            summary = str(analysis.get('summary') or '').strip()[:240]
            tips = [str(tip).strip()[:120] for tip in (analysis.get('tips') or [])[:3] if str(tip).strip()]
            reviewer_note = str(row['review_note'] or '').strip()[:500]
            cookware = [str(item.get('name', '')).strip() for item in (analysis.get('cookware') or [])[:3]
                        if isinstance(item, dict) and item.get('name')]
            parts = [f"已复核菜品：{row['dish_name']}"]
            if summary:
                parts.append(f'做法要点：{summary}')
            if cookware:
                parts.append(f"锅具判断：{'、'.join(cookware)}")
            if tips:
                parts.append(f"避坑：{'；'.join(tips)}")
            if reviewer_note:
                parts.append(f'人工复核补充：{reviewer_note}')
            examples.append('；'.join(parts))
        return '\n'.join(f'- {example}' for example in examples)


knowledge_store = DishKnowledgeStore()
