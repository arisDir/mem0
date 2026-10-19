def wrap_results(items: list) -> dict:
    return {"results": list(items)}


def ping_payload(user) -> dict:
    email = getattr(user, "email", None)
    # The OSS server is single-tenant. Platform clients require identity fields
    # from /v1/ping/ to initialize: the Python client reads snake_case
    # (org_id/project_id/user_email), the TypeScript client checks `status`
    # and reads camelCase (orgId/projectId/userEmail). Return both shapes so
    # either client constructs successfully.
    return {
        "status": "ok",
        "org_id": "self-hosted",
        "project_id": "self-hosted",
        "user_email": email,
        "orgId": "self-hosted",
        "projectId": "self-hosted",
        "userEmail": email,
    }
