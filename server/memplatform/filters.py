import logging
from typing import Any, Dict, Optional, Set

ENTITY_KEYS: Set[str] = {"user_id", "agent_id", "run_id", "app_id"}
ALLOWED_AND_KEYS: Set[str] = {"user_id", "agent_id", "run_id", "app_id"}

logger = logging.getLogger("memplatform.filters")


def platform_filters_to_oss(filters: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not filters:
        return {}

    # Unsupported passthrough if contains AND/OR - flatten AND if simple entity-only
    if isinstance(filters.get("AND"), list):
        flattened: Dict[str, Any] = {}
        for item in filters["AND"]:
            if not isinstance(item, dict):
                return filters
            for k, v in item.items():
                if k not in ALLOWED_AND_KEYS:
                    return filters
                if k in flattened:
                    pass  # last wins per platform semantics; keep simple
                flattened[k] = v
        flattened.pop("app_id", None)
        return flattened

    if "OR" in filters:
        return filters

    # Pass through copy, drop app_id
    out = dict(filters)
    out.pop("app_id", None)
    return out
