"""Train an RL trading agent using stable-baselines3 and export to ONNX.

Usage:
    python train_rl_agent.py --data ./data/exported --output ./models
    python train_rl_agent.py --data ./data/exported --output ./models --algo SAC --timesteps 2000000

After training, upload the ONNX model to the server:
    POST /api/rl-models/upload  (multipart form with .onnx file + metadata)
"""

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import onnx
import torch
from stable_baselines3 import PPO, SAC, A2C
from stable_baselines3.common.callbacks import (
    BaseCallback,
    CheckpointCallback,
    EvalCallback,
)
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv

from rl_environment import TradingEnvironment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────
#  Algorithm registry
# ─────────────────────────────────────────────────────────────────────

ALGORITHMS = {
    "PPO": PPO,
    "SAC": SAC,
    "A2C": A2C,
}

DEFAULT_HYPERPARAMS = {
    "PPO": {
        "learning_rate": 3e-4,
        "n_steps": 2048,
        "batch_size": 64,
        "n_epochs": 10,
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_range": 0.2,
        "ent_coef": 0.01,
        "vf_coef": 0.5,
        "max_grad_norm": 0.5,
    },
    "A2C": {
        "learning_rate": 7e-4,
        "n_steps": 5,
        "gamma": 0.99,
        "gae_lambda": 1.0,
        "ent_coef": 0.01,
        "vf_coef": 0.25,
        "max_grad_norm": 0.5,
    },
    "SAC": {
        "learning_rate": 3e-4,
        "buffer_size": 1_000_000,
        "batch_size": 256,
        "gamma": 0.99,
        "tau": 0.005,
        "ent_coef": "auto",
    },
}


# ─────────────────────────────────────────────────────────────────────
#  Logging callback
# ─────────────────────────────────────────────────────────────────────


class TradingMetricsCallback(BaseCallback):
    """Log portfolio metrics during training."""

    def __init__(self, log_freq: int = 5000, verbose: int = 0):
        super().__init__(verbose)
        self.log_freq = log_freq
        self.episode_rewards: list[float] = []
        self.episode_lengths: list[int] = []

    def _on_step(self) -> bool:
        infos = self.locals.get("infos", [])
        for info in infos:
            if "episode" in info:
                self.episode_rewards.append(info["episode"]["r"])
                self.episode_lengths.append(info["episode"]["l"])

        if self.num_timesteps % self.log_freq == 0 and self.episode_rewards:
            recent = self.episode_rewards[-10:]
            avg_reward = np.mean(recent)
            logger.info(
                "Step %d | Avg reward (last 10 eps): %.4f | Episodes: %d",
                self.num_timesteps, avg_reward, len(self.episode_rewards),
            )

        return True


# ─────────────────────────────────────────────────────────────────────
#  ONNX export
# ─────────────────────────────────────────────────────────────────────


def export_to_onnx(model, obs_dim: int, output_path: str):
    """Export a trained SB3 model's policy network to ONNX format."""
    policy = model.policy
    policy.eval()

    # Create a dummy input matching the observation shape
    dummy_input = torch.randn(1, obs_dim, device=policy.device)

    # For PPO/A2C, extract the actor network
    if hasattr(policy, "action_net"):
        # Build a wrapper that goes through the full forward path
        class PolicyWrapper(torch.nn.Module):
            def __init__(self, sb3_policy):
                super().__init__()
                self.policy = sb3_policy

            def forward(self, obs):
                features = self.policy.extract_features(obs, self.policy.pi_features_extractor)
                latent_pi = self.policy.mlp_extractor.forward_actor(features)
                return self.policy.action_net(latent_pi)

        wrapper = PolicyWrapper(policy)
        wrapper.eval()
    else:
        # Fallback: use the full policy
        class FullPolicyWrapper(torch.nn.Module):
            def __init__(self, sb3_policy):
                super().__init__()
                self.policy = sb3_policy

            def forward(self, obs):
                return self.policy.forward(obs, deterministic=True)[0]

        wrapper = FullPolicyWrapper(policy)
        wrapper.eval()

    # Export
    torch.onnx.export(
        wrapper,
        dummy_input,
        output_path,
        input_names=["input"],
        output_names=["output"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "output": {0: "batch_size"},
        },
        opset_version=14,
    )

    # Validate
    onnx_model = onnx.load(output_path)
    onnx.checker.check_model(onnx_model)
    logger.info("ONNX model exported and validated: %s", output_path)


# ─────────────────────────────────────────────────────────────────────
#  Main training function
# ─────────────────────────────────────────────────────────────────────


