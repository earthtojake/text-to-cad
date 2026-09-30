"""Open Model's file chooser: the operating system's own, run as a child process.

A host's form for choosing a file draws only inside a chat turn, and the page
that has Open Model sits beside a chat with none, so the server asks the
desktop directly. It never draws anything itself, and never runs a shell.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
from collections.abc import Sequence

TIMEOUT_SECONDS = 600

_MAC_SCRIPT = r"""
ObjC.import('AppKit');
function run(argv) {
  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  app.activateIgnoringOtherApps(true);
  const panel = $.NSOpenPanel.openPanel;
  panel.title = 'Open Model';
  panel.prompt = 'Open';
  panel.canChooseDirectories = false;
  panel.canChooseFiles = true;
  panel.allowsMultipleSelection = false;
  panel.allowedFileTypes = $(JSON.parse(argv[0]));
  return panel.runModal == $.NSModalResponseOK
    ? JSON.stringify({path: ObjC.unwrap(panel.URL.path)})
    : JSON.stringify({cancelled: true});
}
"""

_WINDOWS_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$owner = New-Object System.Windows.Forms.Form
try {
    $owner.TopMost = $true; $owner.ShowInTaskbar = $false; $owner.Opacity = 0
    $owner.Show(); $owner.Activate()
    $dialog.Title = 'Open Model'
    $dialog.Filter = $env:CADGEN_PICKER_FILTER
    $dialog.Multiselect = $false
    $dialog.CheckFileExists = $true
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        @{path=$dialog.FileName} | ConvertTo-Json -Compress
    } else { @{cancelled=$true} | ConvertTo-Json -Compress }
} finally { $dialog.Dispose(); $owner.Close(); $owner.Dispose() }
"""


class PickerFailed(Exception):
    """The chooser could not run, or answered with nothing usable."""


def _command(extensions: Sequence[str]) -> tuple[list[str], dict[str, str], bool]:
    """The chooser's argv, extra environment, and whether it answers in JSON."""
    bare = [extension.lstrip(".") for extension in extensions]
    if sys.platform == "darwin":
        osascript = shutil.which("osascript") or "/usr/bin/osascript"
        return [osascript, "-l", "JavaScript", "-e", _MAC_SCRIPT, json.dumps(bare)], {}, True
    if sys.platform == "win32":
        shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
        if shell:
            patterns = ";".join(f"*.{extension}" for extension in bare)
            return [shell, "-NoProfile", "-STA", "-NonInteractive", "-Command", _WINDOWS_SCRIPT], {"CADGEN_PICKER_FILTER": f"CAD models ({patterns})|{patterns}"}, True
    elif os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        patterns = " ".join(f"*.{variant}" for extension in bare for variant in (extension, extension.upper()))
        if shutil.which("zenity"):
            return ["zenity", "--file-selection", "--title=Open Model", f"--file-filter=CAD models | {patterns}"], {}, False
        if shutil.which("kdialog"):
            return ["kdialog", "--title", "Open Model", "--getopenfilename", os.path.expanduser("~"), f"CAD models ({patterns})"], {}, False
    raise PickerFailed("This computer has no file chooser CAD can open (macOS needs osascript, Windows PowerShell, Linux zenity or kdialog on a desktop).")


class FilePicker:
    """One chooser at a time; a second Open Model while one is up says so."""

    def __init__(self) -> None:
        self._busy = threading.Lock()

    def choose(self, extensions: Sequence[str]) -> str | None:
        """The chosen file's absolute path, or ``None`` when the person cancels."""
        if not self._busy.acquire(blocking=False):
            raise PickerFailed("A file chooser is already open.")
        try:
            argv, extra, structured = _command(extensions)
            try:
                done = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT_SECONDS, env={**os.environ, **extra})
            except subprocess.TimeoutExpired as error:
                raise PickerFailed("The file chooser was left open too long and was closed.") from error
            except OSError as error:
                raise PickerFailed(f"The file chooser could not start: {error}") from error
            output = done.stdout.decode("utf-8-sig", errors="replace").strip()
            if not structured:
                if done.returncode == 1 and not output:
                    return None  # zenity and kdialog cancel with 1 and no output
                if done.returncode != 0:
                    raise PickerFailed(done.stderr.decode("utf-8", errors="replace").strip()[:500] or "The file chooser failed.")
                return output or None
            if done.returncode != 0:
                raise PickerFailed(done.stderr.decode("utf-8", errors="replace").strip()[:500] or "The file chooser failed.")
            try:
                answer = json.loads(output)
            except ValueError as error:
                raise PickerFailed("The file chooser answered with something unreadable.") from error
            if not isinstance(answer, dict) or answer.get("cancelled") is True:
                return None
            path = answer.get("path")
            if not isinstance(path, str) or not path:
                raise PickerFailed("The file chooser returned no file.")
            return path
        finally:
            self._busy.release()
