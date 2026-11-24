import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  PARAMETER_REASONS, PARAMETER_REFUSALS, changedParameters, formatParameterValue, parameterIsRanged, parameterStep, parameterValue,
  sameParameterValue, savedParametersNote, settledDrafts, unsavedParametersNote, xbfParameters
} from "@cad/core/lib/xbf/xbfParameters.js";
import { Button } from "@cad/ui/primitives/button";
import { Spinner } from "@cad/ui/primitives/spinner";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { FileSheetNumberProperty, FileSheetSettingRow, parseFileSheetNumberInput } from "../kit/inspector/FileSheet.js";
import { SliderField } from "../kit/inspector/SliderField.jsx";
import { PANEL_ACTION_CLASS, PanelActions } from "../kit/inspector/PanelActions.jsx";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { TreeRowHeading } from "@cad/ui/primitives/tree-row";
import { cn } from "@cad/ui/utils";
import { useI18n } from "@cad/ui/i18n";
import { FlatPanelChanged } from "../kit/shell/FlatPanel.jsx";

// An engine document's Parameters: the view's panel's tab for a model whose script declares named
// numbers (`docs/viewer-ux.md`, "Parameters"). Each is a control over the value the document was
// built with -- the slider control where it declares both ends of a range, a number field
// otherwise -- and what a person sets is a draft, the tab's own, until Save sends every changed
// value in one request (`client.setModelParameters`): the engine rewrites those numbers in the
// script and builds the model again, and the rebuilt document arrives as any new version does.
// While a draft differs, the view shows the model at the drafts (`client.previewModelParameters`):
// the engine builds it for this page alone and writes nothing, and the scene draws it in the
// document's place until Save lands or Reset lets it go. A parameter the engine cannot write is its control,
// off, its hint saying why; Save off for a reason says why in its hint, but where nothing in the tab can work
// (a file's document, a script no worker holds, a script changed since it ran): the foot's status says that,
// once, in place of "Saved".

const NO_DRAFTS = Object.freeze({});
const IDLE = Object.freeze({ drafts: NO_DRAFTS, sent: null, saving: false, saved: false, error: null, locked: null });
// The refusal that says no worker holds the model's run, so nothing can be previewed or saved from here until its
// script runs again: the tab's controls go off, and the foot says why, until the document's next version.
const LOCKING = new Set(["no_worker"]);
// The refusal that says the script on disk is not the one that ran (changed by hand since): no preview or save
// can work until it runs again, but nothing the person set is taken from them. The drafts stay on their controls
// and the view keeps what it drew; nothing more is asked, Save is off, and the foot says why, until the
// document's next version (the engine never watches the file: its next run is how the tab learns of it).
const CHANGED = "script_changed";
// How long a save refused `busy` (a run or another save of the script under way) keeps Save off, if no new
// version of the document comes first.
const BUSY_HOLD_MS = 2000;
// A model building already (`busy`): its preview is asked again, waiting longer each time, never said.
const busyWait = tries => Math.min(250 * 2 ** tries, 2000);
// The cadence of the previews (`docs/viewer-ux.md`, "Parameters"), from how long this model's take, request to
// answer. A model answered within FAST_PREVIEW_MS follows a slider as it moves: the newest values go as each
// answer arrives. A slower one is sent nothing while the slider moves, only the value it comes to: the pointer
// let go, a step of the keyboard or a value typed, or the slider at rest for SETTLED_MS, so no build is spent on
// a value the person has passed already (a build in the kernel cannot be stopped once begun). A quarter second is
// about where a model drawn as it moves stops reading as following the hand; three tenths of a second at rest is
// a person who has found the value, and longer than the gaps between a moving pointer's events.
const FAST_PREVIEW_MS = 250;
const SETTLED_MS = 300;
// How much the newest preview's time weighs in a model's running estimate (the rest, the estimate before it):
// one slow first build is outweighed in two or three, and one stray answer does not swing the cadence.
const ESTIMATE_WEIGHT = 0.5;
// This page's own token, which keeps its previews from another page's (the engine holds each page's apart).
const pageToken = () => {
  const random = globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `page-${random}`.replace(/[^A-Za-z0-9_-]/g, "").slice(0, 64);
};
// A reason that is the whole document's, not one parameter's: said once, over the list, in this order
// (a file's before anything else; a script no worker holds before a view that could not save anyway).
const DOCUMENT_REASONS = ["file", "no_worker", "unavailable"];
// A parameter's row: its name takes the room, and its value a column at the right, ending on the panel's line.
const ROW_COLUMNS = "grid-cols-[minmax(0,1fr)_5.5rem]";
const FOOT_MARKS = Object.freeze({ "data-parameters-foot": "" });

