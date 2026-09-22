param(
  [string]$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")),
  [string]$NssmPath = "nssm.exe",
  [string]$TunnelConfig = (Join-Path $ProjectRoot "infra\cloudflared\config.yml"),
  [string]$AllowedOrigins = "https://live.example.com"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $ProjectRoot)) { throw "Project root not found: $ProjectRoot" }
$python = Join-Path $ProjectRoot ".venv312\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Create the validated Python 3.12 environment first: $python" }
if (-not (Get-Command $NssmPath -ErrorAction SilentlyContinue)) { throw "NSSM was not found. Install it and retry." }
if (-not (Test-Path -LiteralPath $TunnelConfig)) { throw "Copy config.example.yml to $TunnelConfig and fill in the tunnel credentials." }

$apiName = "FlyPokerApi"
$tunnelName = "FlyPokerCloudflared"
$apiArgs = "-m uvicorn flypoker.main:app --app-dir services/api --port 8000"

& $NssmPath install $apiName $python $apiArgs
& $NssmPath set $apiName AppDirectory $ProjectRoot
& $NssmPath set $apiName AppEnvironmentExtra "FLYPOKER_MODE=flybrain" "FLY_DATA=fly-data" "FLYPOKER_READOUT_DIR=artifacts/readout-male-cns-gpu" "FLY_DEVICE=cuda" "FLYPOKER_ALLOWED_ORIGINS=$AllowedOrigins" "FLYPOKER_REQUIRE_ORIGIN=true" "FLYPOKER_MAX_SPECTATORS=200" "FLYPOKER_CONNECTIONS_PER_MINUTE=240"
& $NssmPath set $apiName AppExit Default Restart
& $NssmPath set $apiName AppRestartDelay 5000
& $NssmPath set $apiName Start SERVICE_AUTO_START

& $NssmPath install $tunnelName (Get-Command cloudflared -ErrorAction Stop).Source "tunnel --config `"$TunnelConfig`" run"
& $NssmPath set $tunnelName AppDirectory (Split-Path -Parent $TunnelConfig)
& $NssmPath set $tunnelName AppExit Default Restart
& $NssmPath set $tunnelName AppRestartDelay 5000
& $NssmPath set $tunnelName Start SERVICE_AUTO_START

& $NssmPath start $apiName
& $NssmPath start $tunnelName
Write-Host "Installed and started $apiName and $tunnelName." -ForegroundColor Green
