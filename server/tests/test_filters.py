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
    assert ping_payload(fake_user) == {
        "org_id": None,
        "project_id": None,
        "user_email": "admin@example.com",
    }
