# casdoor-mcp

MCP server for Casdoor IAM/SSO platform.

- **MCP standard:** `/home/ari/src/obsidian_vault/specs/mcp-server.md` — follow it exactly (structure, registry, server dispatch, groups, config, client patterns)
- **Reference implementations:** komodo-mcp (`/home/ari/src/komodo-mcp/`), ticktick-mcp (`/home/ari/src/ticktick-mcp/`)
- **API base:** `https://auth.wand.tsym.nl`, auth: `Bearer {CASDOOR_CLIENT_SECRET}` (or client_id + client_secret)
- **OpenAPI spec:** `https://door.casdoor.com/swagger/` (if available)
- **Hosting:** GitHub
  - **GitHub:** CI/CD from `/home/ari/src/vastai-mcp/.github/workflows/build.yml`, enable Pages (Actions source), create `docs/index.html` setup page

## Groups

casdoor_read    — search, list, show (safe, read-only)
casdoor_write   — create, update (non-destructive)
casdoor_delete  — destroy, delete (destructive)

## Operations

Format: `function_name(params)` → `HTTP_METHOD /path` — description.

### casdoor_read

| Operation | Endpoint | Notes |
|---|---|---|
| `list_organizations()` | `GET /api/get-organizations` | Slim with `_slim_organization` |
| `show_organization(id)` | `GET /api/get-organization?id=org/name` | Full |
| `list_users(owner)` | `GET /api/get-users?owner=org` | Slim with `_slim_user` |
| `show_user(id)` | `GET /api/get-user?id=org/name` | Full |
| `list_applications(owner)` | `GET /api/get-applications?owner=org` | Slim with `_slim_application` |
| `show_application(id)` | `GET /api/get-application?id=org/name` | Full |
| `list_providers(owner)` | `GET /api/get-providers?owner=org` | Slim |
| `show_provider(id)` | `GET /api/get-provider?id=org/name` | Full |
| `list_roles(owner)` | `GET /api/get-roles?owner=org` | Slim |
| `show_role(id)` | `GET /api/get-role?id=org/name` | Full |
| `list_permissions(owner)` | `GET /api/get-permissions?owner=org` | Slim |
| `show_permission(id)` | `GET /api/get-permission?id=org/name` | Full |
| `list_tokens(owner)` | `GET /api/get-tokens?owner=org` | Slim |
| `list_sessions(owner)` | `GET /api/get-sessions?owner=org` | Slim |
| `list_certs(owner)` | `GET /api/get-certs?owner=org` | Slim |
| `list_models(owner)` | `GET /api/get-models?owner=org` | Slim (Casbin models) |
| `list_adapters(owner)` | `GET /api/get-adapters?owner=org` | Slim |
| `list_enforcers(owner)` | `GET /api/get-enforcers?owner=org` | Slim |
| `list_groups(owner)` | `GET /api/get-groups?owner=org` | Slim |
| `list_webhooks(owner)` | `GET /api/get-webhooks?owner=org` | Slim |
| `list_syncers(owner)` | `GET /api/get-syncers?owner=org` | Slim |

### casdoor_write

