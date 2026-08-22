"""One module per chart. ``gallery.build`` discovers whatever is here.

Adding a chart's gallery page means adding one file to this directory and nothing else --
no registry to edit, so the chart PRs do not collide or queue.

Conventions every page follows, so sixteen pages read as one document:

**Fixture names are ``ALL_CAPS``**; intermediates a reader never sees take a leading underscore
(``_rng``, ``_hours``). A page that seeds randomness uses its own ``random.Random(n)`` with a
seed no other page uses, so two pages cannot drift into each other's numbers.

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
"""
