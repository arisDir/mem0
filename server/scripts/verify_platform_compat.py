#!/usr/bin/env python3
"""End-to-end verification of the platform-compatibility layer.

Runs the real platform clients (Python MemoryClient, mem0 CLI) against a live
self-hosted server and exercises the /v1, /v2, /v3 compat routes.

Usage:
    MEM0_API_URL=http://localhost:8888 MEM0_API_KEY=m0sk_... \
        python scripts/verify_platform_compat.py

Exits non-zero if any check fails.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

API_URL = os.environ.get("MEM0_API_URL", "http://localhost:8888").rstrip("/")
API_KEY = os.environ["MEM0_API_KEY"]
# Unique per run: a fixed UID can go stale against the server's dedup state.
UID = "platform-compat-smoke-" + uuid.uuid4().hex[:8]

failures = []


def check(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def raw(method, path, body=None):
    """Call a compat route with the platform client's auth style (Authorization: Token)."""
    req = urllib.request.Request(
        f"{API_URL}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Token {API_KEY}", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}


def verify_python_client():
    """Real MemoryClient against the compat routes."""
    from mem0 import MemoryClient

    c = MemoryClient(api_key=API_KEY, host=API_URL)

    c.add([{"role": "user", "content": "I prefer aisle seats"}], user_id=UID)

    # Memory may be extracted asynchronously; poll briefly.
    hits = []
    for _ in range(15):
        hits = c.search("seat preference", filters={"user_id": UID}).get("results", [])
        if any("aisle" in h.get("memory", "") for h in hits):
            break
        import time

        time.sleep(2)
    check("python: search finds added memory", any("aisle" in h.get("memory", "") for h in hits), hits)

    # List through /v3/memories/ envelope
    listed = c.get_all(filters={"user_id": UID})
    results = listed.get("results", listed if isinstance(listed, list) else [])
    check("python: get_all returns results envelope", isinstance(results, list) and len(results) > 0, listed)

    if results:
        mid = results[0]["id"]
        got = c.get(mid)
        check("python: get by id", bool(got), got)

        upd = c.update(memory_id=mid, text="I prefer window seats on flights")
        check("python: update memory", bool(upd), upd)

        deleted = c.delete(mid)
        check("python: delete memory", bool(deleted), deleted)

    c.delete_all(user_id=UID)
    check("python: delete_all", True)


def verify_token_auth_routes():
    """Routes the SDK may not cover, using Authorization: Token directly."""
    status, body = raw("GET", "/v1/ping/")
    check("http: /v1/ping/ with Token auth", status == 200 and "user_email" in body, (status, body))

    status, body = raw("GET", "/v1/entities/")
    check("http: /v1/entities/ wrapped", status == 200 and isinstance(body.get("results"), list), (status, body))

    status, body = raw("POST", "/v3/memories/add/", {"messages": [{"role": "user", "content": "My favorite editor is Neovim"}], "user_id": UID})
    check("http: /v3/memories/add/", status == 200, (status, body))

    status, body = raw("POST", "/v3/memories/search/", {"query": "editor", "filters": {"AND": [{"user_id": UID}]}})
    check("http: /v3/memories/search/ with AND filter", status == 200 and "results" in body, (status, body))

    status, body = raw("POST", "/v3/memories/", {"filters": {"user_id": UID}})
    check("http: /v3/memories/ list", status == 200 and "results" in body, (status, body))

    status, body = raw("DELETE", "/v2/entities/bogus/some-id/", None)
    check("http: unsupported entity type → 400", status == 400, (status, body))

    status, body = raw("POST", "/v1/summary/", {"filters": {"user_id": UID}})
    check("http: /v1/summary/ → 501", status == 501, (status, body))

    status, body = raw("PUT", "/v1/batch/", {"memories": []})
    check("http: /v1/batch/ → 501", status == 501, (status, body))

    raw("DELETE", "/v1/memories/", {"user_id": UID})


def verify_cli():
    """mem0 CLI against the compat routes, if installed."""
    cli_user = "cli-smoke-" + uuid.uuid4().hex[:8]
    env = dict(os.environ, MEM0_API_KEY=API_KEY, MEM0_API_URL=API_URL, MEM0_USER_ID=cli_user)
    try:
        subprocess.run(["mem0", "--help"], env=env, capture_output=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        print("  [SKIP] cli: mem0 CLI not available")
        return

    def cli(*args, timeout=180):
        return subprocess.run(["mem0", *args], env=env, capture_output=True, text=True, timeout=timeout)

    subprocess.run(["mem0", "config", "set", "platform.base_url", API_URL], env=env, capture_output=True)
    subprocess.run(["mem0", "config", "set", "platform.api_key", API_KEY], env=env, capture_output=True)

    r = cli("add", "I speak fluent French")
    check("cli: add", r.returncode == 0 and "French" in r.stdout, r.stdout[-300:] + r.stderr[-300:])

    r = cli("search", "languages")
    check("cli: search", r.returncode == 0 and "French" in r.stdout, r.stdout[-300:] + r.stderr[-300:])

    r = cli("list", "--json")
    ok = r.returncode == 0 and "results" in r.stdout or "data" in r.stdout
    check("cli: list", ok, r.stdout[-300:] + r.stderr[-300:])

    mem_id = None
    try:
        payload = json.loads(r.stdout)
        rows = payload.get("data") or payload.get("results") or []
        mem_id = rows[0]["id"] if rows else None
    except Exception:
        pass

    if mem_id:
        r = cli("get", mem_id)
        check("cli: get", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])

        r = cli("update", mem_id, "I speak fluent French and Spanish")
        check("cli: update", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])

        r = cli("delete", mem_id)
        check("cli: delete", r.returncode == 0, r.stdout[-300:] + r.stderr[-300:])
    else:
        check("cli: list returns a memory id", False, r.stdout[-300:])


def main():
    if not API_KEY:
        print("MEM0_API_KEY is required", file=sys.stderr)
        return 2

    print(f"Verifying platform compatibility against {API_URL}")
    print("\nPython MemoryClient:")
    verify_python_client()
    print("\nHTTP compat routes (Authorization: Token):")
    verify_token_auth_routes()
    print("\nmem0 CLI:")
    verify_cli()

    if failures:
        print(f"\n{len(failures)} check(s) failed: {failures}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
