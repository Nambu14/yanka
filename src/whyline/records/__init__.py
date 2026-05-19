"""Decision record filesystem model."""

from whyline.records.changelog import (
    ChangelogEntry,
    append_changelog,
    content_hash,
    create_entry,
    iter_changelog,
)
from whyline.records.frontmatter import (
    parse_frontmatter,
    parse_record_markdown,
    split_markdown,
)
from whyline.records.io import iter_records, read_record, write_record
from whyline.records.markdown import record_to_frontmatter_dict, record_to_markdown
from whyline.records.models import (
    Claim,
    ClaimStatus,
    ClaimSupersedes,
    Record,
    RecordBody,
    RecordStatus,
    RecordType,
    parse_record,
    record_from_frontmatter,
)
from whyline.records.slug import (
    record_filename,
    slugify_decision,
    slugify_text,
    unique_record_path,
)
from whyline.records.validate import (
    REQUIRED_FRONTMATTER_KEYS,
    is_complete_record,
    validate_frontmatter_keys,
)

__all__ = [
    "ChangelogEntry",
    "REQUIRED_FRONTMATTER_KEYS",
    "append_changelog",
    "content_hash",
    "create_entry",
    "Claim",
    "ClaimStatus",
    "ClaimSupersedes",
    "Record",
    "RecordBody",
    "RecordFile",
    "RecordStatus",
    "RecordType",
    "is_complete_record",
    "iter_changelog",
    "iter_records",
    "read_record",
    "parse_frontmatter",
    "parse_record",
    "parse_record_markdown",
    "record_filename",
    "record_from_frontmatter",
    "record_to_frontmatter_dict",
    "record_to_markdown",
    "slugify_decision",
    "slugify_text",
    "split_markdown",
    "unique_record_path",
    "validate_frontmatter_keys",
    "write_record",
]
