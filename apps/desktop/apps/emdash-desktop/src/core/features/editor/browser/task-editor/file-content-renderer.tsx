import { observer } from 'mobx-react-lite';
import { useEditorContext } from './editor-provider';

/**
 * Renders the sticky Monaco editor host for text and source-mode files. Owns the host div
 * wiring (setEditorHost). Loading/error/orphaned placeholders come from the tab's
 * OpenFileStore entry and are rendered by FileContent above this component, so it is
 * never blocked by overlay divs.
 *
 * EditorProvider (which creates the Monaco editor instance) lives higher in the tree inside
 * FileTabContent — this component only manages the host attachment point.
 */
export const FileContentRenderer = observer(function FileContentRenderer() {
  const { setEditorHost } = useEditorContext();

  return (
    <div className="relative h-full w-full">
      <div ref={setEditorHost} className="absolute inset-0 flex" />
    </div>
  );
});
