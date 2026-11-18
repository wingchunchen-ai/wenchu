-- Audit ledger for the read-only legacy demo import. One source record maps to
-- deterministic target ids and its exact imported (non-image) content hash.
CREATE TABLE LegacyImportLedger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_system TEXT NOT NULL,
    source_record_id TEXT NOT NULL,
    source_content_sha256 TEXT NOT NULL,
    target_ids_json TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
    UNIQUE (source_system, source_record_id)
);
CREATE INDEX idx_legacy_import_ledger_source ON LegacyImportLedger(source_system, source_record_id);
