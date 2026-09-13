-- Custom SQL migration file, put you code below! --
UPDATE tasks
SET source_branch = json_object('type', 'local', 'branch', source_branch)
WHERE json_valid(source_branch) = 0;