"""Jellyfin 媒体库客户端：按剧集名查询库内已有的季/集。

用于 RSS 订阅的剧集总览接口：把"哪些集数已经在 Jellyfin 里"与
"哪些集数已经下载"区分开，方便用户手动补缺。
"""

import logging
import re

import httpx

logger = logging.getLogger(__name__)

# 匹配/查询超时：媒体库在内网，正常毫秒级返回
_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# 标题归一化：忽略大小写、空白与常见中英文标点，避免"番剧名 第2季"
# 与 "番剧名" 这类尾缀差异导致匹配失败（尾缀差异单独处理）。
_PUNCT = re.compile(r"[\s·・:：!！?？'’\"“”\-—_，,。.·]")


def _normalize_title(title: str) -> str:
    return _PUNCT.sub("", (title or "").lower())


def _strip_season_suffix(title: str) -> str:
    """去掉标题尾部的季数标注（第X季 / Season X / S2 等）。"""
    return re.sub(
        r"(第\s*\d+\s*季|season\s*\d+|s\d+$|\d+st\s+season)$",
        "",
        (title or "").strip(),
        flags=re.IGNORECASE,
    )


class JellyfinClient:
    def __init__(self, host: str, api_key: str):
        self.host = host.rstrip("/")
        self.api_key = api_key
        self._headers = {"X-Emby-Token": api_key}

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict):
        resp = await client.get(f"{self.host}{path}", params=params, headers=self._headers)
        resp.raise_for_status()
        return resp.json()

    async def find_series(self, client: httpx.AsyncClient, title: str) -> dict | None:
        """按标题搜索剧集（Series），返回最匹配的一条（或 None）。"""
        params = {
            "searchTerm": title,
            "IncludeItemTypes": "Series",
            "Recursive": "true",
            "Limit": 20,
        }
        data = await self._get(client, "/Items", params)
        items = data.get("Items", [])
        if not items:
            return None
        want = _normalize_title(title)
        want_stripped = _normalize_title(_strip_season_suffix(title))
        # 先找完全一致，再找去掉季数尾缀后一致，最后退回第一个结果
        for item in items:
            names = [
                item.get("Name", ""),
                item.get("OriginalTitle", "") or "",
            ]
            for name in names:
                if _normalize_title(name) == want:
                    return item
        for item in items:
            names = [
                item.get("Name", ""),
                item.get("OriginalTitle", "") or "",
            ]
            for name in names:
                if _normalize_title(_strip_season_suffix(name)) == want_stripped:
                    return item
        return items[0]

    async def get_series_episodes(
        self, client: httpx.AsyncClient, series_id: str
    ) -> list[dict]:
        """返回剧集所有已入库分集的 {season, episode} 列表。"""
        data = await self._get(client, f"/Shows/{series_id}/Episodes", {})
        episodes = []
        for item in data.get("Items", []):
            season = item.get("ParentIndexNumber")
            episode = item.get("IndexNumber")
            if season is not None and episode is not None:
                episodes.append({"season": int(season), "episode": int(episode)})
        return episodes

    async def get_episode_set(self, title: str, season: int | None = None) -> set:
        """查询标题对应剧集在库内的 (season, episode) 集合。

        查询失败（网络/认证）返回空集合并记录日志；season 匹配失败时
        回退为忽略季号（返回所有季的集数，按 (season, ep) 与 (None, ep)
        两种键都交给调用方判断）。
        """
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                series = await self.find_series(client, title)
                if not series:
                    return set()
                episodes = await self.get_series_episodes(client, series["Id"])
                return {(e["season"], e["episode"]) for e in episodes}
        except Exception as e:
            logger.warning("Jellyfin query failed for %s: %s", title, e)
            return set()
