from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
import shutil
import tempfile
import time
from array import array
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from OCP.BinXCAFDrivers import BinXCAFDrivers
from OCP.Bnd import Bnd_Box
from OCP.BRep import BRep_Builder, BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Curve2d, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.BRepLProp import BRepLProp_SLProps
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.GCPnts import GCPnts_QuasiUniformDeflection
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.STEPControl import STEPControl_Reader
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.Quantity import Quantity_ColorRGBA
from OCP.TDF import TDF_ChildIterator, TDF_Label, TDF_LabelSequence
from OCP.TDocStd import TDocStd_Document
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp, TopExp_Explorer
from OCP.TopLoc import TopLoc_Location
from OCP.TopTools import TopTools_IndexedMapOfShape
from OCP.TopoDS import TopoDS, TopoDS_Compound, TopoDS_Shape
from OCP.XCAFApp import XCAFApp_Application
from OCP.XCAFDoc import (
    XCAFDoc_ColorCurv,
    XCAFDoc_ColorGen,
    XCAFDoc_ColorSurf,
    XCAFDoc_ColorTool,
    XCAFDoc_DocumentTool,
    XCAFDoc_ShapeTool,
)

from cadgen._internal.glb_mesh_payload import (
    DEFAULT_MATERIAL as DEFAULT_TOPOLOGY_MATERIAL,
    normalize_rgba as _normalize_rgba,
    occurrence_color_for_id as _occurrence_color_for_id,
    scene_glb_mesh_payload,
    transform_normal_from_occ as _transform_normal_from_occ,
)
from cadgen._internal.glb_topology import (
    STEP_EDGE_DEFAULT_RENDER_VISIBILITY_CLASSES,
    STEP_EDGE_FLAGS,
    STEP_EDGE_VISIBILITY_CLASSES,
    STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG,
    STEP_TOPOLOGY_EDGE_SAMPLE_COUNT,
    STEP_TOPOLOGY_SCHEMA_VERSION,
    is_displayable_step_edge_surface_class_code,
    normalize_step_edge_render_visibility_classes,
    step_edge_surface_class_code,
    step_topology_capabilities,
)
from cadgen.catalog import CADGEN_DIRNAME, CADGEN_MODELS_DIRNAME
from cadgen.metadata import DEFAULT_MESH_ANGULAR_TOLERANCE, DEFAULT_MESH_TOLERANCE, MeshSettings
from cadgen.selector_types import SelectorBundle, SelectorProfile
from cadgen._internal.step_hash import step_file_hash

from cadgen._internal.step_scene_cache import _STEP_SCENE_CACHE_DIRNAME, _STEP_SCENE_CACHE_MODELS_DIRNAME, _STEP_SCENE_CACHE_SUBDIR, _face_colors_from_index_payload, _face_index_color_payload, _node_from_cache_payload, _node_to_cache_payload, _path_is_skill_runtime, _prune_step_scene_cache_siblings, _read_step_scene_cache, _rgba_from_cache_value, _rgba_to_cache_value, _step_scene_cache_dir, _step_scene_cache_enabled, _write_step_scene_cache, load_step_scene_cached
from cadgen._internal.step_scene_geometry import _angle_between_vectors_deg, _apply_transform_point, _apply_transform_vector, _bbox_from_points, _bbox_from_shape, _classify_edge, _compact_bbox, _cross, _curve_params, _decimate_polyline, _dedupe_consecutive, _distance, _edge_continuity_name, _edge_flags, _edge_points_from_face_polygon, _edge_polygon_node_indices_from_face_mesh, _extract_edge_points_from_curve, _extract_face_geometry, _face_flags, _face_normal_at_edge_fraction, _is_smooth_continuity, _merge_bbox, _normalize, _point_from_occ, _polyline_center, _polyline_length, _round_point, _round_transform, _round_value, _sampled_edge_dihedral_deg, _surface_params, _transform_bbox, _transform_param_dict, _transform_point_from_occ, _triangle_side_key
from cadgen._internal.step_scene_loader import _color_from_label, _color_from_shape, _color_tuple, _compose_locations, _face_color_map_from_label, _label_name, _load_fallback_occurrence_tree, _load_occurrence_tree, _load_occurrence_tree_from_xcaf_doc, _located_shape, _location_from_transform_matrix, _location_transform_matrix, _normalize_label_name, _relative_path_from_directory, _resolve_referred_label, _scene_step_hash, _selector_id, _shape_hash, _shape_location, _step_hash, _unlocated_shape, _xcaf_children, load_step_scene, load_step_scene_from_xcaf_doc
from cadgen._internal.step_scene_mesh import _iter_leaf_occurrences, _leaf_shape, _scene_mesh_resolution_hints, adaptive_mesh_resolution_for_scene, adaptive_mesh_resolution_from_hints, import_step, mesh_step_scene, occurrence_selector_id, scene_export_shape, scene_leaf_occurrences, scene_occurrence_prototype_shape, scene_occurrence_shape, scene_to_build123d_compound
from cadgen._internal.step_scene_selectors import _artifact_relative_manifest_path, _edge_ordinals_from_shape, _extract_prototype, _extract_refs_prototype, _extract_summary_prototype, _face_ordinals_from_shape, _normalize_selector_options, _prototype_shape_entries, extract_selectors_from_scene
from cadgen._internal.step_scene_types import AdaptiveMeshResolution, ColorRGBA, LoadedStepScene, OccurrenceNode, STEP_SCENE_CACHE_SCHEMA_VERSION, SelectorOptions, _STEP_SCENE_CACHE_BINTOOLS_VERSION, _enum_name, _enum_name_cached, _enum_name_from_text, _identity_transform_matrix

