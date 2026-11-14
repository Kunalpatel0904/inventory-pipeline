"""Row-level validation and normalisation. Pure functions, no DB access.

Validation order (first failing rule wins, so each reject has ONE reason):
  required fields -> movement_id format -> movement_type -> dest_location rule
  -> quantity parse -> quantity range -> effective_date -> recorded_at
  -> effective_date <= recorded_at date -> product/location/dest references
  -> transfer source != destination
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import NamedTuple

from .config import (EARLIEST_EFFECTIVE_DATE, MAX_QTY, MIN_QTY, MOVEMENT_ID_PATTERN,
                     MOVEMENT_TYPES, Reason)

_ID_RE = re.compile(MOVEMENT_ID_PATTERN)
_INT_RE = re.compile(r"^[+-]?\d+$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_BASE_REQUIRED = ("movement_id", "movement_type", "product_id", "location_id",
                  "quantity", "effective_date", "recorded_at")


class Rejection(NamedTuple):
    code: str
    detail: str


@dataclass(frozen=True)
class Movement:
    movement_id: str
    movement_type: str
    product_id: str
    location_id: str
    dest_location_id: str | None
    quantity: int
    effective_date: str          # YYYY-MM-DD
    recorded_at: str             # ISO-8601 UTC, e.g. 2026-01-05T10:15:00Z
    content_hash: str
    source_line: int


def parse_timestamp(value: str) -> datetime:
    """ISO-8601 timestamp -> aware UTC datetime. Naive values are assumed UTC."""
    if "T" not in value and " " not in value:
        raise ValueError("timestamp must include a time component")
    dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def compute_hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


def validate_row(raw: dict[str, str], line: int, products: set[str],
                 locations: set[str]) -> Movement | Rejection:
    f = {k: (raw.get(k) or "").strip() for k in
         (*_BASE_REQUIRED, "dest_location_id")}

    blanks = [c for c in _BASE_REQUIRED if not f[c]]
    if blanks:
        return Rejection(Reason.MISSING_REQUIRED_FIELD, f"missing/blank: {', '.join(blanks)}")
    if not _ID_RE.match(f["movement_id"]):
        return Rejection(Reason.INVALID_MOVEMENT_ID, f"movement_id {f['movement_id']!r} must match {MOVEMENT_ID_PATTERN}")

    mtype = f["movement_type"].lower()
    if mtype not in MOVEMENT_TYPES:
        return Rejection(Reason.INVALID_MOVEMENT_TYPE, f"unknown movement_type {f['movement_type']!r}")

    dest = f["dest_location_id"] or None
    if mtype == "transfer" and dest is None:
        return Rejection(Reason.MISSING_REQUIRED_FIELD, "transfer requires dest_location_id")
    if mtype != "transfer" and dest is not None:
        return Rejection(Reason.UNEXPECTED_DEST_LOCATION, f"{mtype} must not have dest_location_id")

    if not _INT_RE.match(f["quantity"]):
        return Rejection(Reason.INVALID_QUANTITY, f"quantity {f['quantity']!r} is not a whole number")
    qty = int(f["quantity"])
    if mtype == "adjustment":
        if qty == 0 or abs(qty) > MAX_QTY:
            return Rejection(Reason.QUANTITY_OUT_OF_RANGE, f"adjustment quantity {qty} must be non-zero and |q| <= {MAX_QTY}")
    elif not (MIN_QTY <= qty <= MAX_QTY):
        return Rejection(Reason.QUANTITY_OUT_OF_RANGE, f"{mtype} quantity {qty} outside [{MIN_QTY}, {MAX_QTY}]")

    if not _DATE_RE.match(f["effective_date"]):
        return Rejection(Reason.INVALID_DATE, f"effective_date {f['effective_date']!r} is not YYYY-MM-DD")
    try:
        eff = date.fromisoformat(f["effective_date"])
    except ValueError:
        return Rejection(Reason.INVALID_DATE, f"effective_date {f['effective_date']!r} is not a real calendar date")
    if eff < date.fromisoformat(EARLIEST_EFFECTIVE_DATE):
        return Rejection(Reason.INVALID_DATE, f"effective_date {eff} before {EARLIEST_EFFECTIVE_DATE}")

    try:
        rec = parse_timestamp(f["recorded_at"])
    except ValueError:
        return Rejection(Reason.INVALID_TIMESTAMP, f"recorded_at {f['recorded_at']!r} is not an ISO-8601 timestamp")
    if eff > rec.date():
        return Rejection(Reason.FUTURE_EFFECTIVE_DATE, f"effective_date {eff} is after recorded_at date {rec.date()}")

    if f["product_id"] not in products:
        return Rejection(Reason.UNKNOWN_PRODUCT, f"product_id {f['product_id']!r} not in dim_product")
    if f["location_id"] not in locations:
        return Rejection(Reason.UNKNOWN_LOCATION, f"location_id {f['location_id']!r} not in dim_location")
    if dest is not None:
        if dest not in locations:
            return Rejection(Reason.UNKNOWN_LOCATION, f"dest_location_id {dest!r} not in dim_location")
        if dest == f["location_id"]:
            return Rejection(Reason.SAME_LOCATION_TRANSFER, "transfer source and destination are identical")

    rec_iso = rec.strftime("%Y-%m-%dT%H:%M:%SZ")
    h = compute_hash([f["movement_id"], mtype, f["product_id"], f["location_id"],
                      dest or "", str(qty), eff.isoformat(), rec_iso])
    return Movement(f["movement_id"], mtype, f["product_id"], f["location_id"], dest,
                    qty, eff.isoformat(), rec_iso, h, line)


def to_legs(m: Movement) -> list[tuple[int, str, str, str, int]]:
    """Expand a movement into stock legs: (leg_no, product, location, leg_type, signed_qty)."""
    if m.movement_type == "receipt":
        return [(1, m.product_id, m.location_id, "receipt", m.quantity)]
    if m.movement_type == "issue":
        return [(1, m.product_id, m.location_id, "issue", -m.quantity)]
    if m.movement_type == "adjustment":
        return [(1, m.product_id, m.location_id, "adjustment", m.quantity)]
    return [(1, m.product_id, m.location_id, "transfer_out", -m.quantity),
            (2, m.product_id, m.dest_location_id or "", "transfer_in", m.quantity)]
