import logging
from typing import Any, Dict, List, Optional

import server_state
from auth import require_admin, verify_auth
from errors import upstream_error
from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from mem0.exceptions import ValidationError as Mem0ValidationError
from pydantic import BaseModel
from routers import entities as native_entities

from .filters import platform_filters_to_oss
from .links import ping_payload, wrap_results

logger = logging.getLogger("memplatform.routes")

router = APIRouter(tags=["platform-compat"])


def _call_oss(method_name: str, params: Dict[str, Any], allow: set):
    """Call an OSS Memory method, dropping params it does not accept.

    Platform clients send fields the hosted API accepts but OSS does not (e.g.
    `source`, `app_id`). Passing those through raises TypeError, so filter to the
    method's accepted parameters.
    """
    instance = server_state.get_memory_instance()
    method = getattr(instance, method_name)
    return method(**{k: v for k, v in params.items() if k in allow})


# Parameters each OSS Memory method accepts (platform-only fields excluded).
ADD_PARAMS = {
    "messages", "user_id", "agent_id", "run_id", "metadata", "timestamp",
    "expiration_date", "infer", "memory_type", "prompt",
}
SEARCH_PARAMS = {"query", "top_k", "filters", "threshold", "rerank", "explain", "reference_date", "show_expired"}
GET_ALL_PARAMS = {"filters", "top_k", "show_expired"}
UPDATE_PARAMS = {"memory_id", "text", "metadata", "expiration_date", "data"}

# Body type for the unsupported-endpoint stubs: accept (and ignore) any JSON.
AnyBody = Optional[Dict[str, Any]]


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
    except Exception:
        raise upstream_error()


@router.post("/v3/memories/add/", summary="Add memory (platform compat)")
def add_memory(req: MemoryAddRequest, _auth=Depends(verify_auth)):
    try:
        params = req.model_dump(exclude_unset=True)
        return _call_oss("add", params, allow=ADD_PARAMS)
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


@router.post("/v3/memories/search/", summary="Search memories (platform compat)")
def search_memories(req: MemorySearchRequest, _auth=Depends(verify_auth)):
    try:
        filters = platform_filters_to_oss(req.filters)
        params = req.model_dump(exclude_unset=True)
        params["filters"] = filters
        return _call_oss("search", params, allow=SEARCH_PARAMS)
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


@router.post("/v3/memories/", summary="List memories (platform compat)")
def list_memories(req: MemoryListRequest = Body(default_factory=MemoryListRequest), _auth=Depends(verify_auth)):
    try:
        filters = platform_filters_to_oss(req.filters)
        params = req.model_dump(exclude_unset=True)
        params["filters"] = filters
        results = _call_oss("get_all", params, allow=GET_ALL_PARAMS)
        if isinstance(results, dict) and "results" in results:
            return wrap_results(results["results"])
        if isinstance(results, list):
            return wrap_results(results)
        try:
            return wrap_results(list(results))
        except Exception:
            return results
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


@router.get("/v1/memories/{memory_id}/", summary="Get memory (platform compat)")
def get_memory(memory_id: str = Path(...), _auth=Depends(verify_auth)):
    try:
        return server_state.get_memory_instance().get(memory_id)
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


@router.put("/v1/memories/{memory_id}/", summary="Update memory (platform compat)")
def update_memory(memory_id: str = Path(...), req: MemoryUpdateRequest = Body(...), _auth=Depends(verify_auth)):
    try:
        params = req.model_dump(exclude_unset=True)
        params["memory_id"] = memory_id
        return _call_oss("update", params, allow=UPDATE_PARAMS)
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


@router.delete("/v1/memories/{memory_id}/", summary="Delete memory (platform compat)")
def delete_memory(memory_id: str = Path(...), _auth=Depends(verify_auth)):
    try:
        return server_state.get_memory_instance().delete(memory_id=memory_id)
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


@router.delete("/v1/memories/", summary="Delete all memories (platform compat)")
def delete_all_memories(
    req: MemoryDeleteAllRequest = Body(default_factory=MemoryDeleteAllRequest),
    user_id: Optional[str] = Query(default=None),
    agent_id: Optional[str] = Query(default=None),
    run_id: Optional[str] = Query(default=None),
    _auth=Depends(require_admin),
):
    try:
        params = req.model_dump(exclude_unset=True)
        # MemoryClient.delete_all() sends entity filters as query parameters,
        # not a JSON body. Query values fill in for any absent body field.
        for key, value in (("user_id", user_id), ("agent_id", agent_id), ("run_id", run_id)):
            if value is not None and key not in params:
                params[key] = value
        return server_state.get_memory_instance().delete_all(**params)
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


@router.get("/v1/memories/{memory_id}/history/", summary="Get memory history (platform compat)")
def get_memory_history(memory_id: str = Path(...), _auth=Depends(verify_auth)):
    try:
        return server_state.get_memory_instance().history(memory_id=memory_id)
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


@router.get("/v1/entities/", summary="List entities (platform compat)")
def list_entities(_auth=Depends(verify_auth)):
    try:
        # Reuse the native /entities scan (distinct user/agent/run ids with counts).
        entities = native_entities.list_entities(_auth=_auth)
        return wrap_results([e.model_dump() if hasattr(e, "model_dump") else e for e in entities])
    except Exception:
        raise upstream_error()


@router.delete("/v2/entities/{entity_type}/{entity_id}/", summary="Delete entity (platform compat)")
def delete_entity(entity_type: str, entity_id: str, _auth=Depends(verify_auth)):
    if entity_type not in ("user", "agent", "run"):
        raise HTTPException(status_code=400, detail=f"Unsupported entity type: {entity_type}")
    try:
        return server_state.get_memory_instance().delete_all(**{f"{entity_type}_id": entity_id})
    except (ValueError, Mem0ValidationError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise upstream_error()


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
