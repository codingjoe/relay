"""Gather the MCP components every app declares in its own `mcp` module."""

from fastmcp import FastMCP
from fastmcp.server.transforms.search import BM25SearchTransform

from docs.mcp import register_docs_resources
from know_how.mcp import register_know_how_resources
from services.email.message.mcp import get_message, list_messages

__all__ = ["bind"]


def bind(mcp: FastMCP) -> None:
    """Register every component offered to MCP clients."""
    mcp.add_tool(list_messages)
    mcp.add_resource(get_message)
    # Content is exposed as one resource per article so clients enumerate them.
    register_docs_resources(mcp)
    register_know_how_resources(mcp)
    mcp.add_transform(BM25SearchTransform())