/**
 * The parameters by the file that declares them, where they come from more than one: the model's own
 * first and unnamed (every parameter not set in another file), then each other file's (`shared`: declared
 * in an imported module) under its name, in the order they are first met. Parameters all from one file are
 * one unnamed group: no heading at all.
 * @param {readonly import("@cad/core/lib/xbf/xbfParameters.js").XbfParameter[]} parameters
 * @returns {{ file: string | null, parameters: import("@cad/core/lib/xbf/xbfParameters.js").XbfParameter[] }[]}
 */
export function parameterGroups(parameters) {
  const own = [], others = new Map();
  for (const parameter of parameters) {
    if (parameter.reason === "shared" && parameter.source) {
      if (!others.has(parameter.source)) others.set(parameter.source, []);
      others.get(parameter.source).push(parameter);
    } else own.push(parameter);
  }
  const groups = [...(own.length ? [{ file: null, parameters: own }] : []), ...[...others].map(([file, listed]) => ({ file, parameters: listed }))];
  return groups.length > 1 ? groups : [{ file: null, parameters: [...parameters] }];
}

/**
 * A save or preview that failed, as the tab says it: the engine's `code` where it is one of its refusals.
 * A failure with no code of the engine's (a code this page does not know, the request that never got an
 * answer) is said as a failure, no more: the engine's message is not shown (a build's can run to many lines).
 */
function failureOf(error) {
  return { code: typeof error?.code === "string" && PARAMETER_REFUSALS.includes(error.code) ? error.code : "" };
}

/**
 * A model's parameters as the tab edits them, kept by the view for as long as the file is on
 * screen (the tab itself is not mounted on a phone, nor while the view loads): the document's
 * `parameters`, the drafts a person set (by name, never stored by the host), the preview of them, and
 * Save and Reset.
 *
 * `setDraft(name, value)` is the write boundary: the value is held as the parameter takes it
 * (`parameterValue`: its range, a whole number for an integer), and a draft equal to the document's
 * value is no draft; `commit(name, value)` is a value the person means (a slider let go or stepped, a value
 * typed). The drafts ask the engine for the model at them (`client.previewModelParameters`), one request out
 * per document at a time, at a cadence set by how long this model's previews take (a running estimate, request
 * to answer, by document): a fast model's newest drafts go as each answer arrives, so the model follows a
 * slider as it rebuilds; a slow model's go only once meant (`commit`) or at rest for SETTLED_MS. While a request
 * is out, nothing is said. An answer is
 * handed to the view to draw (`onPreview(url)`: the scene's `preview`), the camera where it is. Drafts
 * equal to the document (Reset, a Save that landed) let the preview go (`onPreview(null)`, and the
 * engine is told). A model building already (`busy`) is asked again; a preview refused is kept as the reason
 * Save is off (`error`, `during: "preview"`) and the view keeps the last one that built. A refusal that no worker
 * holds the run (`no_worker`, from a preview or a save) locks the tab (`locked`): the drafts and their preview
 * go, and nothing is previewed or saved until the document's next version. A refusal that the script changed
 * since it ran (`script_changed`) is kept until that version too, but takes nothing back: the drafts stay where
 * the person put them, the view keeps what it drew, and nothing more is asked or saved until then.
 *
 * `save()` sends the changed values alone, in one request (`client.setModelParameters`); while it is
 * out the tab is `saving` and nothing more is previewed. A save answered leaves the values it wrote on
 * their controls, and the preview on screen, until the document's next version holds them, which the
 * view then draws; a value it did not write (the script already held it) goes back to the document's.
 * A save refused keeps every draft and the preview, and is the reason Save is off until the next edit (`busy`:
 * for a moment). `reset()` drops the drafts not yet saved, and the view draws the document again.
 *
 * What was saved is remembered (each value before and after, and its script) until a Quick Edit
 * carries it to the agent (`notes`, the shell's `promptNotes`): `take()` hands it to one message at a
 * time, and it is forgotten once that message has gone (`done()`), or handed out again when it did
 * not (`cancel()`). A message sent while unsaved values are on screen says so too, every time
 * (`unsavedParametersNote`): what the agent is shown is not the script.
 *
 * `onEdit()` is told of each edit a person makes (a draft set), before anything is asked: the view lets go of
 * what holds the model (a motion playing or paused), so a preview refused leaves nothing locked; the Joints
 * pose stays while the mechanism is the same, and goes back to Default when the joints changed (`useXbfPose`).
 *
 * @param {{ client: { setModelParameters?: Function, previewModelParameters?: Function } | null,
 *   document: { structure?: object, source?: { kind?: string, doc?: string } } | null,
 *   onPreview?: (url: string | null) => void, onEdit?: (() => void) | null }} options
 */
