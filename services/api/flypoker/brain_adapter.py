from __future__ import annotations

"""Optional MaleCNS adapter boundary.

The visual app and event protocol do not depend on model weights being present.
Install `flybrain[gpu]`, download the MaleCNS artifact, and provide trained
readout files before switching the runtime mode to `flybrain`.
"""

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

import numpy as np


class _IndependentLaneRNG:
    """Give each batched FlyBrain lane its own deterministic noise stream.

    FlyBrain's public batch API accepts one seed and then draws an ``(neurons,
    batch)`` matrix.  That is statistically independent, but it does not make
    the per-fly seed boundary explicit.  The adapter keeps the connectome and
    LIF implementation unchanged and swaps only the RNG object used by
    ``step`` for six independent generators with recorded derived seeds.
    """

    def __init__(self, xp: Any, seeds: tuple[int, ...]) -> None:
        self.xp = xp
        self.generators = [xp.random.default_rng(seed) for seed in seeds]

    def random(self, shape: tuple[int, int]) -> Any:
        neurons, lanes = shape
        if lanes != len(self.generators):
            raise ValueError(f"expected {len(self.generators)} FlyBrain lanes, received {lanes}")
        columns = [generator.random(neurons, dtype=self.xp.float32) for generator in self.generators]
        return self.xp.stack(columns, axis=1)


@dataclass(frozen=True)
class ReadoutManifest:
    connectome_sha256: str
    encoder_schema: str
    pca_version: str
    training_seed: int
    action_macro_f1: float
    artifact_path: str = ""
    sizing_macro_f1: float = 0.0
    mode: str = "production"


