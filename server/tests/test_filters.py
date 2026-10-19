from memplatform.filters import platform_filters_to_oss
from memplatform.links import ping_payload, wrap_results


def test_passthrough_entity_filter():
    assert platform_filters_to_oss({"user_id": "a"}) == {"user_id": "a"}


def test_none_and_empty():
    assert platform_filters_to_oss(None) == {}
    assert platform_filters_to_oss({}) == {}


def test_flatten_and():
    assert platform_filters_to_oss({"AND": [{"user_id": "a"}, {"run_id": "r"}]}) == {
        "user_id": "a",
        "run_id": "r",
    }


def test_unsupported_passthrough():
    f = {"categories": {"contains": "x"}}
    assert platform_filters_to_oss(f) == f


def test_app_id_dropped():
    assert platform_filters_to_oss({"user_id": "a", "app_id": "z"}) == {"user_id": "a"}


def test_wrap_and_ping(fake_user):
    assert wrap_results([1, 2]) == {"results": [1, 2]}
    # Platform clients need an identity from /v1/ping/. The Python client reads
    # snake_case org_id/project_id (None breaks its Project manager); the
    # TypeScript client checks `status` and reads camelCase. Both are truthy.
    payload = ping_payload(fake_user)
    assert payload["status"] == "ok"
    assert payload["org_id"] == "self-hosted" and payload["project_id"] == "self-hosted"
    assert payload["orgId"] == "self-hosted" and payload["projectId"] == "self-hosted"
    assert payload["user_email"] == "admin@example.com"
    assert payload["userEmail"] == "admin@example.com"
