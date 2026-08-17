"""Point-level metadata (pygal precedent: dict-valued series entries, docs/research/01-pygal.md A2)."""

from __future__ import annotations

from collections.abc import Iterable


def attach_metadata(
    values: Iterable[object],
    metadata: Iterable[dict[str, object] | None] | None,
) -> list[dict[str, object]]:
    """Attach a per-point metadata dict (e.g. custom label) alongside plotted values.

    Returns one ``{"value": v, "metadata": m}`` dict per point. ``metadata=None``
    attaches ``None`` metadata to every point (a plain values-only series);
    otherwise ``metadata`` must have exactly one entry per value, and any
    individual point's metadata may itself be ``None``.

    Raises:
        ValueError: if ``metadata`` is given but its length doesn't match ``values``.
    """
    values = list(values)
    if metadata is None:
        metadata_list: list[dict[str, object] | None] = [None] * len(values)
    else:
        metadata_list = list(metadata)
        if len(metadata_list) != len(values):
            raise ValueError(f"metadata length ({len(metadata_list)}) must match values length ({len(values)})")
    return [{"value": value, "metadata": item} for value, item in zip(values, metadata_list, strict=True)]
