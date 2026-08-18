from __future__ import annotations

import subprocess
import sys
import warnings
from pathlib import Path

import pytest

import svgplot
from svgplot.warnings import HeatmapSizeWarning, SvgplotWarning


def test_categories_are_exported_from_the_package_root() -> None:
    assert svgplot.SvgplotWarning is SvgplotWarning
    assert svgplot.HeatmapSizeWarning is HeatmapSizeWarning
    assert "SvgplotWarning" in svgplot.__all__
    assert "HeatmapSizeWarning" in svgplot.__all__


def test_pytest_warns_on_the_base_category_catches_a_specific_one() -> None:
    """The subclass relationship is what lets a caller (and a test) reason about
    "any svgplot warning" without enumerating every subclass.
    """
    with pytest.warns(SvgplotWarning):
        warnings.warn("heatmap is large", HeatmapSizeWarning, stacklevel=1)


def test_filtering_the_base_category_silences_svgplot_warnings_only() -> None:
    """The whole point of the base class: a caller can silence this package
    without also silencing unrelated libraries' UserWarnings. If HeatmapSizeWarning
    were parented straight to UserWarning, the SvgplotWarning filter would miss it
    and both warnings would come through.
    """
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        warnings.filterwarnings("ignore", category=SvgplotWarning)

        warnings.warn("heatmap is large", HeatmapSizeWarning, stacklevel=1)
        warnings.warn("something else entirely", UserWarning, stacklevel=1)

    assert [entry.category for entry in recorded] == [UserWarning]


def test_warnings_are_shown_under_python_default_filters(tmp_path: Path) -> None:
    """Descending from UserWarning (not DeprecationWarning) is load-bearing: these
    describe the current call's output, so they must reach the caller without any
    opt-in.

    Both warnings are raised from an *imported module*, not from ``-c``: Python's
    default filters only hide DeprecationWarning outside ``__main__``, so warning
    straight from the ``-c`` body would show both and prove nothing. Run in a
    subprocess because pytest installs its own filters over the defaults.
    """
    module = tmp_path / "_warn_probe.py"
    module.write_text(
        "import warnings\n"
        "from svgplot.warnings import HeatmapSizeWarning\n"
        "warnings.warn('heatmap is large', HeatmapSizeWarning)\n"
        "warnings.warn('deprecated thing', DeprecationWarning)\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "-c", "import _warn_probe"],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    assert "HeatmapSizeWarning" in result.stderr
    assert "DeprecationWarning" not in result.stderr  # ignored by default outside __main__


def test_module_does_not_shadow_the_standard_library_warnings() -> None:
    """`svgplot/warnings.py` sits next to modules that import stdlib `warnings`;
    absolute imports keep those resolving to the stdlib, not to this module.
    """
    assert warnings.__name__ == "warnings"
    assert not hasattr(warnings, "SvgplotWarning")
    assert callable(warnings.warn)
