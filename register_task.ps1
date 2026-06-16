# Registers the Supreme Court Briefer schedule in Windows Task Scheduler.
#
# Three tasks implement the desired behaviour:
#   1) Prepare-2PM   @ 2:00 PM  - gather + build brief IF the PC is on (does NOT wake the PC).
#                                 If the PC was off at 2 PM, it runs when the PC is next on.
#   2) Prepare-Late  @ 10:30 PM - WAKES the PC and prepares the brief (skips if 2 PM already did).
#   3) Send          @ 10:35 PM - WAKES the PC and emails the brief (the only send).
#
# If the PC is fully shut down, Windows runs the missed tasks the moment you turn it on,
# and Send self-heals (prepares first if needed). Net: the brief reaches your phone at
# 10:35 PM, or as soon as the PC is on after that.
#
# Run this in a normal (non-admin) PowerShell window. Re-run any time to update.

$ErrorActionPreference = "Stop"
$ProjectDir = $PSScriptRoot
$Script     = Join-Path $ProjectDir "main.py"

# Prefer pythonw.exe (no console window); fall back to python.exe.
$pyw = Join-Path $env:LOCALAPPDATA "Programs\Python\Python313\pythonw.exe"
if (-not (Test-Path $pyw)) {
    $cmd = Get-Command pythonw.exe -ErrorAction SilentlyContinue
    if ($cmd) { $pyw = $cmd.Source } else { $pyw = (Get-Command python.exe).Source }
}
Write-Host "Interpreter: $pyw"
Write-Host "Script:      $Script"
Write-Host ""

# Remove the old single task and any previous versions of these tasks.
foreach ($old in @("SupremeCourtDailyBrief","SupremeCourtBrief-Prepare-2PM",
                   "SupremeCourtBrief-Prepare-Late","SupremeCourtBrief-Send")) {
    Unregister-ScheduledTask -TaskName $old -Confirm:$false -ErrorAction SilentlyContinue
}

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

function Register-Job([string]$Name, [string]$Arg, $Time, [bool]$Wake, [string]$Desc) {
    $action = New-ScheduledTaskAction -Execute $pyw -Argument "`"$Script`" $Arg" -WorkingDirectory $ProjectDir
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 5)
    $settings.WakeToRun = $Wake
    Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger `
        -Settings $settings -Principal $principal -Force -Description $Desc | Out-Null
    $w = if ($Wake) { "wakes PC" } else { "no wake" }
    Write-Host ("  {0,-32} @ {1}  ({2})" -f $Name, $Time, $w) -ForegroundColor Green
}

Write-Host "Registering tasks:"
Register-Job "SupremeCourtBrief-Prepare-2PM"  "--prepare" "2:00PM"  $false `
    "Gather + build the Supreme Court brief at 2 PM if the PC is on (no send)."
Register-Job "SupremeCourtBrief-Prepare-Late" "--prepare" "10:30PM" $true `
    "Fallback: wake the PC at 10:30 PM and build the brief if 2 PM was missed (no send)."
Register-Job "SupremeCourtBrief-Send"         "--send"    "10:35PM" $true `
    "Wake the PC at 10:35 PM and email the day's brief."

Write-Host ""
Write-Host "Done. The brief is delivered to your phone at 10:35 PM each day." -ForegroundColor Cyan
Write-Host "Test now:  Start-ScheduledTask -TaskName SupremeCourtBrief-Send"
Write-Host "Remove:    'SupremeCourtBrief-Prepare-2PM','SupremeCourtBrief-Prepare-Late','SupremeCourtBrief-Send' | % { Unregister-ScheduledTask -TaskName `$_ -Confirm:`$false }"
