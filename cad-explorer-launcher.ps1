#requires -Version 5.1
$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

# Win32 hook for the immersive (dark) title bar on Windows 10 1903+ / 11.
if (-not ([System.Management.Automation.PSTypeName]'CadExplorer.Dwm').Type) {
    Add-Type -Namespace CadExplorer -Name Dwm -MemberDefinition @'
[System.Runtime.InteropServices.DllImport("dwmapi.dll")]
public static extern int DwmSetWindowAttribute(System.IntPtr hwnd, int attr, ref int attrValue, int attrSize);
'@
}

function Enable-DarkTitleBar {
    param([System.Windows.Forms.Form] $TargetForm)
    if (-not $TargetForm) { return }
    $useDark = 1
    # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Win10 2004+ / Win11). 19 = same on Win10 1903.
    $rc = [CadExplorer.Dwm]::DwmSetWindowAttribute($TargetForm.Handle, 20, [ref]$useDark, 4)
    if ($rc -ne 0) {
        [void][CadExplorer.Dwm]::DwmSetWindowAttribute($TargetForm.Handle, 19, [ref]$useDark, 4)
    }
}

# Theme palette (mirrors the CAD Explorer web app's dark mode).
$darkBg     = [System.Drawing.Color]::FromArgb(30, 30, 35)
$darkPanel  = [System.Drawing.Color]::FromArgb(45, 45, 52)
$darkText   = [System.Drawing.Color]::FromArgb(238, 238, 240)
$darkBorder = [System.Drawing.Color]::FromArgb(72, 72, 80)

if ($PSScriptRoot) {
    $projectRoot = $PSScriptRoot
} else {
    $projectRoot = Split-Path -Parent ([System.Diagnostics.Process]::GetCurrentProcess().MainModule.FileName)
}

$explorerDir = Join-Path $projectRoot "skills\render\scripts\viewer"
$port        = 4178
$url         = "http://127.0.0.1:$port"

$env:EXPLORER_WORKSPACE_ROOT = $projectRoot

$alreadyRunning = [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)

$viteProcess = $null
if (-not $alreadyRunning) {
    $logFile = Join-Path $projectRoot ".explorer.log"
    $errLog  = Join-Path $projectRoot ".explorer.err.log"

    $viteProcess = Start-Process -FilePath "npm.cmd" `
        -ArgumentList "--prefix", "`"$explorerDir`"", "run", "dev" `
        -WorkingDirectory $projectRoot `
        -RedirectStandardOutput $logFile `
        -RedirectStandardError  $errLog `
        -WindowStyle Hidden `
        -PassThru
}

$browserOpened = $false
$browserTimer  = New-Object System.Windows.Forms.Timer
$browserTimer.Interval = 500
$browserDeadline = (Get-Date).AddSeconds(30)

$form = New-Object System.Windows.Forms.Form
$form.Text = "CAD Explorer"
$form.Size = New-Object System.Drawing.Size(360, 180)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $true
$form.BackColor = $darkBg
$form.ForeColor = $darkText
$form.Add_HandleCreated({ Enable-DarkTitleBar -TargetForm $form })
$form.Add_Shown({ Enable-DarkTitleBar -TargetForm $form })

$status = New-Object System.Windows.Forms.Label
$status.Location = New-Object System.Drawing.Point(20, 20)
$status.Size = New-Object System.Drawing.Size(320, 60)
$status.Text = if ($alreadyRunning) { "Already running at $url" } else { "Starting CAD Explorer at $url ..." }
$status.BackColor = [System.Drawing.Color]::Transparent
$status.ForeColor = $darkText
$form.Controls.Add($status)

$hint = New-Object System.Windows.Forms.Label
$hint.Location = New-Object System.Drawing.Point(20, 90)
$hint.Size = New-Object System.Drawing.Size(320, 40)
$hint.Text = "Close this window to stop the server."
$hint.BackColor = [System.Drawing.Color]::Transparent
$hint.ForeColor = $darkText
$form.Controls.Add($hint)

$copyBtn = New-Object System.Windows.Forms.Button
$copyBtn.Location = New-Object System.Drawing.Point(240, 130)
$copyBtn.Size = New-Object System.Drawing.Size(100, 30)
$copyBtn.Text = "Copy URL"
$copyBtn.BackColor = $darkPanel
$copyBtn.ForeColor = $darkText
$copyBtn.FlatStyle = [System.Windows.Forms.FlatStyle]::Flat
$copyBtn.FlatAppearance.BorderColor = $darkBorder
$copyBtn.Add_Click({ [System.Windows.Forms.Clipboard]::SetText($script:url) })
$form.Controls.Add($copyBtn)

$form.Size = New-Object System.Drawing.Size(360, 210)

if ($alreadyRunning) {
    [System.Windows.Forms.Clipboard]::SetText($url)
    $hint.Text = "URL copied. In Cursor: Ctrl+Shift+B opens the browser - paste the URL."
}

$browserTimer.Add_Tick({
    if ($script:browserOpened) { $browserTimer.Stop(); return }
    if ((Get-Date) -gt $script:browserDeadline) {
        $script:status.Text = "Server did not start within 30s. See .explorer.err.log"
        $browserTimer.Stop()
        return
    }
    if (Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue) {
        [System.Windows.Forms.Clipboard]::SetText($script:url)
        $script:browserOpened = $true
        $script:status.Text = "CAD Explorer running at $($script:url)"
        $script:hint.Text = "URL copied. In Cursor: Ctrl+Shift+B opens the browser - paste the URL."
        $browserTimer.Stop()
    }
})
$browserTimer.Start()

$form.Add_FormClosing({
    $ErrorActionPreference = "SilentlyContinue"
    try {
        $toKill = New-Object System.Collections.Generic.HashSet[int]
        $listeners = Get-NetTCPConnection -LocalPort $script:port -State Listen -ErrorAction SilentlyContinue
        foreach ($conn in $listeners) { [void]$toKill.Add([int]$conn.OwningProcess) }
        if ($script:viteProcess -and -not $script:viteProcess.HasExited) {
            [void]$toKill.Add([int]$script:viteProcess.Id)
        }
        foreach ($pidToKill in $toKill) {
            try {
                Get-CimInstance Win32_Process -Filter "ParentProcessId=$pidToKill" -ErrorAction SilentlyContinue |
                    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
                Stop-Process -Id $pidToKill -Force -ErrorAction SilentlyContinue
            } catch { }
        }
    } catch { }
})

[System.Windows.Forms.Application]::Run($form)
