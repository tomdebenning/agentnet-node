"""Frontend health API test."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from gateway.app import create_app
from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection


@pytest.fixture
def gateway_config(tmp_path) -> GatewayConfig:
    agents = tmp_path / "agents"
    definitions = tmp_path / "definitions"
    agents.mkdir()
    definitions.mkdir()
    return GatewayConfig(
        node=NodeSection(id="test-node"),
        server=ServerSection(host="127.0.0.1", port=8080),
        agents_root=str(agents),
        definitions_root=str(definitions),
        database=str(tmp_path / "gateway.db"),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )


@pytest.mark.asyncio
async def test_frontend_health_when_built(gateway_config: GatewayConfig) -> None:
    from asgi_lifespan import LifespanManager

    app = create_app(gateway_config)
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/frontend-health")
            assert response.status_code == 200
            body = response.json()
            assert body["ok"] is True
            assert body["missing"] == []
