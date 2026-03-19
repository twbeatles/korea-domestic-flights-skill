param(
  [string]$TaskName = "OpenClaw-KoreaDomesticFlights-PriceAlerts",
  [string]$PythonExe = "python",
  [string]$Workspace = (Resolve-Path (Join-Path $PSScriptRoot "../../..")).Path,
  [string]$StorePath = "",
  [int]$IntervalMinutes = 30
)

$scriptPath = Join-Path $Workspace "skills/korea-domestic-flights/scripts/price_alerts.py"
if (-not (Test-Path $scriptPath)) {
  throw "price_alerts.py 를 찾지 못했습니다: $scriptPath"
}

$storeArg = ""
if ($StorePath -and $StorePath.Trim().Length -gt 0) {
  $storeArg = " --store `"$StorePath`""
}

$psCommand = "Set-Location -LiteralPath `"$Workspace`"; & `"$PythonExe`" `"$scriptPath`" check$storeArg"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command $psCommand"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)).Repetition
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "등록 완료: $TaskName"
Write-Host "실행 명령: $PythonExe $scriptPath check$storeArg"
