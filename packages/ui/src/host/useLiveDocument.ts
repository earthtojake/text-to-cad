import { useEffect, useRef } from 'react';
import type { DocumentSession } from '../file-viewer/types.js';
import type { ViewerHost } from './types.js';
import type { LiveTextSnapshot } from './documents.js';

type Binding = { document: DocumentSession; content: string; token: string };
/** The revision advances synchronously, including two commands before React renders. */
export function useLiveDocument(host: ViewerHost, path: string | null, document: DocumentSession | null) {
  const current = useRef<Binding | null>(null);
  if (document) {
    if (!current.current || current.current.document.key !== document.key) current.current = { document, content: document.value, token: crypto.randomUUID() };
    else {
      if (current.current.content !== document.value) { current.current.content = document.value; current.current.token = crypto.randomUUID(); }
      current.current.document = document;
    }
  }
  useEffect(() => {
    if (!host.documents || !path || !document || !current.current) return;
    let active = true;
    // Capture this binding, so a new render cannot replace the departing view's snapshot.
    const binding = current.current;
    const live = () => {
      if (!active) throw new Error('Document is no longer mounted; resolve the resource again.');
      return binding.document;
    };
    const read = (): LiveTextSnapshot => {
      const value = live();
      return { content: binding.content, revision: binding.token, diskRevision: value.revision,
        dirty: value.dirty || binding.content !== value.value, readOnly: value.readOnly, stale: value.stale };
    };
    const checked = (expected: string) => {
      const value = live();
      if (expected !== binding.token) throw new Error('Document revision conflict; read the live buffer again before editing or saving.');
      return value;
    };
    const unbind = host.documents.bind({ sourceId: host.files.id, path, read,
      replace(content, expected) {
        const value = checked(expected);
        if (value.readOnly) throw new Error('This document is read-only.');
        value.setValue(content);
        binding.content = content; binding.token = crypto.randomUUID();
        return read();
      },
      save(expected) { return checked(expected).save(); },
    });
    return () => { unbind(); active = false; };
  }, [host.documents, host.files.id, path, document?.key]);
}
