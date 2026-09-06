-- Run-once retirement of the recurring GitHub KV-account startup backfill
-- (spec: github-git-settings §10, invariant 7). Released builds stored GitHub
-- account metadata in the `githubAccounts` KV namespace; this migration moves
-- it into `provider_accounts` rows exactly once and deletes the namespace.
-- Metadata-only: each account's token already lives in the secrets store under
-- `github-account-token:<id>`, which the row's `credential_ref` points at.
--
-- Upsert semantics mirror the retired GitHubKvAccountBackfillService:
-- entries without a non-empty string id are skipped; existing rows keep their
-- id, credential_ref, is_default, and created_at and only replace meta.
-- `json_patch` drops null keys so absent legacy fields stay absent in meta
-- (the versioned meta schema rejects null for optional string fields).
INSERT INTO `provider_accounts` (`id`, `provider_id`, `account_id`, `credential_ref`, `is_default`, `meta`, `created_at`, `updated_at`)
SELECT
  lower(hex(randomblob(16))),
  'github',
  json_extract(`entry`.`value`, '$.id'),
  'github-account-token:' || json_extract(`entry`.`value`, '$.id'),
  0,
  json_patch('{"version":"1"}', json_object(
    'providerAccountId', json_extract(`entry`.`value`, '$.providerAccountId'),
    'host', json_extract(`entry`.`value`, '$.host'),
    'login', json_extract(`entry`.`value`, '$.login'),
    'avatarUrl', json_extract(`entry`.`value`, '$.avatarUrl'),
    'credentialSource', json_extract(`entry`.`value`, '$.credentialSource')
  )),
  CAST(strftime('%s', 'now') AS INTEGER) * 1000,
  CAST(strftime('%s', 'now') AS INTEGER) * 1000
FROM `kv`, json_each(`kv`.`value`) AS `entry`
WHERE `kv`.`key` = 'githubAccounts:accounts'
  AND json_valid(`kv`.`value`)
  AND json_type(`entry`.`value`, '$.id') = 'text'
  AND json_extract(`entry`.`value`, '$.id') <> ''
ON CONFLICT (`provider_id`, `account_id`) DO UPDATE SET
  `meta` = excluded.`meta`,
  `updated_at` = excluded.`updated_at`;--> statement-breakpoint

-- Honor the legacy default pointer only when it names one of the imported
-- accounts (mirrors the retired service). Clear-then-set in two statements:
-- the partial unique index on (provider_id) WHERE is_default = 1 rejects two
-- defaults mid-update. When no default survives (no pointer, no pre-existing
-- default), the provider-account registry self-heals to the oldest account on
-- first read, which reproduces the retired first-imported-wins behavior.
UPDATE `provider_accounts`
SET `is_default` = 0
WHERE `provider_id` = 'github'
  AND `is_default` = 1
  AND EXISTS (
    SELECT 1
    FROM `kv` AS `pointer_kv`
    WHERE `pointer_kv`.`key` = 'githubAccounts:defaultAccountId'
      AND json_valid(`pointer_kv`.`value`)
      AND json_type(`pointer_kv`.`value`, '$') = 'text'
      AND EXISTS (
        SELECT 1
        FROM `kv` AS `accounts_kv`, json_each(`accounts_kv`.`value`) AS `entry`
        WHERE `accounts_kv`.`key` = 'githubAccounts:accounts'
          AND json_valid(`accounts_kv`.`value`)
          AND json_type(`entry`.`value`, '$.id') = 'text'
          AND json_extract(`entry`.`value`, '$.id') = json_extract(`pointer_kv`.`value`, '$')
      )
  );--> statement-breakpoint

UPDATE `provider_accounts`
SET `is_default` = 1
WHERE `provider_id` = 'github'
  AND `account_id` = (
    SELECT json_extract(`pointer_kv`.`value`, '$')
    FROM `kv` AS `pointer_kv`
    WHERE `pointer_kv`.`key` = 'githubAccounts:defaultAccountId'
      AND json_valid(`pointer_kv`.`value`)
      AND json_type(`pointer_kv`.`value`, '$') = 'text'
  )
  AND EXISTS (
    SELECT 1
    FROM `kv` AS `accounts_kv`, json_each(`accounts_kv`.`value`) AS `entry`
    WHERE `accounts_kv`.`key` = 'githubAccounts:accounts'
      AND json_valid(`accounts_kv`.`value`)
      AND json_type(`entry`.`value`, '$.id') = 'text'
      AND json_extract(`entry`.`value`, '$.id') = `provider_accounts`.`account_id`
  );--> statement-breakpoint

-- Delete the whole namespace (accounts, default pointer, CLI tombstones) so
-- nothing legacy-shaped survives for startup code to probe.
DELETE FROM `kv` WHERE `key` LIKE 'githubAccounts:%';
