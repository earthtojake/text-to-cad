# Queries

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A model asks questions of what it made -- is this casting sound, what is this common's
volume, how close are these parts -- and asks them again on every build. A **query** is
such a question, and the memo keeps its answer as it keeps an operation's result
(`kernel/memo.py`, **Queries**): build123d's `bounding_box`, `is_valid`, `is_manifold`, a
solid's `volume`, `area`, an edge's or a wire's `length`, `center`, `matrix_of_inertia`,
`principal_properties`, `static_moments`, `radius_of_gyration`, `distance`, `distance_to`
and `is_inside`; and the OCCT analyses a model runs itself: `BRepAlgoAPI_Check`
(`IsValid()`), `BRepCheck_Analyzer` (`IsValid()`) and `BRepExtrema_DistShapeShape`
(`IsDone()`, `Value()`).

A query is keyed by the memo key of every shape it reads -- the operation that made it,
what later operations did to it, where it stands, never its label or colour -- and by
every argument and setting that can change its answer: a check's operation, fuzzy value,
parallel mode and oriented boxes; an analyzer's geometric controls and exact method; a
distance's deflection, flag, algorithm and parallel mode; a centre's `center_of`; a point
test's point and tolerance. Its answer is a plain value -- a verdict, a number, a point, a
box -- kept with the shape for as long as the memo holds it, and handed back, a new object
each time, whenever the same key is asked of the very same shapes, by any model the worker
builds. So a stage an edit reaches runs its checks no more than its booleans: on the
W16's housing-colour edit, the `turbos` stage's 16 BOP checks, every one asked of a
boolean the memo handed back, went from 48.2 s to under 0.5 s, the stage from 52.4 s to 1.5 s
and the edit from 67.1 s to 16.4 s.

A query of a shape no operation of the worker made (one made before the build, or
past the engine), or with an argument no key names (a progress range), runs as before
and keeps nothing; with `CAD_ENGINE_MEMO=0` every query runs. A query is only what is a
function of its key: the minimum distance is, but which of several equally near points
an analysis hands back follows the order it visits the shapes' pairs in, which a mesh the
shapes hold can change -- so `closest_points` is no query, and an analysis the memo
answered runs, as it was given, the moment anything else is asked of it (a point, its
faulty shapes). A shell's `volume` (it freezes the shell into a solid of its own), a
model's own `BRepGProp` call (its answer goes into an object the model hands in) and a
classifier the model loads itself are not queries either. A query is no feature: the
names are the same whether it ran or was answered. The report's `memo` counts
`queries_answered` and `queries_run`.
