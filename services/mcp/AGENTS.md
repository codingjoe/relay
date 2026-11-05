# MCP Instructions

Apply these rules to `services/mcp/`.

## Components

- Declare tools, resources, and prompts in the `mcp` module of the app that
  owns the data. Use FastMCP's standalone decorators.
- A content module may expose `register_components(provider)`.
