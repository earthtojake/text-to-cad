import { describe, expect, it } from "vitest";

import { cadSceneBackgroundFor } from "@renderer/features/explorer/cad-layout";

describe("the CAD scene's backdrop", () => {
  it("is the app's own background, so the model sits on the app's ground", () => {
    // shadcn's neutral pair, which is what `--background` resolves to in
    // this app's token layer. The theme keeps its lights, grid and materials
    // — and, since the theme decides nothing outside the scene, a dark
    // scene under a light chrome is a legal picture.
    expect(cadSceneBackgroundFor("light")).toBe("#ffffff");
    expect(cadSceneBackgroundFor("dark")).toBe("#0a0a0a");
  });
});
