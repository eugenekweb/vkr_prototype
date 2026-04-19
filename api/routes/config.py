"""Роутер конфигурации."""
from __future__ import annotations

from algorithms.base import AlgorithmConfig
from algorithms.factory import PrioritizerFactory
from api.dependencies import get_queue_manager
from api.schemas.config import AlgorithmConfigRequest, AlgorithmConfigResponse
from core.queue_manager import QueueManager
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/config", tags=["config"])


@router.get("/algorithm", response_model=AlgorithmConfigResponse)
async def get_algorithm(qm: QueueManager = Depends(get_queue_manager)):
    """Возвращает текущие параметры алгоритма."""
    params = qm._params
    return AlgorithmConfigResponse(
        type=params.type,
        beta=params.beta,
        delta=params.delta,
        epsilon=params.epsilon,
        priority_weights=params.priority_weights,
    )


@router.put("/algorithm", response_model=AlgorithmConfigResponse)
async def set_algorithm(
    body: AlgorithmConfigRequest,
    qm: QueueManager = Depends(get_queue_manager),
):
    """Меняет алгоритм без перезапуска."""
    if body.type.upper() not in PrioritizerFactory.available_algorithms():
        raise HTTPException(
            status_code=422,
            detail=f"Неизвестный алгоритм: {body.type}. Доступны: {PrioritizerFactory.available_algorithms()}",
        )
    current = qm._params
    new_params = AlgorithmConfig(
        type=body.type.upper(),
        beta=body.beta if body.beta is not None else current.beta,
        delta=body.delta if body.delta is not None else current.delta,
        epsilon=body.epsilon if body.epsilon is not None else current.epsilon,
        priority_weights=body.priority_weights if body.priority_weights is not None else current.priority_weights,
    )
    qm.set_algorithm(body.type.upper(), new_params)
    return AlgorithmConfigResponse(
        type=new_params.type,
        beta=new_params.beta,
        delta=new_params.delta,
        epsilon=new_params.epsilon,
        priority_weights=new_params.priority_weights,
    )
