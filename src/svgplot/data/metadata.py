"""Point-level metadata (pygal precedent: dict-valued series entries, docs/research/01-pygal.md A2)."""

from __future__ import annotations


def attach_metadata(values: object, metadata: object) -> object:
    """Attach a per-point metadata dict (e.g. custom label) alongside plotted values."""
    raise NotImplementedError
