"""Data ingestion: long-form DataFrame parsing, hue/col/row semantic channels, point metadata.

Missing-value (``None``/NaN) policy differs by stage, intentionally: ``ingest_longform``
preserves every row as-is (deciding what to do with a missing point is a
chart-type concern, not ingestion's), while ``extract_channels`` drops a row
if any *requested channel* (hue/col/row) is missing — a row with no group
can't be grouped. See each function's docstring for the exact behavior.
"""

from __future__ import annotations

from svgplot.data.ingest import LongFormData, ingest_longform
from svgplot.data.metadata import attach_metadata
from svgplot.data.semantic import extract_channels

__all__ = ["LongFormData", "attach_metadata", "extract_channels", "ingest_longform"]
