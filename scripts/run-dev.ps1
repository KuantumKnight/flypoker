$ErrorActionPreference = "Stop"

Write-Host "Starting Fly Poker API on http://localhost:8000" -ForegroundColor Cyan
$api = Start-Process -FilePath "py" -ArgumentList "-3.12", "-m", "uvicorn", "flypoker.main:app", "--app-dir", "services/api", "--reload", "--port", "8000" -PassThru

try {
  npm run dev
}
finally {
  if ($api -and !$api.HasExited) { Stop-Process -Id $api.Id }
}
