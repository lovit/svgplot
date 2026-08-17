"""Data ingestion: long-form DataFrame parsing, hue/col/row semantic channels, point metadata."""

from __future__ import annotations

from svgplot.data.ingest import ingest_longform
from svgplot.data.metadata import attach_metadata
from svgplot.data.semantic import extract_channels

__all__ = ["attach_metadata", "extract_channels", "ingest_longform"]
