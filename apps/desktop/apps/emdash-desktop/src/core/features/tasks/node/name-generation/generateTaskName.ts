import { humanId } from 'human-id';
import { generateBranchName } from 'nbranch';

const MAX_TASK_NAME_LENGTH = 64;

function sanitize(raw: string): string {
  return raw
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, MAX_TASK_NAME_LENGTH);
}

export function generateRandom(): string {
  return sanitize(humanId({ separator: '-', capitalize: false }));
}

function generateFromInput(title: string, description?: string): string {
  const input = description ? `${title}\n\n${description}` : title;
  const raw = generateBranchName(input, {
    addRandomSuffix: false,
    separator: '-',
    maxLength: MAX_TASK_NAME_LENGTH,
  });
  return sanitize(raw);
}

export function generateTaskName(params: { title?: string; description?: string }): string {
  const { title, description } = params;
  if (title && title.trim().length > 0) {
    return generateFromInput(title.trim(), description?.trim());
  }
  return generateRandom();
}
