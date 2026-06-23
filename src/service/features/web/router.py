from fastapi import APIRouter, Depends, HTTPException
from typing import Any, Dict, Literal, cast
from pydantic import BaseModel

from detectmatelibrary.utils.persistency import PersistencyLoadError

router = APIRouter(prefix="/admin")


class ReconfigPayload(BaseModel):
    config: Dict[str, Any]
    persist: bool = False


def get_service() -> Any:
    # This gets overridden by the server setup in server.py
    raise NotImplementedError


@router.post("/start")  # type: ignore[misc]
async def admin_start(service: Any = Depends(get_service)) -> Dict[str, Any]:
    return {"message": service.start()}


@router.post("/stop")  # type: ignore[misc]
async def admin_stop(service: Any = Depends(get_service)) -> Dict[str, Any]:
    return {"message": service.stop()}


@router.get("/status")  # type: ignore[misc]
async def admin_status(service: Any = Depends(get_service)) -> Any:
    return service._create_status_report(getattr(service, "_running", False))


@router.post("/reconfigure")  # type: ignore[misc]
async def admin_reconfigure(payload: ReconfigPayload, service: Any = Depends(get_service)) -> Dict[str, Any]:
    # format the string to match what internal reconfigure() expects
    result = service.reconfigure(
        config_data=payload.config,
        persist=payload.persist
    )
    return {"message": result}


@router.post("/shutdown")  # type: ignore[misc]
async def admin_shutdown(service: Any = Depends(get_service)) -> Dict[str, Any]:
    # Kills the entire process
    return {"message": service.shutdown()}


class TrainingStatePayload(BaseModel):
    state: Literal[
        "keep_training", "stop_training", "keep_configuring", "stop_configuring"
    ]


def _get_component(service: Any) -> Any:
    """Return the library component, or raise HTTPException 404."""
    component = getattr(service, "library_component", None)
    if component is None:
        raise HTTPException(status_code=404, detail="No library component loaded")
    return component


def _get_saver(service: Any) -> Any:
    """Return the PersistencySaver from the service's library component.

    Raises HTTPException 404 if the component is missing or persistency
    is not configured.
    """
    component = _get_component(service)
    saver = getattr(component, "saver", None)
    if saver is None:
        raise HTTPException(status_code=404, detail="Persistency not configured for this component")
    return saver


@router.post("/persistency/save")  # type: ignore[misc]
async def admin_persistency_save(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Force an immediate flush of in-memory state to storage."""
    saver = _get_saver(service)
    saver.save()
    return {"message": "state saved"}


@router.post("/persistency/load")  # type: ignore[misc]
async def admin_persistency_load(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Restore state from storage, replacing current in-memory state."""
    if getattr(service, "_running", False):
        raise HTTPException(
            status_code=409,
            detail="Stop the engine before loading state (/admin/stop)",
        )
    saver = _get_saver(service)
    try:
        saver.load()
    except PersistencyLoadError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "state loaded"}


@router.get("/persistency/status")  # type: ignore[misc]
async def admin_persistency_status(service: Any = Depends(get_service)) -> Dict[str, Any]:
    return cast(Dict[str, Any], _get_saver(service).get_status())


@router.post("/training/state")  # type: ignore[misc]
async def admin_training_set_state(
    payload: TrainingStatePayload, service: Any = Depends(get_service)
) -> Dict[str, Any]:
    """Override the fit logic training/configuration state on the library
    component."""
    component = _get_component(service)
    component.update_state(payload.state)
    return {"message": f"state updated to: {payload.state}"}


@router.get("/training/state")  # type: ignore[misc]
async def admin_training_get_state(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Return the fit logic state from the last processed message."""
    component = _get_component(service)
    return {"state": component.get_state()}
