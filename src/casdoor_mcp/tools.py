from .client import CasdoorClient
from .registry import ROOT, Group, _op

# -- Client singleton ---------------------------------------------------------

_client: CasdoorClient | None = None


def _get_client() -> CasdoorClient:
    global _client
    if _client is None:
        _client = CasdoorClient()
    return _client


def _ok(data):
    if data is None:
        return {"status": "ok"}
    return data


def _data(resp):
    """Extract resp['data'] if present (Casdoor wraps responses)."""
    if isinstance(resp, dict) and "data" in resp:
        return resp["data"]
    return resp


# -- Slim helpers -------------------------------------------------------------

_SLIM_USER_FIELDS = {
    "owner", "name", "displayName", "email", "phone",
    "type", "isAdmin", "createdTime",
}

_SLIM_ORGANIZATION_FIELDS = {
    "owner", "name", "displayName", "websiteUrl", "createdTime",
}

_SLIM_APPLICATION_FIELDS = {
    "owner", "name", "displayName", "organization",
    "enablePassword", "enableSignUp", "createdTime",
}


def _slim(item: dict, fields: set) -> dict:
    return {k: v for k, v in item.items() if k in fields}


def _slim_list(items, fields: set) -> list:
    if not isinstance(items, list):
        return items
    return [_slim(i, fields) for i in items if isinstance(i, dict)]


# -- Groups -------------------------------------------------------------------

casdoor_read = Group(
    "casdoor_read",
    "Query Casdoor data (safe, read-only).\n\n"
    "Call with operation=\"help\" to list all available read operations.\n"
    "Otherwise pass the operation name and a JSON object with parameters.\n\n"
    "Example: casdoor_read(operation=\"ListUsers\", "
    "params={\"owner\": \"built-in\"})",
)

casdoor_write = Group(
    "casdoor_write",
    "Create or update Casdoor resources (non-destructive).\n\n"
    "Call with operation=\"help\" to list all available write operations.\n"
    "Otherwise pass the operation name and a JSON object with parameters.\n\n"
    "Example: casdoor_write(operation=\"CreateUser\", "
    "params={\"owner\": \"built-in\", \"name\": \"alice\", "
    "\"displayName\": \"Alice\"})",
)

casdoor_delete = Group(
    "casdoor_delete",
    "Delete Casdoor resources (destructive, irreversible).\n\n"
    "Call with operation=\"help\" to list all available delete operations.\n"
    "Otherwise pass the operation name and a JSON object with parameters.\n\n"
    "Example: casdoor_delete(operation=\"DeleteUser\", "
    "params={\"owner\": \"built-in\", \"name\": \"alice\"})",
)


# -- ROOT ---------------------------------------------------------------------

@_op(ROOT)
def casdoor_version():
    """Get the Casdoor MCP server version."""
    from importlib.metadata import version
    return version("casdoor-mcp")


# -- casdoor_read -------------------------------------------------------------

@_op(casdoor_read)
def list_organizations():
    """List all organizations (slim)."""
    resp = _get_client().get("/api/get-organizations")
    return _slim_list(_data(resp), _SLIM_ORGANIZATION_FIELDS)


@_op(casdoor_read)
def show_organization(id: str):
    """Get full organization details. id = 'owner/name'."""
    return _data(_get_client().get("/api/get-organization", params={"id": id}))


@_op(casdoor_read)
def list_users(owner: str):
    """List users in an organization (slim). owner = org name."""
    resp = _get_client().get("/api/get-users", params={"owner": owner})
    return _slim_list(_data(resp), _SLIM_USER_FIELDS)


@_op(casdoor_read)
def show_user(id: str):
    """Get full user details. id = 'owner/name'."""
    return _data(_get_client().get("/api/get-user", params={"id": id}))


@_op(casdoor_read)
def list_applications(owner: str):
    """List applications in an organization (slim). owner = org name."""
    resp = _get_client().get("/api/get-applications", params={"owner": owner})
    return _slim_list(_data(resp), _SLIM_APPLICATION_FIELDS)


@_op(casdoor_read)
def show_application(id: str):
    """Get full application details. id = 'owner/name'."""
    return _data(_get_client().get("/api/get-application", params={"id": id}))


@_op(casdoor_read)
def list_providers(owner: str):
    """List providers in an organization (slim)."""
    return _data(_get_client().get("/api/get-providers", params={"owner": owner}))


