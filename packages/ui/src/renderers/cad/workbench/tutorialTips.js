import { createContext } from "react";
export const TUTORIAL_TIP_IDS = Object.freeze({ COPY_REFERENCE: "copyReference" });
export const TutorialTipsContext = createContext({ seen: [], dismiss: () => {} });
