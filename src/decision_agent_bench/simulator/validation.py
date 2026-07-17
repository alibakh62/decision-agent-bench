"""Integrity checks and canonical hashing for generated worlds."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from decision_agent_bench.simulator.schema import INTERNAL_TABLES, PUBLIC_TABLES, SCHEMA_VERSION

REQUIRED_TABLES = PUBLIC_TABLES | INTERNAL_TABLES


@dataclass(frozen=True)
class WorldValidationReport:
    """Evidence produced by deterministic world validation."""

    table_counts: dict[str, int]
    transaction_count: int


def _read_only_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def logical_digest(path: Path) -> str:
    """Hash canonical table contents, independent of SQLite file layout."""

    digest = hashlib.sha256()
    with _read_only_connection(path) as connection:
        tables = sorted(
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        )
        for table in tables:
            columns = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            order = ", ".join(f'"{column}"' for column in columns)
            digest.update(f"table:{table}\n".encode())
            for row in connection.execute(f'SELECT * FROM "{table}" ORDER BY {order}'):
                values: list[Any] = [row[column] for column in columns]
                digest.update(
                    (json.dumps(values, ensure_ascii=True, separators=(",", ":")) + "\n").encode()
                )
    return digest.hexdigest()


def validate_world(path: Path) -> WorldValidationReport:
    """Validate schema, relationships, accounting identities, and document integrity."""

    if not path.is_file():
        raise FileNotFoundError(path)
    errors: list[str] = []
    with _read_only_connection(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        missing = sorted(REQUIRED_TABLES - tables)
        if missing:
            raise ValueError(f"invalid generated world:\n- missing tables: {', '.join(missing)}")

        version_row = connection.execute(
            "SELECT value FROM metadata WHERE key='schema_version'"
        ).fetchone()
        if version_row is None or version_row[0] != SCHEMA_VERSION:
            errors.append("schema version is missing or unsupported")

        foreign_key_errors = list(connection.execute("PRAGMA foreign_key_check"))
        if foreign_key_errors:
            errors.append(f"foreign key violations: {len(foreign_key_errors)}")

        accounting_errors = connection.execute(
            """
            SELECT COUNT(*) FROM transactions
            WHERE ABS(gross_sales - discount_amount - net_sales) > 0.011
               OR discount_amount > gross_sales
               OR cogs < 0
            """
        ).fetchone()[0]
        if accounting_errors:
            errors.append(f"transaction accounting violations: {accounting_errors}")

        documents = connection.execute("SELECT document_id, body, checksum FROM documents")
        bad_documents = [
            row["document_id"]
            for row in documents
            if hashlib.sha256(row["body"].encode()).hexdigest() != row["checksum"]
        ]
        if bad_documents:
            errors.append(f"document checksum violations: {', '.join(bad_documents)}")

        required_nonempty = PUBLIC_TABLES - {"approvals", "action_ledger"}
        table_counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in sorted(REQUIRED_TABLES)
        }
        empty = sorted(table for table in required_nonempty if table_counts[table] == 0)
        if empty:
            errors.append(f"unexpected empty tables: {', '.join(empty)}")

    if errors:
        raise ValueError("invalid generated world:\n- " + "\n- ".join(errors))
    return WorldValidationReport(
        table_counts=table_counts,
        transaction_count=table_counts["transactions"],
    )
