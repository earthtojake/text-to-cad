export {
  applyGitCredentialsToEnv,
  GIT_CREDENTIAL_HELPER_COMMAND,
  GIT_CREDENTIAL_HELPER_URL_PATH,
  GIT_CREDENTIAL_NONCE_ENV_VAR,
  GIT_CREDENTIAL_PORT_ENV_VAR,
  gitCredentialChannelSchema,
  gitCredentialOperationEnv,
  gitCredentialsSessionSpecSchema,
  type GitCredentialChannel,
  type GitCredentialsSessionSpec,
} from './env';
export {
  parseGitCredentialRequest,
  serializeGitCredentialResponse,
  type GitCredentialRequest,
} from './protocol';