class FlyBrainBatchAdapter:
    """Thin adapter for six independent FlyBrain instances.

    This class intentionally fails closed when the optional dependency or
    artifact is absent. The fallback engine remains available for frontend and
    protocol development.
    """

    PROFILE_ORDER = ("vesper", "sugar", "knuckles", "velvet", "static", "hex")
    DESCENDING_NEURON_COUNT = 1314
    # Temperatures are deliberately bounded: personality variation changes the
    # confidence surface of each trained readout without inventing actions.
    PROFILE_TEMPERATURES = {
        "vesper": 0.82,
        "sugar": 1.12,
        "knuckles": 0.96,
        "velvet": 0.74,
        "static": 1.24,
        "hex": 0.90,
    }

    def __init__(self, artifact_dir: str | Path, device: str = "cuda", data_dir: str | Path | None = None, variant: str = "profiles", seed: int = 20260921) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.data_dir = Path(data_dir) if data_dir is not None else self.artifact_dir
        self.device = device
        self.variant = variant
        self.seed = seed
        self.brain: Any | None = None
        self.manifest: ReadoutManifest | None = None
        self.descending: np.ndarray | None = None
        self.action_readout: Any | None = None
        self.size_readout: Any | None = None
        self.action_readouts: dict[str, Any] = {}
        self.size_readouts: dict[str, Any] = {}
        self.pca_components: np.ndarray | None = None
        self.pca_mean: np.ndarray | None = None
        self.telemetry_region_sets: dict[str, set[int]] = {"sensory": set(), "central": set(), "drives": set(), "motor": set()}
        self.lane_seeds = tuple(self.seed + index for index in range(6))

    @property
    def ready(self) -> bool:
        return self.brain is not None and self.manifest is not None

    def probe(self) -> tuple[bool, str]:
        """Return a user-safe readiness result without downloading anything."""
        manifest_file = self.artifact_dir / "manifest.json"
        try:
            import flybrain  # type: ignore
        except Exception as exc:
            return False, f"flybrain import unavailable: {type(exc).__name__}"
        if not manifest_file.exists():
            return False, f"missing readout manifest: {manifest_file}"
        if not bool(flybrain.has_data(self.data_dir)):
            return False, f"missing MaleCNS data under: {self.data_dir}"
        try:
            import json
            raw = json.loads(manifest_file.read_text(encoding="utf-8"))
            try:
                from training.encoder import ENCODER_SCHEMA
            except ImportError:
                ENCODER_SCHEMA = "poker-feature-detectors-v2"
            if raw.get("encoder_schema") != ENCODER_SCHEMA:
                return False, "encoder schema does not match readout manifest"
            metrics = raw.get("metrics", {})
            if float(raw.get("action_macro_f1", metrics.get("action_macro_f1", 0.0))) < 0.65 or float(metrics.get("legal_action_rate", 0.0)) < 1.0:
                return False, "readout acceptance gate failed"
            variants = raw.get("variants", {})
            if any(float(entry.get("action_macro_f1", 0.0)) < 0.65 for entry in variants.values()):
                return False, "profile readout acceptance gate failed"
            expected = raw.get("connectome_sha256") or raw.get("connectome_hash")
            if expected and not str(expected).startswith("UNSET"):
                actual = self._connectome_hash(self.data_dir)
                if actual != expected:
                    return False, "connectome hash does not match readout manifest"
        except (OSError, ValueError) as exc:
            return False, f"connectome hash validation failed: {type(exc).__name__}"
        return True, "flybrain package, MaleCNS data, and readout manifest detected"

    def load(self) -> None:
        try:
            from flybrain import FlyBrain  # type: ignore
        except ImportError as exc:
            raise RuntimeError("flybrain is not installed; use the simulated adapter") from exc

        manifest_file = self.artifact_dir / "manifest.json"
        if not manifest_file.exists():
            raise RuntimeError(f"missing trained readout manifest: {manifest_file}")
        import json

        raw = json.loads(manifest_file.read_text(encoding="utf-8"))
        try:
            from training.encoder import ENCODER_SCHEMA
        except ImportError:
            ENCODER_SCHEMA = "poker-feature-detectors-v2"
        if raw.get("encoder_schema") != ENCODER_SCHEMA:
            raise RuntimeError("encoder schema does not match readout manifest")
        # Keep the JSON contract strict enough to catch a mismatched artifact,
        # while accepting the early fixture key used by the offline harness.
        raw.setdefault("connectome_sha256", raw.pop("connectome_hash", ""))
        metrics = raw.get("metrics", {})
        raw.setdefault("action_macro_f1", metrics.get("action_macro_f1", 0.0))
        raw.setdefault("sizing_macro_f1", metrics.get("sizing_macro_f1", 0.0))
        if float(raw["action_macro_f1"]) < 0.65 or float(metrics.get("legal_action_rate", 0.0)) < 1.0:
            raise RuntimeError("readout acceptance gate failed")
        if any(float(entry.get("action_macro_f1", 0.0)) < 0.65 for entry in raw.get("variants", {}).values()):
            raise RuntimeError("profile readout acceptance gate failed")
        raw.setdefault("artifact_path", str(manifest_file.parent))
        manifest_keys = {
            "connectome_sha256",
            "encoder_schema",
            "pca_version",
            "training_seed",
            "action_macro_f1",
            "artifact_path",
            "sizing_macro_f1",
            "mode",
        }
        self.manifest = ReadoutManifest(**{key: raw[key] for key in manifest_keys if key in raw})
        if self.manifest.connectome_sha256 and not self.manifest.connectome_sha256.startswith("UNSET"):
            actual_hash = self._connectome_hash(self.data_dir)
            if actual_hash != self.manifest.connectome_sha256:
                raise RuntimeError("connectome hash does not match readout manifest")
        self.brain = FlyBrain(data=self.data_dir, batch=6, device=self.device, seed=self.seed, dt=0.020, sensory_input=False)
        if int(getattr(self.brain, "batch", 0)) != 6:
            raise RuntimeError("FlyBrain batch contract is not six lanes")
        # Reset once more with explicit per-lane streams after FlyBrain has
        # allocated its six voltage columns.  The connectome remains shared;
        # voltages and noise are lane-local.
        self.brain.rng = _IndependentLaneRNG(self.brain.xp, self.lane_seeds)
        self.descending = self.brain.cells(["descending_neuron"])
        if len(self.descending) != self.DESCENDING_NEURON_COUNT:
            raise RuntimeError(
                f"MaleCNS descending-neuron trace contract changed: expected {self.DESCENDING_NEURON_COUNT}, received {len(self.descending)}"
            )
        self.telemetry_region_sets = {
            "sensory": self._cell_set(("LC10a", "LPLC1")),
            "drives": self._cell_set(("LPLC2", "LC4")),
            "motor": {int(index) for index in np.asarray(self.descending).tolist()},
        }
        artifact_root = manifest_file.parent
        variants = raw.get("variants", {})
        if self.variant in ("profiles", "all") and variants:
            for profile in self.PROFILE_ORDER:
                entry = variants.get(profile, {})
                self.action_readouts[profile] = self._load_pickle(
                    artifact_root / entry.get("action_readout", raw.get("action_readout", "action_readout.pkl"))
                )
                self.size_readouts[profile] = self._load_pickle(
                    artifact_root / entry.get("size_readout", raw.get("size_readout", "size_readout.pkl"))
                )
            self.action_readout = self.action_readouts["hex"]
            self.size_readout = self.size_readouts["hex"]
        else:
            entry = variants.get(self.variant, {})
            self.action_readout = self._load_pickle(artifact_root / entry.get("action_readout", raw.get("action_readout", "action_readout.pkl")))
            self.size_readout = self._load_pickle(artifact_root / entry.get("size_readout", raw.get("size_readout", "size_readout.pkl")))
            self.action_readouts = {profile: self.action_readout for profile in self.PROFILE_ORDER}
            self.size_readouts = {profile: self.size_readout for profile in self.PROFILE_ORDER}
        pca_file = artifact_root / "pca.npz"
        if not pca_file.exists():
            raise RuntimeError(f"missing PCA artifact: {pca_file}")
        pca = np.load(pca_file)
        self.pca_components = np.asarray(pca["components"], dtype=np.float32)
        self.pca_mean = np.asarray(pca["mean"], dtype=np.float32)

    def step(self, encoded_inputs: list[list[tuple[np.ndarray, Any]]]) -> dict[str, Any]:
        if not self.ready:
            raise RuntimeError("FlyBrainBatchAdapter.load() must succeed before step()")
        if self.descending is None or self.action_readout is None or self.size_readout is None or self.pca_components is None or self.pca_mean is None:
            raise RuntimeError("readout artifacts are incomplete")

        activity = np.zeros((self.brain.batch, len(self.descending)), dtype=np.float32)
        # Keep a compact, real sample of fired neuron ids for the spectator
        # telemetry.  The full state is intentionally never serialized.
        sampled_spikes: list[list[int]] = [[] for _ in range(self.brain.batch)]
        region_counts = [{"sensory": 0, "central": 0, "drives": 0, "motor": 0} for _ in range(self.brain.batch)]
        descending_lookup = {int(index): position for position, index in enumerate(self.descending)}
        for frame in encoded_inputs:
            fired = self.brain.step(inject=frame)
            for fly_index, fly_spikes in enumerate(fired):
                for neuron_index in np.asarray(fly_spikes).tolist():
                    neuron_id = int(neuron_index)
                    if len(sampled_spikes[fly_index]) < 64:
                        sampled_spikes[fly_index].append(neuron_id)
                    region = self._telemetry_region(neuron_id)
                    region_counts[fly_index][region] += 1
                    position = descending_lookup.get(neuron_id)
                    if position is not None:
                        activity[fly_index, position] += 1.0

        projected = (activity - self.pca_mean) @ self.pca_components.T
        actions: list[Any] = []
        sizings: list[Any] = []
        action_probabilities: list[Any] | None = []
        size_probabilities: list[Any] | None = []
        action_logits: list[Any] | None = []
        for fly_index, profile in enumerate(self.PROFILE_ORDER):
            action_model = self.action_readouts.get(profile, self.action_readout)
            size_model = self.size_readouts.get(profile, self.size_readout)
            row = projected[fly_index : fly_index + 1]
            temperature = self.PROFILE_TEMPERATURES[profile]
            actions.append(self._temperature_predict(action_model, row, temperature))
            sizings.append(self._temperature_predict(size_model, row, temperature))
            if action_probabilities is not None:
                if hasattr(action_model, "predict_proba"):
                    action_probabilities.append(np.asarray(action_model.predict_proba(row)[0]).round(5).tolist())
                else:
                    action_probabilities = None
            if size_probabilities is not None:
                if hasattr(size_model, "predict_proba"):
                    size_probabilities.append(np.asarray(size_model.predict_proba(row)[0]).round(5).tolist())
                else:
                    size_probabilities = None
            if action_logits is not None:
                if hasattr(action_model, "decision_function"):
                    action_logits.append((np.asarray(action_model.decision_function(row)[0], dtype=np.float32) / temperature).round(5).tolist())
                else:
                    action_logits = None
        return {
            "mode": "flybrain",
            "encoded_inputs": len(encoded_inputs),
            "activity": activity.mean(axis=1).round(4).tolist(),
            "sampledSpikes": sampled_spikes,
            "regions": [self._normalize_regions(counts) for counts in region_counts],
            "sampledNeuronCount": 12000,
            "action": actions,
            "sizing": sizings,
            "actionProbabilities": action_probabilities,
            "sizingProbabilities": size_probabilities,
            "actionLogits": action_logits,
            "readoutTemperatures": [self.PROFILE_TEMPERATURES[profile] for profile in self.PROFILE_ORDER],
            "laneSeeds": list(self.lane_seeds),
        }

    def _cell_set(self, names: tuple[str, ...]) -> set[int]:
        """Resolve documented MaleCNS detector populations into neuron IDs."""
        resolved: set[int] = set()
        if self.brain is None:
            return resolved
        for name in names:
            try:
                resolved.update(int(index) for index in np.asarray(self.brain.cells([name])).tolist())
            except (KeyError, RuntimeError, ValueError):
                # A dataset revision may omit one detector; telemetry still
                # remains useful for the populations that are present.
                continue
        return resolved

    def _telemetry_region(self, neuron_id: int) -> str:
        if neuron_id in self.telemetry_region_sets["motor"]:
            return "motor"
        if neuron_id in self.telemetry_region_sets["drives"]:
            return "drives"
        if neuron_id in self.telemetry_region_sets["sensory"]:
            return "sensory"
        return "central"

    @staticmethod
    def _normalize_regions(counts: dict[str, int]) -> dict[str, float]:
        total = max(1, sum(counts.values()))
        # A bounded ratio keeps the live display readable while preserving
        # relative regional firing rather than inventing a neural scalar.
        return {name: round(min(1.0, value / max(4.0, total * 0.35)), 4) for name, value in counts.items()}

    @staticmethod
    def _temperature_predict(model: Any, row: np.ndarray, temperature: float) -> Any:
        """Choose from the trained classes after bounded logit scaling."""
        if hasattr(model, "decision_function") and hasattr(model, "classes_"):
            scores = np.asarray(model.decision_function(row)[0], dtype=np.float32)
            if scores.ndim == 0:
                return model.predict(row)[0]
            return model.classes_[int(np.argmax(scores / max(0.5, min(1.5, temperature))))]
        return model.predict(row)[0]

    def step_features(self, feature_sequences: list[list[dict[str, float]]]) -> dict[str, Any]:
        """Encode six per-fly feature pulse sequences into detector injections."""
        if not self.ready or self.brain is None:
            raise RuntimeError("FlyBrainBatchAdapter.load() must succeed before step_features()")
        if len(feature_sequences) != 6 or any(len(sequence) == 0 for sequence in feature_sequences):
            raise ValueError("feature_sequences must contain six non-empty sequences")
        groups = {name: self.brain.cells([name]) for name in ("LC10a", "LPLC1", "LPLC2", "LC4")}
        sides = {name: (self.brain.side[index] == "L", self.brain.side[index] == "R") for name, index in groups.items()}
        frames: list[list[tuple[np.ndarray, Any]]] = []
        for step in range(min(len(sequence) for sequence in feature_sequences)):
            frame: list[tuple[np.ndarray, Any]] = []
            for name in groups:
                values = np.asarray([feature_sequences[fly][step].get(name, 0.0) for fly in range(6)], dtype=np.float32)
                left, right = sides[name]
                if left.any():
                    frame.append((groups[name][left], np.maximum(values, 0.0)))
                if right.any():
                    frame.append((groups[name][right], np.maximum(-values, 0.0)))
            frames.append(frame)
        return self.step(frames)

    @staticmethod
    def _load_pickle(path: Path) -> Any:
        import pickle

        if not path.exists():
            raise RuntimeError(f"missing readout artifact: {path}")
        with path.open("rb") as handle:
            return pickle.load(handle)

    @staticmethod
    def _connectome_hash(data_dir: Path) -> str:
        digest = hashlib.sha256()
        for name in ("brain.npz", "weights.npz"):
            with (data_dir / name).open("rb") as handle:
                for chunk in iter(lambda: handle.read(1 << 20), b""):
                    digest.update(chunk)
        return digest.hexdigest()
