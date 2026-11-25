# text-to-cad's installer for Windows (Windows PowerShell 5.1 and PowerShell 7):
#
#   irm https://www.texttocad.dev/install.ps1 | iex
#
# It makes sure uv is here and new enough (installing it with uv's own installer when it is not), downloads
# install.py from beside this script and runs it with uv's Python: that installs the cad command as a uv tool
# where there is none, brings a cad that is here up to date, and has cad put the plugin into every agent app on
# this computer (`cad plugin install`; install.py says how). Run it again to update both. It takes no options, and
# names no release. Everything happens inside Install-TextToCad, called on the last
# lines: a download cut short runs nothing, and a failure returns instead of closing the window. Where it fails
# it ends by throwing (see the last lines), so every documented way of running it exits 1: `irm ... | iex` in
# `powershell -Command`, the same through cmd, and `powershell -File install.ps1`.
#
# Where it fails before install.py runs, it sends one anonymous report of where (Send-Report): uv could not be
# installed or is too old (uv), install.py could not be downloaded (fetch), or uv could not run it (python).
# install.py reports what fails after that, and says what a report holds and when none is sent. A run cad started
# says and sends nothing from here (Test-Report).

function Install-TextToCad {
    # 'Continue': a native command's line on stderr is never an error that stops the run (Windows PowerShell 5.1
    # makes each such line an error record where stderr is redirected, as an agent's shell does). Each native
    # command's $LASTEXITCODE is read instead, and each cmdlet that must stop says -ErrorAction Stop.
    $ErrorActionPreference = 'Continue'
    $InstallPy = 'https://www.texttocad.dev/install.py'
    # The oldest uv that runs it: `--managed-python` came in uv 0.6.8, and a stable CPython 3.14 in uv 0.9.0
    # (uv's changelog, changelogs/0.6.x.md and 0.9.x.md).
    $UvMinimum = [Version]'0.9.0'
    # Where a failure's one report goes: cad's own service (CAD_API_URL, cad's own hook, names a stand-in's base).
    $ReportUrl = 'https://api.texttocad.dev/v1/install'
    # Said once, near the start, by a person's run that could send a report: install.py's NOTICE, word for word.
    $Notice = 'If the install fails before cad can run, one anonymous report of where it failed is sent to texttocad.dev (DO_NOT_TRACK=1 turns it off).'

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

    # Whether a failure of this run may be reported: not where the environment says no (DO_NOT_TRACK on,
    # CAD_TELEMETRY off: cad's own spellings), in CI, on a checkout's run (CAD_INSTALL_PY), or where cad's kept
    # settings say no ("choice": "off" in the "telemetry" section of settings.json in its state folder:
    # CAD_STATE_DIR, ~\.local\state\cad, 0.10.0's). A settings file that cannot be read is no yes. And never on a
    # run cad started (CAD_INSTALL_BY_CAD, CAD_INSTALL_ATTEMPT or CAD_INSTALL_REPORT set: its output is a log's, or
    # nobody's): the line said first would be read by no one, and nothing is sent before a person was told. Whether
    # cad told them already is in its settings, which install.py reads: it reports such a run's later failures
    # where they were.
    function Test-Report {
        $word = { param($value) "$value".Trim().ToLowerInvariant() }
        if (@('1', 'on', 'true', 'yes') -contains (& $word $env:DO_NOT_TRACK)) { return $false }
        if (@('0', 'off', 'false', 'no') -contains (& $word $env:CAD_TELEMETRY)) { return $false }
        if (@('', '0', 'off', 'false', 'no') -notcontains (& $word $env:CI)) { return $false }
        if ($env:CAD_INSTALL_PY) { return $false }
        if ($env:CAD_INSTALL_BY_CAD -or $env:CAD_INSTALL_ATTEMPT -or $env:CAD_INSTALL_REPORT) { return $false }
        $state = if ($env:XDG_STATE_HOME) { $env:XDG_STATE_HOME } else { Join-Path $HOME '.local\state' }
        $local = if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME 'AppData\Local' }
        foreach ($folder in @($env:CAD_STATE_DIR, (Join-Path $state 'cad'), (Join-Path $local 'cad-state'))) {
            if (-not $folder) { continue }
            $settings = Join-Path $folder 'settings.json'
            if (-not (Test-Path -LiteralPath $settings)) { continue }
            try {
                $text = Get-Content -LiteralPath $settings -Raw -ErrorAction Stop
            } catch {
                return $false
            }
            try {
                $kept = $text | ConvertFrom-Json -ErrorAction Stop
            } catch {
                continue
            }
            if ($kept -and $kept.telemetry -and $kept.telemetry.choice -ceq 'off') { return $false }
        }
        return $true
    }

    # One anonymous report that this run failed at $stage (uv, fetch, python) with exit status $code, where one may
    # be sent ($reports): the body install.py documents, its run id random and kept nowhere, a person's run always
    # (Test-Report). Two seconds at most. It says nothing, and never changes how the run ends. Each failure returns
    # right after its report: one a run.
    function Send-Report($stage, $code) {
        if (-not $reports) { return }
        try {
            $status = [int64]$code
            if ($status -lt 0 -or $status -gt 255) { $status = 255 }
            $by = 'person'
            $known = if ($version) { "$version" } else { "$had" }
            $with = if ($known -match '^\d+\.\d+\.\d+$') { $known } else { 'none' }
            $platform = if ($PSVersionTable.PSVersion.Major -ge 6 -and -not $IsWindows) { 'other' } else { 'win32' }
            $arch = "$env:PROCESSOR_ARCHITECTURE".ToLowerInvariant() -replace '[^a-z0-9_.+:-]+', '-'
            if ($arch.Length -gt 16) { $arch = $arch.Substring(0, 16) }
            $at = [int64][Math]::Floor(([DateTime]::UtcNow - [DateTime]'1970-01-01').TotalSeconds)
            $body = '{"schema":1,"run":"' + [Guid]::NewGuid().ToString() + '","at":' + $at + ',"stage":"' + $stage +
                '","outcome":"failed","code":' + $status + ',"platform":"' + $platform + '","arch":"' + $arch +
                '","by":"' + $by + '","uv":"' + $with + '"}'
            $url = $ReportUrl
            if ("$env:CAD_API_URL" -match '^https?://') { $url = "$env:CAD_API_URL".TrimEnd('/') + '/install' }
            $null = Invoke-RestMethod -Uri $url -Method Post -ContentType 'application/json' -Body $body -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        } catch {
        }
    }

    # An older Windows PowerShell may not offer TLS 1.2 on its own.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    # What a report of this run would say of uv, once known (the one found too old, where no newer one took its
    # place), and whether one may be sent.
    $version = $null
    $had = $null
    $reports = Test-Report
    if ($reports) { Write-Host $Notice }

    $uv = Find-Uv
    if (-not $uv) {
        Write-Host "uv is not installed: installing it with uv's own installer (https://docs.astral.sh/uv/)."
        $installed = Install-Uv
        if ($installed) {
            Write-Host "error: uv's installer could not be downloaded or failed (exit $installed; what it said is above): check the network connection, or install uv (https://docs.astral.sh/uv/), then run this again" -ForegroundColor Red
            Send-Report 'uv' 1
            $global:LASTEXITCODE = 1
            return
        }
        $uv = Find-Uv
        if (-not $uv) {
            Write-Host 'error: uv was installed, but not found: open a new terminal and run this again' -ForegroundColor Red
            Send-Report 'uv' 1
            $global:LASTEXITCODE = 1
            return
        }
    }

    $version = Get-UvVersion $uv
    if (-not $version -or $version -lt $UvMinimum) {
        $old = if ($version) { "uv $version" } else { 'uv of an unknown version' }
        $had = $version
        # uv's own installer leaves a receipt, which `uv self update` needs.
        $receipt = Join-Path $(if ($env:LOCALAPPDATA) { $env:LOCALAPPDATA } else { Join-Path $HOME 'AppData\Local' }) 'uv\uv-receipt.json'
        if (Test-Path $receipt) {
            Write-Host "$old is older than $UvMinimum, the first that installs Python 3.14: updating it (uv self update)."
            & $uv self update
            $version = Get-UvVersion $uv
            if ($version) { $had = $version }
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
                Send-Report 'uv' 1
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
        Send-Report 'fetch' 1
        $global:LASTEXITCODE = 1
        return
    }
    try {
        # install.py leaves the file CAD_INSTALL_MARK names as it starts, and reports what fails from then on
        # itself: without the file, uv could not run it, which is this script's to report.
        $mark = Join-Path $scratch 'started'
        $env:CAD_INSTALL_MARK = $mark
        & $uv run --no-config --managed-python --python 3.14 --no-project $script
        $code = $LASTEXITCODE
        if ($code -and -not (Test-Path -LiteralPath $mark)) { Send-Report 'python' $code }
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
        Remove-Item Env:CAD_INSTALL_MARK -ErrorAction SilentlyContinue
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
