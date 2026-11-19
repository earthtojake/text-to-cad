import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  PARAMETER_REASONS, PARAMETER_REFUSALS, changedParameters, formatParameterValue, parameterIsRanged, parameterStep, parameterValue,
  sameParameterValue, savedParametersNote, settledDrafts, xbfParameters
} from "@cad/core/lib/xbf/xbfParameters.js";
import { Button } from "@cad/ui/primitives/button";
import { Spinner } from "@cad/ui/primitives/spinner";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { FileSheetNumberProperty, FileSheetSettingRow, FileSheetStatusText, parseFileSheetNumberInput } from "../kit/inspector/FileSheet.js";
import { SliderField } from "../kit/inspector/SliderField.jsx";
import { useFlatPanel } from "../kit/shell/FlatPanel.jsx";
import { useI18n } from "@cad/ui/i18n";

// An engine document's Parameters: the view's panel's tab for a model whose script declares named
// numbers (`docs/settings-ui.md`, "Parameters"). Each is a control over the value the document was
// built with -- the slider control where it declares both ends of a range, a number field
// otherwise -- and what a person sets is a draft, the tab's own, until Save sends every changed
// value in one request (`client.setModelParameters`): the engine rewrites those numbers in the
// script and builds the model again, and the rebuilt document arrives as any new version does.
// Nothing is written while a slider moves, and the scene is never changed from here. A parameter
// the engine cannot write is its value and one line saying why.

const NO_DRAFTS = Object.freeze({});
const IDLE = Object.freeze({ drafts: NO_DRAFTS, sent: null, saving: false, saved: false, error: null });
// The refusals whose own sentence names what is wrong (which parameter, what the build said): said under ours.
const DETAILED = new Set(["unknown_parameter", "not_writable", "not_a_number", "out_of_range", "build_failed"]);
// A reason that is the whole document's, not one parameter's: said once, over the list.
const DOCUMENT_REASONS = new Set(["file", "no_worker", "unavailable"]);
// A parameter's row: its name takes the room, and its value a column at the right, ending on the panel's line.
const ROW_COLUMNS = "grid-cols-[minmax(0,1fr)_5.5rem]";

/** A save that failed, as the tab says it: the engine's `code` where it is one of its refusals, and its words. */
function failureOf(error) {
  const code = typeof error?.code === "string" && PARAMETER_REFUSALS.includes(error.code) ? error.code : "";
  const message = String(error instanceof Error ? error.message : error || "").trim();
  return { code, message, hint: typeof error?.hint === "string" && !code ? error.hint.trim() : "" };
}

/**
 * A model's parameters as the tab edits them, kept by the view for as long as the file is on
 * screen (the tab itself is not mounted on a phone, nor while the view loads): the document's
 * `parameters`, the drafts a person set (by name, never stored by the host), and Save and Reset.
 *
 * `setDraft(name, value)` is the write boundary: the value is held as the parameter takes it
 * (`parameterValue`: its range, a whole number for an integer), and a draft equal to the document's
 * value is no draft. `save()` sends the changed values alone, in one request; while it is out the
 * tab is `saving`. A save answered leaves the drafts as they are -- the scene is the rebuilt
 * document's to change, not the tab's -- and the next version of the document takes each draft it
 * now holds. A save refused keeps every draft and says why (`error`: the engine's `code`, its
 * message, its hint). `reset()` drops the drafts not yet saved.
 *
 * What was saved is remembered (each value before and after, and its script) until a Quick Edit
 * carries it to the agent (`notes`, the shell's `promptNotes`).
 *
 * @param {{ client: { setModelParameters?: Function } | null, document: { structure?: object, source?: { kind?: string, doc?: string } } | null }} options
 */
