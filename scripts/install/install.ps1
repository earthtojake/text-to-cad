# text-to-cad's installer for Windows (Windows PowerShell 5.1 and PowerShell 7):
#
#   irm https://www.texttocad.dev/install.ps1 | iex
#
# It makes sure uv is here and new enough (installing it with uv's own installer when it is not), downloads
# install.py from beside this script and runs it with uv's Python: that installs the cad command as a uv tool
# where there is none (a cad that is here updates itself), and puts the plugin into every agent app on this
# computer (install.py says how). Run it again to update the plugin. It takes no options, and names no release. Everything happens inside Install-TextToCad, called on the last
# lines: a download cut short runs nothing, and a failure returns instead of closing the window. Where it fails
# it ends by throwing (see the last lines), so every documented way of running it exits 1: `irm ... | iex` in
# `powershell -Command`, the same through cmd, and `powershell -File install.ps1`.

function Install-TextToCad {
    # 'Continue': a native command's line on stderr is never an error that stops the run (Windows PowerShell 5.1
    # makes each such line an error record where stderr is redirected, as an agent's shell does). Each native
    # command's $LASTEXITCODE is read instead, and each cmdlet that must stop says -ErrorAction Stop.
    $ErrorActionPreference = 'Continue'
    $InstallPy = 'https://www.texttocad.dev/install.py'
    # The oldest uv that runs it: `--managed-python` came in uv 0.6.8, and a stable CPython 3.14 in uv 0.9.0
    # (uv's changelog, changelogs/0.6.x.md and 0.9.x.md).
    $UvMinimum = [Version]'0.9.0'

    if ($args.Count) {
        Write-Host 'This installer takes no options: run it as it is to install or update text-to-cad in every agent app'
        Write-Host 'on this computer:  irm https://www.texttocad.dev/install.ps1 | iex'
        Write-Host "To remove text-to-cad, run ``uv tool uninstall cad``, and each app's own remove command."
        $global:LASTEXITCODE = 2
        return
    }

    # uv: on PATH, else where uv's installer puts it before a new shell has it on PATH.
    function Find-Uv {
        $command = Get-Command uv -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
        $folders = @($env:UV_INSTALL_DIR)
        if ($env:UV_INSTALL_DIR) { $folders += (Join-Path $env:UV_INSTALL_DIR 'bin') }
        $folders += @($env:XDG_BIN_HOME, (Join-Path $HOME '.local\bin'), (Join-Path $HOME '.cargo\bin'))
        foreach ($folder in $folders) {
            if ($folder -and (Test-Path (Join-Path $folder 'uv.exe'))) { return (Join-Path $folder 'uv.exe') }
        }
        return $null
    }

    # The uv uv's own installer put in place, never PATH's: the first in its folders, in the order it picks one
    # (UV_INSTALL_DIR, and its bin for a Cargo-style folder; XDG_BIN_HOME; XDG_DATA_HOME\..\bin; ~\.local\bin).
    function Find-InstalledUv {
        $folders = @($env:UV_INSTALL_DIR)
        if ($env:UV_INSTALL_DIR) { $folders += (Join-Path $env:UV_INSTALL_DIR 'bin') }
        $folders += @($env:XDG_BIN_HOME)
        if ($env:XDG_DATA_HOME) { $folders += (Join-Path $env:XDG_DATA_HOME '..\bin') }
        $folders += @((Join-Path $HOME '.local\bin'))
        foreach ($folder in $folders) {
            if ($folder -and (Test-Path (Join-Path $folder 'uv.exe'))) { return (Join-Path $folder 'uv.exe') }
        }
        return $null
    }

    # uv's own installer, run by a PowerShell of the kind running this one, its output to the window (never the
    # function's own output); its exit status.
    function Install-Uv {
        $shell = (Get-Process -Id $PID).Path
        & $shell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex' | Out-Host
        return $LASTEXITCODE
    }

    # uv's version, from "uv 0.9.5 (...)"; $null where it does not say. All of what uv prints is taken, then its
    # first line read: never `| Select-Object -First 1` on a program whose $LASTEXITCODE is read. Windows PowerShell
    # 5.1 ends the program once Select-Object has its line, and $LASTEXITCODE is then -1, not the program's status
    # (measured with uv: the right line every time, and -1 on 298 of 300 calls; the first call a PowerShell makes
    # usually gets 0). A current uv then read as one "of an unknown version", and the install stopped.
    function Get-UvVersion($uv) {
        $said = @(& $uv --version 2>$null)
        if ($LASTEXITCODE -eq 0 -and $said.Count -gt 0 -and "$($said[0])" -match '^uv (\d+\.\d+(\.\d+)?)') {
            return [Version]$Matches[1]
        }
        return $null
    }

    # An older Windows PowerShell may not offer TLS 1.2 on its own.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $uv = Find-Uv
    if (-not $uv) {
        Write-Host "uv is not installed: installing it with uv's own installer (https://docs.astral.sh/uv/)."
        $installed = Install-Uv
        if ($installed) {
            Write-Host "error: uv's installer could not be downloaded or failed (exit $installed; what it said is above): check the network connection, or install uv (https://docs.astral.sh/uv/), then run this again" -ForegroundColor Red
            $global:LASTEXITCODE = 1
            return
        }
        $uv = Find-Uv
        if (-not $uv) {
            Write-Host 'error: uv was installed, but not found: open a new terminal and run this again' -ForegroundColor Red
            $global:LASTEXITCODE = 1
            return
        }
    }

    $version = Get-UvVersion $uv
    if (-not $version -or $version -lt $UvMinimum) {
        $old = if ($version) { "uv $version" } else { 'uv of an unknown version' }
        # uv's own installer leaves a receipt, which `uv self update` needs.
        $receipt = Join-Path $(if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME 'AppData\Local' }) 'uv\uv-receipt.json'
        if (Test-Path $receipt) {
            Write-Host "$old is older than $UvMinimum, the first that installs Python 3.14: updating it (uv self update)."
            & $uv self update
            $version = Get-UvVersion $uv
        }
        # One that cannot update itself (winget's, pip's), or did not: uv's own installer puts a newer uv in its own
        # folder, as where uv is missing, and this run uses that one, whatever PATH finds first.
        if (-not $version -or $version -lt $UvMinimum) {
            Write-Host "$old is older than $UvMinimum, the first that installs Python 3.14: installing a newer uv with uv's own installer (https://docs.astral.sh/uv/)."
            $null = Install-Uv
            $version = $null
            $uv = Find-InstalledUv
            if ($uv) { $version = Get-UvVersion $uv }
            if (-not $version -or $version -lt $UvMinimum) {
                Write-Host "error: $old is older than $UvMinimum, and uv's installer did not install a newer uv (what it said is above)." -ForegroundColor Red
                $global:LASTEXITCODE = 1
                return
            }
        }
    }
    # uv's folder on this window's PATH: a window open before uv's installer ran does not see it.
    $env:Path = "$(Split-Path $uv);$env:Path"

    $scratch = Join-Path ([IO.Path]::GetTempPath()) ("text-to-cad-" + [Guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType Directory -Path $scratch -ErrorAction Stop | Out-Null
        $script = Join-Path $scratch 'install.py'
        # CAD_INSTALL_PY: a local install.py instead (the installer rehearsals run this checkout's).
        if ($env:CAD_INSTALL_PY) {
            Copy-Item -LiteralPath $env:CAD_INSTALL_PY -Destination $script -ErrorAction Stop
        } else {
            Invoke-WebRequest -Uri $InstallPy -OutFile $script -UseBasicParsing -ErrorAction Stop
        }
    } catch {
        Write-Host "error: could not download $InstallPy ($($_.Exception.Message))" -ForegroundColor Red
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
        $global:LASTEXITCODE = 1
        return
    }
    try {
        & $uv run --no-config --managed-python --python 3.14 --no-project $script
        $code = $LASTEXITCODE
        # uv's Python could not be set up, so install.py never ran. Inside an app's package (the Claude app's) on a
        # computer where uv has never made its Python folder, Windows keeps the new folder to that app and uv fails
        # ("Missing expected target directory for Python minor version link", measured): once uv has run from an
        # ordinary window, it works inside the app too.
        if ($code) {
            & $uv python find --no-config --system --managed-python 3.14 *> $null  # --system: no venv of the folder it ran in
            if ($LASTEXITCODE) {
                Write-Host "uv could not set up Python 3.14 here (what it said is above). If this ran inside an app (the Claude app, say), open PowerShell from the Start menu, run the install command there once, then go back to the app." -ForegroundColor Red
            }
        }
        # The window that ran this finds cad at once: uv's bin folder on its PATH. Windows gives the user's PATH to a
        # window or app as it starts, so one open before cad's folder was put there does not see it (measured).
        $bin = & $uv tool dir --bin 2>$null | Select-Object -Last 1
        if ($LASTEXITCODE -eq 0 -and $bin -and (Test-Path -LiteralPath $bin) -and
                -not (($env:Path -split ';') -contains $bin)) {
            $env:Path = "$bin;$env:Path"
        }
        if ($code) {
            Write-Host "The installer exited $code; what it said is above." -ForegroundColor Red
        }
        $global:LASTEXITCODE = $code
    } finally {
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# Its status is $LASTEXITCODE, which it sets on every path (its output goes to the window as it comes).
$global:LASTEXITCODE = 0
Install-TextToCad @args
# A failure ends in `throw`, a terminating error, the one form that sets the exit status of every way it is run
# without closing a window a person typed it into:
# - `powershell -Command "irm ... | iex"` (and through cmd) exits 1 when its command ends in an unhandled terminating
#   error; Invoke-Expression passes a `throw` in the script on as one. It ignores $LASTEXITCODE, and a Write-Error is
#   non-terminating: the run it ends still counts as a success (measured on Windows 11: exit 0).
# - `powershell -File install.ps1` exits 1 on a script that ends in an unhandled terminating error.
# - Typed in a window (`irm ... | iex`), a throw prints the error and returns to the prompt. `exit` would end that
#   PowerShell, closing the window (iex runs the script in the window's own session).
# The exit status is 1 whatever the installer's own was: the message names that one.
if ($LASTEXITCODE) {
    throw "text-to-cad's installer did not finish (exit $LASTEXITCODE): see what it said above."
}
