"""Gateway URL helpers tests."""

from __future__ import annotations

from gateway.config import ControlPlaneSection, GatewayConfig, NodeSection, ServerSection
from gateway.urls import gateway_base_urls, listen_hosts


def test_listen_hosts_all_interfaces() -> None:
    hosts = listen_hosts("0.0.0.0")
    assert "127.0.0.1" in hosts
    assert len(hosts) >= 2


def test_gateway_base_urls_includes_advertised_host() -> None:
    config = GatewayConfig(
        node=NodeSection(id="n1", descriptive_info={"host": "dev-box"}),
        server=ServerSection(host="0.0.0.0", port=8080),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )
    urls = gateway_base_urls(config)
    assert any("dev-box" in url for url in urls)


def test_listen_hosts_specific() -> None:
    assert listen_hosts("127.0.0.1") == ["127.0.0.1"]


def test_gateway_base_urls() -> None:
    config = GatewayConfig(
        node=NodeSection(id="n1"),
        server=ServerSection(host="127.0.0.1", port=9090),
        control_plane=ControlPlaneSection(url="http://127.0.0.1:8000"),
    )
    assert gateway_base_urls(config) == ["http://127.0.0.1:9090"]
