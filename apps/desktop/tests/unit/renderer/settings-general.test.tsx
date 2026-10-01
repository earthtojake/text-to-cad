import { beforeEach, describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { TooltipProvider } from "@text-to-cad/ui/primitives/tooltip";
import { SettingsRoute } from "@renderer/features/settings/SettingsRoute";
import { useSettings } from "@renderer/state/settings";
import { useUi } from "@renderer/state/ui";
import { defaultSettings } from "@shared/types";

/**
 * Settings › General says what telemetry sends, and only that: each event by
 * name, and for a file only its kind — never its name or its path.
 */
beforeEach(() => {
  useUi.setState({ route: "settings", settingsSection: "general", commandPaletteOpen: false });
  useSettings.setState({ settings: defaultSettings(), ready: true });
});

describe("Settings › General", () => {
  it("lists every telemetry event it sends, and says a file is never named", () => {
    render(<TooltipProvider><SettingsRoute /></TooltipProvider>);
    expect(screen.getByText("Share usage data")).toBeInTheDocument();
    for (const event of ["App launched", "Session created", "File opened", "Settings changed"]) {
      expect(screen.getByText(event, { exact: true })).toBeInTheDocument();
    }
    expect(screen.getByText(/never the name or the path/)).toBeInTheDocument();
  });
});
