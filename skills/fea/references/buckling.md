# Buckling (`buckling`)

**Not available in this cadgen yet.** `cadgen fea solve` refuses a study with `"analysis": "buckling"` ("'buckling' is planned but not in this cadgen yet"), so do not write one; tell the user it is coming, and see the skill's "When the question needs an analysis that is not here yet". This page is filled in, with its schema, an example, a hand check, its limits and its adapted steps, when it ships.

It will answer "will this column, strut or thin wall buckle, and at how many times this load": the load factor at which the part's shape gives way sideways, and the shape it buckles into. A static solve under the same fixtures and loads runs first, inside it.

On top of the common keys in [study-file.md](study-file.md#common-keys), it will take:

- `fixtures` and `loads`: as `static`.
- `modes`: how many buckling shapes to find.
- Check `buckling`: `margin` (1 or more, default 3), the load factor it must keep: "Buckles at 13× this load, needs 3×".
