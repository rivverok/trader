"""RL Agent — ONNX-based inference for trading decisions.

Loads a trained RL model exported as ONNX and runs inference on
the assembled state vector. The model outputs discrete actions per stock.

Action space (per stock):
  0 = strong_sell  (close position or go to 0%)
  1 = sell         (reduce position by 50%)
  2 = hold         (no change)
  3 = buy          (add 2.5% portfolio weight)
  4 = strong_buy   (add 5% portfolio weight)
"""

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


class RLAgent:
    """ONNX-based RL agent for trading inference."""

    def __init__(self) -> None:
        self.session = None  # onnxruntime.InferenceSession
        self.model_info: dict | None = None
        self._input_name: str | None = None

    def load_model(self, onnx_path: str, state_spec: dict) -> None:
        """Load an ONNX model file for inference.

        Args:
            onnx_path: Path to the .onnx file on disk.
            state_spec: Expected input schema (feature names, dimensions).
        """
        path = Path(onnx_path)
        if not path.exists():
            raise FileNotFoundError(f"ONNX model not found: {onnx_path}")

        import onnxruntime as ort

        self.session = ort.InferenceSession(
            str(path),
            providers=["CPUExecutionProvider"],
        )
        self.model_info = state_spec
        self._input_name = self.session.get_inputs()[0].name
        logger.info("RL model loaded: %s (%s)", path.name, state_spec.get("algorithm", "unknown"))

    def unload_model(self) -> None:
        """Unload the current model."""
        self.session = None
        self.model_info = None
        self._input_name = None
        logger.info("RL model unloaded")

    def predict(self, state_vector: np.ndarray) -> np.ndarray:
        """Run inference on a state vector, return actions.

        Args:
            state_vector: 1-D or 2-D float32 array of assembled features.

        Returns:
            Array of discrete actions (one per stock in the universe).
        """
        if self.session is None:
            raise RuntimeError("No RL model loaded")

        # Ensure 2D: (1, features)
        if state_vector.ndim == 1:
            state_vector = state_vector.reshape(1, -1)

        state_vector = state_vector.astype(np.float32)
        outputs = self.session.run(None, {self._input_name: state_vector})
        return outputs[0]

    @property
    def is_loaded(self) -> bool:
        """Whether a model is currently loaded for inference."""
        return self.session is not None


# Singleton instance — shared across the application
rl_agent = RLAgent()