export function useXbfParameters({ client, document }) {
  const structure = document?.structure || null;
  const parameters = useMemo(() => xbfParameters(structure), [structure]);
  // Only a model has a script to write: the engine says so of every parameter of any other document.
  const model = document?.source?.kind === "model" ? String(document.source.doc || "") : "";
  const savable = Boolean(model) && typeof client?.setModelParameters === "function";
  const [state, setState] = useState(IDLE);
  const live = useRef(null);
  live.current = { state, parameters, model, client, savable };
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  // A new version of the document: each draft it now holds is no draft, and what was sent is answered.
  const read = useRef(parameters);
  useEffect(() => {
    if (read.current === parameters) return;
    read.current = parameters;
    setState(now => {
      const drafts = settledDrafts(parameters, now.drafts);
      return drafts === now.drafts && !now.sent ? now : { ...now, drafts, sent: null };
    });
  }, [parameters]);

  const changed = useMemo(() => changedParameters(parameters, state.drafts, state.sent), [parameters, state.drafts, state.sent]);
  const setDraft = useCallback((name, next) => {
    const parameter = live.current.parameters.find(item => item.name === name);
    if (!parameter?.writable || live.current.state.saving) return;
    const value = parameterValue(parameter, next);
    if (value === null) return;
    setState(now => {
      const drafts = { ...now.drafts };
      if (sameParameterValue(parameter, value, parameter.value)) delete drafts[name]; else drafts[name] = value;
      return { ...now, drafts, saved: false, error: null };
    });
  }, []);
  // What was sent stays on its controls until the rebuilt document arrives; everything else goes back.
  const reset = useCallback(() => setState(now => (now.saving ? now : {
    ...now, saved: false, error: null,
    drafts: Object.fromEntries(Object.entries(now.drafts).filter(([name]) => now.sent && Object.hasOwn(now.sent, name) && now.sent[name] === now.drafts[name]))
  })), []);

  const saved = useRef([]);
  const save = useCallback(async () => {
    const { state: now, parameters: declared, model: id, client: service, savable: able } = live.current;
    const values = changedParameters(declared, now.drafts, now.sent);
    if (!able || now.saving || !Object.keys(values).length) return;
    setState(current => ({ ...current, saving: true, saved: false, error: null }));
    try {
      const answer = await service.setModelParameters(id, values);
      for (const entry of Array.isArray(answer?.written) ? answer.written : []) {
        if (typeof entry?.name === "string") saved.current = [...saved.current, { name: entry.name, from: entry.from, to: entry.to, file: entry.file }];
      }
      if (!mounted.current) return;
      setState(current => {
        // Still on its control, and not yet the document's: awaited, not sent again.
        const sent = Object.fromEntries(Object.entries(values).filter(([name, value]) => current.drafts[name] === value));
        return { ...current, saving: false, saved: true, error: null, sent: Object.keys(sent).length ? { ...current.sent, ...sent } : current.sent };
      });
    } catch (error) {
      if (mounted.current) setState(current => ({ ...current, saving: false, saved: false, error: failureOf(error) }));
    }
  }, []);

  const notes = useMemo(() => ({
    take() {
      const taken = saved.current;
      const text = savedParametersNote(taken);
      // Told once: what this message carried is forgotten when it has gone, what was saved since is kept.
      return text ? { text, done: () => { saved.current = saved.current.filter(entry => !taken.includes(entry)); } } : null;
    }
  }), []);

  return useMemo(() => ({ parameters, drafts: state.drafts, changed, dirty: Object.keys(changed).length > 0, saving: state.saving, saved: state.saved,
    error: state.error, savable, setDraft, reset, save, notes }),
  [parameters, state.drafts, state.saving, state.saved, state.error, changed, savable, setDraft, reset, save, notes]);
}

/**
 * @param {{ parameters: ReturnType<typeof useXbfParameters> }} props  The view's parameters (`useXbfParameters`).
 */
