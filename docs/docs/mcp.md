---
name: MCP
description: Connect an AI assistant to relay with the Model Context Protocol
author: Johannes Maron
---

# MCP

Relay exposes your mail to AI assistants through the
[Model Context Protocol](https://modelcontextprotocol.io). An assistant
connects to the endpoint below, signs in with your account, and reads or
searches the mail of the organizations you belong to. It never receives your
password or API key.

## The endpoint

The MCP endpoint is the platform domain with `/mcp` appended to it:

```text
https://your.platform.example/mcp
```

The same URL serves the web application.

## Connect a client

Most clients only need that URL. Codex accepts it directly:

```sh
codex mcp add relay --url https://your.platform.example/mcp
```

Other clients use a JSON configuration:

```json
{
  "mcpServers": {
    "relay": {
      "url": "https://your.platform.example/mcp"
    }
  }
}
```

The first time the client connects, relay opens a browser window. Sign in
there and approve the connection. The exact client address is shown before
you confirm.

## What an assistant can do

An assistant with the `messages:read` permission can:

- **list_messages**. Return the sent and received mail of your organizations,
  newest first. Filter by direction, sender or recipient address, and message
  status. Results paginate, 25 messages per page by default and up to 100.
- **get_message**. Return one message with its headers, scan verdicts, and
  delivery summary. A `body_url` points at the message's authorized body view.

## Permissions

relay asks for consent before issuing a token. Two permissions matter:

- **messages:read**. View sent and received messages of your organizations.
  Consent is granted per client. Revoke a client from the account settings at
  any time; its tokens stop working immediately.

## Inspecting deliveries

Every message carries its delivery record: the number of delivery attempts,
the time the last one finished, and how long delivery took. The assistant
uses these to answer questions like "did this message arrive yet?" without
opening the dashboard.

## Security notes

- relay issues an access token to the client, scoped to one user and one
  set of permissions. The client never holds a relay credential.
- An assistant sees only the mail of organizations you belong to.
- Raw bodies load from signed, expiring URLs, so a captured link cannot
  re-download the message later.
