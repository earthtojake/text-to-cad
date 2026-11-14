# text-to-cad's installer for Windows (Windows PowerShell 5.1 and PowerShell 7):
#
#   irm https://www.texttocad.dev/install.ps1 | iex
#
# It makes sure uv is here (installing it with uv's own installer when it is not), downloads install.py
# from beside this script and runs it with uv's Python: that installs the newest release of text-to-cad
# and puts the plugin into every agent app on this computer (install.py says how). Run it again to update.
# It takes no options. Everything happens inside Install-TextToCad, called on the last line: a download cut
# short runs nothing, and a failure returns instead of closing the window.

function Install-TextToCad {
    $ErrorActionPreference = 'Stop'
    $InstallPy = 'https://www.texttocad.dev/install.py'

    if ($args.Count) {
        Write-Host 'This installer takes no options: run it as it is to install or update text-to-cad in every agent app'
        Write-Host 'on this computer:  irm https://www.texttocad.dev/install.ps1 | iex'
        Write-Host "To remove text-to-cad, run ``cad uninstall``, and each app's own remove command."
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

    # An older Windows PowerShell may not offer TLS 1.2 on its own.
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12

    $uv = Find-Uv
    if (-not $uv) {
        Write-Host "uv is not installed: installing it with uv's own installer (https://docs.astral.sh/uv/)."
        $shell = (Get-Process -Id $PID).Path
        & $shell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
        $uv = Find-Uv
        if (-not $uv) {
            Write-Host 'error: uv was installed, but not found: open a new terminal and run this again' -ForegroundColor Red
            return
        }
    }
    # uv's folder on PATH, so install.py finds uvx beside it.
    $env:Path = "$(Split-Path $uv);$env:Path"

    $scratch = Join-Path ([IO.Path]::GetTempPath()) ("text-to-cad-" + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $scratch | Out-Null
    $script = Join-Path $scratch 'install.py'
    try {
        # CAD_INSTALL_PY: a local install.py instead (the installer rehearsals run this checkout's).
        if ($env:CAD_INSTALL_PY) {
            Copy-Item -LiteralPath $env:CAD_INSTALL_PY -Destination $script
        } else {
            try {
                Invoke-WebRequest -Uri $InstallPy -OutFile $script -UseBasicParsing
            } catch {
                Write-Host "error: could not download $InstallPy ($($_.Exception.Message))" -ForegroundColor Red
                return
            }
        }
        & $uv run --no-config --managed-python --python 3.14 --no-project $script
        if ($LASTEXITCODE) {
            Write-Host "The installer exited $LASTEXITCODE; what it said is above." -ForegroundColor Red
        }
    } finally {
        Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Install-TextToCad @args
