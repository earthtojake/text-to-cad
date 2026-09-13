import { defineVersionedSchema } from '@emdash/core/primitives/versioned-schema/api';
import z from 'zod';

// ---------------------------------------------------------------------------
// v0 schema — unversioned legacy format stored in tasks.linked_issue
// ---------------------------------------------------------------------------

const v0Schema = z.object({
  provider: z.enum([
    'github',
    'linear',
    'jira',
    'gitlab',
    'plane',
    'plain',
    'forgejo',
    'featurebase',
    'asana',
    'monday',
    'notion',
    'trello',
  ]),
  url: z.string(),
  title: z.string(),
  identifier: z.string(),
  displayIdentifier: z.string().nullable().optional(),
  description: z.string().optional(),
  context: z.string().optional(),
  branchName: z.string().optional(),
  status: z.string().optional(),
  assignees: z.array(z.string()).optional(),
  project: z.string().optional(),
  updatedAt: z.string().optional(),
  fetchedAt: z.string().optional(),
});

// ---------------------------------------------------------------------------
// Versioned schema
// ---------------------------------------------------------------------------

/**
 * Versioned schema for a linked issue stored in `tasks.linked_issue`.
 *
 * A task's linked issue captures the issue metadata at the time of linking.
 * The stored shape is a flat object with no version field (unversioned legacy).
 */
export const linkedIssue = defineVersionedSchema().unversioned(v0Schema).build();

// ---------------------------------------------------------------------------
// Exports
// ---------------------------------------------------------------------------

/** The Zod schema for the latest linked issue shape. */
export const linkedIssueSchema = linkedIssue.schema;

/** The TypeScript type for a linked issue. */
export type LinkedIssue = typeof linkedIssue.Type;

export function linkedIssueDisplayIdentifier(
  issue: Pick<LinkedIssue, 'identifier' | 'displayIdentifier'>
): string | null {
  return issue.displayIdentifier === null ? null : (issue.displayIdentifier ?? issue.identifier);
}

export function linkedIssueMentionName(
  issue: Pick<LinkedIssue, 'identifier' | 'displayIdentifier' | 'title'>
): string {
  return linkedIssueDisplayIdentifier(issue) ?? (issue.title || 'Linked issue');
}
