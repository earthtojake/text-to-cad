import { app, BrowserWindow } from "electron";
import { BrowserService } from "../../../src/main/browser/service";
app.setName("HardcoreBrowserTest");
void app.whenReady().then(async () => {
const window = new BrowserWindow({ show: false, width: 1200, height: 800, webPreferences: { backgroundThrottling: false } });
await window.loadURL("about:blank");
const service = new BrowserService();
Object.assign(globalThis, { browserFixture: { service, window } });
app.on("before-quit", () => service.dispose());

});
