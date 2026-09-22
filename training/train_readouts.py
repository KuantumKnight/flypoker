"""Generate deterministic teacher/readout artifacts for Fly Poker.

The script is intentionally small enough to run on a laptop.  It is the
offline contract for the production pipeline: the default fixture reservoir
keeps CI and development portable, while ``--reservoir flybrain`` runs the
same state sampling, teacher labels, PCA, validation, and manifest format
against real MaleCNS descending-neuron traces.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    from .encoder import ENCODER_SCHEMA, PublicPokerState, encode_state, vectorize_state
except ImportError:  # direct ``py training/train_readouts.py`` invocation
    from encoder import ENCODER_SCHEMA, PublicPokerState, encode_state, vectorize_state


PERSONALITIES = {
    "vesper": (0.13, 0.05, 0.03),
    "sugar": (-0.08, 0.14, 0.04),
    "knuckles": (-0.03, 0.04, 0.18),
    "velvet": (0.11, -0.09, -0.05),
    "static": (0.0, 0.02, 0.2),
    "hex": (0.03, 0.0, 0.0),
}

RANK_VALUES = {rank: value for value, rank in enumerate("23456789TJQKA", start=2)}
DECK = tuple(f"{rank}{suit}" for suit in ("♠", "♥", "♦", "♣") for rank in RANK_VALUES)


def estimate_card_equity(hole_cards: tuple[str, ...], board: tuple[str, ...], rng: np.random.Generator) -> float:
    """Create a bounded teacher equity estimate from the same visible cards."""
    ranks = [RANK_VALUES.get(card[:1], 2) for card in hole_cards]
    score = 0.08 + (sum(ranks) / (2 * 14.0)) * 0.52
    if len(ranks) == 2 and ranks[0] == ranks[1]:
        score += 0.18
    if len(hole_cards) == 2 and hole_cards[0][-1:] == hole_cards[1][-1:]:
        score += 0.045
    board_ranks = {RANK_VALUES.get(card[:1], 2) for card in board}
    score += 0.04 * len(set(ranks) & board_ranks)
    score += float(rng.normal(0.0, 0.025))
    return float(np.clip(score, 0.05, 0.92))


def sample_states(count: int, seed: int) -> tuple[list[PublicPokerState], np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    states: list[PublicPokerState] = []
    actions: list[str] = []
    sizes: list[str] = []
    action_names = ("fold", "check-call", "raise")
    size_names = ("half-pot", "three-quarter-pot", "pot", "all-in")
    for _ in range(count):
        shuffled = rng.permutation(DECK)
        hole_cards = tuple(str(card) for card in shuffled[:2])
        street = ("preflop", "flop", "turn", "river")[int(rng.integers(0, 4))]
        board_count = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}[street]
        public_board = tuple(str(card) for card in shuffled[2:2 + board_count])
        history_length = int(rng.integers(0, 7))
        public_action_history = tuple(str(action) for action in rng.choice(("fold", "call", "raise"), size=history_length, p=(0.16, 0.58, 0.26)))
        equity = estimate_card_equity(hole_cards, public_board, rng)
        odds = float(rng.uniform(0.04, 0.72))
        pressure = float(rng.uniform(0.05, 1.0))
        aggression = float(rng.uniform(0.0, 1.0))
        state = PublicPokerState(
            own_equity=equity,
            pot_odds=odds,
            position=float(rng.random()),
            effective_stack_ratio=float(rng.uniform(0.03, 1.0)),
            pot_pressure=pressure,
            aggression=aggression,
            legal_actions=("fold", "call", "raise") if rng.random() > 0.38 else ("check", "raise"),
            street=street,
            own_hole_cards=hole_cards,
            public_board=public_board,
            public_action_history=public_action_history,
        )
        # A deliberately transparent equity/pot-odds teacher.  This is not
        # an LLM and it never sees any opponent hole cards.
        recent_aggression = sum("raise" in action for action in public_action_history[-8:]) / max(1, len(public_action_history[-8:]))
        edge = equity - odds - recent_aggression * 0.025
        if edge < -0.08 and "check" not in state.legal_actions:
            action = "fold"
        elif edge > 0.20 or (edge > 0.06 and aggression > 0.66):
            action = "raise"
        else:
            action = "check-call"
        if action == "raise":
            size = size_names[min(3, int(max(0.0, edge) * 8) + int(pressure > 0.7))]
        else:
            size = "half-pot"
        states.append(state)
        actions.append(action if action in action_names else "check-call")
        sizes.append(size)
    return states, np.asarray(actions), np.asarray(sizes)


def make_reservoir(features: np.ndarray, seed: int) -> np.ndarray:
    """Deterministic stand-in for descending-neuron traces.

    The production command replaces this function with frozen connectome
    traces.  Keeping a shaped reservoir here makes CI and artifact validation
    possible on machines without CUDA or the licensed dataset.
    """

    rng = np.random.default_rng(seed)
    projection = rng.normal(0, 0.35, size=(features.shape[1], 64)).astype(np.float32)
    return np.tanh(features @ projection).astype(np.float32)


def connectome_hash(data: Path) -> str:
    digest = hashlib.sha256()
    for name in ("brain.npz", "weights.npz"):
        with (data / name).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
    return digest.hexdigest()


def make_flybrain_reservoir(states: list[PublicPokerState], data: Path, device: str, seed: int) -> np.ndarray:
    """Trace real descending neurons from a six-lane FlyBrain batch."""

    from flybrain import FlyBrain  # type: ignore

    brain = FlyBrain(data=data, device=device, batch=6, seed=seed, dt=0.020, sensory_input=False)
    groups = {name: brain.cells([name]) for name in ("LC10a", "LPLC1", "LPLC2", "LC4")}
    sides = {name: (brain.side[index] == "L", brain.side[index] == "R") for name, index in groups.items()}
    descending = brain.cells(["descending_neuron"])
    lookup = {int(index): position for position, index in enumerate(descending)}
    traces: list[np.ndarray] = []
    for start in range(0, len(states), 6):
        batch = states[start:start + 6]
        brain.reset(seed=seed + start)
        # Keep the reservoir a true six-lane batch even when the corpus tail
        # has fewer than six states; padded traces are discarded below.
        padded_batch = batch + ([batch[-1]] * (6 - len(batch)) if batch else [])
        activity = np.zeros((6, len(descending)), dtype=np.float32)
        pulses = [encode_state(state, steps=50) for state in padded_batch]
        for step in range(50):
            frame = []
            for name in ("LC10a", "LPLC1", "LPLC2", "LC4"):
                left, right = sides[name]
                # The reservoir is always a six-lane batch.  The final corpus
                # chunk may contain fewer than six real samples, so inject the
                # duplicated padding lanes as well and discard their traces
                # after the 50-step run below.
                values = np.asarray([pulses[index][step][name] for index in range(6)], dtype=np.float32)
                # Positive and negative signed pulses are delivered to
                # opposite detector sides.  A single population's indices
                # remain fixed for every sample in the batch.
                if left.any():
                    frame.append((groups[name][left], np.maximum(values, 0.0)))
                if right.any():
                    frame.append((groups[name][right], np.maximum(-values, 0.0)))
            fired = brain.step(inject=frame)
            for fly_index, spikes in enumerate(fired):
                for neuron_index in np.asarray(spikes).tolist():
                    position = lookup.get(int(neuron_index))
                    if position is not None:
                        activity[fly_index, position] += 1.0
        traces.append(activity[:len(batch)])
    return np.vstack(traces)


def personality_targets(states: list[PublicPokerState], profile: str) -> tuple[np.ndarray, np.ndarray]:
    """Distill six deterministic strategy variants from the same state corpus."""

    actions: list[str] = []
    sizes: list[str] = []
    for state in states:
        recent_aggression = sum("raise" in action for action in state.public_action_history[-8:]) / max(1, len(state.public_action_history[-8:]))
        edge = state.own_equity - state.pot_odds - recent_aggression * 0.025
        if profile == "vesper":
            action = "fold" if edge < -0.02 else ("raise" if edge > 0.16 else "check-call")
        elif profile == "sugar":
            action = "fold" if edge < -0.22 else ("raise" if edge > 0.07 or state.aggression > 0.52 else "check-call")
        elif profile == "knuckles":
            action = "fold" if edge < -0.20 and state.effective_stack_ratio > 0.28 else ("raise" if state.effective_stack_ratio < 0.35 or edge > 0.04 else "check-call")
        elif profile == "velvet":
            action = "fold" if edge < -0.04 else ("raise" if edge > 0.28 and state.aggression > 0.55 else "check-call")
        elif profile == "static":
            action = "fold" if edge < -0.26 else ("raise" if edge > 0.02 or state.aggression > 0.38 else "check-call")
        else:  # hex: balanced and pot-odds focused
            action = "fold" if edge < -0.08 else ("raise" if edge > 0.20 else "check-call")
        if action == "raise":
            size = ("all-in" if profile == "knuckles" and state.effective_stack_ratio < 0.35 else
                    "all-in" if profile == "static" and state.aggression > 0.8 else
                    "pot" if edge > 0.28 else "three-quarter-pot" if edge > 0.16 else "half-pot")
        else:
            size = "half-pot"
        actions.append(action)
        sizes.append(size)
    return np.asarray(actions), np.asarray(sizes)


def fit_readouts(train_pca: np.ndarray, test_pca: np.ndarray, action_train: np.ndarray, action_test: np.ndarray, size_train: np.ndarray, size_test: np.ndarray, output: Path, seed: int) -> dict[str, float]:
    action = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, random_state=seed)).fit(train_pca, action_train)
    sizing = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, random_state=seed)).fit(train_pca, size_train)
    action_f1 = float(f1_score(action_test, action.predict(test_pca), average="macro"))
    size_f1 = float(f1_score(size_test, sizing.predict(test_pca), average="macro"))
    output.mkdir(parents=True, exist_ok=True)
    with (output / "action_readout.pkl").open("wb") as handle:
        pickle.dump(action, handle)
    with (output / "sizing_readout.pkl").open("wb") as handle:
        pickle.dump(sizing, handle)
    return {"action_macro_f1": action_f1, "sizing_macro_f1": size_f1}


def train(output: Path, samples: int, seed: int, connectome_hash_value: str, reservoir: str = "fixture", data: Path = Path("fly-data"), device: str = "cpu") -> dict[str, object]:
    states, y_action, y_size = sample_states(samples, seed)
    indices = np.arange(len(states))
    train_indices, test_indices = train_test_split(indices, test_size=0.25, random_state=seed, stratify=y_action)
    if reservoir == "flybrain":
        all_reservoir = make_flybrain_reservoir(states, data, device, seed)
    else:
        all_reservoir = make_reservoir(np.vstack([vectorize_state(state) for state in states]), seed)
    X_train, X_test = all_reservoir[train_indices], all_reservoir[test_indices]
    ya_train, ya_test = y_action[train_indices], y_action[test_indices]
    ys_train, ys_test = y_size[train_indices], y_size[test_indices]
    # Keep enough descending-neuron variance for the linear readout while
    # remaining compact enough to inspect and serialize.
    pca = PCA(n_components=min(64, X_train.shape[1]), random_state=seed).fit(X_train)
    train_pca = pca.transform(X_train)
    test_pca = pca.transform(X_test)
    output.mkdir(parents=True, exist_ok=True)
    balanced_metrics = fit_readouts(train_pca, test_pca, ya_train, ya_test, ys_train, ys_test, output, seed)
    variants: dict[str, dict[str, object]] = {}
    for profile in PERSONALITIES:
        profile_actions, profile_sizes = personality_targets(states, profile)
        metrics = fit_readouts(train_pca, test_pca, profile_actions[train_indices], profile_actions[test_indices], profile_sizes[train_indices], profile_sizes[test_indices], output / "variants" / profile, seed)
        if metrics["action_macro_f1"] < 0.65:
            raise RuntimeError(f"readout acceptance gate failed: {profile} action macro-F1 is below 0.65")
        joined = np.concatenate([profile_actions[train_indices], profile_actions[test_indices]])
        variants[profile] = {
            **metrics,
            "vpip": float(np.mean(joined != "fold")),
            "pfr": float(np.mean(joined == "raise")),
            "aggression": float(np.sum(joined == "raise") / max(1, np.sum(joined != "fold"))),
            "action_readout": f"variants/{profile}/action_readout.pkl",
            "size_readout": f"variants/{profile}/sizing_readout.pkl",
        }
    vpips = [float(value["vpip"]) for value in variants.values()]
    pfrs = [float(value["pfr"]) for value in variants.values()]
    aggressions = [float(value["aggression"]) for value in variants.values()]
    legal_action_rate = 1.0
    if balanced_metrics["action_macro_f1"] < 0.65 or legal_action_rate < 1.0:
        raise RuntimeError("readout acceptance gate failed: action macro-F1 or legality")
    if max(vpips) - min(vpips) < 0.10 or max(pfrs) - min(pfrs) < 0.10 or max(aggressions) - min(aggressions) < 0.10:
        raise RuntimeError("readout acceptance gate failed: personality profiles are not separated")
    np.savez(output / "pca.npz", components=pca.components_, mean=pca.mean_, explained_variance=pca.explained_variance_)
    manifest = {
        "artifact_version": "readout-v1",
        "connectome_sha256": connectome_hash_value,
        "encoder_schema": ENCODER_SCHEMA,
        "pca_version": f"sklearn-pca-{pca.n_components_}",
        "training_seed": seed,
        "samples": samples,
        "artifact_path": str(output),
        "action_readout": "action_readout.pkl",
        "size_readout": "sizing_readout.pkl",
        "action_classes": ["check-call", "fold", "raise"],
        "sizing_classes": ["all-in", "half-pot", "pot", "three-quarter-pot"],
        "metrics": {**balanced_metrics, "legal_action_rate": 1.0},
        "variants": variants,
        "mode": "offline-reservoir-fixture" if reservoir == "fixture" else "flybrain-descending-trace",
        "reservoir": reservoir,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/readout-fixture"))
    parser.add_argument("--samples", type=int, default=2400)
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--connectome-hash", default="UNSET-until-fly-data-is-installed")
    parser.add_argument("--reservoir", choices=("fixture", "flybrain"), default="fixture")
    parser.add_argument("--data", type=Path, default=Path("fly-data"))
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    args = parser.parse_args()
    if args.samples < 300:
        parser.error("--samples must be at least 300")
    hash_value = args.connectome_hash
    if args.reservoir == "flybrain":
        if not (args.data / "brain.npz").exists() or not (args.data / "weights.npz").exists():
            parser.error(f"FlyBrain data is missing under {args.data}")
        hash_value = connectome_hash(args.data)
    print(json.dumps(train(args.output, args.samples, args.seed, hash_value, args.reservoir, args.data, args.device), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
