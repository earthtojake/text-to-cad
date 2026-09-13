PRAGMA foreign_keys=OFF;

CREATE TABLE `__new_tasks` (
  `id` text PRIMARY KEY NOT NULL,
  `project_id` text NOT NULL,
  `name` text NOT NULL,
  `status` text NOT NULL,
  `source_branch` text,
  `task_branch` text,
  `linked_issue` text,
  `archived_at` text,
  `created_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
  `updated_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
  `last_interacted_at` text,
  `status_changed_at` text DEFAULT CURRENT_TIMESTAMP NOT NULL,
  `is_pinned` integer DEFAULT 0 NOT NULL,
  FOREIGN KEY (`project_id`) REFERENCES `projects`(`id`) ON UPDATE no action ON DELETE cascade
);

INSERT INTO `__new_tasks` (
  `id`,
  `project_id`,
  `name`,
  `status`,
  `source_branch`,
  `task_branch`,
  `linked_issue`,
  `archived_at`,
  `created_at`,
  `updated_at`,
  `last_interacted_at`,
  `status_changed_at`,
  `is_pinned`
)
SELECT
  `id`,
  `project_id`,
  `name`,
  `status`,
  `source_branch`,
  `task_branch`,
  `linked_issue`,
  `archived_at`,
  `created_at`,
  `updated_at`,
  `last_interacted_at`,
  `status_changed_at`,
  `is_pinned`
FROM `tasks`;

DROP TABLE `tasks`;
ALTER TABLE `__new_tasks` RENAME TO `tasks`;
CREATE INDEX `idx_tasks_project_id` ON `tasks` (`project_id`);

PRAGMA foreign_keys=ON;
