"""The home's Import: the operating system's own chooser of a file or a folder, run as a child process.

A page cannot ask for a path -- a browser hands over a file's bytes, never where it
is, and an app's form draws only inside a chat turn -- so the server that runs the
page, the CAD app's or the viewer's, asks the desktop directly. It never draws
anything itself, and never runs a shell. Every file can be chosen -- none is greyed
out -- and the server says which kinds CAD opens when one it cannot is picked. A
folder is chosen the same way (``folder``), the chooser opening where it is asked
to (``start``): a standalone document's folder, so the person picks the level.
A Mac's open panel also takes either in one (``either``), as VS Code's "Open…" does
there; Windows' and Linux's choosers take a file or a folder, never both, so they
have no such chooser (``takes_either``).
A path given to a chooser goes as an argument or as base64, never as code.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
import threading

from cad.engine import executables

TIMEOUT_SECONDS = 600

# Its arguments: ``file``, ``folder`` or ``either`` (one panel taking a file or a folder), then the folder it
# starts in (or nothing).
_MAC_SCRIPT = r"""
ObjC.import('AppKit');
function run(argv) {
  const mode = argv[0];
  const app = $.NSApplication.sharedApplication;
  app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
  app.activateIgnoringOtherApps(true);
  const panel = $.NSOpenPanel.openPanel;
  panel.title = mode === 'either' ? 'Import' : mode === 'folder' ? 'Import folder' : 'Import file';
  panel.prompt = 'Import';
  panel.canChooseDirectories = mode !== 'file';
  panel.canChooseFiles = mode !== 'folder';
  panel.canCreateDirectories = false;
  panel.allowsMultipleSelection = false;
  if (argv[1]) panel.directoryURL = $.NSURL.fileURLWithPathIsDirectory(argv[1], true);
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
    $dialog.Title = 'Import file'
    $dialog.Multiselect = $false
    $dialog.CheckFileExists = $true
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        @{path=$dialog.FileName} | ConvertTo-Json -Compress
    } else { @{cancelled=$true} | ConvertTo-Json -Compress }
} finally { $dialog.Dispose(); $owner.Close(); $owner.Dispose() }
"""

# The folder it starts in comes as base64 of its UTF-8 (``__START__``): no character of a path is code here.
_WINDOWS_FOLDER_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$owner = New-Object System.Windows.Forms.Form
try {
    $owner.TopMost = $true; $owner.ShowInTaskbar = $false; $owner.Opacity = 0
    $owner.Show(); $owner.Activate()
    $dialog.Description = 'Import folder'
    $dialog.ShowNewFolderButton = $false
    $start = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('__START__'))
    if ($start) { $dialog.SelectedPath = $start }
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        @{path=$dialog.SelectedPath} | ConvertTo-Json -Compress
    } else { @{cancelled=$true} | ConvertTo-Json -Compress }
} finally { $dialog.Dispose(); $owner.Close(); $owner.Dispose() }
"""


class PickerFailed(Exception):
    """The chooser could not run, or answered with nothing usable."""


def takes_either() -> bool:
    """Whether this computer has one chooser that takes a file or a folder (a Mac's open panel): the home's Import
    is then one button. Windows' ``OpenFileDialog`` and ``FolderBrowserDialog``, and zenity's and kdialog's file
    and folder choosers, each take one or the other."""
    return sys.platform == "darwin"


def _command(folder: bool = False, start: str | None = None, either: bool = False) -> tuple[list[str], dict[str, str], bool]:
    """The chooser's argv, extra environment, and whether it answers in JSON: of a file, of a folder (``folder``),
    or of either in one (``either``, a Mac's alone: ``takes_either``), opening in the folder ``start`` where one is
    named. Every chooser by its absolute path (``executables.find``), never one a PATH entry relative to the
    working folder names."""
    title = "Import folder" if folder else "Import file"
    if sys.platform == "darwin":
        mode = "either" if either else "folder" if folder else "file"
        return ["/usr/bin/osascript", "-l", "JavaScript", "-e", _MAC_SCRIPT, mode, start or ""], {}, True
    if either:
        raise PickerFailed("This computer's chooser takes a file or a folder, not either in one.")
    if sys.platform == "win32":
        shell = executables.find("powershell.exe") or executables.find("pwsh.exe")
        if shell:
            script = _WINDOWS_FOLDER_SCRIPT.replace("__START__", base64.b64encode((start or "").encode("utf-8")).decode("ascii")) \
                if folder else _WINDOWS_SCRIPT
            return [shell, "-NoProfile", "-STA", "-NonInteractive", "-Command", script], {}, True
    elif os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        if zenity := executables.find("zenity"):
            # zenity opens in the folder a name ending in a separator names.
            return [zenity, "--file-selection", f"--title={title}", *(["--directory"] if folder else []),
                    *([f"--filename={os.path.join(start, '')}"] if start else [])], {}, False
        if kdialog := executables.find("kdialog"):
            return [kdialog, "--title", title, "--getexistingdirectory" if folder else "--getopenfilename",
                    start or os.path.expanduser("~")], {}, False
    raise PickerFailed("This computer has no file chooser CAD can open (macOS needs osascript, Windows PowerShell, Linux zenity or kdialog on a desktop).")


def available() -> bool:
    """Whether this computer has a chooser to open: the home shows Import only where it does."""
    try:
        _command()
    except PickerFailed:
        return False
    return True


class FilePicker:
    """One chooser at a time; a second Import while one is up says so."""

    def __init__(self) -> None:
        self._busy = threading.Lock()

    def choose(self, *, folder: bool = False, start: str | None = None, either: bool = False) -> str | None:
        """The chosen file's (or ``folder``'s, or with ``either`` whichever the person chose) absolute path, or
        ``None`` when the person cancels; the chooser opens in the folder ``start`` where one is named."""
        if not self._busy.acquire(blocking=False):
            raise PickerFailed("A file chooser is already open.")
        try:
            argv, extra, structured = _command(folder, start, either)
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
                raise PickerFailed("The file chooser returned no folder." if folder else "The file chooser returned no file.")
            return path
        finally:
            self._busy.release()
