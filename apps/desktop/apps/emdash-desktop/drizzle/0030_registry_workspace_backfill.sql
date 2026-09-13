UPDATE `workspaces`
SET `location` = CASE
  WHEN `type` IN ('project-ssh', 'byoi') THEN 'remote'
  WHEN `type` = 'local' THEN 'local'
  ELSE `location`
END
WHERE `location` IS NULL;--> statement-breakpoint

UPDATE `workspaces`
SET `ssh_connection_id` = COALESCE(
  (
    SELECT `projects`.`ssh_connection_id`
    FROM `projects`
    WHERE `projects`.`repository_workspace_id` = `workspaces`.`id`
      AND `projects`.`deleted_at` IS NULL
      AND `projects`.`ssh_connection_id` IS NOT NULL
    LIMIT 1
  ),
  (
    SELECT `projects`.`ssh_connection_id`
    FROM `tasks`
    INNER JOIN `projects` ON `projects`.`id` = `tasks`.`project_id`
    WHERE `tasks`.`workspace_id` = `workspaces`.`id`
      AND `tasks`.`deleted_at` IS NULL
      AND `projects`.`deleted_at` IS NULL
      AND `projects`.`ssh_connection_id` IS NOT NULL
    LIMIT 1
  ),
  `ssh_connection_id`
)
WHERE `location` = 'remote'
  AND `ssh_connection_id` IS NULL;--> statement-breakpoint

UPDATE `workspaces`
SET `kind` = CASE
  WHEN EXISTS (
    SELECT 1
    FROM `projects`
    WHERE `projects`.`repository_workspace_id` = `workspaces`.`id`
      AND `projects`.`deleted_at` IS NULL
  ) THEN 'project-root'
  WHEN `type` = 'byoi' THEN 'byoi'
  WHEN EXISTS (
    SELECT 1
    FROM `tasks`
    WHERE `tasks`.`workspace_id` = `workspaces`.`id`
      AND `tasks`.`deleted_at` IS NULL
  ) THEN 'worktree'
  ELSE 'worktree'
END
WHERE `kind` IS NULL;--> statement-breakpoint

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
  AND EXISTS (
    SELECT 1
    FROM `tasks`
    INNER JOIN `projects` ON `projects`.`id` = `tasks`.`project_id`
    WHERE `tasks`.`workspace_id` = `workspaces`.`id`
      AND `tasks`.`deleted_at` IS NULL
      AND `projects`.`deleted_at` IS NULL
      AND `projects`.`repository_workspace_id` IS NOT NULL
  );--> statement-breakpoint

CREATE TEMP TABLE `_registry_workspace_dedup` (
  `workspace_id` text PRIMARY KEY,
  `keep_workspace_id` text NOT NULL
);--> statement-breakpoint

WITH `candidates` AS (
  SELECT
    `workspaces`.`id`,
    `workspaces`.`location`,
    `workspaces`.`ssh_connection_id`,
    `workspaces`.`path`,
    `workspaces`.`created_at`,
    `workspaces`.`updated_at`,
    CASE
      WHEN EXISTS (
        SELECT 1
        FROM `projects`
        WHERE `projects`.`repository_workspace_id` = `workspaces`.`id`
          AND `projects`.`deleted_at` IS NULL
      ) THEN 0
      WHEN EXISTS (
        SELECT 1
        FROM `tasks`
        WHERE `tasks`.`workspace_id` = `workspaces`.`id`
          AND `tasks`.`deleted_at` IS NULL
      ) THEN 1
      ELSE 2
    END AS `reference_priority`
  FROM `workspaces`
  WHERE `workspaces`.`deleted_at` IS NULL
    AND `workspaces`.`path` IS NOT NULL
    AND `workspaces`.`location` IS NOT NULL
    AND (`workspaces`.`location` = 'local' OR `workspaces`.`ssh_connection_id` IS NOT NULL)
),
`ranked` AS (
  SELECT
    `candidates`.`id`,
    FIRST_VALUE(`candidates`.`id`) OVER (
      PARTITION BY `candidates`.`location`, `candidates`.`ssh_connection_id`, `candidates`.`path`
      ORDER BY
        `candidates`.`reference_priority`,
        `candidates`.`updated_at` DESC,
        `candidates`.`created_at` DESC,
        `candidates`.`id`
    ) AS `keep_workspace_id`,
    ROW_NUMBER() OVER (
      PARTITION BY `candidates`.`location`, `candidates`.`ssh_connection_id`, `candidates`.`path`
      ORDER BY
        `candidates`.`reference_priority`,
        `candidates`.`updated_at` DESC,
        `candidates`.`created_at` DESC,
        `candidates`.`id`
    ) AS `rank`
  FROM `candidates`
)
INSERT INTO `_registry_workspace_dedup` (`workspace_id`, `keep_workspace_id`)
SELECT `id`, `keep_workspace_id`
FROM `ranked`
WHERE `rank` > 1;--> statement-breakpoint

UPDATE `tasks`
SET `workspace_id` = (
  SELECT `keep_workspace_id`
  FROM `_registry_workspace_dedup`
  WHERE `_registry_workspace_dedup`.`workspace_id` = `tasks`.`workspace_id`
)
WHERE `workspace_id` IN (SELECT `workspace_id` FROM `_registry_workspace_dedup`);--> statement-breakpoint

UPDATE `projects`
SET `repository_workspace_id` = (
  SELECT `keep_workspace_id`
  FROM `_registry_workspace_dedup`
  WHERE `_registry_workspace_dedup`.`workspace_id` = `projects`.`repository_workspace_id`
)
WHERE `repository_workspace_id` IN (
  SELECT `workspace_id` FROM `_registry_workspace_dedup`
);--> statement-breakpoint

UPDATE `workspaces`
SET
  `deleted_at` = COALESCE(`deleted_at`, CURRENT_TIMESTAMP),
  `updated_at` = CURRENT_TIMESTAMP
WHERE `id` IN (SELECT `workspace_id` FROM `_registry_workspace_dedup`);--> statement-breakpoint

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
  AND EXISTS (
    SELECT 1
    FROM `tasks`
    INNER JOIN `projects` ON `projects`.`id` = `tasks`.`project_id`
    WHERE `tasks`.`workspace_id` = `workspaces`.`id`
      AND `tasks`.`deleted_at` IS NULL
      AND `projects`.`deleted_at` IS NULL
      AND `projects`.`repository_workspace_id` IS NOT NULL
  );--> statement-breakpoint

DROP TABLE `_registry_workspace_dedup`;