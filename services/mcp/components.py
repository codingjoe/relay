"""Gather the MCP components every app declares in its own `mcp` module."""

from fastmcp import FastMCP

from services.email.message.mcp import get_message, list_messages

__all__ = ["bind"]


def bind(mcp: FastMCP) -> None:
    """Add every component relay offers MCP clients to the server."""
    mcp.add_tool(list_messages)
    mcp.add_resource(get_message)
