"""Dedicated, bounded process boundary for the optional GPU brain runner."""

from __future__ import annotations

import multiprocessing as mp
import queue
import traceback
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BrainWorkerConfig:
    artifact_dir: str = "artifacts/readout-male-cns-gpu"
    data_dir: str = "fly-data"
    device: str = "cuda"
    variant: str = "profiles"
    seed: int = 20260921
    queue_size: int = 64


def _run_worker(requests: Any, responses: Any, config: BrainWorkerConfig) -> None:
    from .brain_adapter import FlyBrainBatchAdapter

    adapter = FlyBrainBatchAdapter(config.artifact_dir, device=config.device, data_dir=config.data_dir, variant=config.variant, seed=config.seed)
    try:
        adapter.load()
        responses.put({"type": "system.status", "status": "ready", "mode": "flybrain"})
    except Exception as exc:  # fail closed; the API can stay in simulator mode
        responses.put({"type": "system.status", "status": "unavailable", "error": type(exc).__name__})
        return
    while True:
        request = requests.get()
        if request is None:
            return
        request_id, kind, payload = request
        try:
            result = adapter.step_features(payload) if kind == "features" else adapter.step(payload)
            responses.put({"requestId": request_id, "result": result})
        except Exception as exc:
            responses.put({"requestId": request_id, "error": f"{type(exc).__name__}: {exc}", "trace": traceback.format_exc(limit=3)})


class BrainWorkerProcess:
    """Six-brain process with bounded IPC queues and non-blocking submit."""

    def __init__(self, config: BrainWorkerConfig | None = None) -> None:
        self.config = config or BrainWorkerConfig()
        context = mp.get_context("spawn")
        self.requests = context.Queue(maxsize=self.config.queue_size)
        self.responses = context.Queue(maxsize=self.config.queue_size)
        self.process: mp.Process | None = None

    @property
    def alive(self) -> bool:
        return bool(self.process and self.process.is_alive())

    def start(self) -> None:
        if self.alive:
            return
        self.process = mp.get_context("spawn").Process(target=_run_worker, args=(self.requests, self.responses, self.config), daemon=True)
        self.process.start()

    def stop(self) -> None:
        if not self.process:
            return
        try:
            self.requests.put_nowait(None)
        except queue.Full:
            self.process.terminate()
        self.process.join(timeout=3)
        if self.process.is_alive():
            self.process.terminate()

    def submit(self, request_id: str, encoded_inputs: Any) -> bool:
        try:
            self.requests.put_nowait((request_id, "encoded", encoded_inputs))
            return True
        except queue.Full:
            return False

    def poll(self) -> dict[str, Any] | None:
        try:
            return self.responses.get_nowait()
        except queue.Empty:
            return None

    def submit_features(self, request_id: str, feature_sequences: Any) -> bool:
        try:
            self.requests.put_nowait((request_id, "features", feature_sequences))
            return True
        except queue.Full:
            return False

    def wait_ready(self, timeout: float = 30.0) -> bool:
        """Wait for the worker's one-time load status without blocking clients."""
        if not self.process:
            return False
        try:
            status = self.responses.get(timeout=timeout)
        except queue.Empty:
            return False
        return status.get("type") == "system.status" and status.get("status") == "ready"
