from tests.conftest import TOKEN


def test_ping(client):
    r = client.get("/v1/ping/", headers=TOKEN)
    assert r.status_code == 200 and r.json()["user_email"] == "admin@example.com"


def test_ping_supplies_org_and_project_for_memory_client(client):
    """MemoryClient requires org_id/project_id from /v1/ping/ to construct."""
    body = client.get("/v1/ping/", headers=TOKEN).json()
    assert body["org_id"] and body["project_id"]


def test_add(client, fake_memory):
    r = client.post(
        "/v3/memories/add/",
        headers=TOKEN,
        json={"messages": [{"role": "user", "content": "hi"}], "user_id": "a"},
    )
    assert r.status_code == 200
    fake_memory.add.assert_called_once()


def test_search_translates_and(client, fake_memory):
    client.post(
        "/v3/memories/search/",
        headers=TOKEN,
        json={"query": "q", "filters": {"AND": [{"user_id": "a"}]}},
    )
    assert fake_memory.search.call_args.kwargs["filters"] == {"user_id": "a"}


def test_get_all_route(client, fake_memory):
    fake_memory.get_all.return_value = {"results": []}
    r = client.post("/v3/memories/", headers=TOKEN, json={"filters": {"user_id": "a"}})
    assert "results" in r.json()


def test_get_memory_trailing_slash(client, fake_memory):
    fake_memory.get.return_value = {"results": []}
    assert client.get("/v1/memories/abc/", headers=TOKEN).status_code == 200


def test_entities_wrapped(client, fake_memory):
    # Delegates to the native /entities scan; fake_memory's vector_store.list()
    # yields no rows, so the envelope is empty but well-formed.
    r = client.get("/v1/entities/", headers=TOKEN)
    assert r.status_code == 200 and isinstance(r.json()["results"], list)


def test_delete_entity(client, fake_memory):
    fake_memory.delete_all.return_value = {"deleted": True}
    r = client.delete("/v2/entities/user/alice/", headers=TOKEN)
    assert r.status_code == 200


def test_unsupported_summary_501(client):
    r = client.post("/v1/summary/", headers=TOKEN, json={"filters": {"user_id": "a"}})
    assert r.status_code == 501 and "summary" in r.json()["detail"].lower()


def test_unsupported_batch_501(client):
    assert client.put("/v1/batch/", headers=TOKEN, json={"memories": []}).status_code == 501


def test_delete_all_via_query_params(client, fake_memory):
    """MemoryClient.delete_all() sends entity filters as query params, not a body."""
    fake_memory.delete_all.return_value = {"deleted": 0}
    r = client.delete("/v1/memories/?user_id=alice", headers=TOKEN)
    assert r.status_code == 200
    assert fake_memory.delete_all.call_args.kwargs["user_id"] == "alice"


def test_add_drops_platform_only_fields(client, fake_memory):
    """The CLI sends `source`, which OSS Memory.add() does not accept."""
    r = client.post(
        "/v3/memories/add/",
        headers=TOKEN,
        json={"messages": [{"role": "user", "content": "hi"}], "user_id": "a", "source": "CLI"},
    )
    assert r.status_code == 200
    assert "source" not in fake_memory.add.call_args.kwargs


def test_search_drops_platform_only_fields(client, fake_memory):
    client.post(
        "/v3/memories/search/",
        headers=TOKEN,
        json={"query": "q", "filters": {"user_id": "a"}, "source": "CLI", "latest_only": True},
    )
    kwargs = fake_memory.search.call_args.kwargs
    assert "source" not in kwargs and "latest_only" not in kwargs
