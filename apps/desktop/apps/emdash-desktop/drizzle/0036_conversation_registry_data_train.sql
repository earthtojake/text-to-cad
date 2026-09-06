-- Conversation-registry migration train, step 2 of 3: observation seeds.
-- Step 1 (0035) added the registry columns; step 3 (0037) drops the legacy
-- columns, relaxes the task/project links to nullable, and drops the vestigial
-- messages table. Ordering per the retirement precedent: value copies first,
-- so the column drops in 0037 cannot lose information. The old authoritative
-- values become the first cached observation (spec §10.2).

-- 1. Rename-by-copy: the provider resume handle and last-activity timestamp
--    move into their observation-cache columns.
UPDATE `conversations`
SET `provider_session_id` = `session_id`
WHERE `session_id` IS NOT NULL;--> statement-breakpoint

UPDATE `conversations`
SET `last_session_activity_at` = `last_interacted_at`
WHERE `last_interacted_at` IS NOT NULL;--> statement-breakpoint

-- 2. Observation seed: every pre-existing row was client-authoritative truth,
--    so it enters the registry as a present, just-observed record.
UPDATE `conversations`
SET
  `observed_status` = 'present',
  `last_observed_at` = `updated_at`,
  `origin` = 'registered';--> statement-breakpoint

-- 3. Source host identity from the owning project's repository workspace row
--    (host identity moved onto workspaces in the 0032 retirement train).
UPDATE `conversations`
SET
  `location` = COALESCE(
    (
      SELECT `workspaces`.`location`
      FROM `projects`
      INNER JOIN `workspaces` ON `workspaces`.`id` = `projects`.`repository_workspace_id`
      WHERE `projects`.`id` = `conversations`.`project_id`
    ),
    'local'
  ),
  `ssh_connection_id` = (
    SELECT `workspaces`.`ssh_connection_id`
    FROM `projects`
    INNER JOIN `workspaces` ON `workspaces`.`id` = `projects`.`repository_workspace_id`
    WHERE `projects`.`id` = `conversations`.`project_id`
  );--> statement-breakpoint

-- 4. Workspace association seed from the task's workspace path (a path value,
--    not a FK; emdash sessions run in the workspace root, so cwd matches).
UPDATE `conversations`
SET
  `workspace_path` = (
    SELECT `workspaces`.`path`
    FROM `tasks`
    INNER JOIN `workspaces` ON `workspaces`.`id` = `tasks`.`workspace_id`
    WHERE `tasks`.`id` = `conversations`.`task_id`
  ),
  `cwd` = (
    SELECT `workspaces`.`path`
    FROM `tasks`
    INNER JOIN `workspaces` ON `workspaces`.`id` = `tasks`.`workspace_id`
    WHERE `tasks`.`id` = `conversations`.`task_id`
  )
WHERE EXISTS (
  SELECT 1
  FROM `tasks`
  INNER JOIN `workspaces` ON `workspaces`.`id` = `tasks`.`workspace_id`
  WHERE `tasks`.`id` = `conversations`.`task_id`
    AND `workspaces`.`path` IS NOT NULL
);
