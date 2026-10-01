import { app, BrowserWindow } from "electron";
import { BrowserService } from "../../../src/main/browser/service";
import { armQuitDeadline } from "../../../src/main/quit-deadline";
app.setName("TextToCadBrowserTest");
// The app's own quit deadline (src/main/quit-deadline.ts): once a window has held native pages,
// Chromium's shutdown on macOS can take tens of seconds that no test is waiting on.
app.on("will-quit", () => armQuitDeadline());
void app.whenReady().then(async () => {
const window = new BrowserWindow({ show: false, width: 1200, height: 800, webPreferences: { backgroundThrottling: false } });
await window.loadURL("about:blank");
const service = new BrowserService();
Object.assign(globalThis, { browserFixture: { service, window } });
app.on("before-quit", () => service.dispose());

});
