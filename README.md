# casdoor-mcp

MCP server for Casdoor IAM/SSO platform.

## Install

Three authentication methods are supported. Priority: access_token > client_id+secret > access_key+secret.

### Method 1: Client ID + Secret (recommended)

Where to get: Casdoor UI -> Applications -> select your app -> edit page. Copy the Client ID and Client Secret.

```json
{
  "mcpServers": {
    "casdoor": {
      "command": "uvx",
      "args": ["--refresh", "--extra-index-url", "https://nikitatsym.github.io/casdoor-mcp/simple", "casdoor-mcp"],
      "env": {
        "CASDOOR_ENDPOINT": "https://your-casdoor.example.com",
        "CASDOOR_CLIENT_ID": "your-client-id",
        "CASDOOR_CLIENT_SECRET": "your-client-secret"
      }
    }
  }
}
```

### Method 2: Access Token

Where to get: OAuth flow or Client Credentials Grant (`POST /api/login/oauth/access_token`).

```json
{
  "mcpServers": {
    "casdoor": {
      "command": "uvx",
      "args": ["--refresh", "--extra-index-url", "https://nikitatsym.github.io/casdoor-mcp/simple", "casdoor-mcp"],
      "env": {
        "CASDOOR_ENDPOINT": "https://your-casdoor.example.com",
        "CASDOOR_ACCESS_TOKEN": "your-access-token"
      }
    }
  }
}
```

### Method 3: Access Key + Secret

Where to get: User account settings or `update-user` API (per-user credentials).

```json
{
  "mcpServers": {
    "casdoor": {
      "command": "uvx",
      "args": ["--refresh", "--extra-index-url", "https://nikitatsym.github.io/casdoor-mcp/simple", "casdoor-mcp"],
      "env": {
        "CASDOOR_ENDPOINT": "https://your-casdoor.example.com",
        "CASDOOR_ACCESS_KEY": "your-access-key",
        "CASDOOR_ACCESS_SECRET": "your-access-secret"
      }
    }
  }
}
```

## Groups

| Tool | Description |
|------|-------------|
| `casdoor_read` | List/show organizations, users, applications, roles, permissions, etc. (read-only) |
| `casdoor_write` | Create/update users, organizations, applications, providers, roles, permissions, groups |
| `casdoor_delete` | Delete users, organizations, applications, providers, roles, permissions, tokens, sessions, groups |

Call any group with `operation="help"` to list available operations.

## License

MIT
