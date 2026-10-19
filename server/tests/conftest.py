import contextlib
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# `main.py` calls `initialize_state()` -> `Memory.from_config()` at import time,
# which builds real pgvector/Ollama clients (DB + network). Stub the constructor
# so the app imports hermetically; route tests inject their own memory instance
# through the `fake_memory` fixture.
patch("mem0.Memory.from_config", return_value=MagicMock()).start()

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from auth import verify_auth  # noqa: E402

TOKEN = {"Authorization": "Token m0sk_test"}


@contextlib.contextmanager
def _noop_session():
    """Stand-in for `SessionLocal()` in tests that patch out the DB."""
    yield MagicMock()


@pytest.fixture()
def fake_user():
    from models import User

    user = MagicMock(spec=User)
    user.email = "admin@example.com"
    user.role = "admin"
    return user


@pytest.fixture()
def fake_memory(monkeypatch):
    """Replace the memory instance the routes resolve at call time.

    `routers/entities.py` binds `get_memory_instance` at import time, so the
    platform-compat delegate to it needs that name patched too.
    """
    memory = MagicMock()
    monkeypatch.setattr("server_state.get_memory_instance", lambda: memory)
    monkeypatch.setattr("routers.entities.get_memory_instance", lambda: memory)
    return memory


@pytest.fixture()
def client(fake_user):
    main.app.dependency_overrides[verify_auth] = lambda: fake_user
    with TestClient(main.app) as test_client:
        yield test_client
    main.app.dependency_overrides.clear()


@pytest.fixture()
def raw_client():
    """No dependency overrides — exercises the real `verify_auth` stack."""
    with TestClient(main.app) as test_client:
        yield test_client
