import { useSyncExternalStore } from "react";

const EMPTY_PARAMETER_VALUES = Object.freeze({});
const listeners = new Set();

let snapshot = {
  elapsedSec: 0,
  parameterValues: EMPTY_PARAMETER_VALUES
};

function notify() {
  for (const listener of listeners) {
    listener();
  }
}

function subscribe(listener) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function normalizedElapsedSec(value) {
  const numericValue = Number(value);
  return Number.isFinite(numericValue) && numericValue > 0 ? numericValue : 0;
}

function normalizedParameterValues(values) {
  return values && typeof values === "object" ? values : EMPTY_PARAMETER_VALUES;
}

function publishSnapshot(nextSnapshot) {
  const next = {
    elapsedSec: normalizedElapsedSec(nextSnapshot.elapsedSec),
    parameterValues: normalizedParameterValues(nextSnapshot.parameterValues)
  };
  if (
    next.elapsedSec === snapshot.elapsedSec &&
    next.parameterValues === snapshot.parameterValues
  ) {
    return;
  }
  snapshot = next;
  notify();
}

function getSnapshot() {
  return snapshot;
}

function getElapsedSnapshot() {
  return snapshot.elapsedSec;
}

export function setStepAnimationFrame({ elapsedSec, parameterValues }) {
  publishSnapshot({
    elapsedSec,
    parameterValues: parameterValues === undefined ? snapshot.parameterValues : parameterValues
  });
}

export function setStepAnimationElapsed(elapsedSec) {
  publishSnapshot({
    elapsedSec,
    parameterValues: snapshot.parameterValues
  });
}

export function resetStepAnimationStore({ elapsedSec = 0, parameterValues = EMPTY_PARAMETER_VALUES } = {}) {
  publishSnapshot({
    elapsedSec,
    parameterValues
  });
}

export function getStepAnimationElapsed() {
  return snapshot.elapsedSec;
}

export function getStepAnimationParameterValues() {
  return snapshot.parameterValues;
}

export function useStepAnimationSnapshot() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}

export function useStepAnimationElapsed() {
  return useSyncExternalStore(subscribe, getElapsedSnapshot, getElapsedSnapshot);
}
