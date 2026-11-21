# Known and accepted

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

Two byte-level drifts are accepted, on one condition: no bug and no major impact. Each is
the same geometry and the same names written in another order.

- **A replayed body's BRep order.** A body the memo replays can write its BRep entries in
  another order than its cold run did (the f1's casing, the f14d, the radial's barrels).
- **Parallel booleans on a cold build.** OCCT's parallel booleans can order one result's
  sub-shapes differently from one cold build to the next (the w16, 3 of 794 parts; tom's
  yokes; the moonwatch's tachymeter).

Why that holds, checked:

- **Nothing keys on a document's bytes.** The restart key is digests of the model's code
  and inputs and the toolchain (**Build closure**); a derived file is translated from the
  document, and the write compares bytes only to leave an identical file untouched. The one
  place a document's bytes count is a document *read as an input* (`xbf.read`, `step.read`
  of another model's file), which is keyed by its bytes like any input: an order-only rewrite
  of that file builds the reading model once more, to the same result.
- **Names and refs resolve alike.** On the moonwatch's case (its tachymeter one of these),
  a cold build, a body re-run whose 2,673 kernel calls all replayed, and a second cold build
  in a new daemon wrote three different files of one size; their 15,646 element names are the
  same set, each on the same geometry (a face's area and centre, an edge's length and
  centre, a vertex's point), and refs resolve to the same elements through `cad <type> inspect`.
  `test_memo_marker.py` holds the same for a cold build, a replay and a second cold build.
- **`verify=True` reads it as `same`.** A leaf whose BRep differs only in order measures alike
  (**Memo functions**): a verification reports it `same`, never `differs`.

The snapshot's part listing (0.7's `--mode list`) is gone by decision: `xbf.read` and `step.read`
(a document's tree) and `cad xbf inspect DOC REF` (what a ref names) are the facts route.
