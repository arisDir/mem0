import logging
from typing import Any, Dict, List, Optional

import server_state
from auth import require_admin, verify_auth
from errors import upstream_error
from fastapi import APIRouter, Body, Depends, HTTPException, Path
from pydantic import BaseModel

from .filters import platform_filters_to_oss
from .links import ping_payload, wrap_results

logger = logging.getLogger("memplatform.routes")

router = APIRouter(tags=["platform-compat"])


def _client_error(message: str) -> HTTPException:
    return HTTPException(status_code=400, detail=message)


def _unsupported(surface: str) -> HTTPException:
    return HTTPException(
        status_code=501,
        detail=f"The '{surface}' endpoint is not available on the self-hosted OSS server.",
    )


class Message(BaseModel):
    role: str
    content: str


class MemoryAddRequest(BaseModel):
    messages: List[Message]
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    expiration_date: Optional[str] = None
    infer: Optional[bool] = None
    memory_type: Optional[str] = None
    prompt: Optional[str] = None

    model_config = {"extra": "allow"}


class MemorySearchRequest(BaseModel):
    query: str
    filters: Optional[Dict[str, Any]] = None
    top_k: Optional[int] = None
    limit: Optional[int] = None
    threshold: Optional[float] = None
    rerank: Optional[bool] = None
    reranker: Optional[Dict[str, Any]] = None

    model_config = {"extra": "allow"}


class MemoryListRequest(BaseModel):
    filters: Optional[Dict[str, Any]] = None
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None
    top_k: Optional[int] = None
    show_expired: Optional[bool] = None

    model_config = {"extra": "allow"}


class MemoryUpdateRequest(BaseModel):
    text: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    expiration_date: Optional[str] = None

    model_config = {"extra": "allow"}


class MemoryDeleteAllRequest(BaseModel):
    user_id: Optional[str] = None
    agent_id: Optional[str] = None
    run_id: Optional[str] = None

    model_config = {"extra": "allow"}


@router.get("/v1/ping/", summary="Platform ping (compat)")
def ping(_auth=Depends(verify_auth)):
    try:
        return ping_payload(_auth)
    except Exception as e:
        raise upstream_error(e)