def train(
    data_path: str,
    output_dir: str,
    algo_name: str = "PPO",
    total_timesteps: int = 1_000_000,
    reward_type: str = "risk_adjusted",
    seed: int = 42,
):
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # ── Create environment ───────────────────────────────────────────
    env_config = {
        "initial_capital": 100_000.0,
        "reward_type": reward_type,
        "max_position_pct": 0.20,
        "transaction_cost_bps": 5,
    }

    def make_env():
        env = TradingEnvironment(data_path=data_path, config=env_config)
        env = Monitor(env)
        return env

    train_env = DummyVecEnv([make_env])

    # Eval env for periodic evaluation
    eval_env = DummyVecEnv([make_env])

    # ── Load metadata for naming ─────────────────────────────────────
    with open(Path(data_path) / "metadata.json") as f:
        metadata = json.load(f)

    obs_dim = train_env.observation_space.shape[0]
    logger.info(
        "Training %s | obs_dim=%d | stocks=%d | dates=%d | timesteps=%d",
        algo_name, obs_dim, metadata["num_stocks"],
        metadata["num_snapshots"], total_timesteps,
    )

    # ── Configure algorithm ──────────────────────────────────────────
    algo_cls = ALGORITHMS.get(algo_name)
    if algo_cls is None:
        raise ValueError(f"Unknown algorithm: {algo_name}. Choose from: {list(ALGORITHMS)}")

    hyperparams = DEFAULT_HYPERPARAMS.get(algo_name, {})

    # Note: SAC requires continuous action space — skip if MultiDiscrete
    if algo_name == "SAC":
        logger.warning("SAC requires continuous actions — falling back to PPO for MultiDiscrete")
        algo_cls = PPO
        algo_name = "PPO"
        hyperparams = DEFAULT_HYPERPARAMS["PPO"]

    model = algo_cls(
        "MlpPolicy",
        train_env,
        verbose=1,
        seed=seed,
        tensorboard_log=str(output_path / "tb_logs"),
        **hyperparams,
    )

    # ── Callbacks ────────────────────────────────────────────────────
    checkpoint_cb = CheckpointCallback(
        save_freq=50_000,
        save_path=str(output_path / "checkpoints"),
        name_prefix=f"rl_{algo_name.lower()}",
    )

    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path=str(output_path / "best_model"),
        log_path=str(output_path / "eval_logs"),
        eval_freq=20_000,
        n_eval_episodes=3,
        deterministic=True,
    )

    metrics_cb = TradingMetricsCallback(log_freq=10_000)

    # ── Train ────────────────────────────────────────────────────────
    start_time = time.time()
    model.learn(
        total_timesteps=total_timesteps,
        callback=[checkpoint_cb, eval_cb, metrics_cb],
        progress_bar=True,
    )
    train_duration = time.time() - start_time

    logger.info("Training complete in %.1f seconds", train_duration)

    # ── Save SB3 model ───────────────────────────────────────────────
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    model_name = f"rl_trading_{algo_name.lower()}_v{timestamp}"
    sb3_path = str(output_path / f"{model_name}.zip")
    model.save(sb3_path)
    logger.info("SB3 model saved: %s", sb3_path)

    # ── Export to ONNX ───────────────────────────────────────────────
    onnx_path = str(output_path / f"{model_name}.onnx")
    export_to_onnx(model, obs_dim, onnx_path)

    # ── Save training metadata ───────────────────────────────────────
    train_meta = {
        "model_name": model_name,
        "algorithm": algo_name,
        "total_timesteps": total_timesteps,
        "reward_type": reward_type,
        "hyperparams": {k: str(v) for k, v in hyperparams.items()},
        "obs_dim": obs_dim,
        "num_stocks": metadata["num_stocks"],
        "stock_universe": metadata["stock_universe"],
        "data_date_range": metadata["date_range"],
        "training_duration_sec": round(train_duration, 1),
        "seed": seed,
        "sb3_path": sb3_path,
        "onnx_path": onnx_path,
        "trained_at": datetime.now(timezone.utc).isoformat(),
    }

    meta_path = output_path / f"{model_name}_meta.json"
    with open(meta_path, "w") as f:
        json.dump(train_meta, f, indent=2)
    logger.info("Training metadata saved: %s", meta_path)

    print(f"\n{'='*60}")
    print(f"  Training Complete")
    print(f"{'='*60}")
    print(f"  Algorithm:    {algo_name}")
    print(f"  Timesteps:    {total_timesteps:,}")
    print(f"  Duration:     {train_duration:.1f}s")
    print(f"  ONNX model:   {onnx_path}")
    print(f"  SB3 model:    {sb3_path}")
    print(f"  Metadata:     {meta_path}")
    print(f"\nNext steps:")
    print(f"  1. Upload ONNX model:  POST /api/rl-models/upload")
    print(f"  2. Activate model:     POST /api/rl-models/{{id}}/activate")
    print(f"  3. Switch to trading:  PUT /api/system/mode")
    print(f"{'='*60}\n")

    train_env.close()
    eval_env.close()


# ─────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Train RL trading agent")
    parser.add_argument(
        "--data", type=str, required=True,
        help="Path to exported Parquet data directory",
    )
    parser.add_argument(
        "--output", type=str, default="./models",
        help="Output directory for models and logs",
    )
    parser.add_argument(
        "--algo", type=str, default="PPO", choices=list(ALGORITHMS.keys()),
        help="RL algorithm to use",
    )
    parser.add_argument(
        "--timesteps", type=int, default=1_000_000,
        help="Total training timesteps",
    )
    parser.add_argument(
        "--reward", type=str, default="risk_adjusted",
        choices=["simple_return", "risk_adjusted", "log_return", "asymmetric"],
        help="Reward function type",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed")

    args = parser.parse_args()
    train(
        data_path=args.data,
        output_dir=args.output,
        algo_name=args.algo,
        total_timesteps=args.timesteps,
        reward_type=args.reward,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
