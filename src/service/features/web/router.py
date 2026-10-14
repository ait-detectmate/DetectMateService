import io
import zipfile
from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse
from typing import Any, Dict, List, Literal, cast
from pydantic import BaseModel

from detectmatelibrary.utils.persistency import PersistencyLoadError
from service.features.engine import EngineState
from service.features.web.auth import require_api_key, get_service

router = APIRouter(prefix="/admin", dependencies=[Depends(require_api_key)])


class ReconfigPayload(BaseModel):
    config: Dict[str, Any]
    persist: bool = False


@router.post("/start")  # type: ignore[misc]
async def admin_start(service: Any = Depends(get_service)) -> Dict[str, Any]:
    result = service.start()
    if result.startswith("error:"):
        raise HTTPException(status_code=500, detail=result)
    return {"message": result}


@router.post("/stop")  # type: ignore[misc]
async def admin_stop(service: Any = Depends(get_service)) -> Dict[str, Any]:
    result = service.stop()
    if result.startswith("error:"):
        raise HTTPException(status_code=500, detail=result)
    return {"message": result}


@router.get("/status")  # type: ignore[misc]
async def admin_status(service: Any = Depends(get_service)) -> Any:
    return service._create_status_report(getattr(service, "_state", None) == EngineState.RUNNING)


@router.post("/reconfigure")  # type: ignore[misc]
async def admin_reconfigure(payload: ReconfigPayload, service: Any = Depends(get_service)) -> Dict[str, Any]:
    # format the string to match what internal reconfigure() expects
    result = service.reconfigure(
        config_data=payload.config,
        persist=payload.persist
    )
    if result.startswith("reconfigure: error"):
        raise HTTPException(status_code=400, detail=result)
    if result == "reconfigure: no config manager configured":
        raise HTTPException(status_code=409, detail=result)
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


def _require_persistency(component: Any) -> None:
    """Raise HTTPException 404 if the component has no persistency
    configured."""
    if getattr(component, "persistency", None) is None:
        raise HTTPException(status_code=404, detail="Persistency not configured for this component")


def _require_stopped(service: Any, action: str) -> None:
    """Raise HTTPException 409 if the engine is running or stopping."""
    if getattr(service, "_state", None) in (EngineState.RUNNING, EngineState.STOPPING):
        raise HTTPException(
            status_code=409,
            detail=f"Stop the engine before {action} (/admin/stop)",
        )


@router.post("/persistency/save")  # type: ignore[misc]
async def admin_persistency_save(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Force an immediate flush of in-memory state to storage."""
    saver = _get_saver(service)
    saver.save()
    return {"message": "state saved"}


@router.post("/persistency/load")  # type: ignore[misc]
async def admin_persistency_load(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """Restore state from storage, replacing current in-memory state."""
    _require_stopped(service, "loading state")
    saver = _get_saver(service)
    try:
        saver.load()
    except PersistencyLoadError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"message": "state loaded"}


@router.get("/persistency/status")  # type: ignore[misc]
async def admin_persistency_status(service: Any = Depends(get_service)) -> Dict[str, Any]:
    return cast(Dict[str, Any], _get_saver(service).get_status())


@router.get("/persistency/export")  # type: ignore[misc]
async def admin_persistency_export(service: Any = Depends(get_service)) -> StreamingResponse:
    """Stream the current learned state as a zip archive."""
    component = _get_component(service)
    _require_persistency(component)
    data = component.export_state()
    if data is None:
        raise HTTPException(status_code=404, detail="Persistency not configured for this component")
    name = getattr(component, "name", "state")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}_state.zip"'},
    )


@router.post("/persistency/import")  # type: ignore[misc]
async def admin_persistency_import(
    service: Any = Depends(get_service),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Restore learned state from an uploaded zip archive."""
    component = _get_component(service)
    _require_persistency(component)
    _require_stopped(service, "importing state")
    data = await file.read()
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise HTTPException(status_code=422, detail="Uploaded file is not a valid zip archive")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        if not any(name.lstrip("/") == "metadata.json" for name in zf.namelist()):
            raise HTTPException(status_code=422, detail="Invalid state archive: metadata.json not found")
    try:
        component.import_state(data)
    except PersistencyLoadError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"message": "state imported"}


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


