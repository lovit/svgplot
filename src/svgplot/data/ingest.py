"""Long-form DataFrame ingestion — the seaborn-style ``data=, x=, y=`` entry point.

Wide-form auto-detection is a 2차 addition planned for this same file
(docs/research/10-feature-matrix.md A2, docs/research/14-scope-recommendation.md).
"""

from __future__ import annotations


def ingest_longform(data: object, x: str, y: str | None = None) -> object:
    """Validate and normalize a long-form DataFrame (or array-like) input."""
    raise NotImplementedError
