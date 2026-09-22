# Fly Poker API

Development mode uses `LiveEngine`, a deterministic adapter with the production event protocol. This keeps the visual client runnable before the MaleCNS data and trained readouts are installed.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -r requirements-dev.txt  # optional tests and smoke tooling
uvicorn flypoker.main:app --app-dir services/api --reload --port 8000
```

When configured, the GPU adapter replaces the simulator's decision step while
preserving the `EventEnvelope`, snapshot, and replay interfaces.
`flypoker.brain_worker.BrainWorkerProcess` provides the bounded Windows-safe
spawn boundary so neural work cannot block WebSocket clients.

Set `FLYPOKER_MODE=flybrain` when you want `/v1/status` and `/health/ready` to
start the six-lane GPU worker. `FLY_DATA` points at the two MaleCNS `.npz`
files, while `FLYPOKER_READOUT_DIR` points at the versioned manifest/readouts
(for example `artifacts/readout-male-cns-gpu`). A failed import, missing data,
missing artifact, or connectome hash mismatch is reported as
`brain_runtime: unavailable`; the service
never silently labels the development simulator as a biological run.

Set `FLYPOKER_ALLOWED_ORIGINS` to a comma-separated list before exposing the
service through Cloudflare Tunnel. WebSocket handshakes from other origins
are rejected with policy code 1008.

The service accepts up to 200 concurrent spectators by default and permits
240 connection attempts per client address per minute (`FLYPOKER_CONNECTIONS_PER_MINUTE`)
to absorb an initial audience burst while bounding reconnect storms. In
configured `flybrain` mode, `/health/ready` returns 503 and `/v1/status`
reports `offline` whenever the GPU worker is unavailable.

Set `FLYPOKER_REPLAY_UPLOAD_URL` and `FLYPOKER_REPLAY_UPLOAD_TOKEN` to enable
the optional authenticated compact-replay upload. Upload failures are emitted
as a `system.status` event and do not stop the live table.
