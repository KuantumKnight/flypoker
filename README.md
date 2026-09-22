# Fly Poker

Six fruit-fly connectome avatars at a cinematic poker table.

The repository ships a complete visual/API vertical slice plus a validated
optional MaleCNS GPU host. The simulator remains the safe default; when the
versioned data and readouts are present, a bounded worker runs six independent
FlyBrain lanes through the same event protocol and SQLite journal.

## Run the API

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r services/api/requirements.txt
pip install -r services/api/requirements-dev.txt  # optional test tooling
py -3.12 -m uvicorn flypoker.main:app --app-dir services/api --reload --port 8000
```

For the validated RTX 5070 host, install the CUDA overlay too:

```powershell
pip install -r services/api/requirements-gpu.txt
```

## Run the web client

```powershell
npm install
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
$env:NEXT_PUBLIC_LIVE_WS_URL = "ws://localhost:8000/v1/live/ws"
# Optional: Cloudflare Worker base URL for replay fallback while the GPU host sleeps.
$env:NEXT_PUBLIC_REPLAY_API_URL = "https://replays.example.com"
npm run dev
```

The WebGL scene ships real, license-tracked assets in `public/models/`: the
CC-BY Spy Fly body plus the CC0 Poker Pack table, card, and chip meshes. The
six avatars wrap that body with insect-only articulated forelegs that reach
for cards and chips on action beats. Set `NEXT_PUBLIC_FLY_GLTF_URL` to replace the bundled fly with a
production GLB; if the browser has no WebGL support (or the probe fails), the
deterministic CSS table remains available. Set
`NEXT_PUBLIC_ENABLE_WEBGL_SCENE=false` to force CSS-only mode for constrained
devices. See `public/models/CREDITS.md` and `ATTRIBUTIONS.md` before
redistributing the build.

The app falls back to a seeded local table when the API is unavailable. The
production adapter boundary is in `services/api/flypoker/brain_adapter.py`;
install `services/api/requirements-gpu.txt` and provide the checksum-verified
MaleCNS files plus a versioned readout manifest under `artifacts/` before
switching the runtime from `simulated` to `flybrain`.

## Checks

```powershell
py -3.12 -m compileall -q services/api/flypoker
py -3.12 -m pytest -q services/api/tests
py -3.12 training/train_readouts.py --output artifacts/readout-fixture
.venv312\Scripts\python.exe scripts/export-protocol-schema.py
py -3.12 scripts/export-protocol-types.py
```

The real connectome integration intentionally fails closed when its model data
or artifacts are absent. This keeps the interface honest: the development
adapter is labeled simulated and never presents mock activity as biological
evidence.

Probe the optional runtime without starting the web service:

```powershell
.venv312\Scripts\python.exe scripts/probe-flybrain.py --device cuda --steps 50
```

The checked-in `artifacts/readout-fixture` is an offline-reservoir validation
fixture only. It proves the PCA/readout/manifest contract and is not a
MaleCNS-derived artifact; replace it with a real connectome trace and hash
before enabling `FLYPOKER_MODE=flybrain`.

Verify the Windows spawn worker and six-lane readout independently with:

```powershell
.venv312\Scripts\python.exe scripts/verify-brain-worker.py
.venv312\Scripts\python.exe scripts/verify-readout.py
.venv312\Scripts\python.exe scripts/launch-preflight.py
.venv312\Scripts\python.exe scripts/smoke-live-api.py
.venv312\Scripts\python.exe scripts/load-test.py --clients 200 --seconds 60
.venv312\Scripts\python.exe scripts/soak-test.py --hours 0.01 --hands 100
.venv312\Scripts\python.exe scripts/soak-test.py --gpu --hours 12 --hands 100000 --database data/soak-gpu-12h.db
.venv312\Scripts\python.exe scripts/soak-test.py --hours 0.001 --hands 2 --database data/replay-check.db
.venv312\Scripts\python.exe scripts/verify-replay.py --database data/replay-check.db
```

After installing the validated GPU stack (`flybrain==0.1.0` plus
`cupy-cuda13x`) and downloading the two checksum-verified files into
`fly-data/`, run the real host with:

```powershell
$env:FLYPOKER_MODE = "flybrain"
$env:FLY_DATA = "fly-data"
$env:FLYPOKER_READOUT_DIR = "artifacts/readout-male-cns-gpu"
$env:FLY_DEVICE = "cuda"
$env:FLY_BRAIN_SEED = "20260921"
.venv312\Scripts\python.exe -m uvicorn flypoker.main:app --app-dir services/api --port 8000
```

The browser and API still default to the simulator when these variables or
artifacts are absent.

For a read-only launch gate on the Windows host, run
`scripts/launch-preflight.py --production`. It checks the CUDA tools,
connectome/readout gates, production origins, tunnel configuration, and
replay Worker wiring without printing any secret values.

## Portfolio deployment on Vercel

The public portfolio UI is a normal Next.js deployment on Vercel. It does not
need the RTX 5070 to stay on: when the laptop API is unavailable, the page
falls back to its seeded showcase table and can read the latest replay from
`NEXT_PUBLIC_REPLAY_API_URL`.

In the Vercel project, add these client-safe environment variables when the
live host and replay Worker are ready:

```text
NEXT_PUBLIC_API_URL=https://live.example.com
NEXT_PUBLIC_LIVE_WS_URL=wss://live.example.com/v1/live/ws
NEXT_PUBLIC_REPLAY_API_URL=https://replays.example.com
```

Deploy from the repository root with `vercel --prod`, or connect the GitHub
repository in the Vercel dashboard for automatic deployments. The short free
address is intended to be `flypoker.vercel.app` if that project name is
available.

## Cloudflare replay deployment and laptop tunnel

The replay ingest Worker lives under `infra/cloudflare`. The optional replay
fallback uses the checked-in `wrangler.jsonc` configuration:

```powershell
$env:NEXT_PUBLIC_API_URL = "https://live.example.com"
$env:NEXT_PUBLIC_LIVE_WS_URL = "wss://live.example.com/v1/live/ws"
$env:NEXT_PUBLIC_REPLAY_API_URL = "https://replays.example.com"
npm run cloudflare:build
npx wrangler deploy --config wrangler.jsonc --dry-run
```

Create the `fly-poker-live-ui-opennext-cache` R2 bucket and replace the
placeholder Worker name/domain before the credentialed deploy. OpenNext warns
on Windows; use WSL for the production build if the host reports a filesystem
compatibility issue.

## Attribution and limits

The optional neural runtime is built around the open-source
[fly.ai / FlyBrain implementation](https://github.com/alextitonis/fly.ai) and
the public MaleCNS data, with their licenses and citations retained alongside
the downloaded artifacts. Poker rules are delegated to
[PokerKit](https://pokerkit.readthedocs.io/en/stable/reference.html). The
connectome is biological source material; the poker encoder, teacher policy,
PCA, and linear readouts are engineered software. This project does not claim
that biological flies understand poker.

See [ATTRIBUTIONS.md](ATTRIBUTIONS.md) for the external-work and data notes.
