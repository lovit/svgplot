"""HTML for the gallery: one chart's page, and the index over all of them.

Written as string templates rather than with a template engine because the package itself has
no runtime dependencies and a docs build that needs one would be the only thing in the repo
that does.

Every value that reaches the HTML goes through :func:`escape`. The captions and notes are
written by hand in this repo, so this is not defending against an attacker -- it is defending
against a chart name or a note containing ``<`` and silently swallowing the rest of the page.
"""

from __future__ import annotations

from html import escape

from gallery.example import Page
from gallery.interaction import NOTE, markup, stylesheet

STYLE = """\
      :root {
        --bg: #ffffff;
        --fg: #16181d;
        --muted: #5c6370;
        --rule: #e3e6ea;
        --accent: #1d4ed8;
        --code-bg: #f4f5f7;
        --figure-bg: #ffffff;
      }
      @media (prefers-color-scheme: dark) {
        :root {
          --bg: #14161a;
          --fg: #e8eaed;
          --muted: #9aa1ac;
          --rule: #2a2e35;
          --accent: #7aa2f7;
          --code-bg: #1d2027;
          --figure-bg: #f7f8fa;
        }
      }
      * { box-sizing: border-box; }
      body {
        margin: 0 auto;
        max-width: 52rem;
        padding: 3rem 1.5rem 6rem;
        background: var(--bg);
        color: var(--fg);
        font-family: system-ui, -apple-system, "Segoe UI", "Noto Sans KR", sans-serif;
        line-height: 1.7;
      }
      a { color: var(--accent); }
      nav { margin-bottom: 2.5rem; font-size: 0.9rem; color: var(--muted); }
      h1 { margin: 0 0 0.35rem; font-size: 2rem; letter-spacing: -0.02em; }
      h2 {
        margin: 3rem 0 1rem;
        padding-top: 1.5rem;
        border-top: 1px solid var(--rule);
        font-size: 1.1rem;
      }
      h3 { margin: 2.5rem 0 0.75rem; font-size: 1rem; }
      .summary { margin: 0 0 1.75rem; color: var(--muted); font-size: 1.02rem; }
      dl.meta { margin: 0 0 2rem; padding: 0.9rem 1.1rem; background: var(--code-bg); border-radius: 6px; }
      dl.meta dt { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
      dl.meta dd { margin: 0.15rem 0 0.9rem; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; }
      dl.meta dd:last-child { margin-bottom: 0; }
      pre { background: var(--code-bg); padding: 0.9rem 1.1rem; border-radius: 6px; overflow-x: auto; }
      pre code { font-size: 0.84rem; line-height: 1.55; }
      code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
      /* Each chart is inlined into this page. An SVG's <style> is not scoped to the SVG --
         it applies to the whole document -- so two charts here would both define .series-1
         with opposite rules and the later one would repaint the earlier. Every chart is
         emitted under its own scope class (Chart.set_scope) and every rule sits under it,
         which is what makes inlining safe. The trade-offs of each embedding route are in
         ../tutorial/. */
      figure { margin: 0 0 1rem; }
      figure > svg {
        display: block;
        max-width: 100%;
        height: auto;
        background: var(--figure-bg);
        border: 1px solid var(--rule);
        border-radius: 6px;
      }
      /* The info= footnote table, which a figure carries when its chart was built with one.
         Without these it renders as an unstyled browser-default table inside an otherwise
         styled page -- the one piece of the gallery that looked unfinished. */
      figure table { width: 100%; border-collapse: collapse; margin-top: 0.75rem; font-size: 0.9rem; }
      figure th, figure td { padding: 0.35rem 0.6rem; border-bottom: 1px solid var(--rule); text-align: left; }
      figure th { font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); }
      figure td { font-variant-numeric: tabular-nums; }
      /* The thumbnail wrapper. Named so it stops inheriting ul.index span, which is the rule
         for the summary line beneath it. */
      ul.index .thumb { display: block; }
      ul.notes { margin: 0; padding-left: 1.2rem; color: var(--muted); }
      ul.notes li { margin-bottom: 0.3rem; }
      ul.index { display: grid; grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr)); gap: 1.5rem; margin: 0; padding: 0; list-style: none; }
      ul.index a { display: block; text-decoration: none; color: inherit; }
      ul.index svg { width: 100%; height: auto; background: var(--figure-bg); border: 1px solid var(--rule); border-radius: 6px; }
      ul.index strong { display: block; margin-top: 0.5rem; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.9rem; color: var(--accent); }
      ul.index span { display: block; color: var(--muted); font-size: 0.85rem; line-height: 1.5; }
      footer { margin-top: 3.5rem; padding-top: 1.5rem; border-top: 1px solid var(--rule); color: var(--muted); font-size: 0.9rem; }
"""

