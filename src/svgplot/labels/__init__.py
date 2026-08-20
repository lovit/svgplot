"""LabelSpec (field+format) and its static renderers — see docs-research/17-static-hover-alternative.md.

v1 ships the "단일 스펙, 다중 출력" spec plus the table renderer; inline/panel
renderers are 2차 additions planned for this same package.
"""

from __future__ import annotations

from svgplot.labels.spec import LabelSpec
from svgplot.labels.table import render_table

__all__ = ["LabelSpec", "render_table"]
