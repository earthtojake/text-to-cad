/**
 * Identity payload for a provider account as delivered by auth flows (OAuth
 * exchange, provider-token dispatch, device flow) before persistence.
 *
 * This is the one shared provider-account identity shape; Wire contracts and
 * services must import or derive from it instead of redeclaring it.
 */
export type ProviderAccountIdentity = {
  providerId: string;
  /** The provider's own id for the account, e.g. a numeric GitHub user id. */
  providerAccountId: string;
  /** Provider host the account belongs to, e.g. "github.com". */
  host: string;
  login: string;
  avatarUrl: string;
};
