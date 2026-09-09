"""设置页连通性测试：TMDB / 下载器 / Jellyfin。

设计要点：
- 短超时、单次尝试 —— 用户点一下按钮就该尽快拿到结果，不能沿用共享
  客户端的 3 次重试 × 5s 退避。
- 走 ``build_proxy_url()`` —— 与应用实际请求同一代理配置，测出来的是
  "应用视角"的连通性，而不是裸网络连通性。
- 区分三类失败：网络不通（DNS/TCP/TLS/超时）、认证失败（key/密码错）、
  服务端拒绝（4xx/5xx 其他），给用户可操作的提示。
- 下载器测试绝不重试认证 —— qBittorrent 默认 5 次失败即封禁来源 IP。
"""

import logging
import time

import httpx

from module.conf import TMDB_API, settings
from module.network.request_url import build_proxy_url

logger = logging.getLogger(__name__)

# 与 api/config.py 的敏感字段掩码一致：表单未改动的已保存密钥传上来是掩码
MASK = "********"

_TIMEOUT = httpx.Timeout(connect=5.0, read=8.0, write=5.0, pool=5.0)


def _client(use_proxy: bool, verify: bool = True) -> httpx.AsyncClient:
    """构造测试客户端，行为对齐各服务的真实客户端：

    - trust_env=False：不读系统/环境变量代理（Windows 下会把注册表里的
      系统代理套用到所有地址，内网服务经代理转发会挂起）。
    - TMDB 走共享 RequestContent 客户端 → 跟随应用代理设置；
      下载器/Jellyfin 在应用里都自建客户端（不走代理、qB 还关了证书
      校验），测试保持一致，否则"测试通过但应用不通"或反之。
    """
    kwargs: dict = {
        "timeout": _TIMEOUT,
        "follow_redirects": True,
        "trust_env": False,
        "verify": verify,
    }
    if use_proxy:
        proxy_url = build_proxy_url()
        if proxy_url:
            if proxy_url.startswith("socks5://"):
                from httpx_socks import AsyncProxyTransport

                kwargs["transport"] = AsyncProxyTransport.from_url(
                    proxy_url, rdns=True
                )
            else:
                kwargs["proxy"] = proxy_url
    return httpx.AsyncClient(**kwargs)


def _result(
    ok: bool, latency_ms: int, msg_zh: str, msg_en: str, detail: str | None = None
) -> dict:
    return {
        "ok": ok,
        "latency_ms": latency_ms,
        "msg_zh": msg_zh,
        "msg_en": msg_en,
        "detail": detail,
    }


def _network_error(e: Exception, latency_ms: int) -> dict:
    kind = type(e).__name__
    if isinstance(e, httpx.TimeoutException):
        hint_zh = "连接超时，请检查地址/端口是否正确（需要代理的服务请先在代理设置中开启）"
        hint_en = (
            "Connection timed out. Check the address/port (enable the proxy in proxy settings if the service needs one)."
        )
    else:
        hint_zh = "无法建立连接，请检查地址与端口、或代理设置"
        hint_en = "Unable to connect. Check the address/port or proxy settings."
    return _result(False, latency_ms, hint_zh, hint_en, detail=kind)


def _normalize_host(host: str) -> str:
    host = host.strip().rstrip("/")
    if "://" not in host:
        host = f"http://{host}"
    return host


def _unmask(form_value: str, saved_value: str) -> str:
    """表单密钥是掩码（未改动已保存值）或为空时，回退到已保存配置。"""
    if not form_value or form_value == MASK:
        return saved_value
    return form_value


def _is_v4_token(key: str) -> bool:
    return key.startswith("eyJ") and key.count(".") == 2


async def test_tmdb(base_url: str, api_key: str) -> dict:
    """按应用真实调用方式（v3 参数 / v4 Bearer）探测 /3/configuration。"""
    base = (base_url or "").strip().rstrip("/") or "https://api.themoviedb.org"
    key = _unmask(api_key, settings.network.tmdb_api_key) or TMDB_API
    key_kind = "v4" if _is_v4_token(key) else "v3"

    url = f"{base}/3/configuration"
    headers: dict = {}
    params: dict = {}
    if key_kind == "v4":
        headers["Authorization"] = f"Bearer {key}"
    else:
        params["api_key"] = key

    start = time.perf_counter()
    try:
        async with _client(use_proxy=True) as client:
            resp = await client.get(url, headers=headers, params=params)
        latency = int((time.perf_counter() - start) * 1000)
    except httpx.RequestError as e:
        logger.info("TMDB connectivity test failed: %s: %s", type(e).__name__, e)
        return _network_error(e, int((time.perf_counter() - start) * 1000))

    if resp.status_code == 200:
        return _result(
            True,
            latency,
            f"连接成功，{key_kind} 密钥有效",
            f"Connected. The {key_kind} key is valid.",
        )
    if resp.status_code in (401, 403):
        return _result(
            False,
            latency,
            f"可连通，但密钥无效（HTTP {resp.status_code}），请检查 API Key",
            f"Reachable, but the API key was rejected (HTTP {resp.status_code}).",
        )
    return _result(
        False,
        latency,
        f"服务端返回 HTTP {resp.status_code}",
        f"Server responded with HTTP {resp.status_code}.",
    )