# ---------- federation (stack-later) ----------

def _fed_enabled(component: Any) -> bool:
    return getattr(getattr(component, "config", None), "allow_fed", False) is True


def _get_fed_component(service: Any, action: str) -> Any:
    """Return the library component if it can take part in federation right
    now.

    Raises 404 if there is no component, 409 if federation is disabled
    or finalized, or the engine is running.
    """
    component = _get_component(service)
    if not _fed_enabled(component):
        raise HTTPException(
            status_code=409,
            detail="Federation is not enabled for this component (set allow_fed: true in its config)",
        )
    if service.federation.finalized:
        raise HTTPException(status_code=409, detail="Federation has been finalized for this component")
    _require_stopped(service, action)
    return component


def _binary_response(data: bytes | None, filename: str) -> Response:
    return Response(
        content=data or b"",
        media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _read_binaries(files: List[UploadFile]) -> List[bytes]:
    binaries = [await f.read() for f in files]
    if not all(binaries):
        raise HTTPException(status_code=422, detail="Uploaded federation binary is empty")
    return binaries


@router.get("/federation/status")  # type: ignore[misc]
async def admin_federation_status(service: Any = Depends(get_service)) -> Dict[str, Any]:
    component = _get_component(service)
    return {"enabled": _fed_enabled(component), **asdict(service.federation)}


@router.get("/federation/export")  # type: ignore[misc]
async def admin_federation_export(service: Any = Depends(get_service)) -> Response:
    """Return this component's federation binary for a hub to stack."""
    component = _get_fed_component(service, "exporting federation state")
    data = component.to_binary()
    if not data:
        raise HTTPException(status_code=409, detail="This component does not support federation export")
    return _binary_response(data, f"{component.name}_federation.bin")


@router.post("/federation/stack")  # type: ignore[misc]
async def admin_federation_stack(
    service: Any = Depends(get_service),
    files: List[UploadFile] = File(...),
) -> Dict[str, Any]:
    """Stack one or more peer federation binaries for the next aggregate."""
    component = _get_fed_component(service, "stacking peer state")
    binaries = await _read_binaries(files)
    try:
        component.stack(binaries)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid federation binary: {e}")
    service.federation.stacked_peers += len(binaries)
    return {"message": f"stacked {len(binaries)} peer(s)", "stacked_peers": service.federation.stacked_peers}


@router.post("/federation/aggregate")  # type: ignore[misc]
async def admin_federation_aggregate(unstack: bool = True, service: Any = Depends(get_service)) -> Response:
    """Merge the stacked peers into this component and return the global
    binary."""
    component = _get_fed_component(service, "aggregating")
    state = service.federation
    if state.stacked_peers == 0:
        raise HTTPException(status_code=409, detail="No peer state stacked (/admin/federation/stack)")
    data = component.aggregate(unstack=unstack)
    state.rounds_aggregated += 1
    state.last_aggregated_at = datetime.now(timezone.utc).isoformat()
    if unstack:
        state.stacked_peers = 0
    return _binary_response(data, f"{component.name}_global.bin")


@router.post("/federation/adopt")  # type: ignore[misc]
async def admin_federation_adopt(
    service: Any = Depends(get_service),
    file: UploadFile = File(...),
) -> Dict[str, Any]:
    """Replace this component's state with a global binary from the hub."""
    component = _get_fed_component(service, "adopting federation state")
    if not hasattr(component, "load_binary"):
        raise HTTPException(
            status_code=501,
            detail="The installed DetectMateLibrary has no load_binary(); "
                   "import the hub's /admin/persistency/export archive instead",
        )
    (data,) = await _read_binaries([file])
    try:
        component.load_binary(data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid federation binary: {e}")
    return {"message": "federation state adopted"}


@router.post("/federation/finalize")  # type: ignore[misc]
async def admin_federation_finalize(service: Any = Depends(get_service)) -> Dict[str, Any]:
    """End federation for this component and remove its federation files.

    This cannot be undone: export, stack and aggregate are rejected
    afterwards.
    """
    component = _get_fed_component(service, "finalizing federation")
    component.finalize_federation()
    service.federation.finalized = True
    service.federation.stacked_peers = 0
    return {"message": "federation finalized"}
