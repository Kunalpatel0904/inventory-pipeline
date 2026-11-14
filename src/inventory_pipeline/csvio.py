"""Tolerant CSV reading with explicit header (schema) validation."""
from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass, field
from pathlib import Path


class SchemaError(Exception):
    """File-level structural problem (missing header / required columns)."""


@dataclass
class ParsedFile:
    header: list[str]
    rows: list[tuple[int, list[str]]]          # (source_line, fields)
    extra_columns: list[str] = field(default_factory=list)
    blank_lines_skipped: int = 0


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_csv(path: Path, required: tuple[str, ...]) -> ParsedFile:
    """Read a CSV. Raises SchemaError when header is missing/duplicated or
    required columns are absent. Extra columns are tolerated (reported).
    Raises UnicodeDecodeError on bad encoding (caller treats as FAILED_READ).
    Rows with the wrong number of fields are NOT dropped here: they are
    returned so the caller can quarantine them with their line number."""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        try:
            header_raw = next(reader)
        except StopIteration:
            raise SchemaError("empty file: no header row") from None
        header = [h.strip().lower() for h in header_raw]
        if len(set(header)) != len(header):
            raise SchemaError(f"duplicate column names in header: {header}")
        missing = [c for c in required if c not in header]
        if missing:
            raise SchemaError(f"missing required column(s): {missing}; found: {header}")
        extra = [c for c in header if c not in required]
        rows: list[tuple[int, list[str]]] = []
        blanks = 0
        for fields in reader:
            if not fields:
                blanks += 1
                continue
            rows.append((reader.line_num, fields))
    return ParsedFile(header=header, rows=rows, extra_columns=extra, blank_lines_skipped=blanks)