export function useXbfParameters({ client, document, onPreview = null, onEdit = null }) {
  const structure = document?.structure || null;
  const parameters = useMemo(() => xbfParameters(structure), [structure]);
  // Only a model has a script to write: the engine says so of every parameter of any other document.
  const model = document?.source?.kind === "model" ? String(document.source.doc || "") : "";
  // A host that cannot make the request leaves the client's method out: its view shows the values alone.
  const savable = Boolean(model) && typeof client?.setModelParameters === "function";
  const previewable = savable && typeof client?.previewModelParameters === "function";
  const [state, setState] = useState(IDLE);
  const live = useRef(null);
  live.current = { state, parameters, model, client, savable, previewable, onPreview, onEdit };
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  // ---- the preview: the model at the drafts, one request out at a time, the newest values next ---------
  const page = useRef(null);
  if (page.current === null) page.current = pageToken();
  // What the engine holds for this page (the values last answered, as text, "{}" for none, and as values), the
  // request out, how many times it was busy, and a count that each Reset, Save and model change moves on, so
  // an answer to a request sent before one is not drawn. The cadence's own: each model's running estimate of a
  // preview's time (ms, by document id; none before its first answer), whether the values on the controls are
  // meant (`settled`: let go, stepped, typed, or at rest), when they last moved, and the wait for them to rest.
  const asked = useRef({ held: "{}", out: false, busy: 0, timer: null, round: 0,
    estimates: new Map(), settled: false, movedAt: 0, rest: null, restFor: "" });
  // What the view was last told to draw: told again only when it changes.
  const told = useRef(null);
  const draw = useCallback(url => {
    if (told.current === url) return;
    told.current = url;
    live.current.onPreview?.(url);
  }, []);
  const stopResting = () => {
    const flight = asked.current;
    if (flight.rest !== null) clearTimeout(flight.rest);
    flight.rest = null;
    flight.restFor = "";
  };
  const ask = useCallback(async () => {
    const { state: now, parameters: declared, model: id, client: service, previewable: able } = live.current;
    const flight = asked.current;
    if (!able || now.saving || now.sent || now.locked) return;
    const values = changedParameters(declared, now.drafts);
    const text = JSON.stringify(values);
    // The drafts back at the document's values: the document is drawn at once, whatever is out; the engine is
    // told after.
    if (text === "{}") draw(null);
    if (now.error?.code === CHANGED) return;
    if (flight.out || flight.timer !== null) return;
    if (text === flight.held) { flight.settled = false; stopResting(); return; }
    // A slow model: values still moving are not sent. They go once they are meant: let go, stepped or typed
    // (`settled`), or at rest for SETTLED_MS since they last moved. A model not yet previewed is taken as fast.
    const estimate = flight.estimates.get(id) ?? null;
    if (text !== "{}" && !flight.settled && estimate !== null && estimate >= FAST_PREVIEW_MS) {
      const wait = flight.movedAt + SETTLED_MS - performance.now();
      if (wait > 0) {
        if (flight.restFor !== text) {
          stopResting();
          flight.restFor = text;
          flight.rest = setTimeout(() => { flight.rest = null; flight.restFor = ""; flight.settled = true; void askRef.current(); }, wait);
        }
        return;
      }
    }
    flight.settled = false;
    stopResting();
    const round = flight.round;
    flight.out = true;
    const started = performance.now();
    let again = true;
    try {
      const answer = await service.previewModelParameters(id, values, { page: page.current });
      flight.busy = 0;
      if (!answer?.superseded) {
        flight.held = answer?.preview ? text : "{}";
      }
      // A build answered: its time, request to answer, moves the model's estimate. (Values that are the
      // document's build nothing, and one superseded never built: neither says how long this model takes.)
      if (answer?.preview && !answer.superseded) {
        const took = performance.now() - started;
        const before = flight.estimates.get(id);
        flight.estimates.set(id, before === undefined ? took : before * (1 - ESTIMATE_WEIGHT) + took * ESTIMATE_WEIGHT);
      }
      // Drawn unless a Reset, a save or another model came since, or the drafts went back to the document's.
      const drafted = Object.keys(changedParameters(live.current.parameters, live.current.state.drafts)).length > 0;
      if (round === asked.current.round && mounted.current && !answer?.superseded) {
        if (answer?.preview?.url && drafted) draw(answer.preview.url);
        else if (!drafted) draw(null);
        setState(current => (current.error?.during === "preview" ? { ...current, error: null } : current));
      }
    } catch (error) {
      const failure = failureOf(error);
      if (failure.code === "busy") {
        // A run or a save of the script first: asked again once it may be done, with the newest drafts then.
        again = false;
        const wait = busyWait(flight.busy++);
        flight.timer = setTimeout(() => { asked.current.timer = null; void askRef.current(); }, wait);
      } else if (LOCKING.has(failure.code)) {
        // The script can't be previewed from here until it runs again: so said in the foot, the controls off.
        again = false;
        if (round === asked.current.round && mounted.current) lockRef.current(failure);
      } else if (failure.code === CHANGED) {
        // The script changed since it ran: said in the foot, nothing taken back, nothing more asked until it runs.
        again = false;
        flight.held = text;
        if (round === asked.current.round && mounted.current) setState(current => ({ ...current, error: { ...failure, during: "preview" } }));
      } else {
        // Refused: Save says why, and the last preview that built stays on screen. The same values are not asked again.
        flight.held = text;
        if (round === asked.current.round && mounted.current) setState(current => ({ ...current, error: { ...failure, during: "preview" } }));
      }
    } finally {
      flight.out = false;
    }
    if (again && mounted.current) void askRef.current();
  }, [draw]);
  const askRef = useRef(ask);
  askRef.current = ask;
  const letGo = useCallback(() => {
    // Reset, a save, another model: no answer sent before it is drawn, nothing waits to be asked again or to
    // rest.
    const flight = asked.current;
    flight.round += 1;
    if (flight.timer !== null) clearTimeout(flight.timer);
    flight.timer = null;
    flight.busy = 0;
    flight.settled = false;
    stopResting();
  }, []);
  // A refusal that the script must run again first: the drafts and their preview go (none of them can be
  // shown or saved), the document is drawn, and the tab is locked until the document's next version.
  const lock = useCallback(failure => {
    letGo();
    draw(null);
    setState(now => ({ ...now, drafts: NO_DRAFTS, sent: null, saving: false, saved: false, error: null, locked: failure }));
  }, [letGo, draw]);
  const lockRef = useRef(lock);
  lockRef.current = lock;
  // The drafts moved, a save landed, or a refusal was cleared (the script run again): the model at them is asked
  // for (or let go, at the document's values).
  useEffect(() => { void askRef.current(); }, [state.drafts, state.sent, state.saving, state.error, parameters]);

  // A new version of the document: each draft it now holds is no draft, and what was sent is answered.
  const read = useRef(parameters);
  useEffect(() => {
    if (read.current === parameters) return;
    read.current = parameters;
    setState(now => {
      const drafts = settledDrafts(parameters, now.drafts);
      // A new version ran the script again, or ended the build a save waited on.
      const locked = null, error = now.error?.code === "busy" || now.error?.code === CHANGED ? null : now.error;
      return drafts === now.drafts && !now.sent && !now.locked && error === now.error ? now : { ...now, drafts, sent: null, locked, error };
    });
  }, [parameters]);

  // A save refused `busy`: Save is off for a moment, then may be pressed again.
  useEffect(() => {
    if (state.error?.code !== "busy") return undefined;
    const busy = state.error;
    const timer = setTimeout(() => setState(now => (now.error === busy ? { ...now, error: null } : now)), BUSY_HOLD_MS);
    return () => clearTimeout(timer);
  }, [state.error]);
  const changed = useMemo(() => changedParameters(parameters, state.drafts, state.sent), [parameters, state.drafts, state.sent]);
  const setDraft = useCallback((name, next) => {
    const parameter = live.current.parameters.find(item => item.name === name);
    if (!parameter?.writable || live.current.state.saving || live.current.state.locked) return;
    const value = parameterValue(parameter, next);
    if (value === null) return;
    // A person's edit of the model is a change of it as a motion's is of its pose: what moves it lets go first
    // (`onEdit`: the view's motion), whether or not the preview it asks for is ever drawn.
    live.current.onEdit?.();
    asked.current.movedAt = performance.now();
    setState(now => {
      const drafts = { ...now.drafts };
      if (sameParameterValue(parameter, value, parameter.value)) delete drafts[name]; else drafts[name] = value;
      // A changed script is not cleared by an edit: only its next run tells the tab it can work again.
      return { ...now, drafts, saved: false, error: now.error?.code === CHANGED ? now.error : null };
    });
  }, []);
  // A value the person means (a slider let go or stepped by the keyboard, a value typed): set as a draft, and its
  // preview asked for now, whatever the model's cadence. A slider let go where it last moved changes no draft.
  const commit = useCallback((name, next) => {
    const parameter = live.current.parameters.find(item => item.name === name);
    const { state: now } = live.current;
    if (!parameter?.writable || now.saving || now.locked) return;
    const value = parameterValue(parameter, next);
    if (value === null) return;
    asked.current.settled = true;
    const current = Object.hasOwn(now.drafts, name) ? now.drafts[name] : parameter.value;
    if (!sameParameterValue(parameter, value, current)) setDraft(name, value);
    else void askRef.current();
  }, [setDraft]);
  // What was sent stays on its controls until the rebuilt document arrives; everything else goes back, and the
  // view draws the document again at once.
  const reset = useCallback(() => {
    if (live.current.state.saving) return;
    letGo();
    if (!live.current.state.sent) draw(null);
    setState(now => (now.saving ? now : {
      ...now, saved: false, error: now.error?.code === CHANGED ? now.error : null,
      drafts: Object.fromEntries(Object.entries(now.drafts).filter(([name]) => now.sent && Object.hasOwn(now.sent, name) && now.sent[name] === now.drafts[name]))
    }));
  }, [letGo, draw]);

  const saved = useRef([]);
  const inFlight = useRef(false);
  const save = useCallback(async () => {
    const { state: now, parameters: declared, model: id, client: service, savable: able } = live.current;
    const values = changedParameters(declared, now.drafts, now.sent);
    // One save at a time, a second press before the first has re-rendered included.
    if (!able || now.saving || now.locked || now.error || inFlight.current || !Object.keys(values).length) return;
    inFlight.current = true;
    letGo();  // a preview answered from now on is of values before the save: the save's version is drawn next
    setState(current => ({ ...current, saving: true, saved: false, error: null }));
    try {
      const answer = await service.setModelParameters(id, values);
      const written = Array.isArray(answer?.written) ? answer.written.filter(entry => typeof entry?.name === "string" && entry.name) : null;
      for (const entry of written || []) saved.current = [...saved.current, { name: entry.name, from: entry.from, to: entry.to, file: entry.file }];
      if (!mounted.current) return;
      setState(current => {
        // A value the engine did not write (its script already held it) brings no new version: its
        // draft goes, and the control shows the document's value again.
        const wrote = written ? new Set(written.map(entry => entry.name)) : null;
        const drafts = !wrote ? current.drafts : Object.fromEntries(Object.entries(current.drafts)
          .filter(([name, value]) => wrote.has(name) || !Object.hasOwn(values, name) || values[name] !== value));
        // Written, still on its control and not yet the document's: awaited, not sent again.
        const sent = Object.fromEntries(Object.entries(values).filter(([name, value]) => drafts[name] === value));
        return { ...current, drafts, saving: false, saved: true, error: null, sent: Object.keys(sent).length ? { ...current.sent, ...sent } : current.sent };
      });
    } catch (error) {
      const failure = failureOf(error);
      if (!mounted.current) return;
      if (LOCKING.has(failure.code)) lock(failure);
      else setState(current => ({ ...current, saving: false, saved: false, error: { ...failure, during: "save" } }));
    } finally {
      inFlight.current = false;
    }
  }, [letGo, lock]);

  // Another model: nothing set for the last one goes to this one, and its preview is let go.
  const shownModel = useRef(model);
  useEffect(() => {
    if (shownModel.current === model) return;
    const before = { id: shownModel.current, held: asked.current.held, client: live.current.client };
    shownModel.current = model;
    letGo();
    draw(null);
    asked.current.held = "{}";
    if (before.id && before.held !== "{}") void before.client?.previewModelParameters?.(before.id, {}, { page: page.current }).catch(() => {});
    setState(IDLE);
  }, [model, letGo, draw]);
  // The view closed: the engine is told it may let this page's preview go (else it does once nobody reads it).
  useEffect(() => () => {
    letGo();
    const { model: id, client: service } = live.current;
    if (id && asked.current.held !== "{}") void service?.previewModelParameters?.(id, {}, { page: page.current }).catch(() => {});
  }, [letGo]);

  // What a message on its way carries: handed out once, so a second message pressed before the first has
  // gone carries none of it; forgotten when that message has gone (`done`), handed out again when it did
  // not go (`cancel`).
  const handed = useRef(new Set());
  const notes = useMemo(() => ({
    take() {
      const taken = saved.current.filter(entry => !handed.current.has(entry));
      // Values on screen and not saved: said with every message while they are, never remembered as a change.
      const { state: now, parameters: declared } = live.current;
      const unsaved = now.sent ? "" : unsavedParametersNote(declared, changedParameters(declared, now.drafts));
      const text = [savedParametersNote(taken), unsaved].filter(Boolean).join("\n");
      if (!text) return null;
      for (const entry of taken) handed.current.add(entry);
      const release = () => { for (const entry of taken) handed.current.delete(entry); };
      // Told once: what this message carried is forgotten when it has gone, what was saved since is kept.
      return { text,
        done: () => { saved.current = saved.current.filter(entry => !taken.includes(entry)); release(); },
        cancel: release };
    }
  }), []);

  return useMemo(() => ({ parameters, drafts: state.drafts, changed, dirty: Object.keys(changed).length > 0, saving: state.saving, saved: state.saved,
    error: state.error, locked: state.locked, ofModel: Boolean(model), savable, setDraft, commit, reset, save, notes }),
  [parameters, state.drafts, state.saving, state.saved, state.error, state.locked, changed, model, savable, setDraft, commit, reset, save, notes]);
}

