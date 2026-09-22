# Fly Poker training pipeline

This directory is reserved for offline artifacts and experiments. The live
engine must never train or mutate the connectome.

The production pipeline is:

1. Generate poker states with public information only.
2. Label states with an equity/pot-odds teacher policy.
   The corpus carries the fly's own hole cards, public board, legal actions,
   and public action history; opponent private cards are never sampled.
3. Encode features as temporal pulses into the documented MaleCNS feature
   detector groups (`LC10a`, `LPLC1`, `LPLC2`, `LC4`).
4. Run a six-element `FlyBrain(batch=6)` reservoir and trace descending neurons.
5. Fit a fixed PCA transform plus action and sizing readouts.
6. Evaluate held-out macro-F1, legality, and personality separation.
7. Write `manifest.json` and readout artifacts with the connectome hash,
   encoder schema, PCA version, seed, and metrics.

Until those artifacts exist, the app intentionally labels itself as the
simulated development adapter.

## Reproducible fixture run

The laptop-safe harness creates the same manifest/readout file shape without
pretending that a synthetic reservoir is the MaleCNS brain:

```powershell
py -3.12 training/train_readouts.py --output artifacts/readout-fixture
```

Its manifest is marked `offline-reservoir-fixture`. The production
`--reservoir flybrain` path runs the six-element `FlyBrain(batch=6)` trace and
writes the real connectome hash; only that artifact may enable
`FLYPOKER_MODE=flybrain`.

## Real MaleCNS artifact run

With `fly-data/brain.npz` and `fly-data/weights.npz` installed, the validated
GPU command is:

```powershell
.venv312\\Scripts\\python.exe training/train_readouts.py `
  --reservoir flybrain --data fly-data --device cuda --samples 900 `
  --output artifacts/readout-male-cns-gpu
```

The generated manifest records the connectome hash, descending-neuron PCA,
held-out metrics, and six independently distilled profiles under
`variants/`. The current validated run exceeds the action macro-F1 gate
(`0.7557` versus `0.65`) and shows distinct VPIP/PFR/aggression rates; sizing is separately reported
and legally clamped by the live adapter.
The training command fails closed if the 0.65 action/legal gate or profile
separation thresholds are not met.
