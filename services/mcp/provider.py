"""Discover the MCP components each Django app declares in its `mcp` module."""

from collections.abc import Iterator
from importlib import import_module
from types import ModuleType

from django.apps import apps
from fastmcp.prompts.base import Prompt
from fastmcp.resources.base import Resource
from fastmcp.resources.template import ResourceTemplate
from fastmcp.server.providers import LocalProvider
from fastmcp.server.providers.filesystem_discovery import extract_components
from fastmcp.tools.base import Tool
from fastmcp.utilities.components import FastMCPComponent


class AppMCPProvider(LocalProvider):
    """Register the MCP components declared in each app's `mcp` module."""

    @classmethod
    def app_mcp_modules(cls) -> Iterator[ModuleType]:
        """Yield the `mcp` module of every installed app that declares one."""
        for app_config in apps.get_app_configs():
            module_name = f"{app_config.name}.mcp"
            try:
                yield import_module(module_name)
            except ModuleNotFoundError as error:
                # An absent `mcp` module is expected, a missing import inside one is not.
                if error.name != module_name:
                    raise

    def __init__(self) -> None:
        super().__init__()
        for module in self.app_mcp_modules():
            for component in extract_components(module):
                self.register_component(component)
            if register_components := getattr(module, "register_components", None):
                register_components(self)

    def register_component(self, component: FastMCPComponent) -> None:
        """Add one extracted tool, resource, template, or prompt."""
        match component:
            case ResourceTemplate():
                self.add_template(component)
            case Resource():
                self.add_resource(component)
            case Tool():
                self.add_tool(component)
            case Prompt():
                self.add_prompt(component)
