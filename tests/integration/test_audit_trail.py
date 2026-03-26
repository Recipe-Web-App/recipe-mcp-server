"""Integration tests verifying audit log entries after tool mutations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastmcp import Client
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from recipe_mcp_server.db.tables import AuditLogTable


@pytest.mark.integration
class TestAuditTrail:
    """Tests that mutating tools write audit log entries."""

    @staticmethod
    async def _query_audit_log(db_path: Path) -> list[AuditLogTable]:
        """Open a separate DB connection to read the audit_log table."""
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            rows = (await session.execute(select(AuditLogTable))).scalars().all()
        await engine.dispose()
        return list(rows)

    async def test_create_recipe_writes_audit_entry(
        self, mcp_client: Client, tmp_path: Path
    ) -> None:
        """Creating a recipe should produce an audit log entry."""
        result = await mcp_client.call_tool(
            "create_recipe",
            {"title": "Audit Test Recipe", "servings": 2},
        )

        text_content = result.content[0].text
        recipe_data = json.loads(text_content)
        recipe_id = recipe_data.get("id")
        assert recipe_id is not None

        rows = await self._query_audit_log(tmp_path / "test.db")
        audit_entries = [r for r in rows if r.entity_type == "recipe" and r.action == "create"]
        assert len(audit_entries) >= 1
        entry = audit_entries[-1]
        assert entry.tool_name == "create_recipe"

    async def test_delete_recipe_writes_audit_entry(
        self, mcp_client: Client, tmp_path: Path
    ) -> None:
        """Deleting a recipe should produce a delete audit entry."""
        create_result = await mcp_client.call_tool(
            "create_recipe",
            {"title": "To Delete Recipe"},
        )
        recipe_data = json.loads(create_result.content[0].text)
        recipe_id = recipe_data["id"]

        await mcp_client.call_tool("delete_recipe", {"recipe_id": recipe_id})

        rows = await self._query_audit_log(tmp_path / "test.db")
        delete_entries = [
            r
            for r in rows
            if r.entity_type == "recipe" and r.action == "delete" and r.entity_id == recipe_id
        ]
        assert len(delete_entries) >= 1
        assert delete_entries[-1].tool_name == "delete_recipe"

    async def test_audit_log_immutable_no_tool_exposed(self, mcp_client: Client) -> None:
        """No tool should exist that modifies or deletes audit log entries."""
        tools = await mcp_client.list_tools()
        tool_names = {t.name for t in tools}
        assert "update_audit_log" not in tool_names
        assert "delete_audit_log" not in tool_names
