"""MCP spec compliance tests: capabilities, server info, and field validation."""

from __future__ import annotations

import pytest
from fastmcp import Client


@pytest.mark.e2e
class TestServerInfo:
    """Verify the server reports correct identity on initialization."""

    async def test_server_name(self, mcp_client: Client) -> None:
        init = mcp_client.initialize_result
        assert init is not None
        assert init.serverInfo.name == "recipe-mcp-server"

    async def test_server_version_present(self, mcp_client: Client) -> None:
        init = mcp_client.initialize_result
        assert init is not None
        assert init.serverInfo.version


@pytest.mark.e2e
class TestCapabilities:
    """Verify the server declares the expected MCP capabilities."""

    async def test_tools_capability(self, mcp_client: Client) -> None:
        caps = mcp_client.initialize_result.capabilities
        assert caps.tools is not None

    async def test_resources_capability(self, mcp_client: Client) -> None:
        caps = mcp_client.initialize_result.capabilities
        assert caps.resources is not None

    async def test_prompts_capability(self, mcp_client: Client) -> None:
        caps = mcp_client.initialize_result.capabilities
        assert caps.prompts is not None


@pytest.mark.e2e
class TestConnectivity:
    """Basic protocol-level connectivity checks."""

    async def test_ping(self, mcp_client: Client) -> None:
        await mcp_client.ping()


@pytest.mark.e2e
class TestDefinitionFields:
    """Every primitive definition includes all MCP-required fields."""

    async def test_tools_have_name_description_schema(self, mcp_client: Client) -> None:
        tools = await mcp_client.list_tools()
        assert len(tools) > 0
        for tool in tools:
            assert tool.name, f"Tool missing name: {tool}"
            assert tool.description, f"Tool '{tool.name}' missing description"
            assert tool.inputSchema is not None, f"Tool '{tool.name}' missing inputSchema"

    async def test_static_resources_have_uri_and_name(self, mcp_client: Client) -> None:
        resources = await mcp_client.list_resources()
        for resource in resources:
            assert resource.uri, "Resource missing uri"
            assert resource.name, "Resource missing name"

    async def test_prompts_have_name_and_description(self, mcp_client: Client) -> None:
        prompts = await mcp_client.list_prompts()
        assert len(prompts) > 0
        for prompt in prompts:
            assert prompt.name, f"Prompt missing name: {prompt}"
            assert prompt.description, f"Prompt '{prompt.name}' missing description"

    async def test_resource_templates_have_uri_with_placeholder(self, mcp_client: Client) -> None:
        templates = await mcp_client.list_resource_templates()
        assert len(templates) > 0
        for tmpl in templates:
            assert tmpl.uriTemplate, f"Template missing uriTemplate: {tmpl}"
            assert "{" in tmpl.uriTemplate, f"Template '{tmpl.name}' uriTemplate has no placeholder"
