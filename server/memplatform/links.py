def wrap_results(items: list) -> dict:
    return {"results": list(items)}


def ping_payload(user) -> dict:
    email = getattr(user, "email", None)
    return {"org_id": None, "project_id": None, "user_email": email}
