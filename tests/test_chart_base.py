"""Tests for svgplot.chart.base.Chart."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from svgplot._svg import SvgDocument
from svgplot.chart.base import Chart


def _sample_chart() -> Chart:
    document = SvgDocument(width=100, height=100)
    document.add_node(None, "circle", attrib={"cx": "50", "cy": "50", "r": "10"}, classes=["series-1"])
    return Chart(document)


def test_to_string_returns_svg_string_with_expected_tag_and_class() -> None:
    chart = _sample_chart()

    output = chart.to_string()

    assert "<circle" in output
    assert 'class="series-1"' in output


def test_to_string_compact_is_single_line() -> None:
    chart = _sample_chart()

    assert "\n" not in chart.to_string(pretty=False)


def test_to_string_is_idempotent() -> None:
    chart = _sample_chart()

    assert chart.to_string() == chart.to_string()


def test_set_title_returns_self_for_chaining() -> None:
    chart = _sample_chart()

    result = chart.set_title("My Chart")

    assert result is chart
    assert chart._title == "My Chart"


def test_set_title_reaches_the_rendered_output() -> None:
    chart = _sample_chart()

    chart.set_title("My Chart")

    assert "My Chart" in chart.to_string()


def test_a_chart_offers_no_palette_method() -> None:
    """``Chart.palette`` existed, recorded its argument, and was read by nothing -- calling it
    changed no output byte while its first docstring line said "Record a palette override".

    Removed rather than wired up: a ``Chart`` is a finished document, and a setter that
    re-renders one would have to be joined by ``theme()``, ``title()`` and the rest to be
    coherent. ``Theme(palette=...)`` is the way to choose colours and is now in the README.

    Pinned as an absence so the name cannot come back without a decision -- and because
    ``getattr`` on a missing method raises where a no-op silently succeeded (#260).
    """
    chart = _sample_chart()

    assert not hasattr(chart, "palette")
    with pytest.raises(AttributeError):
        chart.palette(["#e69f00"])  # type: ignore[attr-defined]


def test_repr_svg_returns_compact_svg_string() -> None:
    chart = _sample_chart()

    output = chart._repr_svg_()

    assert "<circle" in output
    assert "\n" not in output


def test_save_writes_svg_file(tmp_path: Path) -> None:
    chart = _sample_chart()
    path = tmp_path / "chart.svg"

    chart.save(str(path))

    content = path.read_text(encoding="utf-8")
    assert "<circle" in content


@pytest.mark.parametrize("extension", [".svg", ".SVG", ".Svg"])
def test_save_svg_extension_is_case_insensitive(tmp_path: Path, extension: str) -> None:
    chart = _sample_chart()
    path = tmp_path / f"chart{extension}"

    chart.save(str(path))

    assert "<circle" in path.read_text(encoding="utf-8")


def test_save_rejects_unsupported_extension(tmp_path: Path) -> None:
    chart = _sample_chart()

    with pytest.raises(ValueError, match="unsupported file extension"):
        chart.save(str(tmp_path / "chart.pdf"))


def test_save_rejects_path_with_no_extension(tmp_path: Path) -> None:
    chart = _sample_chart()

    with pytest.raises(ValueError, match="unsupported file extension"):
        chart.save(str(tmp_path / "chart"))


def test_save_png_without_cairosvg_installed_raises_import_error(cairosvg_unavailable: None, tmp_path: Path) -> None:
    chart = _sample_chart()

    with pytest.raises(ImportError, match="png"):
        chart.save(str(tmp_path / "chart.png"))


def test_save_writes_png_file_when_cairosvg_available(require_cairosvg: None, tmp_path: Path) -> None:
    chart = _sample_chart()
    path = tmp_path / "chart.png"

    chart.save(str(path))

    assert path.exists()
    assert path.read_bytes().startswith(b"\x89PNG")


# ---------------------------------------------------------------------------
# accessibility wiring (issue #29)
# ---------------------------------------------------------------------------


def test_rendered_chart_carries_accessibility_defaults_without_any_setup() -> None:
    """Accessibility is a default, not an opt-in (docs-research/10-feature-matrix.md A9),
    so a chart nobody configured still announces itself to assistive tech.
    """
    svg = _sample_chart().to_string()

    assert 'role="img"' in svg
    assert f'aria-label="{Chart.DEFAULT_TITLE}"' in svg
    assert f"<title>{Chart.DEFAULT_TITLE}</title>" in svg
    assert "<desc>" in svg


def test_repeated_renders_do_not_stack_duplicate_title_and_desc() -> None:
    """add_accessibility appends <title>/<desc> and is documented as once-per-document,
    but to_string/save/_repr_svg_ are all callable repeatedly — so the render path
    applies it to a copy. Without that, every render would add another pair.
    """
    chart = _sample_chart()

    chart.to_string()
    chart._repr_svg_()
    svg = chart.to_string()

    assert svg.count("<title>") == 1
    assert svg.count("<desc>") == 1


def test_set_title_after_an_earlier_render_still_takes_effect() -> None:
    """The title is read at serialization time, not baked in at first render."""
    chart = _sample_chart()
    chart.to_string()

    svg = chart.set_title("Quarterly sales").to_string()

    assert 'aria-label="Quarterly sales"' in svg
    assert "<title>Quarterly sales</title>" in svg
    assert svg.count("<title>") == 1


def test_rendering_leaves_the_charts_own_document_untouched() -> None:
    """Accessibility is applied to a throwaway copy, so the Chart's stored document
    stays exactly as the plotting function built it — anything reading it directly
    (e.g. chart.composition's nesting) sees no injected title/desc.
    """
    chart = _sample_chart()

    chart.to_string()

    assert "<title>" not in chart._svg_document.to_string()
    assert 'role="img"' not in chart._svg_document.to_string()


def test_a_title_containing_markup_is_escaped_not_injected() -> None:
    svg = _sample_chart().set_title("</title><script>alert(1)</script>").to_string()

    assert "<script>" not in svg
    assert "&lt;script&gt;" in svg


def test_saved_svg_file_also_carries_accessibility(tmp_path: Path) -> None:
    """save() must not bypass the render path that to_string() goes through."""
    target = tmp_path / "chart.svg"

    _sample_chart().set_title("Saved").save(str(target))

    written = target.read_text(encoding="utf-8")
    assert 'role="img"' in written
    assert "<title>Saved</title>" in written


@pytest.mark.parametrize("blank", ["", "   ", "\t\n "])
def test_a_blank_title_falls_back_to_the_default_instead_of_erroring(blank: str) -> None:
    """`""` and `"   "` used to diverge: the former fell back quietly, the latter hit
    add_accessibility's empty-title ValueError — and only at save()/to_string() time,
    far from the set_title() that caused it. Both now take the same fallback.
    """
    svg = _sample_chart().set_title(blank).to_string()

    assert f'aria-label="{Chart.DEFAULT_TITLE}"' in svg
    assert f"<title>{Chart.DEFAULT_TITLE}</title>" in svg


def test_to_string_carries_an_xml_prolog_by_default() -> None:
    """The default is unchanged, and that matters more than it looks: every committed SVG in
    the repo starts with this line, so a silent flip would rewrite all of them."""
    assert _sample_chart().to_string().startswith('<?xml version="1.0" encoding="UTF-8"?>\n')


def test_to_string_without_a_declaration_starts_at_the_svg_element() -> None:
    """What inlining into an HTML document needs. A prolog is only legal at the very start of
    an entity, so one sitting mid-document renders as text and refuses to parse."""
    output = _sample_chart().to_string(declaration=False)

    assert output.startswith("<svg")
    assert "<?xml" not in output


def test_dropping_the_declaration_changes_nothing_else() -> None:
    """Not `in`: the two must differ by the prolog and by nothing at all -- a version that
    also reformatted, or dropped the namespace, would pass a substring check."""
    chart = _sample_chart()

    assert chart.to_string() == '<?xml version="1.0" encoding="UTF-8"?>\n' + chart.to_string(declaration=False)


def test_a_declaration_free_string_parses_where_a_prolog_bearing_one_would_not() -> None:
    """The failure this parameter exists to prevent, stated as the pair it comes in."""
    chart = _sample_chart()

    ET.fromstring(f"<div>{chart.to_string(declaration=False)}</div>")
    with pytest.raises(ET.ParseError, match="declaration not at start"):
        ET.fromstring(f"<div>{chart.to_string()}</div>")


def test_declaration_is_keyword_only_and_composes_with_pretty() -> None:
    chart = _sample_chart()

    compact = chart.to_string(pretty=False, declaration=False)

    assert compact.startswith("<svg")
    # ``declaration`` is a no-op in compact mode -- the clause ``_svg.py`` states, and a
    # library property rather than a property of this fixture.
    assert compact == chart.to_string(pretty=False)
    with pytest.raises(TypeError):
        chart.to_string(False)  # type: ignore[misc]