/**
 * A control that is off for a reason the person can act on: its hint says why, on a wrapper that takes the
 * pointer and the keyboard for it (a disabled control takes neither).
 */
function Explained({ reason, description = "", children, className = "", ...props }) {
  if (!reason) return children;
  return <TooltipHint content={reason} explainsDisabled side="right">
    <div tabIndex={0} aria-description={description || (typeof reason === "string" ? reason : undefined)}
      className={cn("rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 [&_:disabled]:pointer-events-none", className)} {...props}>
      {children}
    </div>
  </TooltipHint>;
}

/**
 * @param {{ parameters: ReturnType<typeof useXbfParameters> }} props  The view's parameters (`useXbfParameters`).
 */
export default function XbfParametersSection({ parameters: model }) {
  const { t } = useI18n();
  const { parameters, drafts, saving, savable } = model;
  // The panel's search covers its tree-like tabs alone, never Parameters: every parameter is shown.
  const shown = parameters;
  // Why a parameter is not set here: the engine's reason; a document that is no model's (a file,
  // whatever it says); or this view's own (a host that cannot save).
  const reasonOf = parameter => (!parameter.writable ? parameter.reason || "unknown" : !model.ofModel ? "file" : savable ? "" : "unavailable");
  const reasons = parameters.map(reasonOf);
  // A reason that is the document's own (a file, a model whose script no worker holds, a view that cannot
  // save), or a refusal that says the same (the script changed or ran out since it ran): every control is
  // off, and Save says why. A parameter's own (declared elsewhere, computed) is said on its control.
  const documentReason = DOCUMENT_REASONS.find(reason => reasons.includes(reason)) || "";
  const locked = model.locked;
  const why = (parameter, reason) => (reason === "shared" ? (parameter.source ? t("parameters.reason.sharedIn", { source: parameter.source }) : t("parameters.reason.shared"))
    : t(`parameters.reason.${[...PARAMETER_REASONS, "unavailable"].includes(reason) ? reason : "unknown"}`));
  const editable = reasons.some(reason => !reason);
  const error = model.error;
  // Why nothing in the tab can work, where that is so: a file's document, a script no worker holds (its reason,
  // or a refusal that found it), a script changed since it ran. Said once, as the foot's status, in place of
  // "Saved"; Save is simply off then, with no hint of its own.
  const blockedBy = saving ? ""
    : documentReason === "file" || documentReason === "no_worker" ? documentReason
    : locked?.code === "no_worker" || error?.code === "script_changed" ? (locked || error).code
    : "";
  const blocked = blockedBy ? t(blockedBy === "script_changed" ? "parameters.error.script_changed" : `parameters.reason.${blockedBy}`) : "";
  // No count of what is unsaved: Save on is the sign. "Saved" once a save is answered and nothing differs.
  const status = blocked || (!saving && !model.dirty && model.saved ? t("parameters.saved") : "");
  // Why Save is off, where it is for another reason: a view that cannot save, then the last refusal (until an
  // edit). One short line, the tab's own: the engine's message is never in it (a build's can run to many lines).
  // Nothing to save is no reason: Save is simply off.
  const failure = locked || error;
  const saveReason = saving || blocked ? ""
    : documentReason ? t(`parameters.reason.${documentReason}`)
    : failure ? t(failure.code
      ? (failure.during === "preview" && failure.code === "build_failed" ? "parameters.error.preview_build_failed" : `parameters.error.${failure.code}`)
      : failure.during === "preview" ? "parameters.error.preview_failed" : "parameters.error.failed")
    : "";
  const frozen = saving || Boolean(documentReason) || Boolean(locked);

  const row = (parameter) => {
    const reason = reasons[parameters.indexOf(parameter)];
    const name = parameter.name;
    // A parameter of its own reason (declared elsewhere, computed) is off, its hint saying why; one the
    // document's reason or a lock holds is off, Save saying why.
    const own = reason && !DOCUMENT_REASONS.includes(reason) ? why(parameter, reason) : "";
    const off = Boolean(reason) || frozen;
    const value = !reason && Object.hasOwn(drafts, name) ? drafts[name] : parameter.value;
    const text = formatParameterValue(parameter, value);
    const typed = draft => {
      // A value left as it shows writes nothing: its text may round the value it shows.
      if (String(draft ?? "").trim() === text.trim()) return;
      model.commit(name, parseFileSheetNumberInput(draft, { fallback: value, min: parameter.min ?? -Infinity, max: parameter.max ?? Infinity, integer: parameter.kind === "int" }));
    };
    const ranged = parameterIsRanged(parameter);
    const marks = { "data-parameter": name, "data-parameter-control": ranged ? "slider" : "number", "data-parameter-reason": reason || undefined };
    if (ranged) {
      const control = <SliderField key={name} label={name} labelTitle={name} name={name} disabled={off} text={text} onTextCommit={typed}
        textLabel={t("field.value", { name })} value={value} min={parameter.min} max={parameter.max} step={parameterStep(parameter) ?? 1}
        onValueChange={next => model.setDraft(name, next ?? value)} onValueCommit={next => model.commit(name, next ?? value)}
        {...(own ? {} : marks)} />;
      return own ? <Explained key={name} reason={own} {...marks}>{control}</Explained> : control;
    }
    const control = <FileSheetSettingRow label={name} disabled={off} className={`h-control ${ROW_COLUMNS}`}>
      <FileSheetNumberProperty label={name} value={text} disabled={off} onValueCommit={typed} className="w-full" />
    </FileSheetSettingRow>;
    // 8px under it, as under a slider, before the next control or the foot.
    return own ? <Explained key={name} reason={own} className="pb-2" {...marks}>{control}</Explained> : <div key={name} className="pb-2" {...marks}>{control}</div>;
  };

  // Save and Reset, the section's foot, under the list; what they say (the status: why they are off, or "Saved")
  // directly over them, right-aligned on their right edge, one line or two (a narrow panel), read whole, never cut
  // off — and the hint of a button it holds off. Save off for another reason says why in its own hint, on the wrapper
  // that takes the pointer for it.
  const actions = (editable || documentReason) && shown.length ? <PanelActions footProps={FOOT_MARKS} className="flex-col items-end gap-1" data-parameters-actions="">
    <span role="status" className={cn("max-w-full text-right leading-(--cad-leading-xs) text-muted-foreground empty:hidden", blocked ? "line-clamp-2" : "truncate")} data-parameters-status=""
      data-parameters-status-reason={blockedBy || undefined}>{status}</span>
    <div className="flex items-center justify-end gap-2" data-parameters-buttons="">
    <Explained reason={blocked && !(saving || !model.dirty) ? "" : blocked} className="shrink-0">
      <Button type="button" variant="ghost" size="xs" className={PANEL_ACTION_CLASS} disabled={saving || !model.dirty} onClick={model.reset}
        data-parameters-reset="">{t("parameters.reset")}</Button>
      {/* The tab's dot: on exactly while Reset is. */}
      <FlatPanelChanged on={!(saving || !model.dirty)} />
    </Explained>
    <Explained reason={saveReason || blocked} className="shrink-0" data-parameters-save-reason={saveReason ? (documentReason || failure?.code || "unknown") : undefined}>
      {/* Save is the one filled button while it can save; off, it is drawn as Reset is off (the neutral button's
          disabled look), so it never reads as a button to press. */}
      <Button type="button" variant={saving || (model.dirty && !(saveReason || blocked)) ? "default" : "ghost"} size="xs" className={PANEL_ACTION_CLASS} disabled={saving || !model.dirty || Boolean(saveReason || blocked)}
        aria-busy={saving || undefined} onClick={model.save} data-parameters-save="">
        {saving ? <Spinner className="size-3" role="presentation" aria-hidden="true" aria-label={undefined} /> : null}
        {t(saving ? "parameters.saving" : "parameters.save")}
      </Button>
    </Explained>
    </div>
  </PanelActions> : null;

  return <ToolPanel id="parameters" title={t("parameters.title")} label={t("parameters.controls")} fit="details">
    <div>
      {parameterGroups(shown).map(group => <div key={group.file ?? ""} className="contents" data-parameters-group={group.file ?? undefined}>
        {group.file ? <TreeRowHeading as="h4" data-parameters-file={group.file}>{group.file}</TreeRowHeading> : null}
        {group.parameters.map(row)}
      </div>)}
      {/* The tab's foot (`PanelActions`): kept in sight at the panel's bottom edge while a long list scrolls
          under it, so Save is never scrolled away from the values it saves; where the list is short it stands
          under the last row. */}
      {actions}
    </div>
  </ToolPanel>;
}
