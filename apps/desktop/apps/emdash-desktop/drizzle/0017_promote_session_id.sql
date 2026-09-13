-- Custom SQL migration file, put you code below! --

UPDATE `conversations`
SET `session_id` = json_extract(`config`, '$.providerSessionId')
WHERE json_extract(`config`, '$.providerSessionId') IS NOT NULL;

UPDATE `conversations`
SET `config` = json_remove(`config`, '$.providerSessionId')
WHERE json_extract(`config`, '$.providerSessionId') IS NOT NULL;
