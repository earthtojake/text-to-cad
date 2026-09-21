import { useCallback, useMemo, useReducer, useRef } from "react";
import {
  dxfMaterialPreset, dxfSettingsRecord, normalizeDxfBendAngleDeg, normalizeDxfBendDirection,
  normalizeDxfBendRadiusMm, normalizeDxfBendStyle, normalizeDxfBends, normalizeDxfKFactor,
  normalizeDxfMaterial, normalizeDxfOrientation, normalizeDxfThicknessMm, normalizeDxfUnits,
  normalizeDxfView, readDxfSettings, DXF_DEFAULT_BEND_ANGLE_DEG,
  DXF_DEFAULT_MATERIAL, DXF_DEFAULT_ORIENTATION, DXF_DEFAULT_THICKNESS_MM, DXF_DEFAULT_UNITS
} from "./dxfSettings.js";

/** One bend row per bend line the FILE has. The record is restored before the parse lands,
 *  so the rows are sized when it does, keeping the angles of the bends that still exist. */
function sizeBends(state, bendCount) {
  return state.bends.length === bendCount ? state : { ...state, bends: normalizeDxfBends(state.bends, bendCount) };
}

function reduce(state, action) {
  const current = sizeBends(state, action.bendCount);
  switch (action.type) {
    case "thickness": return { ...current, thicknessMm: normalizeDxfThicknessMm(action.value, current.thicknessMm) };
    case "units": return { ...current, units: normalizeDxfUnits(action.value, current.units) };
    case "material": return { ...current, material: normalizeDxfMaterial(action.value, current.material) };
    case "bendStyle": return { ...current, bendStyle: normalizeDxfBendStyle(action.value, current.bendStyle) };
    case "bendRadius": return { ...current, bendRadiusMm: normalizeDxfBendRadiusMm(action.value, current.bendRadiusMm) };
    case "kFactor": return { ...current, kFactor: normalizeDxfKFactor(action.value, current.kFactor) };
    case "view": return { ...current, view: normalizeDxfView(action.value, current.view) };
    case "bend": return { ...current, bends: current.bends.map((bend, index) => (index === action.index ? {
      angleDeg: normalizeDxfBendAngleDeg(action.patch.angleDeg ?? bend.angleDeg, bend.angleDeg),
      direction: normalizeDxfBendDirection(action.patch.direction ?? bend.direction, bend.direction)
    } : bend)) };
    case "rotate": return { ...current, orientation: normalizeDxfOrientation({
      ...current.orientation, [action.axis]: current.orientation[action.axis] + 1
    }) };
    case "layer": return { ...current, hiddenLayers: action.visible
      ? current.hiddenLayers.filter(name => name !== action.name)
      : current.hiddenLayers.includes(action.name) ? current.hiddenLayers : [...current.hiddenLayers, action.name] };
    case "resetMaterial": return { ...current, thicknessMm: DXF_DEFAULT_THICKNESS_MM,
      units: DXF_DEFAULT_UNITS, material: DXF_DEFAULT_MATERIAL };
    case "resetBends": return { ...current,
      bends: current.bends.map(() => ({ angleDeg: DXF_DEFAULT_BEND_ANGLE_DEG, direction: "up" })) };
    case "resetOrientation": return { ...current, orientation: { ...DXF_DEFAULT_ORIENTATION } };
    default: return current;
  }
}

/**
 * The DXF renderer's own state: one reducer over the ten settings and the view, restored
 * from the per-file record and written back through it.
 *
 * @param {unknown} restored  The record's `renderer` slot as the renderer read it.
 * @param {number} bendCount  How many bend lines the parsed file has, which sizes `bends`.
 */
export function useDxfSettings(restored, bendCount) {
  const [stored, dispatch] = useReducer(reduce, null, () => readDxfSettings(restored));
  const bendCountRef = useRef(bendCount);
  bendCountRef.current = bendCount;
  const send = useCallback(action => dispatch({ ...action, bendCount: bendCountRef.current }), []);
  const state = useMemo(() => sizeBends(stored, bendCount), [stored, bendCount]);

  return {
    state,
    /** What the scene reads. A new identity only when something the scene draws changed. */
    scene: useMemo(() => ({
      thicknessMm: state.thicknessMm, bends: state.bends, bendStyle: state.bendStyle,
      bendRadiusMm: state.bendRadiusMm, kFactor: state.kFactor, hiddenLayers: state.hiddenLayers,
      orientation: state.orientation, tintHex: dxfMaterialPreset(state.material).colorHex
    }), [state.thicknessMm, state.bends, state.bendStyle, state.bendRadiusMm, state.kFactor,
      state.hiddenLayers, state.orientation, state.material]),
    /** The record's own slot. A dependency of the shell's save effect, so it is memoized. */
    record: useMemo(() => dxfSettingsRecord(state), [state]),
    setThickness: useCallback(value => send({ type: "thickness", value }), [send]),
    setUnits: useCallback(value => send({ type: "units", value }), [send]),
    setMaterial: useCallback(value => send({ type: "material", value }), [send]),
    setBendStyle: useCallback(value => send({ type: "bendStyle", value }), [send]),
    setBendRadius: useCallback(value => send({ type: "bendRadius", value }), [send]),
    setKFactor: useCallback(value => send({ type: "kFactor", value }), [send]),
    setView: useCallback(value => send({ type: "view", value }), [send]),
    changeBend: useCallback((index, patch) => send({ type: "bend", index, patch }), [send]),
    rotate: useCallback(axis => send({ type: "rotate", axis }), [send]),
    setLayerVisible: useCallback((name, visible) => send({ type: "layer", name, visible }), [send]),
    resetMaterial: useCallback(() => send({ type: "resetMaterial" }), [send]),
    resetBends: useCallback(() => send({ type: "resetBends" }), [send]),
    resetOrientation: useCallback(() => send({ type: "resetOrientation" }), [send])
  };
}