@router.post("/v3/memories/add/", summary="Add memory (platform compat)")
def add_memory(req: MemoryAddRequest, _auth=Depends(verify_auth)):
    try:
        params = req.model_dump(exclude_unset=True)
        return server_state.get_memory_instance().add(**params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.post("/v3/memories/search/", summary="Search memories (platform compat)")
def search_memories(req: MemorySearchRequest, _auth=Depends(verify_auth)):
    try:
        filters = platform_filters_to_oss(req.filters)
        params = req.model_dump(exclude_unset=True)
        params["filters"] = filters
        return server_state.get_memory_instance().search(query=params.pop("query"), **params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.post("/v3/memories/", summary="List memories (platform compat)")
def list_memories(req: MemoryListRequest = Body(default_factory=MemoryListRequest), _auth=Depends(verify_auth)):
    try:
        filters = platform_filters_to_oss(req.filters)
        params = req.model_dump(exclude_unset=True)
        params["filters"] = filters
        results = server_state.get_memory_instance().get_all(**params)
        if isinstance(results, dict) and "results" in results:
            return wrap_results(results["results"])
        if isinstance(results, list):
            return wrap_results(results)
        try:
            return wrap_results(list(results))
        except Exception:
            return results
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.get("/v1/memories/{memory_id}/", summary="Get memory (platform compat)")
def get_memory(memory_id: str = Path(...), _auth=Depends(verify_auth)):
    try:
        return server_state.get_memory_instance().get(memory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.put("/v1/memories/{memory_id}/", summary="Update memory (platform compat)")
def update_memory(memory_id: str = Path(...), req: MemoryUpdateRequest = Body(...), _auth=Depends(verify_auth)):
    try:
        params = req.model_dump(exclude_unset=True)
        params["memory_id"] = memory_id
        return server_state.get_memory_instance().update(**params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.delete("/v1/memories/{memory_id}/", summary="Delete memory (platform compat)")
def delete_memory(memory_id: str = Path(...), _auth=Depends(verify_auth)):
    try:
        return server_state.get_memory_instance().delete(memory_id=memory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.delete("/v1/memories/", summary="Delete all memories (platform compat)")
def delete_all_memories(req: MemoryDeleteAllRequest = Body(default_factory=MemoryDeleteAllRequest), _auth=Depends(require_admin)):
    try:
        params = req.model_dump(exclude_unset=True)
        return server_state.get_memory_instance().delete_all(**params)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.get("/v1/memories/{memory_id}/history/", summary="Get memory history (platform compat)")
def get_memory_history(memory_id: str = Path(...), _auth=Depends(verify_auth)):
    try:
        return server_state.get_memory_instance().history(memory_id=memory_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


@router.get("/v1/entities/", summary="List entities (platform compat)")
def list_entities(_auth=Depends(verify_auth)):
    try:
        results = server_state.get_memory_instance().get_all()
    except Exception as e:
        raise upstream_error(e)
    if isinstance(results, dict) and "results" in results:
        return wrap_results(results["results"])
    if isinstance(results, list):
        return wrap_results(results)
    try:
        return wrap_results(list(results))
    except Exception:
        return wrap_results([])


@router.delete("/v2/entities/{entity_type}/{entity_id}/", summary="Delete entity (platform compat)")
def delete_entity(entity_type: str, entity_id: str, _auth=Depends(verify_auth)):
    try:
        if entity_type == "user":
            return server_state.get_memory_instance().delete_all(user_id=entity_id)
        if entity_type == "agent":
            return server_state.get_memory_instance().delete_all(agent_id=entity_id)
        if entity_type == "run":
            return server_state.get_memory_instance().delete_all(run_id=entity_id)
        raise HTTPException(status_code=400, detail=f"Unsupported entity type: {entity_type}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_error(e)


AnyBody = Optional[Dict[str, Any]]


@router.post("/v1/summary/", summary="Summary (platform compat)")
def summary_post_unsupported(req: AnyBody = Body(default=None)):
    raise _unsupported("summary")


@router.get("/v1/summary/", summary="Summary (platform compat)")
def summary_get_unsupported():
    raise _unsupported("summary")


@router.post("/v1/exports/", summary="Exports (platform compat)")
def exports_post_unsupported(req: AnyBody = Body(default=None)):
    raise _unsupported("exports")


@router.post("/v1/exports/get/", summary="Exports get (platform compat)")
def exports_get_unsupported(req: AnyBody = Body(default=None)):
    raise _unsupported("exports")


@router.post("/v1/feedback/", summary="Feedback (platform compat)")
def feedback_unsupported(req: AnyBody = Body(default=None)):
    raise _unsupported("feedback")


@router.get("/v2/entities/user/{id}/profile/", summary="Profile (platform compat)")
def profile_unsupported(id: str = Path(...)):
    raise _unsupported("profile")


@router.post("/v1/batch/", summary="Batch (platform compat)")
def batch_post_unsupported(req: AnyBody = Body(default=None)):
    raise _unsupported("batch")


@router.put("/v1/batch/", summary="Batch update (platform compat)")
def batch_put_unsupported(req: AnyBody = Body(default=None)):
    raise _unsupported("batch")


@router.delete("/v1/batch/", summary="Batch delete (platform compat)")
def batch_delete_unsupported(req: AnyBody = Body(default=None)):
    raise _unsupported("batch")


@router.get("/v1/events/", summary="Events (platform compat)")
def events_unsupported_get():
    raise _unsupported("events")


@router.get("/v1/event/{event_id}/", summary="Event (platform compat)")
def event_unsupported_get(event_id: str = Path(...)):
    raise _unsupported("events")
