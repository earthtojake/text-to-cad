"""The implicit engine: signed distance fields as an expression tree.

A part is a tree of :class:`~cadgen._internal.implicit.field.Field` nodes.
Every node evaluates, for a batch of points, the signed distance to its
surface (negative inside, positive outside) and the id of the *leaf* -- the
primitive in the author's code -- whose surface is the closest one at that
point. Booleans are arithmetic on those distances (union is ``min``,
intersection ``max``, subtraction ``max(a, -b)``), so a spatial question is
an expression over the same fields the part is made of.

The tree is data: :mod:`.tape` writes it as JSON beside a mesh so a saved
part can be re-meshed or probed without its source, and :mod:`.mesh`
contours it with surface nets using numpy alone -- the only dependency the
engine has, so it runs wherever cadgen does.
"""
