import type { ShareableProjectSettingsWriteField } from '@core/primitives/project-settings/api';

export type ShareableFieldFormKey =
  | 'preservePatterns'
  | 'scriptPrepare'
  | 'scriptSetup'
  | 'scriptRun'
  | 'scriptTeardown';

export type ShareableFieldDescriptor = {
  id: ShareableProjectSettingsWriteField;
  formKey: ShareableFieldFormKey;
  modalLabel: string;
  leafLabel: string;
  defaultWrite: boolean;
  normalizeText(value: string): string;
  placeholder?: string;
  description?: string;
  multiline: boolean;
  group?: 'lifecycle';
};

function trimText(value: string): string {
  return value.trim();
}

function normalizePatternList(value: string): string {
  return value
    .split('\n')
    .map((pattern) => pattern.trim())
    .filter(Boolean)
    .join('\n');
}

export const SHAREABLE_FIELD_DESCRIPTORS: ShareableFieldDescriptor[] = [
  {
    id: 'preservePatterns',
    formKey: 'preservePatterns',
    modalLabel: 'Preserve patterns',
    leafLabel: 'preserve patterns',
    defaultWrite: true,
    normalizeText: normalizePatternList,
    placeholder: '.env\n.env.local',
    description:
      'Gitignored and untracked files matching these glob patterns are copied from the main repo into each worktree. One pattern per line.',
    multiline: true,
  },
  {
    id: 'scripts.prepare',
    formKey: 'scriptPrepare',
    modalLabel: 'Prepare script',
    leafLabel: 'prepare',
    defaultWrite: true,
    normalizeText: trimText,
    placeholder: 'python -m venv .venv\nmise install',
    description:
      'Blocking commands run after the workspace exists and before task sessions start. Use this for environment setup that agents depend on.',
    multiline: true,
    group: 'lifecycle',
  },
  {
    id: 'scripts.setup',
    formKey: 'scriptSetup',
    modalLabel: 'Setup script',
    leafLabel: 'setup',
    defaultWrite: true,
    normalizeText: trimText,
    placeholder: 'npm install\ncp .env.example .env',
    multiline: true,
    group: 'lifecycle',
  },
  {
    id: 'scripts.run',
    formKey: 'scriptRun',
    modalLabel: 'Run script',
    leafLabel: 'run',
    defaultWrite: true,
    normalizeText: trimText,
    placeholder: 'npm run dev',
    multiline: true,
    group: 'lifecycle',
  },
  {
    id: 'scripts.teardown',
    formKey: 'scriptTeardown',
    modalLabel: 'Teardown script',
    leafLabel: 'teardown',
    defaultWrite: true,
    normalizeText: trimText,
    placeholder: 'docker compose down',
    multiline: true,
    group: 'lifecycle',
  },
];

export const SHAREABLE_FIELD_DESCRIPTOR_BY_ID = Object.fromEntries(
  SHAREABLE_FIELD_DESCRIPTORS.map((descriptor) => [descriptor.id, descriptor])
) as Record<ShareableProjectSettingsWriteField, ShareableFieldDescriptor>;

export const DEFAULT_WRITE_FIELDS = SHAREABLE_FIELD_DESCRIPTORS.filter(
  (descriptor) => descriptor.defaultWrite
).map((descriptor) => descriptor.id);

export const SHAREABLE_FIELD_FORM_KEY = Object.fromEntries(
  SHAREABLE_FIELD_DESCRIPTORS.map((descriptor) => [descriptor.id, descriptor.formKey])
) as Record<ShareableProjectSettingsWriteField, ShareableFieldFormKey>;
