"""API routes for RL model management — upload, list, activate, delete."""

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.rl_model import RLModel

router = APIRouter(prefix="/api/rl-models", tags=["rl-models"])

RL_MODEL_DIR = Path(os.getenv("RL_MODEL_DIR", "/data/rl_models"))


# ── Response schemas ─────────────────────────────────────────────────


class RLModelResponse(BaseModel):
    id: int
    name: str
    version: str
    algorithm: str
    onnx_path: str
    state_spec: dict | None
    action_spec: dict | None
    training_metadata: dict | None
    backtest_metrics: dict | None
    is_active: bool
    activated_at: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class RLModelListResponse(BaseModel):
    models: list[RLModelResponse]
    active_model_id: int | None


# ── Endpoints ────────────────────────────────────────────────────────


@router.get("", response_model=RLModelListResponse)
async def list_rl_models(db: AsyncSession = Depends(get_db)):
    """List all uploaded RL models."""
    result = await db.execute(
        select(RLModel).order_by(desc(RLModel.created_at))
    )
    models = result.scalars().all()

    active_id = None
    items = []
    for m in models:
        if m.is_active:
            active_id = m.id
        items.append(RLModelResponse(
            id=m.id,
            name=m.name,
            version=m.version,
            algorithm=m.algorithm,
            onnx_path=m.onnx_path,
            state_spec=m.state_spec,
            action_spec=m.action_spec,
            training_metadata=m.training_metadata,
            backtest_metrics=m.backtest_metrics,
            is_active=m.is_active,
            activated_at=m.activated_at.isoformat() if m.activated_at else None,
            created_at=m.created_at.isoformat(),
            updated_at=m.updated_at.isoformat(),
        ))
    return RLModelListResponse(models=items, active_model_id=active_id)


@router.post("/upload", response_model=RLModelResponse, status_code=201)
async def upload_rl_model(
    file: UploadFile = File(...),
    name: str = Form(...),
    version: str = Form(...),
    algorithm: str = Form("PPO"),
    state_spec: str = Form("{}"),
    action_spec: str = Form("{}"),
    training_metadata: str = Form("{}"),
    backtest_metrics: str = Form("{}"),
    db: AsyncSession = Depends(get_db),
):
    """Upload an ONNX model file with metadata."""
    if not file.filename or not file.filename.endswith(".onnx"):
        raise HTTPException(400, "File must be a .onnx file")

    # Validate file size (max 500MB)
    content = await file.read()
    if len(content) > 500 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 500MB)")

    import json
    try:
        state_spec_dict = json.loads(state_spec)
        action_spec_dict = json.loads(action_spec)
        training_meta_dict = json.loads(training_metadata)
        backtest_dict = json.loads(backtest_metrics)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON in metadata: {e}")

    # Save file to disk
    RL_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{name}_{version}.onnx".replace(" ", "_").replace("/", "_").replace("\\", "_")
    dest = RL_MODEL_DIR / safe_name

    with open(dest, "wb") as f:
        f.write(content)

    model = RLModel(
        name=name,
        version=version,
        algorithm=algorithm,
        onnx_path=str(dest),
        state_spec=state_spec_dict,
        action_spec=action_spec_dict,
        training_metadata=training_meta_dict,
        backtest_metrics=backtest_dict,
        is_active=False,
    )
    db.add(model)
    await db.commit()
    await db.refresh(model)

    return RLModelResponse(
        id=model.id,
        name=model.name,
        version=model.version,
        algorithm=model.algorithm,
        onnx_path=model.onnx_path,
        state_spec=model.state_spec,
        action_spec=model.action_spec,
        training_metadata=model.training_metadata,
        backtest_metrics=model.backtest_metrics,
        is_active=model.is_active,
        activated_at=None,
        created_at=model.created_at.isoformat(),
        updated_at=model.updated_at.isoformat(),
    )


@router.post("/{model_id}/activate", response_model=RLModelResponse)
async def activate_rl_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Set a model as the active RL model. Deactivates any previously active model."""
    result = await db.execute(select(RLModel).where(RLModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "Model not found")

    # Verify the ONNX file exists
    if not Path(model.onnx_path).exists():
        raise HTTPException(400, f"ONNX file missing: {model.onnx_path}")

    # Deactivate all models
    await db.execute(
        update(RLModel).values(is_active=False, activated_at=None)
    )

    # Activate this one
    now = datetime.now(timezone.utc)
    model.is_active = True
    model.activated_at = now

    # Load model into the RL agent singleton
    from app.engine.rl_agent import rl_agent
    rl_agent.load_model(model.onnx_path, model.state_spec or {})

    await db.commit()
    await db.refresh(model)

    return RLModelResponse(
        id=model.id,
        name=model.name,
        version=model.version,
        algorithm=model.algorithm,
        onnx_path=model.onnx_path,
        state_spec=model.state_spec,
        action_spec=model.action_spec,
        training_metadata=model.training_metadata,
        backtest_metrics=model.backtest_metrics,
        is_active=model.is_active,
        activated_at=model.activated_at.isoformat() if model.activated_at else None,
        created_at=model.created_at.isoformat(),
        updated_at=model.updated_at.isoformat(),
    )


@router.post("/{model_id}/deactivate")
async def deactivate_rl_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Deactivate a model and unload from the RL agent."""
    result = await db.execute(select(RLModel).where(RLModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "Model not found")

    model.is_active = False
    model.activated_at = None

    from app.engine.rl_agent import rl_agent
    rl_agent.unload_model()

    await db.commit()
    return {"status": "ok", "message": f"Model {model.name} v{model.version} deactivated"}


@router.get("/{model_id}", response_model=RLModelResponse)
async def get_rl_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Get model details."""
    result = await db.execute(select(RLModel).where(RLModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "Model not found")

    return RLModelResponse(
        id=model.id,
        name=model.name,
        version=model.version,
        algorithm=model.algorithm,
        onnx_path=model.onnx_path,
        state_spec=model.state_spec,
        action_spec=model.action_spec,
        training_metadata=model.training_metadata,
        backtest_metrics=model.backtest_metrics,
        is_active=model.is_active,
        activated_at=model.activated_at.isoformat() if model.activated_at else None,
        created_at=model.created_at.isoformat(),
        updated_at=model.updated_at.isoformat(),
    )


@router.delete("/{model_id}")
async def delete_rl_model(model_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a model and its ONNX file."""
    result = await db.execute(select(RLModel).where(RLModel.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(404, "Model not found")

    if model.is_active:
        raise HTTPException(400, "Cannot delete active model. Deactivate it first.")

    # Remove ONNX file from disk
    onnx_path = Path(model.onnx_path)
    if onnx_path.exists():
        onnx_path.unlink()

    await db.delete(model)
    await db.commit()
    return {"status": "ok", "message": f"Model {model.name} v{model.version} deleted"}
