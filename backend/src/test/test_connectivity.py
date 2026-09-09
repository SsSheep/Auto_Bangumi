"""设置页连通性测试：TMDB / 下载器 / Jellyfin。"""

from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from module.api import v1
from module.api.deps import get_context
from module.manager import connectivity
from module.security.api import get_current_user


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.fixture
def patch_client():
    """把 connectivity._client 替换为 MockTransport 客户端的工厂。"""

    def _install(handler):
        return patch.object(
            connectivity, "_client", lambda **kw: _mock_client(handler)
        )

    return _install


# ---------------------------------------------------------------------------
# TMDB
# ---------------------------------------------------------------------------


async def test_tmdb_v3_key_ok(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_key"] == "v3key"
        assert "Authorization" not in request.headers
        return httpx.Response(200, json={"images": {}})

    with patch_client(handler):
        result = await connectivity.test_tmdb("https://api.example/", "v3key")
    assert result["ok"] is True
    assert "v3" in result["msg_zh"]
    assert result["latency_ms"] >= 0


async def test_tmdb_v4_token_uses_bearer(patch_client):
    v4 = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig"
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        captured["api_key"] = request.url.params.get("api_key")
        return httpx.Response(200, json={"images": {}})

    with patch_client(handler):
        result = await connectivity.test_tmdb("", v4)
    assert result["ok"] is True
    assert captured["auth"] == f"Bearer {v4}"
    assert captured["api_key"] is None
    assert "v4" in result["msg_zh"]


async def test_tmdb_invalid_key(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"status_message": "Invalid API key"})

    with patch_client(handler):
        result = await connectivity.test_tmdb("", "bad")
    assert result["ok"] is False
    assert "密钥无效" in result["msg_zh"]