@_op(casdoor_read)
def show_provider(id: str):
    """Get full provider details. id = 'owner/name'."""
    return _data(_get_client().get("/api/get-provider", params={"id": id}))


@_op(casdoor_read)
def list_roles(owner: str):
    """List roles in an organization (slim)."""
    return _data(_get_client().get("/api/get-roles", params={"owner": owner}))


@_op(casdoor_read)
def show_role(id: str):
    """Get full role details. id = 'owner/name'."""
    return _data(_get_client().get("/api/get-role", params={"id": id}))


@_op(casdoor_read)
def list_permissions(owner: str):
    """List permissions in an organization (slim)."""
    return _data(_get_client().get("/api/get-permissions", params={"owner": owner}))


@_op(casdoor_read)
def show_permission(id: str):
    """Get full permission details. id = 'owner/name'."""
    return _data(_get_client().get("/api/get-permission", params={"id": id}))


@_op(casdoor_read)
def list_tokens(owner: str):
    """List tokens in an organization."""
    return _data(_get_client().get("/api/get-tokens", params={"owner": owner}))


@_op(casdoor_read)
def list_sessions(owner: str):
    """List sessions in an organization."""
    return _data(_get_client().get("/api/get-sessions", params={"owner": owner}))


@_op(casdoor_read)
def list_certs(owner: str):
    """List certificates in an organization."""
    return _data(_get_client().get("/api/get-certs", params={"owner": owner}))


@_op(casdoor_read)
def list_models(owner: str):
    """List Casbin models in an organization."""
    return _data(_get_client().get("/api/get-models", params={"owner": owner}))


@_op(casdoor_read)
def list_adapters(owner: str):
    """List Casbin adapters in an organization."""
    return _data(_get_client().get("/api/get-adapters", params={"owner": owner}))


@_op(casdoor_read)
def list_enforcers(owner: str):
    """List Casbin enforcers in an organization."""
    return _data(_get_client().get("/api/get-enforcers", params={"owner": owner}))


@_op(casdoor_read)
def list_groups(owner: str):
    """List groups in an organization."""
    return _data(_get_client().get("/api/get-groups", params={"owner": owner}))


@_op(casdoor_read)
def list_webhooks(owner: str):
    """List webhooks in an organization."""
    return _data(_get_client().get("/api/get-webhooks", params={"owner": owner}))


@_op(casdoor_read)
def list_syncers(owner: str):
    """List syncers in an organization."""
    return _data(_get_client().get("/api/get-syncers", params={"owner": owner}))


# -- casdoor_write ------------------------------------------------------------

@_op(casdoor_write)
def create_user(owner: str, name: str, displayName: str = "", **kwargs):
    """Create a user. Required: owner, name. Optional: displayName, email, phone, password, etc."""
    body = {"owner": owner, "name": name, "displayName": displayName, **kwargs}
    return _ok(_get_client().post("/api/add-user", json=body))


@_op(casdoor_write)
def update_user(owner: str, name: str, **kwargs):
    """Update a user. Pass owner+name to identify, plus fields to change."""
    body = {"owner": owner, "name": name, **kwargs}
    return _ok(_get_client().post("/api/update-user", json=body))


@_op(casdoor_write)
def create_organization(owner: str, name: str, displayName: str = "", **kwargs):
    """Create an organization. Required: owner (usually 'admin'), name."""
    body = {"owner": owner, "name": name, "displayName": displayName, **kwargs}
    return _ok(_get_client().post("/api/add-organization", json=body))


@_op(casdoor_write)
def update_organization(owner: str, name: str, **kwargs):
    """Update an organization. Pass owner+name to identify, plus fields to change."""
    body = {"owner": owner, "name": name, **kwargs}
    return _ok(_get_client().post("/api/update-organization", json=body))


@_op(casdoor_write)
def create_application(owner: str, name: str, displayName: str = "", **kwargs):
    """Create an application. Required: owner (org name), name."""
    body = {"owner": owner, "name": name, "displayName": displayName, **kwargs}
    return _ok(_get_client().post("/api/add-application", json=body))


@_op(casdoor_write)
def update_application(owner: str, name: str, **kwargs):
    """Update an application. Pass owner+name to identify, plus fields to change."""
    body = {"owner": owner, "name": name, **kwargs}
    return _ok(_get_client().post("/api/update-application", json=body))


