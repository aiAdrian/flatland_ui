# Start the whole stack — LLM server, backend, frontend — and shut down again on Ctrl-C.
# macOS / Linux: use scripts/start.sh. First-time LLM install: scripts/setup-llm.ps1.
#
# Only processes this script starts are stopped again. An Ollama that was already
# running (the Windows tray app / a service) is left exactly as it was found.
$ErrorActionPreference = 'Stop'

Set-Location (Join-Path $PSScriptRoot '..')
$root = $PWD.Path

$model       = if ($env:LLM_MODEL) { $env:LLM_MODEL } else { 'qwen3.5:4b' }
$baseUrl     = if ($env:LLM_BASE_URL) { $env:LLM_BASE_URL } else { 'http://localhost:11434/v1' }
$ollamaHost  = $baseUrl -replace '/v1$', ''
$backendPort = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { '8000' }

$ollama = $null   # set only if *we* start the server
$backend = $null
$frontend = $null

function Log($msg)  { Write-Host "==> $msg" -ForegroundColor Cyan }
function Warn($msg) { Write-Host "!!  $msg" -ForegroundColor Yellow }

function Test-Url($url) {
  try { Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true }
  catch { return $false }
}

function Wait-Url($url, $seconds, $what) {
  for ($i = 0; $i -lt $seconds; $i++) {
    if (Test-Url $url) { return $true }
    Start-Sleep -Seconds 1
  }
  Warn "$what did not come up at $url"
  return $false
}

function Stop-Tree($name, $proc) {
  if (-not $proc -or $proc.HasExited) { return }
  Log "stopping $name"
  # /T kills the child processes too — uvicorn --reload and ng serve both spawn them.
  taskkill /PID $proc.Id /T /F 2>&1 | Out-Null
}

try {
  # -------------------------------------------------------------- 1. LLM server
  if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Warn 'Ollama is not installed — run scripts\setup-llm.ps1 first (see docs/reference/llm-setup.md)'
    exit 1
  }

  if (Test-Url "$ollamaHost/api/version") {
    Log "Ollama already running at $ollamaHost — leaving it alone"
  } else {
    Log "starting Ollama at $ollamaHost"
    $ollama = Start-Process ollama -ArgumentList 'serve' -PassThru -WindowStyle Hidden
    if (-not (Wait-Url "$ollamaHost/api/version" 30 'Ollama')) { exit 1 }
  }

  $installed = (& ollama list | Select-Object -Skip 1 | ForEach-Object { ($_ -split '\s+')[0] })
  if ($installed -notcontains $model) {
    Log "model $model is missing — pulling it (one time, ~3.4 GB)"
    & ollama pull $model
  }
  Log "model ready: $model"

  # Embedding model for docs Q&A — missing is a warning, not a failure: the
  # chat degrades to keyword-only retrieval without it.
  $embedModel = if ($env:RAG_EMBED_MODEL) { $env:RAG_EMBED_MODEL } else { 'nomic-embed-text' }
  if (($installed -notcontains $embedModel) -and ($installed -notcontains "${embedModel}:latest")) {
    Log "embedding model $embedModel is missing — pulling it (one time, ~274 MB)"
    & ollama pull $embedModel
    if ($LASTEXITCODE -ne 0) { Warn "could not pull $embedModel — docs Q&A falls back to keyword search" }
  }

  # ----------------------------------------------------------------- 2. backend
  $venv = Join-Path $root 'backend\.venv\Scripts\python.exe'
  if (-not (Test-Path $venv)) {
    Warn 'no backend\.venv — using the active Python (see README)'
    $python = 'python'
  } else {
    $python = $venv
  }
  Log "starting backend on :$backendPort"
  $backend = Start-Process $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', $backendPort `
    -WorkingDirectory (Join-Path $root 'backend') -PassThru -NoNewWindow
  if (-not (Wait-Url "http://localhost:$backendPort/health" 60 'backend')) { exit 1 }

  # ---------------------------------------------------------------- 3. frontend
  if (-not (Test-Path (Join-Path $root 'frontend\node_modules'))) {
    Log 'installing frontend deps'
    Start-Process npm -ArgumentList 'install' -WorkingDirectory (Join-Path $root 'frontend') -NoNewWindow -Wait
  }
  Log 'starting frontend on :4200'
  $frontend = Start-Process npm -ArgumentList 'start' `
    -WorkingDirectory (Join-Path $root 'frontend') -PassThru -NoNewWindow

  Write-Host ''
  Write-Host "  UI        http://localhost:4200      (LLM Chat panel, bottom of the left pane)"
  Write-Host "  API docs  http://localhost:$backendPort/docs"
  Write-Host "  LLM       $model via $ollamaHost"
  Write-Host ''
  Write-Host '  Ctrl-C stops everything this script started.'
  Write-Host ''

  # Exit as soon as *any* of them dies, so a crashed backend doesn't look like a hang.
  while (-not $backend.HasExited -and -not $frontend.HasExited) { Start-Sleep -Seconds 1 }
  Warn 'a service exited — shutting the rest down'
}
finally {
  Stop-Tree 'frontend' $frontend
  Stop-Tree 'backend' $backend
  if ($ollama) { Stop-Tree 'ollama (we started it)' $ollama }
  else { Log 'leaving Ollama running — it was already up before this script' }
}