_DOCUMENT = """\
<!doctype html>
<html lang="ko">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{title}</title>
    <meta name="description" content="{description}" />
    <style>
{style}    </style>
  </head>
  <body>
{body}  </body>
</html>
"""


def _document(*, title: str, description: str, body: str, style_extra: str = "") -> str:
    """One page. ``style_extra`` is this page's own CSS, appended to the shared stylesheet.

    A channel rather than more of ``STYLE`` because ``STYLE`` is shared by all seventeen
    files: a rule added there for one chart's toggles rewrites the other sixteen pages too.
    ``STYLE`` ends in a newline, so a page with nothing of its own is byte-for-byte what it
    was before this parameter existed.
    """
    return _DOCUMENT.format(title=escape(title), description=escape(description), style=STYLE + style_extra, body=body)


def chart_page(page: Page) -> str:
    """One chart's page: what it draws, what data it needs, and worked examples."""
    parts = [
        '    <nav><a href="../">svgplot</a> · <a href="./">갤러리</a></nav>\n',
        f"    <h1>{escape(page.title)}</h1>\n",
        f'    <p class="summary">{escape(page.summary)}</p>\n',
        '    <dl class="meta">\n',
        f"      <dt>데이터</dt>\n      <dd>{escape(page.requires)}</dd>\n",
        "    </dl>\n",
        "    <h2>데이터</h2>\n",
        f"    <pre><code>{escape(page.setup)}</code></pre>\n",
        "    <h2>예시</h2>\n",
    ]
    controls = [example.controls for example in page.examples if example.controls]
    if controls:
        # Once per page, above the first figure that has controls, because it is a statement
        # about the mechanism rather than about one chart. The text lives in interaction.py so
        # sixteen pages cannot end up describing it sixteen slightly different ways.
        parts.append(f'    <p class="interaction-note">{escape(NOTE)}</p>\n')
    for example in page.examples:
        parts += [
            f"    <h3>{escape(example.caption)}</h3>\n",
            "    <figure>\n",
            # The controls come before the SVG and are its direct siblings: the rules in
            # interaction.py reach the chart with ``~``, which only sees following siblings.
            *([markup(example.controls)] if example.controls else []),
            # The SVG goes in as the serializer produced it. Re-indenting to match the
            # surrounding HTML would put spaces inside the <style> element's text, which is
            # real content -- prettier markup at the cost of changing what the file says.
            example.svg,
            *([f"      {example.table}\n"] if example.table else []),
            "    </figure>\n",
            f"    <pre><code>{escape(example.code)}</code></pre>\n",
        ]
    if page.notes:
        parts.append('    <h2>메모</h2>\n    <ul class="notes">\n')
        parts += [f"      <li>{escape(note)}</li>\n" for note in page.notes]
        parts.append("    </ul>\n")
    parts.append(
        "    <footer>\n"
        f'      <a href="./">갤러리로</a> · '
        f'<a href="https://github.com/lovit/svgplot/blob/main/gallery/examples/{page.name}.py">이 페이지의 예시 소스</a>\n'
        "    </footer>\n"
    )
    return _document(
        title=f"{page.title} — svgplot",
        description=page.summary,
        body="".join(parts),
        style_extra=stylesheet(controls),
    )


def index_page(pages: list[Page]) -> str:
    """The gallery index: every chart that has an example file, with its first figure."""
    parts = [
        '    <nav><a href="../">svgplot</a></nav>\n',
        "    <h1>갤러리</h1>\n",
        f'    <p class="summary">예시 {len(pages)}종. 각 그림 아래에 그것을 그린 코드가 함께 있다.</p>\n',
        '    <ul class="index">\n',
    ]
    for page in pages:
        parts += [
            "      <li>\n",
            f'        <a href="{page.name}.html">\n',
            # aria-hidden because the thumbnail is decoration here: the chart carries its
            # caption as an accessible name, and without this the link would be announced as
            # that whole sentence followed by the title it is actually named by.
            '          <span class="thumb" aria-hidden="true">\n',
            page.examples[0].svg,
            "          </span>\n",
            f"          <strong>{escape(page.title)}</strong>\n",
            f"          <span>{escape(page.summary)}</span>\n",
            "        </a>\n      </li>\n",
        ]
    parts.append('    </ul>\n    <footer><a href="../">svgplot 소개로</a></footer>\n')
    return _document(title="갤러리 — svgplot", description="svgplot 차트 예시 모음.", body="".join(parts))
