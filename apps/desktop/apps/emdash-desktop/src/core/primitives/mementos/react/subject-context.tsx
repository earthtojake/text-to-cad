import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import type { z } from 'zod';
import type { Subject, SubjectDef } from '@core/primitives/subjects/api';
import type { MementoClient, SubjectSpace } from '../browser';

const MementoClientContext = createContext<MementoClient | undefined>(undefined);

interface SubjectContextNode {
  readonly space: SubjectSpace<string>;
  readonly parent: SubjectContextNode | undefined;
}

interface ReadySubjectSpace<TKind extends string> {
  readonly kind: TKind;
  readonly key: string;
  readonly space: SubjectSpace<TKind>;
}

const SubjectContext = createContext<SubjectContextNode | undefined>(undefined);

export interface MementoClientProviderProps {
  readonly client: MementoClient;
  readonly children: ReactNode;
}

export function MementoClientProvider({ client, children }: MementoClientProviderProps): ReactNode {
  return <MementoClientContext.Provider value={client}>{children}</MementoClientContext.Provider>;
}

export interface SubjectProviderProps<TKind extends string> {
  readonly subject: Subject<TKind>;
  readonly children: ReactNode;
  readonly fallback?: ReactNode;
}

export function SubjectProvider<TKind extends string>({
  subject,
  children,
  fallback = null,
}: SubjectProviderProps<TKind>): ReactNode {
  const client = useMementoClient();
  const parent = useContext(SubjectContext);
  const { kind, key } = subject;
  const [ready, setReady] = useState<ReadySubjectSpace<TKind>>();

  useEffect(() => {
    const space = client.subject({ kind, key } as Subject<TKind>);
    let active = true;
    void space.ready
      .catch((error: unknown) => client.reportError(error))
      .then(() => {
        if (active) setReady({ kind, key, space });
      });
    return () => {
      active = false;
      void space.release().catch((error: unknown) => client.reportError(error));
    };
  }, [client, kind, key]);

  const space = ready?.kind === kind && ready.key === key ? ready.space : undefined;

  const node = useMemo<SubjectContextNode | undefined>(
    () => (space ? { space: space as SubjectSpace<string>, parent } : undefined),
    [parent, space]
  );

  if (!node) return fallback;
  return <SubjectContext.Provider value={node}>{children}</SubjectContext.Provider>;
}

export function useMementoClient(): MementoClient {
  const client = useContext(MementoClientContext);
  if (!client) throw new Error('useMementoClient must be used inside MementoClientProvider');
  return client;
}

export function useSubject<TKind extends string>(
  definition: SubjectDef<TKind, z.ZodType>
): Subject<TKind> {
  return useSubjectSpace(definition).subject;
}

export function useSubjectSpace<TKind extends string>(
  definition?: SubjectDef<TKind, z.ZodType>
): SubjectSpace<TKind> {
  let node = useContext(SubjectContext);
  if (!node) throw new Error('A memento subject hook must be used inside SubjectProvider');

  if (!definition) return node.space as SubjectSpace<TKind>;
  while (node) {
    if (node.space.subject.kind === definition.kind) {
      return node.space as SubjectSpace<TKind>;
    }
    node = node.parent;
  }
  throw new Error(`No SubjectProvider for subject kind '${definition.kind}'`);
}
