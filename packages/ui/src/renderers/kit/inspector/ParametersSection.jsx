import { memo, useEffect, useRef, useState } from "react";
import { useI18n } from "@cad/ui/i18n";
import { SliderField } from "./SliderField.jsx";
import ToolPanel from "../tools/ToolPanel.jsx";

// A value as its text: enough digits for the slider's span, no trailing zeros.
function shown(value, span) {
  const digits = span >= 100 ? 1 : span >= 10 ? 2 : 3;
  return String(Number(value.toFixed(digits)));
}

// One parameter: a slider over the model's own range. It writes at most once per animation frame,
// so a drag marches the field once a frame and no more, and a write asks the server for nothing: the
// value is a number in the field's uniform block.
const ParameterRow = memo(function ParameterRow({ parameter, scene, onChange }) {
  const { t } = useI18n();
  const { name, min, max } = parameter;
  const [value, setValue] = useState(() => scene.parameterValue(name));
  const pending = useRef({ frame: 0, value });
  useEffect(() => () => { if (pending.current.frame) cancelAnimationFrame(pending.current.frame); }, []);
  const write = (next) => {
    const clamped = Math.min(Math.max(Number(next), min), max);
    if (!Number.isFinite(clamped)) return;
    setValue(clamped);
    pending.current.value = clamped;
    if (pending.current.frame) return;
    pending.current.frame = requestAnimationFrame(() => {
      pending.current.frame = 0;
      if (scene.setParameter(name, pending.current.value)) onChange();
    });
  };
  return <SliderField data-field-parameter={name} label={name} name={name} textLabel={t("field.parameter.value", { name })}
    value={value} min={min} max={max} step={(max - min) / 200} origin={min}
    text={shown(value, max - min)} onValueChange={write} onTextCommit={write}
    hint={t("field.parameter.range", { min: shown(min, max - min), max: shown(max, max - min) })} />;
});

/**
 * The view's panel's Parameters tab: the model's sliders, each over the range the model gives it.
 * Moving one redraws the field as it would be with that value; the file is not changed.
 */
export default function ParametersSection({ scene, revision, onChange }) {
  const { t } = useI18n();
  return <ToolPanel id="parameters" title={t("field.parameters.title")} label={t("field.parameters.controls")} fit="details">
    {scene.parameters.map(parameter => <ParameterRow key={`${revision}:${parameter.name}`} parameter={parameter} scene={scene} onChange={onChange} />)}
  </ToolPanel>;
}
