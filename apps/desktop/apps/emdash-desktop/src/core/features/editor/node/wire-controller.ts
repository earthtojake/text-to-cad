import { createController, type Controller } from '@emdash/wire/rpc';
import { editorContract } from '../api';
import type { EditorBufferService } from './editor-buffer-service';

export type CreateEditorWireControllerOptions = Readonly<{
  editorBuffer: EditorBufferService;
}>;

export function createEditorWireController(options: CreateEditorWireControllerOptions): Controller {
  return createController(editorContract, {
    saveBuffer: ({ uri, content }) => options.editorBuffer.saveBuffer(uri, content),
    clearBuffer: ({ uri }) => options.editorBuffer.clearBuffer(uri),
    listBuffers: ({ root }) => options.editorBuffer.listBuffers(root),
  });
}
