"""Migration error for the retired assembly interference checks."""

raise ImportError(
    "cadgen.interference has been removed; use cadgen.geometry.closest_points "
    "and cadgen.geometry.overlap_volume on native geometry in a Python script. "
    "Choose pair selection, exclusions and thresholds in the caller."
)
