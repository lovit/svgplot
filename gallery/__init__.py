"""Source for the published gallery under ``docs/gallery/``.

Not part of the ``svgplot`` package and not installed. It lives at the repo root because it
imports ``svgplot`` as a consumer would, which is the point: if an example here stops working,
a reader's copy of it stopped working too.

``build`` discovers ``examples/*.py`` rather than reading a registry. That is what lets one
chart's gallery page be added by a PR that touches exactly one new file -- no shared index to
edit, no ordering between chart PRs, and no rebase queue. See the plan's "이슈 단위" section.
"""
