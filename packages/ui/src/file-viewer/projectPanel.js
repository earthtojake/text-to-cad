import { createContext, useContext } from "react";

/**
 * The project a file's view is shown beside (`FileViewer`'s `project`): the Project tab the view's panel leads with
 * where the document is in a project (`renderers/kit/shell/ViewFrame.jsx`), before the view's own tabs, and the one
 * tab of a view that has none. Its `content` is the project's list (`navigation/ProjectList.jsx`); null where the
 * document is in no project.
 *
 * @type {import("react").Context<{ label: string, content: import("react").ReactNode } | null>}
 */
export const ProjectPanelContext = createContext(null);

/** The project tab the view's panel leads with (`ProjectPanelContext`), or null. */
export const useProjectPanel = () => useContext(ProjectPanelContext);

/** The Project tab's id among a panel's tabs (and its kind, for a panel that is that tab alone). */
export const PROJECT_TAB = "project";
