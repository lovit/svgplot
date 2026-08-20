"""Value -> 0-1 fraction mapping for colormap sampling (docs-research/02-matplotlib.md,
"Colormap과 완전히 분리된 조합 가능 객체").

Deliberately *not* a job for :class:`svgplot.scales.LinearScale`, for two reasons a
colormap consumer can't work around:

1. **Clamping.** A heatmap turns this fraction into a level index; a value outside the
   domain must saturate at the end color, never index past the end of the color list.
   ``LinearScale`` extrapolates instead (correct for pixels — an off-canvas point still
   has a well-defined coordinate — but wrong for a bounded palette).
2. **Two-slope (``center``).** A diverging map is only honest when its neutral midpoint
   sits on the value the data diverges *around*, which is rarely the arithmetic middle
   of the domain. That needs two independent slopes (``vmin -> 0.0``, ``center -> 0.5``,
   ``vmax -> 1.0``); ``LinearScale``'s single ratio cannot express it.

Scope: only the plain and two-slope mappings. Log/power/symlog normalizations are 2차
(docs-research/10-feature-matrix.md rates them "낮음(heatmap 전용)").
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _require_finite_number(value: object, *, field: str) -> float:
    """Reject non-real / non-finite input before it can become a silent ``nan`` fraction
    and, downstream, a nonsense level index.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a real number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite, got {value!r}")
    return float(value)


@dataclass(frozen=True)
class Normalize:
    """Map a data value onto ``[0.0, 1.0]``, clamped, for sampling a colormap.

    With ``center`` given the mapping is two-slope: ``vmin -> 0.0``, ``center -> 0.5``,
    ``vmax -> 1.0``, so a diverging colormap's neutral band lands exactly on the value
    the data diverges around rather than on the domain's arithmetic middle.

    Raises:
        ValueError: if ``vmin``/``vmax``/``center`` isn't a finite real number, if
            ``vmin > vmax``, or if ``center`` falls outside ``[vmin, vmax]``.
    """

    vmin: float
    vmax: float
    center: float | None = None

    def __post_init__(self) -> None:
        vmin = _require_finite_number(self.vmin, field="vmin")
        vmax = _require_finite_number(self.vmax, field="vmax")
        # Inverted domains are rejected rather than supported, unlike ``LinearScale``
        # (which allows them so a chart can flip SVG's y-axis). A 0-1 colormap fraction
        # has no comparable "flip" meaning — a caller wanting the reversed ramp reverses
        # the color list — and allowing vmin > vmax would make the ``center`` range check
        # below silently vacuous.
        if vmin > vmax:
            raise ValueError(f"vmin must not exceed vmax, got vmin={self.vmin!r}, vmax={self.vmax!r}")
        object.__setattr__(self, "vmin", vmin)
        object.__setattr__(self, "vmax", vmax)
        if self.center is not None:
            center = _require_finite_number(self.center, field="center")
            if not vmin <= center <= vmax:
                raise ValueError(f"center must lie within [vmin, vmax] = [{vmin!r}, {vmax!r}], got {self.center!r}")
            object.__setattr__(self, "center", center)

    def __call__(self, value: float) -> float:
        """Return ``value``'s position in ``[0.0, 1.0]``, clamped to the domain.

        Raises:
            ValueError: if ``value`` isn't a finite real number.
        """
        number = _require_finite_number(value, field="value")
        # Clamp first so every branch below works on an in-domain number; this is what
        # guarantees the result can never index past the end of a colormap.
        number = max(self.vmin, min(self.vmax, number))
        if self.vmax == self.vmin:
            # Degenerate domain: every value is equally "middle". Mirrors
            # ``LinearScale.__call__``'s range-midpoint answer rather than dividing by zero.
            return 0.5
        if self.center is None:
            return (number - self.vmin) / (self.vmax - self.vmin)
        if number <= self.center:
            span = self.center - self.vmin
            # center == vmin collapses the lower half; the only value that can reach here
            # is the center itself, which is 0.5 by definition.
            return 0.5 * (number - self.vmin) / span if span else 0.5
        span = self.vmax - self.center
        return 0.5 + 0.5 * (number - self.center) / span if span else 0.5

    def inverse(self, position: float) -> float:
        """The value that :meth:`__call__` maps to ``position``.

        A legend has to name the value each colour step begins at, and with ``center`` set
        the mapping is two straight lines rather than one -- undoing it by assuming a
        single slope mislabels every step on the shorter side.

        Raises:
            ValueError: if ``position`` isn't a finite number in ``[0, 1]``.
        """
        fraction = _require_finite_number(position, field="position")
        if not 0.0 <= fraction <= 1.0:
            raise ValueError(f"position must be in [0, 1], got {position!r}")
        if self.center is None:
            return self.vmin + fraction * (self.vmax - self.vmin)
        if fraction <= 0.5:
            return self.vmin + 2.0 * fraction * (self.center - self.vmin)
        return self.center + 2.0 * (fraction - 0.5) * (self.vmax - self.center)

    @classmethod
    def from_values(cls, values: list[float], *, center: float | None = None) -> Normalize:
        """Build a ``Normalize`` spanning ``values``' own range.

        Raises:
            ValueError: if ``values`` is empty or holds a non-finite / non-real entry,
                or if ``center`` falls outside the resulting range.
        """
        numbers = [_require_finite_number(value, field="value") for value in values]
        if not numbers:
            raise ValueError("cannot build a Normalize from an empty value list")
        return cls(min(numbers), max(numbers), center)
