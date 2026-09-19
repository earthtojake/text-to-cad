"""Migration error for the retired automatic validity verdict."""

raise ImportError(
    "cadgen.validity has been removed; use cadgen.geometry.topology_errors, "
    "cadgen.geometry.boundary_edges and cadgen.geometry.self_intersections "
    "on native geometry in a Python script. Choose the verdict in the caller."
)