async def test_bgm(base_url: str) -> dict:
    """探测 Bangumi.tv API（放送日历端点，与应用实际调用一致；无需鉴权）。"""
    base = (base_url or "").strip().rstrip("/") or "https://api.bgm.tv"
    url = f"{base}/calendar"

    start = time.perf_counter()
    try:
        async with _client(use_proxy=True) as client:
            resp = await client.get(url)
        latency = int((time.perf_counter() - start) * 1000)
    except httpx.RequestError as e:
        logger.info("bgm connectivity test failed: %s: %s", type(e).__name__, e)
        return _network_error(e, int((time.perf_counter() - start) * 1000))

    if resp.status_code == 200:
        try:
            days = len(resp.json())
        except ValueError:
            days = 0
        return _result(
            True,
            latency,
            "连接成功",
            "Connected.",
            detail=f"{days} 天日历数据" if days else None,
        )
    return _result(
        False,
        latency,
        f"服务端返回 HTTP {resp.status_code}，请确认这是 Bangumi API 地址",
        f"Server responded with HTTP {resp.status_code}; is this a Bangumi API address?",
    )


async def test_downloader(dl_type: str, host: str, username: str, password: str) -> dict:
    host = _normalize_host(host or "")
    password = _unmask(password, settings.downloader.password)

    start = time.perf_counter()
    if dl_type == "aria2":
        return await _test_aria2(host, password, start)
    return await _test_qbittorrent(host, username, password, start)


async def _test_qbittorrent(host: str, username: str, password: str, start: float) -> dict:
    try:
        # verify=False：与 qb_downloader._new_client 一致（NAS 自签证书常态）
        async with _client(use_proxy=False, verify=False) as client:
            # 单次尝试，绝不重试：qB 默认 5 次认证失败即封禁来源 IP
            resp = await client.post(
                f"{host}/api/v2/auth/login",
                data={"username": username, "password": password},
            )
            latency = int((time.perf_counter() - start) * 1000)
            ok = (resp.status_code == 200 and resp.text.startswith("Ok")) or (
                resp.status_code == 204
            )
            version = None
            if ok:
                ver_resp = await client.get(f"{host}/api/v2/app/version")
                if ver_resp.status_code == 200:
                    version = ver_resp.text.strip()
    except httpx.RequestError as e:
        return _network_error(e, int((time.perf_counter() - start) * 1000))

    if ok:
        return _result(
            True,
            latency,
            "连接成功，认证通过",
            "Connected and authenticated.",
            detail=f"qBittorrent {version}" if version else None,
        )
    if resp.status_code in (200, 401) or resp.text.startswith("Fails"):
        return _result(
            False,
            latency,
            "可连通，但用户名或密码错误",
            "Reachable, but the username or password is wrong.",
        )
    if resp.status_code == 403:
        return _result(
            False,
            latency,
            "可连通，但认证被拒绝（HTTP 403）——可能因多次失败被 qBittorrent 封禁了本机 IP",
            "Reachable but rejected (HTTP 403) — this IP may be banned by qBittorrent after failed logins.",
        )
    return _result(
        False,
        latency,
        f"服务端返回 HTTP {resp.status_code}，请确认这是 qBittorrent 地址",
        f"Server responded with HTTP {resp.status_code}; is this a qBittorrent address?",
    )


async def _test_aria2(host: str, secret: str, start: float) -> dict:
    try:
        async with _client(use_proxy=False) as client:
            resp = await client.post(
                f"{host}/jsonrpc",
                json={
                    "jsonrpc": "2.0",
                    "id": "ab-test",
                    "method": "aria2.getVersion",
                    "params": [f"token:{secret}"],
                },
            )
            latency = int((time.perf_counter() - start) * 1000)
    except httpx.RequestError as e:
        return _network_error(e, int((time.perf_counter() - start) * 1000))

    try:
        body = resp.json()
    except ValueError:
        return _result(
            False,
            latency,
            f"返回了非 JSON 内容（HTTP {resp.status_code}），请确认这是 aria2 RPC 地址",
            f"Non-JSON response (HTTP {resp.status_code}); is this an aria2 RPC address?",
        )

    if "result" in body:
        version = (body.get("result") or {}).get("version")
        return _result(
            True,
            latency,
            "连接成功，RPC 令牌有效",
            "Connected. The RPC secret is valid.",
            detail=f"aria2 {version}" if version else None,
        )
    err = body.get("error") or {}
    if err.get("message") == "Unauthorized":
        return _result(
            False,
            latency,
            "可连通，但 RPC 密钥（密码）错误",
            "Reachable, but the RPC secret (password) is wrong.",
        )
    return _result(
        False,
        latency,
        f"RPC 错误：{err.get('message', body)}",
        f"RPC error: {err.get('message', body)}",
    )


async def test_jellyfin(host: str, api_key: str) -> dict:
    host = _normalize_host(host or "")
    api_key = _unmask(api_key, settings.media_library.api_key)

    start = time.perf_counter()
    try:
        async with _client(use_proxy=False) as client:
            # 与 JellyfinClient 一致：X-Emby-Token 头
            resp = await client.get(
                f"{host}/System/Info", headers={"X-Emby-Token": api_key}
            )
        latency = int((time.perf_counter() - start) * 1000)
    except httpx.RequestError as e:
        return _network_error(e, int((time.perf_counter() - start) * 1000))

    if resp.status_code == 200:
        info = {}
        try:
            info = resp.json()
        except ValueError:
            pass
        server = info.get("ServerName") or ""
        version = info.get("Version") or ""
        detail = " ".join(x for x in (server, version) if x) or None
        return _result(
            True,
            latency,
            "连接成功，API 密钥有效",
            "Connected. The API key is valid.",
            detail=detail,
        )
    if resp.status_code in (401, 403):
        return _result(
            False,
            latency,
            f"可连通，但 API 密钥无效（HTTP {resp.status_code}）",
            f"Reachable, but the API key was rejected (HTTP {resp.status_code}).",
        )
    return _result(
        False,
        latency,
        f"服务端返回 HTTP {resp.status_code}，请确认这是 Jellyfin 地址",
        f"Server responded with HTTP {resp.status_code}; is this a Jellyfin address?",
    )
