import { isLocalHostRef, type HostRef } from '@emdash/core/primitives/host/api';
import { and, eq, isNull, type Column, type SQL } from 'drizzle-orm';

/** The shape every host-scoped mirror table shares: where the record's host lives. */
type HostIdentityColumns = {
  location: Column;
  sshConnectionId: Column;
};

/**
 * Scopes a mirror read to one host's rows — the shared predicate for every reconcile
 * sweep kind (workspaces, conversations, future kinds); only the table differs.
 */
export function hostIdentityFilter(host: HostRef, table: HostIdentityColumns): SQL | undefined {
  return isLocalHostRef(host)
    ? and(eq(table.location, 'local'), isNull(table.sshConnectionId))
    : and(eq(table.location, 'remote'), eq(table.sshConnectionId, host.id));
}
