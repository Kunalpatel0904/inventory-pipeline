"""Constants and business-rule parameters (single place to change a rule)."""
from __future__ import annotations

REQUIRED_COLUMNS = (
    "movement_id",
    "movement_type",
    "product_id",
    "location_id",
    "dest_location_id",
    "quantity",
    "effective_date",
    "recorded_at",
)
MOVEMENT_TYPES = ("receipt", "issue", "transfer", "adjustment")
LEG_TYPES = ("receipt", "issue", "transfer_in", "transfer_out", "adjustment")

MIN_QTY = 1                 # receipts / issues / transfers
MAX_QTY = 1_000_000         # absolute cap, all types
EARLIEST_EFFECTIVE_DATE = "2000-01-01"
MOVEMENT_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

# File-level statuses (file_load.status)
FILE_SUCCESS = "SUCCESS"
FILE_EMPTY = "EMPTY_BATCH"
FILE_SKIPPED = "SKIPPED_ALREADY_LOADED"
FILE_FAILED_SCHEMA = "FAILED_SCHEMA"
FILE_FAILED_READ = "FAILED_READ"
FILE_FAILED_PROCESSING = "FAILED_PROCESSING"
FILE_FAILED = (FILE_FAILED_SCHEMA, FILE_FAILED_READ, FILE_FAILED_PROCESSING)

# Run-level statuses (pipeline_run.status)
RUN_SUCCESS = "SUCCESS"
RUN_PARTIAL = "PARTIAL_FAILURE"
RUN_FAILED = "FAILED"
RUN_NOOP = "NOOP"


class Reason:
    """Reject reason codes (reject_record.reason_code)."""
    MALFORMED_ROW = "MALFORMED_ROW"
    MISSING_REQUIRED_FIELD = "MISSING_REQUIRED_FIELD"
    INVALID_MOVEMENT_ID = "INVALID_MOVEMENT_ID"
    INVALID_MOVEMENT_TYPE = "INVALID_MOVEMENT_TYPE"
    UNEXPECTED_DEST_LOCATION = "UNEXPECTED_DEST_LOCATION"
    INVALID_QUANTITY = "INVALID_QUANTITY"
    QUANTITY_OUT_OF_RANGE = "QUANTITY_OUT_OF_RANGE"
    INVALID_DATE = "INVALID_DATE"
    INVALID_TIMESTAMP = "INVALID_TIMESTAMP"
    FUTURE_EFFECTIVE_DATE = "FUTURE_EFFECTIVE_DATE"
    UNKNOWN_PRODUCT = "UNKNOWN_PRODUCT"
    UNKNOWN_LOCATION = "UNKNOWN_LOCATION"
    SAME_LOCATION_TRANSFER = "SAME_LOCATION_TRANSFER"
    DUPLICATE_EVENT = "DUPLICATE_EVENT"
    DUPLICATE_CONFLICT = "DUPLICATE_CONFLICT"
    REFERENCE_MISSING_KEY = "REFERENCE_MISSING_KEY"
    REFERENCE_DUPLICATE_KEY = "REFERENCE_DUPLICATE_KEY"
