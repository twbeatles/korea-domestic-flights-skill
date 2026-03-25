param(
  [string]$TaskName = "OpenClaw-KoreaDomesticFlights-PriceAlerts",
  [string]$PythonExe = "python",
  [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$StorePath = "",
  [string]$SourceRepoPath = "",
  [int]$IntervalMinutes = 30
)

$scriptCandidates = @(
  (Join-Path $RepoRoot "scripts/price_alerts.py"),
  (Join-Path $RepoRoot "skills/korea-domestic-flights/scripts/price_alerts.py")
)
$scriptPath = $scriptCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $scriptPath) {
  throw "price_alerts.py 를 찾지 못했습니다. 확인한 경로: $($scriptCandidates -join ', ')"
}
$workingDir = Split-Path -Parent (Split-Path -Parent $scriptPath)

$storeArg = ""
if ($StorePath -and $StorePath.Trim().Length -gt 0) {
  $storeArg = " --store `"$StorePath`""
}

$repoArg = ""
if ($SourceRepoPath -and $SourceRepoPath.Trim().Length -gt 0) {
  $repoArg = " --repo-path `"$SourceRepoPath`""
}

$psCommand = "Set-Location -LiteralPath `"$workingDir`"; & `"$PythonExe`" -X utf8 `"$scriptPath`"$storeArg$repoArg check"
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command $psCommand"
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
$trigger.Repetition = (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) -RepetitionDuration ([TimeSpan]::MaxValue)).Repetition
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "등록 완료: $TaskName"
Write-Host "실행 명령: $PythonExe -X utf8 $scriptPath$storeArg$repoArg check"
