# Build the Next.js dashboard front end into mota/dashboard/web/out (served by FastAPI at /).
# Usage: .\scripts\build_web.ps1 [-Dev]   (-Dev starts `next dev` on :3000 proxying to the API on :8080)
param([switch]$Dev)
$ErrorActionPreference = "Stop"
$web = Join-Path $PSScriptRoot "..\mota\dashboard\web"
Push-Location $web
try {
    if (-not (Test-Path "node_modules")) { npm ci --no-audit --no-fund }
    if ($Dev) { npm run dev } else { npm run build; Write-Host "built -> $web\out  (python -m mota.dashboard serves it at /)" }
} finally { Pop-Location }