export default function XbfParametersSection({ parameters: model }) {
  const { t } = useI18n();
  const flatPanel = useFlatPanel();
  const { parameters, drafts, saving, savable } = model;
  // The panel's search finds a parameter by its name; its hits are the tab's rows.
  const searching = Boolean(flatPanel?.searching);
  const query = searching ? String(flatPanel.query || "").trim().toLowerCase() : "";
  const shown = query ? parameters.filter(parameter => parameter.name.toLowerCase().includes(query)) : parameters;
  // Why a parameter is not set here: the engine's reason, or this view's (a host that cannot save).
  const reasonOf = parameter => (!parameter.writable ? parameter.reason || "unknown" : savable ? "" : "unavailable");
  const reasons = parameters.map(reasonOf);
  // One reason for all of them that is the document's own (a file, a model whose script is not held): said once.
  const shared = reasons.length && reasons.every(reason => reason === reasons[0]) && DOCUMENT_REASONS.has(reasons[0]) ? reasons[0] : "";
  const why = (parameter, reason) => (reason === "shared" ? (parameter.source ? t("parameters.reason.sharedIn", { source: parameter.source }) : t("parameters.reason.shared"))
    : t(`parameters.reason.${[...PARAMETER_REASONS, "unavailable"].includes(reason) ? reason : "unknown"}`));
  const editable = reasons.some(reason => !reason);
  const count = Object.keys(model.changed).length;
  const status = saving ? "" : count ? t("parameters.unsaved", { count }) : model.saved ? t("parameters.saved") : "";
  const error = model.error;
  const hit = searching ? "" : undefined;

  const row = (parameter, at) => {
    const reason = reasons[parameters.indexOf(parameter)];
    const name = parameter.name;
    if (reason) {
      return <div key={name} data-parameter={name} data-parameter-control="none" data-flat-panel-hit={hit}>
        <FileSheetSettingRow label={name} className={ROW_COLUMNS}>
          <span className="min-w-0 flex-1 truncate text-right text-tiny tabular-nums text-foreground" data-parameter-value="">{formatParameterValue(parameter, parameter.value)}</span>
        </FileSheetSettingRow>
        {shared ? null : <FileSheetStatusText data-parameter-reason={reason}>{why(parameter, reason)}</FileSheetStatusText>}
      </div>;
    }
    const value = Object.hasOwn(drafts, name) ? drafts[name] : parameter.value;
    const text = formatParameterValue(parameter, value);
    const typed = draft => {
      // A value left as it shows writes nothing: its text may round the value it shows.
      if (String(draft ?? "").trim() === text.trim()) return;
      model.setDraft(name, parseFileSheetNumberInput(draft, { fallback: value, min: parameter.min ?? -Infinity, max: parameter.max ?? Infinity, integer: parameter.kind === "int" }));
    };
    if (parameterIsRanged(parameter)) {
      return <SliderField key={name} label={name} labelTitle={name} name={name} disabled={saving} text={text} onTextCommit={typed}
        textLabel={t("field.value", { name })} value={value} min={parameter.min} max={parameter.max} step={parameterStep(parameter) ?? 1}
        // Filled from the document's value to the draft: what is changed, and how far, at a glance.
        origin={Math.min(Math.max(parameter.value, parameter.min), parameter.max)} hint={t("position.range", { min: formatParameterValue(parameter, parameter.min), max: formatParameterValue(parameter, parameter.max) })}
        onValueChange={next => model.setDraft(name, next ?? value)}
        data-parameter={name} data-parameter-control="slider" data-flat-panel-hit={hit} />;
    }
    return <div key={name} data-parameter={name} data-parameter-control="number" data-flat-panel-hit={hit}>
      <FileSheetSettingRow label={name} disabled={saving} className={`h-7 ${ROW_COLUMNS}`}>
        <FileSheetNumberProperty label={name} hint={null} value={text} disabled={saving} onValueCommit={typed} className="w-full" />
      </FileSheetSettingRow>
    </div>;
  };

  return <ToolPanel id="parameters" title={t("parameters.title")} label={t("parameters.controls")} fit="details">
    <div className="space-y-1 pb-2 pt-0.5">
      {/* Save and Reset, the tab's first row as Position's Pose row is: what there is to save at its left. */}
      {editable && shown.length ? <div className="flex h-8 items-center gap-1.5 px-2" data-parameters-actions="">
        <span role="status" className="min-w-0 flex-1 truncate text-tiny leading-4 text-muted-foreground" data-parameters-status="">{status}</span>
        <Button type="button" variant="ghost" size="xs" className="h-6 shrink-0 px-1.5 text-tiny font-normal" disabled={saving || !model.dirty} onClick={model.reset}
          data-parameters-reset="">{t("parameters.reset")}</Button>
        <Button type="button" variant="default" size="xs" className="h-6 shrink-0 px-2 text-tiny font-normal" disabled={saving || !model.dirty} aria-busy={saving || undefined}
          onClick={model.save} data-parameters-save="">
          {saving ? <Spinner className="size-3" role="presentation" aria-hidden="true" aria-label={undefined} /> : null}
          {t(saving ? "parameters.saving" : "parameters.save")}
        </Button>
      </div> : null}
      {error ? <div role="alert" className="space-y-0.5 px-2 pb-1 text-tiny leading-4 text-destructive" data-parameters-error={error.code || "unknown"}>
        <p>{t(error.code ? `parameters.error.${error.code}` : "parameters.error.failed")}</p>
        {error.message && (!error.code || DETAILED.has(error.code)) ? <p className="wrap-anywhere whitespace-pre-wrap text-muted-foreground" data-parameters-error-detail="">
          {[error.message, error.hint].filter(Boolean).join("\n")}</p> : null}
      </div> : null}
      {shared && shown.length ? <FileSheetStatusText data-parameter-reason={shared}>{t(`parameters.reason.${shared}`)}</FileSheetStatusText> : null}
      {shown.map(row)}
    </div>
  </ToolPanel>;
}
