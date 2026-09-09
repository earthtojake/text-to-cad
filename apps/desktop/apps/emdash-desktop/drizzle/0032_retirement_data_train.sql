-- Retirement migration train, step 1 of 2: value rewrites + backfills.
-- Step 2 (0033) drops the legacy indexes/columns and renames deleted_at.
-- Ordering per the contract-phase sequencing ticket: value rewrites first,
-- then backfills, so the column drops in 0033 cannot lose information.

-- 1. Kind vocabulary rewrites: project-root → repository, path → directory.
UPDATE `workspaces`
SET `kind` = 'repository', `updated_at` = CURRENT_TIMESTAMP
WHERE `kind` = 'project-root';--> statement-breakpoint

UPDATE `workspaces`
SET `kind` = 'directory', `updated_at` = CURRENT_TIMESTAMP
WHERE `kind` = 'path';--> statement-breakpoint

-- 2. BYOI untrack sweep: the feature is removed; its rows leave the live set.
--    Bound tasks keep their workspace_id and surface missing-workspace with
--    delete as the out.
UPDATE `workspaces`
SET
  `deleted_at` = COALESCE(`deleted_at`, CURRENT_TIMESTAMP),
  `updated_at` = CURRENT_TIMESTAMP
WHERE `type` = 'byoi' OR `kind` = 'byoi';--> statement-breakpoint

UPDATE `workspaces`
SET `kind` = 'directory'
WHERE `kind` = 'byoi';--> statement-breakpoint

UPDATE `workspaces`
SET `type` = 'project-ssh'
WHERE `type` = 'byoi';--> statement-breakpoint

-- 3. Residual kind normalization: anything left outside the final vocabulary
--    collapses to worktree (matches the deleted normalizeWorkspaceKind()).
UPDATE `workspaces`
SET `kind` = 'worktree', `updated_at` = CURRENT_TIMESTAMP
WHERE `kind` IS NULL OR `kind` NOT IN ('repository', 'worktree', 'directory');--> statement-breakpoint

-- 4. Unlink live projects whose repository row is missing or untracked, so the
--    backfill below can re-link or recreate it.
UPDATE `projects`
SET `repository_workspace_id` = NULL
WHERE `deleted_at` IS NULL
  AND `repository_workspace_id` IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM `workspaces`
    WHERE `workspaces`.`id` = `projects`.`repository_workspace_id`
      AND `workspaces`.`deleted_at` IS NULL
  );--> statement-breakpoint

-- 5. Repository-row backfill (a): point every live project at the live
--    workspace row matching its host identity + path, when one exists.
UPDATE `projects`
SET `repository_workspace_id` = (
  SELECT `workspaces`.`id`
  FROM `workspaces`
  WHERE `workspaces`.`deleted_at` IS NULL
    AND `workspaces`.`path` = `projects`.`path`
    AND CASE
      WHEN `projects`.`workspace_provider` = 'ssh' THEN
        `workspaces`.`location` = 'remote'
        AND `workspaces`.`ssh_connection_id` IS `projects`.`ssh_connection_id`
      ELSE `workspaces`.`location` = 'local'
    END
  LIMIT 1
)
WHERE `deleted_at` IS NULL
  AND EXISTS (
    SELECT 1
    FROM `workspaces`
    WHERE `workspaces`.`deleted_at` IS NULL
      AND `workspaces`.`path` = `projects`.`path`
      AND CASE
        WHEN `projects`.`workspace_provider` = 'ssh' THEN
          `workspaces`.`location` = 'remote'
          AND `workspaces`.`ssh_connection_id` IS `projects`.`ssh_connection_id`
        ELSE `workspaces`.`location` = 'local'
      END
  );--> statement-breakpoint

-- 6. Repository-row backfill (b): create rows for live projects that still
--    have none. Deterministic ids keep the insert and the link in step 7
--    trivially consistent.
INSERT INTO `workspaces` (
  `id`, `type`, `kind`, `location`, `ssh_connection_id`, `path`, `created_at`, `updated_at`
)
SELECT
  'repo-' || `projects`.`id`,
  CASE WHEN `projects`.`workspace_provider` = 'ssh' THEN 'project-ssh' ELSE 'local' END,
  'repository',
  CASE WHEN `projects`.`workspace_provider` = 'ssh' THEN 'remote' ELSE 'local' END,
  CASE WHEN `projects`.`workspace_provider` = 'ssh' THEN `projects`.`ssh_connection_id` END,
  `projects`.`path`,
  CURRENT_TIMESTAMP,
  CURRENT_TIMESTAMP
FROM `projects`
WHERE `projects`.`deleted_at` IS NULL
  AND `projects`.`repository_workspace_id` IS NULL;--> statement-breakpoint

UPDATE `projects`
SET `repository_workspace_id` = 'repo-' || `id`
WHERE `deleted_at` IS NULL
  AND `repository_workspace_id` IS NULL;--> statement-breakpoint

-- 7. Host-identity backfill onto repository rows: every row referenced by a
--    live project carries kind/location/ssh/path before the project columns
--    drop in 0033.
UPDATE `workspaces`
SET
  `kind` = 'repository',
  `location` = COALESCE(
    `location`,
    CASE
      WHEN (
        SELECT `projects`.`workspace_provider`
        FROM `projects`
        WHERE `projects`.`repository_workspace_id` = `workspaces`.`id`
          AND `projects`.`deleted_at` IS NULL
        LIMIT 1
      ) = 'ssh' THEN 'remote'
      ELSE 'local'
    END
  ),
  `ssh_connection_id` = COALESCE(
    `ssh_connection_id`,
    (
      SELECT `projects`.`ssh_connection_id`
      FROM `projects`
      WHERE `projects`.`repository_workspace_id` = `workspaces`.`id`
        AND `projects`.`deleted_at` IS NULL
      LIMIT 1
    )
  ),
  `path` = COALESCE(
    `path`,
    (
      SELECT `projects`.`path`
      FROM `projects`
      WHERE `projects`.`repository_workspace_id` = `workspaces`.`id`
        AND `projects`.`deleted_at` IS NULL
      LIMIT 1
    )
  ),
  `updated_at` = CURRENT_TIMESTAMP
WHERE `deleted_at` IS NULL
  AND EXISTS (
    SELECT 1
    FROM `projects`
    WHERE `projects`.`repository_workspace_id` = `workspaces`.`id`
      AND `projects`.`deleted_at` IS NULL
  );--> statement-breakpoint

-- 8. Re-parent live worktrees under their project's repository row (covers
--    repository rows created in step 6; mirrors the 0030 backfill).
UPDATE `workspaces`
SET `parent_id` = (
  SELECT `projects`.`repository_workspace_id`
  FROM `tasks`
  INNER JOIN `projects` ON `projects`.`id` = `tasks`.`project_id`
  WHERE `tasks`.`workspace_id` = `workspaces`.`id`
    AND `tasks`.`deleted_at` IS NULL
    AND `projects`.`deleted_at` IS NULL
    AND `projects`.`repository_workspace_id` IS NOT NULL
  LIMIT 1
)
WHERE `parent_id` IS NULL
  AND `kind` = 'worktree'
  AND `deleted_at` IS NULL
  AND EXISTS (
    SELECT 1
    FROM `tasks`
    INNER JOIN `projects` ON `projects`.`id` = `tasks`.`project_id`
    WHERE `tasks`.`workspace_id` = `workspaces`.`id`
      AND `tasks`.`deleted_at` IS NULL
      AND `projects`.`deleted_at` IS NULL
      AND `projects`.`repository_workspace_id` IS NOT NULL
  );