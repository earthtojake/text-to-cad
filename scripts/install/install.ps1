# text-to-cad's installer for Windows:
#
#   irm https://www.texttocad.dev/install.ps1 | iex
#
# It finds uv, or installs it with uv's own installer, then runs `cad setup` from the newest
# release of text-to-cad's server through uvx: text-to-cad set up or updated in every agent app on this machine,
# with nothing asked. Run it again to update; with --uninstall it runs `cad uninstall` instead; with
# --add X it installs release X alone (`cad setup --add`), which a skill's setup block asks for.
# For its options, run it as a script block:
#
#   & ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --help
#   & ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --add X.Y.Z
#
# Everything happens inside Install-TextToCad, called on the last line: a download cut short runs
# nothing, and a failure returns instead of closing the window.

function Install-TextToCad {
    $ErrorActionPreference = 'Stop'
    # The release this script was published with, installed when the version feed cannot be read.
    $CadVersion = "0.11.11"
    # The first release whose `cad uninstall` asks before it destroys, and takes --yes for an answer.
    $ConsentSince = '0.11.0'
    # The first release that installs itself alone, `cad setup --add`: the first whose skills pin their release.
    $AddSince = '0.11.11'
    $VersionFeed = 'https://api.texttocad.dev/v1/versions'
    $Releases = 'https://github.com/earthtojake/text-to-cad/releases/download'

    function Show-Usage {
        Write-Host "text-to-cad's installer: installs or updates text-to-cad in every agent app on this machine. It"
        Write-Host 'prints its plan and carries it out, asking nothing; --dry-run prints the plan alone.'
        Write-Host ''
        Write-Host '  irm https://www.texttocad.dev/install.ps1 | iex'
        Write-Host '  & ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --dry-run'
        Write-Host '  & ([scriptblock]::Create((irm https://www.texttocad.dev/install.ps1))) --add X.Y.Z'
        Write-Host ''
        Write-Host 'Options (all but --version, --from, --add and --uninstall go to `cad setup`, or to `cad uninstall`):'
        Write-Host '  --dry-run          print the plan and stop: nothing is changed'
        Write-Host '  --only APP[,APP]   only these apps: claude, claude-desktop, codex, cursor, grok, gemini, or'
        Write-Host '                     the agents the skills go to through the Skills CLI (cad setup --help)'
        Write-Host '  --uninstall        take text-to-cad out again: runs cad uninstall (with --purge, everything)'
        Write-Host '  --add X.Y.Z        install release X.Y.Z alone, and the cad command, and change nothing else: no app,'
        Write-Host '                     no other release, no setting (`cad setup --add`, which a skill''s setup block asks'
        Write-Host '                     for). It reads no version feed and installs exactly X.Y.Z; it takes no other option'
        Write-Host '  --no-telemetry     turn telemetry off'
        Write-Host "  --version X.Y.Z    install that release (default: the newest, from $VersionFeed,"
        Write-Host "                     never older than this script's own, $CadVersion)"
        Write-Host '  --from SPEC        run the server from SPEC instead: a wheel, a folder or a requirement'
        Write-Host '                     (also the CAD_INSTALL_FROM variable); for testing a build before its release,'
        Write-Host '                     with UV_FIND_LINKS naming the folder of the library''s wheel beside it'
        Write-Host ''
        Write-Host "uv comes from its own installer when it is missing; UV_NO_MODIFY_PATH=1 keeps it from editing"
        Write-Host 'your PATH. To read this script before running it, or to keep to one release, take the copy'
        Write-Host "attached to that release and check it against the release's SHA256SUMS:"
        Write-Host ''
        Write-Host "  irm $Releases/v$CadVersion/install.ps1 -OutFile install.ps1"
        Write-Host "  irm $Releases/v$CadVersion/SHA256SUMS"
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
    # a release older than the one it was published with: that one has no `cad setup`.
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
    $add = $null
    $verb = 'setup'
    $rest = @()
    for ($index = 0; $index -lt $args.Count; $index++) {
        $argument = [string]$args[$index]
        if ($argument -eq '-h' -or $argument -eq '--help') { Show-Usage; return }
        if ($argument -eq '--version') {
            if ($index + 1 -ge $args.Count) {
                Write-Host "error: --version needs a release, as in --version $CadVersion" -ForegroundColor Red
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
        if ($argument -eq '--add') {
            if ($index + 1 -ge $args.Count -or -not [string]$args[$index + 1]) {
                Write-Host "error: --add needs a release, as in --add $CadVersion" -ForegroundColor Red
                return
            }
            $index++
            $add = [string]$args[$index]
            continue
        }
        if ($argument.StartsWith('--add=')) {
            $add = $argument.Substring(6)
            if (-not $add) {
                Write-Host "error: --add needs a release, as in --add $CadVersion" -ForegroundColor Red
                return
            }
            continue
        }
        $rest += $argument
    }

    if ($add) {
        # Exactly that release, alone: no feed read, no newer one taken, nothing else asked of it.
        $refusal = $null
        if ($verb -ne 'setup') { $refusal = '--add installs a release; it does not go with --uninstall' }
        elseif ($version) { $refusal = '--add names its release; it does not go with --version' }
        elseif ($rest.Count) { $refusal = "--add takes no other option: $($rest -join ' ')" }
        elseif ($add -like '*-dev.*') {
            $refusal = "$add is a development version: it is installed from its own checkout alone (scripts/install/dev_install.py)"
        }
        elseif ($add -notmatch '^[0-9][0-9A-Za-z.+-]*$') { $refusal = "not a release: $add" }
        elseif (-not $from -and -not $env:CAD_INSTALL_FROM -and (Test-Older $add $AddSince)) {
            $refusal = "$add installs no release alone (the first that does is $AddSince): run this without --add"
        }
        if ($refusal) {
            Write-Host "error: $refusal" -ForegroundColor Red
            return
        }
        $version = $add
        $rest = @('--add')
    }

    if (-not $from -and $env:CAD_INSTALL_FROM) { $from = $env:CAD_INSTALL_FROM }
    if ($from) {
        # A build named outright (a wheel, a folder, a requirement): uvx takes it as it is, nothing refreshed. With
        # --add, it must be that release's: a wheel's file name says its version.
        $leaf = Split-Path $from -Leaf
        if ($add -and ($leaf -like 'cad_server-*.whl' -or $leaf -like 'cad-server==*') -and
                -not ($leaf -like "cad_server-$add-*.whl" -or $leaf -eq "cad-server==$add")) {
            Write-Host "error: --from $from is not text-to-cad $add" -ForegroundColor Red
            return
        }
        $requirement = $from
        $refresh = @()
        $version = if ($add) { $add } else { $from }
        $origin = 'as --from asked'
    } else {
        if ($add) {
            $origin = 'as --add asked'
        } elseif ($version) {
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
                $version = $CadVersion
                $origin = "this script's own: the version feed could not be read"
            } elseif (Test-Older $version $CadVersion) {
                $origin = "this script's own: the version feed still names $version"
                $version = $CadVersion
            } else {
                $origin = 'the newest release'
            }
        }
        if ($version -notmatch '^[0-9][0-9A-Za-z.+-]*$') {
            Write-Host "error: not a release: $version" -ForegroundColor Red
            return
        }
        # Going back below the first pinned release on a device that runs one: that release knows no version
        # folders, and would point clients of it at another version than the default channel's. Not supported.
        $state = if ($env:CAD_STATE_DIR) { $env:CAD_STATE_DIR } else {
            Join-Path $(if ($env:XDG_STATE_HOME) { $env:XDG_STATE_HOME } else { Join-Path $HOME '.local\state' }) 'cad'
        }
        if ($origin -eq 'as --version asked' -and (Test-Older $version $AddSince) -and
                (Test-Path -LiteralPath (Join-Path $state 'default') -PathType Leaf)) {
            Write-Host "error: this computer runs text-to-cad $AddSince or newer: going back to $version, a release before $AddSince, is not supported" -ForegroundColor Red
            return
        }
        $requirement = "cad-server==$version"
        # The server, and the library it pins at its own release: uv reads both anew from the index.
        $refresh = @('--refresh-package', 'cad-server', '--refresh-package', 'cad')
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
    # uvx's folder on PATH: `cad setup` writes uvx's absolute path into the apps' configs.
    $env:Path = "$(Split-Path $uvx);$env:Path"

    # --uninstall is the person's own word: `cad uninstall` is told yes for them (it would ask at a terminal),
    # but a release from before it asked, which takes no --yes. A build named outright is taken as this one.
    if ($verb -eq 'uninstall' -and ($from -or -not (Test-Older $version $ConsentSince))) { $rest += '--yes' }
    # cad asks nothing here: every other argument goes to it as given.
    $arguments = @('--no-config', '--managed-python', '--python', '3.14') + $refresh + @('--from', $requirement, 'cad', $verb) + $rest
    Write-Host "text-to-cad: $version ($origin). The first run downloads it, which takes a minute."
    Write-Host "Running: $uvx $($arguments -join ' ')"
    & $uvx @arguments
    if ($LASTEXITCODE) {
        Write-Host "cad $verb exited $LASTEXITCODE; what it said is above." -ForegroundColor Red
    }
}

Install-TextToCad @args