async def test_tmdb_network_error(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("reset by peer", request=request)

    with patch_client(handler):
        result = await connectivity.test_tmdb("", "v3key")
    assert result["ok"] is False
    assert "无法建立连接" in result["msg_zh"]
    assert result["detail"] == "ConnectError"


async def test_tmdb_masked_key_falls_back_to_settings():
    """表单密钥为掩码时回退到已保存配置（复用 _unmask 逻辑验证）。"""
    assert connectivity._unmask("********", "saved") == "saved"
    assert connectivity._unmask("", "saved") == "saved"
    assert connectivity._unmask("new", "saved") == "new"


# ---------------------------------------------------------------------------
# Bangumi API
# ---------------------------------------------------------------------------


async def test_bgm_ok(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/calendar"
        return httpx.Response(200, json=[{}, {}, {}])

    with patch_client(handler):
        result = await connectivity.test_bgm("")
    assert result["ok"] is True
    assert result["detail"] == "3 天日历数据"


async def test_bgm_custom_base_url(patch_client):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json=[])

    with patch_client(handler):
        await connectivity.test_bgm("https://mirror.example/")
    assert captured["url"].startswith("https://mirror.example/calendar")


async def test_bgm_unreachable(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("reset", request=request)

    with patch_client(handler):
        result = await connectivity.test_bgm("")
    assert result["ok"] is False
    assert "无法建立连接" in result["msg_zh"]


async def test_bgm_server_error(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with patch_client(handler):
        result = await connectivity.test_bgm("")
    assert result["ok"] is False
    assert "503" in result["msg_zh"]


# ---------------------------------------------------------------------------
# qBittorrent
# ---------------------------------------------------------------------------


async def test_qbittorrent_ok(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(200, text="Ok.")
        if request.url.path == "/api/v2/app/version":
            return httpx.Response(200, text="v5.0.0")
        return httpx.Response(404)

    with patch_client(handler):
        result = await connectivity.test_downloader(
            "qbittorrent", "192.168.1.10:8080", "admin", "pass"
        )
    assert result["ok"] is True
    assert result["detail"] == "qBittorrent v5.0.0"


async def test_qbittorrent_204_new_version(patch_client):
    """qB >= 5.2 成功登录返回 204 空响应体。"""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v2/auth/login":
            return httpx.Response(204)
        return httpx.Response(404)

    with patch_client(handler):
        result = await connectivity.test_downloader(
            "qbittorrent", "http://192.168.1.10:8080", "admin", "pass"
        )
    assert result["ok"] is True


async def test_qbittorrent_wrong_password(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Fails.")

    with patch_client(handler):
        result = await connectivity.test_downloader(
            "qbittorrent", "192.168.1.10:8080", "admin", "bad"
        )
    assert result["ok"] is False
    assert "密码错误" in result["msg_zh"]


async def test_qbittorrent_banned(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="banned")

    with patch_client(handler):
        result = await connectivity.test_downloader(
            "qbittorrent", "192.168.1.10:8080", "admin", "bad"
        )
    assert result["ok"] is False
    assert "403" in result["msg_zh"]


async def test_qbittorrent_unreachable(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with patch_client(handler):
        result = await connectivity.test_downloader(
            "qbittorrent", "192.168.1.10:9999", "admin", "x"
        )
    assert result["ok"] is False
    assert "无法建立连接" in result["msg_zh"]


# ---------------------------------------------------------------------------
# aria2
# ---------------------------------------------------------------------------


async def test_aria2_ok(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"result": {"version": "1.37.0"}, "id": "ab-test"}
        )

    with patch_client(handler):
        result = await connectivity.test_downloader(
            "aria2", "http://192.168.1.10:6800", "", "secret"
        )
    assert result["ok"] is True
    assert result["detail"] == "aria2 1.37.0"


async def test_aria2_bad_secret(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"error": {"code": 1, "message": "Unauthorized"}}
        )

    with patch_client(handler):
        result = await connectivity.test_downloader(
            "aria2", "192.168.1.10:6800", "", "bad"
        )
    assert result["ok"] is False
    assert "密钥" in result["msg_zh"]


# ---------------------------------------------------------------------------
# Jellyfin
# ---------------------------------------------------------------------------


async def test_jellyfin_ok(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-Emby-Token") == "jfkey"
        return httpx.Response(
            200, json={"ServerName": "nas", "Version": "10.9.0"}
        )

    with patch_client(handler):
        result = await connectivity.test_jellyfin("http://192.168.1.10:8096/", "jfkey")
    assert result["ok"] is True
    assert result["detail"] == "nas 10.9.0"


async def test_jellyfin_bad_key(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    with patch_client(handler):
        result = await connectivity.test_jellyfin("192.168.1.10:8096", "bad")
    assert result["ok"] is False
    assert "密钥无效" in result["msg_zh"]


async def test_jellyfin_unreachable(patch_client):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    with patch_client(handler):
        result = await connectivity.test_jellyfin("192.168.1.10:8096", "k")
    assert result["ok"] is False
    assert "超时" in result["msg_zh"]


# ---------------------------------------------------------------------------
# API endpoints（鉴权 + 载荷透传）
# ---------------------------------------------------------------------------


@pytest.fixture
def authed_client():
    app = FastAPI()
    app.include_router(v1, prefix="/api")

    async def mock_user():
        return "testuser"

    app.dependency_overrides[get_current_user] = mock_user
    app.dependency_overrides[get_context] = lambda: None
    with TestClient(app) as client:
        yield client


def test_endpoints_require_auth():
    from module.api.config import router

    routes = {r.path: r for r in router.routes}
    for path in (
        "/config/test/tmdb",
        "/config/test/bgm",
        "/config/test/downloader",
        "/config/test/jellyfin",
    ):
        assert path in routes, f"missing route {path}"
        deps = routes[path].dependencies
        assert any(d.dependency is get_current_user for d in deps), path


def test_tmdb_endpoint_passes_payload(authed_client):
    async def fake_test(base_url, api_key):
        assert base_url == "https://api.example"
        assert api_key == "********"
        return {"ok": True, "latency_ms": 12, "msg_zh": "z", "msg_en": "e",
                "detail": None}

    with patch("module.manager.connectivity.test_tmdb", fake_test):
        resp = authed_client.post(
            "/api/v1/config/test/tmdb",
            json={"tmdb_base_url": "https://api.example", "tmdb_api_key": "********"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] is True
    assert body["ok"] is True
    assert body["latency_ms"] == 12


def test_downloader_endpoint_passes_payload(authed_client):
    async def fake_test(dl_type, host, username, password):
        assert (dl_type, host, username) == ("qbittorrent", "h", "u")
        return {"ok": False, "latency_ms": 3, "msg_zh": "z", "msg_en": "e",
                "detail": None}

    with patch("module.manager.connectivity.test_downloader", fake_test):
        resp = authed_client.post(
            "/api/v1/config/test/downloader",
            json={"type": "qbittorrent", "host": "h", "username": "u",
                  "password": ""},
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


# ---------------------------------------------------------------------------
# 空表单值回退已保存配置（host/username 也回退，与密钥行为一致）
# ---------------------------------------------------------------------------


async def test_downloader_empty_form_falls_back_to_settings():
    assert connectivity._unmask("", "saved") == "saved"


async def test_jellyfin_empty_host_uses_saved(monkeypatch):
    """空 host 回退到已保存的 Jellyfin 地址（media_library.host 属性）。"""
    from types import SimpleNamespace

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"ServerName": "s", "Version": "1"})

    saved = SimpleNamespace(host="http://192.168.1.10:8096", api_key="savedkey")
    monkeypatch.setattr(connectivity.settings, "media_library", saved)
    with patch.object(connectivity, "_client", lambda **kw: _mock_client(handler)):
        result = await connectivity.test_jellyfin("", "********")
    assert result["ok"] is True
    assert captured["url"].startswith("http://192.168.1.10:8096/System/Info")
