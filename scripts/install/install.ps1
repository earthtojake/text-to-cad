# text-to-cad's installer for Windows:
#
#   irm https://www.texttocad.dev/install.ps1 | iex
#
# It finds uv, or installs it with uv's own installer, then runs `cadgen setup` from the newest
# cadgen release through uvx: text-to-cad set up or updated in every agent app on this machine,
# with nothing asked. Run it again to update; with --uninstall it runs `cadgen uninstall` instead.
# For its options, run it as a script block:
#
#   & ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --help
#
# Everything happens inside Install-TextToCad, called on the last line: a download cut short runs
# nothing, and a failure returns instead of closing the window.

function Install-TextToCad {
    $ErrorActionPreference = 'Stop'
    # The release this script was published with, installed when the version feed cannot be read.
    $CadgenVersion = "0.8.4"
    $VersionFeed = 'https://api.texttocad.dev/v1/versions'
    $Releases = 'https://github.com/earthtojake/text-to-cad/releases/download'

    function Show-Usage {
        Write-Host "text-to-cad's installer: installs or updates text-to-cad in every agent app on this machine. It"
        Write-Host 'prints its plan and carries it out, asking nothing; --dry-run prints the plan alone.'
        Write-Host ''
        Write-Host '  irm https://www.texttocad.dev/install.ps1 | iex'
        Write-Host '  & ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --dry-run'
        Write-Host ''
        Write-Host 'Options (all but --version, --from and --uninstall go to `cadgen setup`, or to `cadgen uninstall`):'
        Write-Host '  --dry-run          print the plan and stop: nothing is changed'
        Write-Host '  --only APP[,APP]   only these apps: claude, claude-desktop, codex, cursor, grok, gemini, or'
        Write-Host '                     the agents the skills go to through the Skills CLI (cadgen setup --help)'
        Write-Host '  --uninstall        take text-to-cad out again: runs cadgen uninstall (with --purge, cadgen''s state and caches too)'
        Write-Host '  --no-telemetry     turn telemetry off'
        Write-Host "  --version X.Y.Z    install that cadgen release (default: the newest, from $VersionFeed,"
        Write-Host "                     never older than this script's own, $CadgenVersion)"
        Write-Host '  --from SPEC        run cadgen from SPEC instead: a wheel, a folder or a requirement'
        Write-Host '                     (also the CADGEN_INSTALL_FROM variable); for testing a build before its release'
        Write-Host ''
        Write-Host "uv comes from its own installer when it is missing; UV_NO_MODIFY_PATH=1 keeps it from editing"
        Write-Host 'your PATH. To read this script before running it, or to keep to one release, take the copy'
        Write-Host "attached to that release and check it against the release's SHA256SUMS:"
        Write-Host ''
        Write-Host "  irm $Releases/v$CadgenVersion/install.ps1 -OutFile install.ps1"
        Write-Host "  irm $Releases/v$CadgenVersion/SHA256SUMS"
        Write-Host '  (Get-FileHash install.ps1 -Algorithm SHA256).Hash'
        Write-Host '  powershell -ExecutionPolicy ByPass -File install.ps1'
        Write-Host ''
        Write-Host 'On macOS and Linux: curl -fsSL https://texttocad.dev/install.sh | sh'
    }

    # uvx: on PATH, else where uv's installer puts it before a new shell has it on PATH.
    function Find-Uvx {
        $command = Get-Command uvx -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
        $folders = @($env:UV_INSTALL_DIR)
        if ($env:UV_INSTALL_DIR) { $folders += (Join-Path $env:UV_INSTALL_DIR 'bin') }
        $folders += @($env:XDG_BIN_HOME, (Join-Path $HOME '.local\bin'), (Join-Path $HOME '.cargo\bin'))
        foreach ($folder in $folders) {
            if ($folder -and (Test-Path (Join-Path $folder 'uvx.exe'))) { return (Join-Path $folder 'uvx.exe') }
        }
        return $null
    }

    # Whether release $a is older than $b: the dotted numbers compared, a suffix ignored; never when
    # either is no version. The feed lags a release by up to an hour, and this script never installs
    # a release older than the one it was published with: that one has no `cadgen setup`.
    function Test-Older($a, $b) {
        try {
            return ([version]($a -replace '[^0-9.].*$', '')) -lt ([version]($b -replace '[^0-9.].*$', ''))
        } catch {
            return $false
        }
    }

    # --version picks the release, --from a build outright and --uninstall the verb; every other
    # argument goes to it, in order.
    $version = $null
    $from = $null
    $verb = 'setup'
    $rest = @()
    for ($index = 0; $index -lt $args.Count; $index++) {
        $argument = [string]$args[$index]
        if ($argument -eq '-h' -or $argument -eq '--help') { Show-Usage; return }
        if ($argument -eq '--version') {
            if ($index + 1 -ge $args.Count) {
                Write-Host "error: --version needs a release, as in --version $CadgenVersion" -ForegroundColor Red
                return
            }
            $index++
            $version = [string]$args[$index]
            continue
        }
        if ($argument.StartsWith('--version=')) { $version = $argument.Substring(10); continue }
        if ($argument -eq '--from') {
            if ($index + 1 -ge $args.Count) {
                Write-Host "error: --from needs a wheel, a folder or a requirement" -ForegroundColor Red
                return
            }
            $index++
            $from = [string]$args[$index]
            continue
        }
        if ($argument.StartsWith('--from=')) { $from = $argument.Substring(7); continue }
        if ($argument -eq '--uninstall') { $verb = 'uninstall'; continue }
        $rest += $argument
    }

    if (-not $from -and $env:CADGEN_INSTALL_FROM) { $from = $env:CADGEN_INSTALL_FROM }
    if ($from) {
        # A build named outright (a wheel, a folder, a requirement): uvx takes it as it is, nothing refreshed.
        $requirement = $from
        $refresh = @()
        $version = $from
        $origin = 'as --from asked'
    } else {
        if ($version) {
            $origin = 'as --version asked'
        } else {
            # An older Windows PowerShell may not offer TLS 1.2 on its own.
            [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
            try {
                $version = [string](Invoke-RestMethod -Uri $VersionFeed -TimeoutSec 3).latest
            } catch {
                $version = $null
            }
            if (-not $version) {
                $version = $CadgenVersion
                $origin = "this script's own: the version feed could not be read"
            } elseif (Test-Older $version $CadgenVersion) {
                $origin = "this script's own: the version feed still names $version"
                $version = $CadgenVersion
            } else {
                $origin = 'the newest release'
            }
        }
        if ($version -notmatch '^[0-9][0-9A-Za-z.+-]*$') {
            Write-Host "error: not a cadgen release: $version" -ForegroundColor Red
            return
        }
        $requirement = "cadgen==$version"
        $refresh = @('--refresh-package', 'cadgen')
    }

    $uvx = Find-Uvx
    if (-not $uvx) {
        Write-Host "uv is not installed: installing it with uv's own installer (https://docs.astral.sh/uv/):"
        Write-Host '  irm https://astral.sh/uv/install.ps1 | iex'
        $shell = (Get-Process -Id $PID).Path
        & $shell -NoProfile -ExecutionPolicy ByPass -Command 'irm https://astral.sh/uv/install.ps1 | iex'
        $uvx = Find-Uvx
        if (-not $uvx) {
            Write-Host 'error: uv was installed, but uvx was not found: open a new terminal and run this again' -ForegroundColor Red
            return
        }
    }
    # uvx's folder on PATH: `cadgen setup` writes uvx's absolute path into the apps' configs.
    $env:Path = "$(Split-Path $uvx);$env:Path"

    # cadgen asks nothing: every other argument goes to it as given.
    $arguments = @('--no-config', '--managed-python', '--python', '3.14') + $refresh + @('--from', $requirement, 'cadgen', $verb) + $rest
    Write-Host "text-to-cad: cadgen $version ($origin). The first run downloads it, which takes a minute."
    Write-Host "Running: $uvx $($arguments -join ' ')"
    & $uvx @arguments
    if ($LASTEXITCODE) {
        Write-Host "cadgen $verb exited $LASTEXITCODE; what it said is above." -ForegroundColor Red
    }
}

Install-TextToCad @args