@_op(casdoor_write)
def create_provider(owner: str, name: str, displayName: str = "", **kwargs):
    """Create a provider. Required: owner (org name), name."""
    body = {"owner": owner, "name": name, "displayName": displayName, **kwargs}
    return _ok(_get_client().post("/api/add-provider", json=body))


@_op(casdoor_write)
def update_provider(owner: str, name: str, **kwargs):
    """Update a provider. Pass owner+name to identify, plus fields to change."""
    body = {"owner": owner, "name": name, **kwargs}
    return _ok(_get_client().post("/api/update-provider", json=body))


@_op(casdoor_write)
def create_role(owner: str, name: str, displayName: str = "", **kwargs):
    """Create a role. Required: owner (org name), name."""
    body = {"owner": owner, "name": name, "displayName": displayName, **kwargs}
    return _ok(_get_client().post("/api/add-role", json=body))


@_op(casdoor_write)
def update_role(owner: str, name: str, **kwargs):
    """Update a role. Pass owner+name to identify, plus fields to change."""
    body = {"owner": owner, "name": name, **kwargs}
    return _ok(_get_client().post("/api/update-role", json=body))


@_op(casdoor_write)
def create_permission(owner: str, name: str, displayName: str = "", **kwargs):
    """Create a permission. Required: owner (org name), name."""
    body = {"owner": owner, "name": name, "displayName": displayName, **kwargs}
    return _ok(_get_client().post("/api/add-permission", json=body))


@_op(casdoor_write)
def update_permission(owner: str, name: str, **kwargs):
    """Update a permission. Pass owner+name to identify, plus fields to change."""
    body = {"owner": owner, "name": name, **kwargs}
    return _ok(_get_client().post("/api/update-permission", json=body))


@_op(casdoor_write)
def create_group(owner: str, name: str, displayName: str = "", **kwargs):
    """Create a group. Required: owner (org name), name."""
    body = {"owner": owner, "name": name, "displayName": displayName, **kwargs}
    return _ok(_get_client().post("/api/add-group", json=body))


@_op(casdoor_write)
def update_group(owner: str, name: str, **kwargs):
    """Update a group. Pass owner+name to identify, plus fields to change."""
    body = {"owner": owner, "name": name, **kwargs}
    return _ok(_get_client().post("/api/update-group", json=body))


# -- casdoor_delete -----------------------------------------------------------

@_op(casdoor_delete)
def delete_user(owner: str, name: str):
    """Delete a user. Irreversible."""
    return _ok(_get_client().post("/api/delete-user", json={"owner": owner, "name": name}))


@_op(casdoor_delete)
def delete_organization(owner: str, name: str):
    """Delete an organization. Irreversible."""
    return _ok(_get_client().post("/api/delete-organization", json={"owner": owner, "name": name}))


@_op(casdoor_delete)
def delete_application(owner: str, name: str):
    """Delete an application. Irreversible."""
    return _ok(_get_client().post("/api/delete-application", json={"owner": owner, "name": name}))


@_op(casdoor_delete)
def delete_provider(owner: str, name: str):
    """Delete a provider. Irreversible."""
    return _ok(_get_client().post("/api/delete-provider", json={"owner": owner, "name": name}))


@_op(casdoor_delete)
def delete_role(owner: str, name: str):
    """Delete a role. Irreversible."""
    return _ok(_get_client().post("/api/delete-role", json={"owner": owner, "name": name}))


@_op(casdoor_delete)
def delete_permission(owner: str, name: str):
    """Delete a permission. Irreversible."""
    return _ok(_get_client().post("/api/delete-permission", json={"owner": owner, "name": name}))


@_op(casdoor_delete)
def delete_token(owner: str, name: str):
    """Delete a token. Irreversible."""
    return _ok(_get_client().post("/api/delete-token", json={"owner": owner, "name": name}))


@_op(casdoor_delete)
def delete_session(owner: str, name: str):
    """Delete a session. Irreversible."""
    return _ok(_get_client().post("/api/delete-session", json={"owner": owner, "name": name}))


@_op(casdoor_delete)
def delete_group(owner: str, name: str):
    """Delete a group. Irreversible."""
    return _ok(_get_client().post("/api/delete-group", json={"owner": owner, "name": name}))
