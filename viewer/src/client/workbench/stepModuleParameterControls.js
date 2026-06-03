import {
  buildParameterValuesCopyText,
  parseParameterValuesPasteText,
  resolveParameterNumberControlStep
} from "./parameterControls.js";

export function resolveStepModuleNumberControlStep(parameter) {
  return resolveParameterNumberControlStep(parameter);
}

export function buildStepModuleParamsCopyText(definition, values = {}) {
  return buildParameterValuesCopyText(definition, values);
}

export function parseStepModuleParamsPasteText(definition, text) {
  return parseParameterValuesPasteText(definition, text, {
    label: "STEP parameter",
    unknownLabel: "STEP parameter"
  });
}
