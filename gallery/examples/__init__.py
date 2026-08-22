"""One module per chart. ``gallery.build`` discovers whatever is here.

Adding a chart's gallery page means adding one file to this directory and nothing else --
no registry to edit, so the chart PRs do not collide or queue.

Conventions every page follows, so sixteen pages read as one document:

**Fixture names are ``ALL_CAPS``**; the values built on the way to one take a leading underscore
(``_rng``, ``_hours``). Not because they are hidden -- ``SETUP`` is printed verbatim on the page,
so a reader sees every name in it -- but so that a glance separates *the data this page is
about* from the scaffolding that produced it. A page that seeds randomness uses its own
``random.Random(n)`` with a seed no other page uses, so two pages cannot drift into each
other's numbers.

**Column names are Korean nouns, and carry no Latin script.** Where a unit belongs in the name
it is spelled in Korean too -- ``"대기분"``, ``"응답밀리초"``, ``"기가바이트"``, not ``"ms"`` or
``"GB"``. The point is not tidiness: a reader scanning a page should be able to tell a column
name from an argument name at a glance, and Latin in a column makes the two look alike. The
same noun must not mean two things across pages -- ``"시각"`` is a clock hour and ``"시간"`` a
duration, which were once both ``"시간"``.

**A secondary dataset lives inside the example that needs it**, not in ``SETUP``, unless every
example uses it. ``example.py`` runs each example in a copy of the namespace, so an inline name
never leaks to the next figure -- which is why a fixture two examples need is written out twice
rather than hoisted.

Conventions for the prose, which is the half nothing executes:

**A caption names what changed and ends in a verb.** The first is always ``기본 — <what the
default shows>``: bare ``기본`` tells a reader nothing, and the caption is the figure's
``aria-label``, so it is the only description a screen reader gets. After that a caption names
the argument it is demonstrating, spelled the way it is passed (``stat="count"``, ``fill=True``,
``hue=``), and says what that does to the picture. Two shapes are allowed to end in a noun: one
naming a size or a value (``기본 — 120x24``) and one contrasting with the figure above it
(``xscale="log" — x 가 자릿수로 벌어질 때``). Nothing else may end in a noun phrase, and no
caption may refer to another figure by its position -- insert one above and the reference is
silently wrong.

**A caption may only claim what its own figure draws.** Not what the argument does in general,
and not what a neighbouring figure shows. ``test_gallery`` checks one half of this by machine --
every option a figure passes must be named in its caption -- and the other half, that the claim
is true of the rendered figure, is checked by rendering it. A caption once said a single-row
gauge had no legend while the figure it named drew one.

**In ``NOTES``, a name written with ``=`` is an argument and a name written bare is not.**
``inner= 은 "box" 또는 None 이다`` is about the parameter; ``theme.marker_size``, ``hue 값``,
``(data, x, y, hue)`` and ``fill: none`` are a field, a value, a signature and a CSS
declaration, and stay bare. No page uses backticks -- sixteen out of sixteen, so it is a
convention rather than an accident.

**``REQUIRES`` is ``name: what it must be``, joined by ``·``.** A channel a chart does not take
gets its own field saying so (``hue 는 받지 않는다``), because a reader looking for ``hue=``
needs to find the answer, not the silence. The word for an unrestricted channel is
``아무 타입``; a channel that subdivides a category is ``카테고리 안에서 한 번 더 나눌 값``.
Constraints that are not about one channel come last, after the channels they constrain.

**The interaction note is one sentence with a fixed shape**: which figures carry a control,
then ``이 페이지의 CSS 와 마크업이고 JavaScript 는 0줄이다``. A page with no controls says
which figure would have had one and why it does not, and drops the JavaScript clause -- there
is no CSS to disclaim.
"""
