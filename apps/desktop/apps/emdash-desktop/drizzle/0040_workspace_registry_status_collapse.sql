-- Workspace-registry mirror migration, data step (ADR 0005): 0039 added the host
-- registry observation columns; this collapses the legacy 'corrupted' observed status
-- into 'missing' (the record survives, the reason stays in observed_data), and seeds
-- origin for pre-existing rows: every row the desktop registered or annotated entered
-- deliberately; rows the pull-based scan adopted (config IS NULL) stay 'adopted'.
UPDATE `workspaces`
SET `observed_status` = 'missing'
WHERE `observed_status` = 'corrupted';--> statement-breakpoint

UPDATE `workspaces`
SET `origin` = CASE WHEN `config` IS NULL THEN 'adopted' ELSE 'registered' END
WHERE `origin` IS NULL;
