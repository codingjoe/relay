"""Gather the MCP components every app declares in its own `mcp` module."""

from fastmcp import FastMCP

from docs.mcp import get_docs_article, list_docs
from know_how.mcp import get_know_how_article, list_know_how
from services.email.message.mcp import get_message, list_messages
from services.email.msa.mcp import send_message

__all__ = ["bind"]


def bind(mcp: FastMCP) -> None:
    """Register every component offered to MCP clients."""
    mcp.add_tool(list_messages)
    mcp.add_tool(send_message)
    mcp.add_tool(list_docs)
    mcp.add_tool(list_know_how)
    mcp.add_resource(get_message)
    # Content may be read one article at a time.
    mcp.add_resource(get_docs_article)
    mcp.add_resource(get_know_how_article)
