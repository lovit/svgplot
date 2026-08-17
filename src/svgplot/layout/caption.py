"""Composition-level captions and the Tabs-replacement heading-per-chart pattern
(docs/research/16-layout-vocabulary.md, "Tabs 대체 관용구" 기본안)."""

from __future__ import annotations

from svgplot.chart.composition import Composition


def add_caption(composition: Composition, text: str, location: str = "below") -> Composition:
    """Attach a shared caption/title to a Composition (replaces Bokeh's shared-toolbar unity cue)."""
    raise NotImplementedError
