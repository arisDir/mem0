from tests.conftest import TOKEN


def test_ping(client):
    r = client.get("/v1/ping/", headers=TOKEN)
    assert r.status_code == 200 and r.json()["user_email"] == "admin@example.com"


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
    fake_memory.get_all.return_value = {"results": []}
    r = client.get("/v1/entities/", headers=TOKEN)
    assert isinstance(r.json()["results"], list)