| Operation | Endpoint | Notes |
|---|---|---|
| `create_user(owner, name, displayName="", **kwargs)` | `POST /api/add-user` | body includes owner, name, displayName, and caller-supplied Casdoor fields |
| `update_user(owner, name, **kwargs)` | `GET /api/get-user?id=owner/name` then `POST /api/update-user?id=owner/name` | read-modify-write: Casdoor rewrites every column, so kwargs are laid over the current object |
| `create_organization(owner, name, displayName="", **kwargs)` | `POST /api/add-organization` | body includes owner, name, displayName, and caller-supplied Casdoor fields |
| `update_organization(owner, name, **kwargs)` | `GET /api/get-organization?id=owner/name` then `POST /api/update-organization?id=owner/name` | read-modify-write: Casdoor rewrites every column, so kwargs are laid over the current object |
| `create_application(owner, name, displayName="", **kwargs)` | `POST /api/add-application` | body includes owner, name, displayName, and caller-supplied Casdoor fields |
| `update_application(owner, name, **kwargs)` | `GET /api/get-application?id=owner/name` then `POST /api/update-application?id=owner/name` | read-modify-write: Casdoor rewrites every column, so kwargs are laid over the current object |
| `create_provider(owner, name, displayName="", **kwargs)` | `POST /api/add-provider` | body includes owner, name, displayName, and caller-supplied Casdoor fields |
| `update_provider(owner, name, **kwargs)` | `GET /api/get-provider?id=owner/name` then `POST /api/update-provider?id=owner/name` | read-modify-write: Casdoor rewrites every column, so kwargs are laid over the current object |
| `create_role(owner, name, displayName="", **kwargs)` | `POST /api/add-role` | body includes owner, name, displayName, and caller-supplied Casdoor fields |
| `update_role(owner, name, **kwargs)` | `GET /api/get-role?id=owner/name` then `POST /api/update-role?id=owner/name` | read-modify-write: Casdoor rewrites every column, so kwargs are laid over the current object |
| `create_permission(owner, name, displayName="", **kwargs)` | `POST /api/add-permission` | body includes owner, name, displayName, and caller-supplied Casdoor fields |
| `update_permission(owner, name, **kwargs)` | `GET /api/get-permission?id=owner/name` then `POST /api/update-permission?id=owner/name` | read-modify-write: Casdoor rewrites every column, so kwargs are laid over the current object |
| `create_group(owner, name, displayName="", **kwargs)` | `POST /api/add-group` | body includes owner, name, displayName, and caller-supplied Casdoor fields |
| `update_group(owner, name, **kwargs)` | `GET /api/get-group?id=owner/name` then `POST /api/update-group?id=owner/name` | read-modify-write: Casdoor rewrites every column, so kwargs are laid over the current object |

### casdoor_delete

| Operation | Endpoint | Notes |
|---|---|---|
| `delete_user(owner, name)` | `POST /api/delete-user` | body = owner + name |
| `delete_organization(owner, name)` | `POST /api/delete-organization` | body = owner + name |
| `delete_application(owner, name)` | `POST /api/delete-application` | body = owner + name |
| `delete_provider(owner, name)` | `POST /api/delete-provider` | body = owner + name |
| `delete_role(owner, name)` | `POST /api/delete-role` | body = owner + name |
| `delete_permission(owner, name)` | `POST /api/delete-permission` | body = owner + name |
| `delete_token(owner, name, organization)` | `POST /api/delete-token` | body = owner + name + organization; Casdoor filters the delete by organization |
| `delete_session(owner, name, application)` | `POST /api/delete-session` | body = owner + name + application; Casdoor keys sessions by all three |
| `delete_group(owner, name)` | `POST /api/delete-group` | body = owner + name |

## Slim fields

_SLIM_USER_FIELDS = {"owner", "name", "displayName", "email", "phone", "type", "isAdmin", "createdTime"}

_SLIM_ORGANIZATION_FIELDS = {"owner", "name", "displayName", "websiteUrl", "createdTime"}

_SLIM_APPLICATION_FIELDS = {"owner", "name", "displayName", "organization", "enablePassword", "enableSignUp", "createdTime"}

## Out of scope

- SAML/CAS/OAuth protocol endpoints — handled by Casdoor directly, not through MCP
- Payment/pricing endpoints — not relevant
- System health/version — low value

## Deploy checklist

- [ ] CI/CD workflow (`.github/workflows/build.yml`)
- [ ] GitHub: enable Pages in repo settings (source: GitHub Actions) — `gh api repos/OWNER/REPO/pages -X POST -f build_type=workflow`
- [ ] GitHub: `docs/index.html` setup page (API key input → config JSON generator)
- [ ] First push to `main` triggers build → tag v1.0.0 → release with wheel → PEP 503 index
- [ ] Verify install: `uvx --extra-index-url INDEX_URL casdoor-mcp`
