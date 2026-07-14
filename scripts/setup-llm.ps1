# Set up the local LLM (Windows). macOS/Linux: use scripts/setup-llm.sh.
# See docs/reference/llm-setup.md for the full guide.
#
# Run from a PowerShell prompt:
#   powershell -ExecutionPolicy Bypass -File scripts\setup-llm.ps1
$ErrorActionPreference = "Stop"

$Model   = if ($env:LLM_MODEL)    { $env:LLM_MODEL }    else { "qwen3.5:4b" }
$BaseUrl = if ($env:LLM_BASE_URL) { $env:LLM_BASE_URL } else { "http://localhost:11434/v1" }
$Root    = $BaseUrl -replace '/v1$', ''

Write-Host "==> Checking for Ollama"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Host @"
Ollama is not installed.

  winget install Ollama.Ollama
  (or download the installer: https://ollama.com/download)

Install it, then re-run this script.
Native Windows builds exist for both x86_64 and ARM64 — no WSL needed.
"@
    exit 1
}
Write-Host "    found: $(ollama --version)"

Write-Host "==> Checking the Ollama server is up"
function Test-Ollama {
    try { Invoke-RestMethod -Uri "$Root/api/version" -TimeoutSec 2 | Out-Null; return $true }
    catch { return $false }
}
if (-not (Test-Ollama)) {
    Write-Host "    server not responding - starting it"
    Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Ollama) { break }
        Start-Sleep -Seconds 1
    }
    if (-not (Test-Ollama)) {
        Write-Error "could not start the Ollama server - run 'ollama serve' in another terminal"
        exit 1
    }
}
Write-Host "    server up at $Root"

Write-Host "==> Pulling model: $Model"
ollama pull $Model
if ($LASTEXITCODE -ne 0) { Write-Error "ollama pull failed"; exit 1 }

$EmbedModel = if ($env:RAG_EMBED_MODEL) { $env:RAG_EMBED_MODEL } else { "nomic-embed-text" }
Write-Host "==> Pulling embedding model: $EmbedModel (docs Q&A retrieval, ~274 MB)"
ollama pull $EmbedModel
if ($LASTEXITCODE -ne 0) { Write-Error "ollama pull failed"; exit 1 }

# Tested over HTTP rather than `ollama run`: same wire format the backend uses, and
# the output stays readable when piped to a log.
Write-Host "==> Smoke test: chat model"
$chatBody = @{
    model    = $Model
    messages = @(@{ role = 'user'; content = 'Reply with exactly one word: ready' })
    reasoning_effort = 'none'
} | ConvertTo-Json -Depth 5
$chat = Invoke-RestMethod -Uri "$BaseUrl/chat/completions" -Method Post -ContentType 'application/json' -Body $chatBody
$reply = $chat.choices[0].message.content.Trim()
if (-not $reply) { Write-Error "$Model returned no text"; exit 1 }
Write-Host "    $Model says: $reply"

Write-Host "==> Smoke test: embedding model (docs Q&A)"
$embedBody = @{ model = $EmbedModel; input = 'railway dispatching' } | ConvertTo-Json
$embed = Invoke-RestMethod -Uri "$BaseUrl/embeddings" -Method Post -ContentType 'application/json' -Body $embedBody
Write-Host "    $EmbedModel returns $($embed.data[0].embedding.Count)-dimensional vectors"

Write-Host @"

==> Done.

The backend defaults to this setup, so there is nothing else to configure.
To override, copy backend\.env.example to backend\.env.

Verify through the API:
  cd backend; uvicorn app.main:app --reload
  curl.exe localhost:8000/llm/health
  curl.exe -X POST localhost:8000/llm/complete -H "content-type: application/json" -d '{\"prompt\":\"Say hello in one sentence.\"}'
"@
