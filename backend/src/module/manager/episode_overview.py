"""RSS 订阅剧集总览服务。

把一个 RSS 订阅源（拉取实时报文 + 本地已存记录）按番剧、按集聚合：

- 总共有哪些集可以下载（实时解析 RSS 报文里的种子）；
- 哪些集数已经下载（本地 ``torrent.downloaded``）；
- 哪些集数已经在 Jellyfin 媒体库里（可选，需在设置中启用）；
- 每集的 TMDB 放送日期（自动获取）；
- 支持对手动选中的种子单个/批量下载（按 id 或 URL）。
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

from module.conf import settings
from module.database import Database
from module.downloader import AddResult, DownloadClient
from module.manager.medialibrary import JellyfinClient
from module.models import (
    Bangumi,
    BangumiEpisodeGroup,
    EpisodeEntry,
    EpisodeOverview,
    EpisodeStatusRequest,
    EpisodeTorrentInfo,
    ResponseModel,
    Torrent,
)
from module.network import RequestContent
from module.parser.analyser.raw_parser import raw_parser
from module.parser.analyser.tmdb_parser import (
    get_season_episode_air_dates,
    tmdb_parser,
)
from module.rss.engine import (
    RSSEngine,
    _interval_due,
    _parse_check_time,
    _parse_check_weekdays,
    _weekly_due,
)

logger = logging.getLogger(__name__)

# 放送日期获取的预算与缓存：TMDB 不可达时不能拖住剧集总览弹窗
_AIR_DATE_BUDGET = 5.0  # 每次请求的总时间预算（秒）
_AIR_DATE_TTL_OK = 24 * 3600  # 成功结果缓存 24h
_AIR_DATE_TTL_FAIL = 600  # 失败结果缓存 10min，避免死循环重试
_air_date_cache: dict[
    tuple[str, int, str], tuple[float, dict[int, str] | None]
] = {}


class EpisodeOverviewService:
    def __init__(self, db: Database):
        self.db = db

    # ---------- 内部工具 ----------

    @staticmethod
    def _new_group(bangumi: Bangumi) -> BangumiEpisodeGroup:
        return BangumiEpisodeGroup(
            bangumi_id=bangumi.id,
            official_title=bangumi.official_title,
            season=bangumi.season,
            poster_link=bangumi.poster_link,
            check_interval=bangumi.check_interval,
        )

    async def _live_and_stored(self, rss) -> tuple[list[Torrent], dict[str, Torrent]]:
        """拉取实时报文并与本地记录合并（保留 id/downloaded/bangumi_id）。"""
        engine = RSSEngine(self.db)
        try:
            live_torrents = await engine._get_torrents(rss)
        except Exception as e:
            logger.warning("Failed to fetch RSS feed %s: %s", rss.name, e)
            live_torrents = []
        stored = await self.db.torrent.search_rss(rss.id)
        stored_by_url: dict[str, Torrent] = {}
        for torrent in stored:
            old = stored_by_url.get(torrent.url)
            if old is None:
                stored_by_url[torrent.url] = torrent
            else:
                # 同 URL 的重复历史行：合并已下载标记，保留最小 id 作稳定身份
                old.downloaded = old.downloaded or torrent.downloaded
                if torrent.id is not None and (old.id is None or torrent.id < old.id):
                    old.id, torrent.id = torrent.id, old.id
        bangumi_list = await self.db.bangumi.search_all()
        merged: list[Torrent] = []
        seen_urls: set[str] = set()
        for torrent in live_torrents:
            torrent.rss_id = rss.id
            old = stored_by_url.get(torrent.url)
            if old:
                torrent.id = old.id
                torrent.downloaded = old.downloaded
                torrent.bangumi_id = old.bangumi_id
                # 旧记录可能是在番剧规则建立前入库的（bangumi_id 为空），
                # 规则存在时应重新匹配，避免历史种子永远卡在未匹配区
                if torrent.bangumi_id is None:
                    engine.match_torrent(torrent, bangumi_list)
            else:
                # 用与自动流程一致的匹配规则（含过滤器）关联番剧
                engine.match_torrent(torrent, bangumi_list)
            merged.append(torrent)
            seen_urls.add(torrent.url)
        # 本地有、报文已翻页看不到的记录也保留（历史下载）
        merged.extend(t for t in stored if t.url not in seen_urls)
        return merged, stored_by_url

    async def _apply_air_dates(self, groups: dict[int, BangumiEpisodeGroup]) -> None:
        """自动获取 TMDB 放送日期并写入对应分组。

        带总时间预算和 TTL 缓存：TMDB 不可达（如代理未开）时最多等
        ``_AIR_DATE_BUDGET`` 秒即放弃，日期留空显示"未知"，不阻塞弹窗。
        """
        language = settings.rss_parser.language or "zh"
        now = time.monotonic()

        # 先用缓存填充，剩下的才需要现场抓取
        pending: list[BangumiEpisodeGroup] = []
        for group in groups.values():
            if not group.official_title or not group.episodes:
                continue
            key = (group.official_title, group.season, language)
            hit = _air_date_cache.get(key)
            if hit is not None:
                ts, dates = hit
                ttl = _AIR_DATE_TTL_OK if dates is not None else _AIR_DATE_TTL_FAIL
                if now - ts <= ttl:
                    if dates:
                        for entry in group.episodes:
                            entry.air_date = dates.get(int(entry.episode))
                    continue
            pending.append(group)
        if not pending:
            return

        async def _fetch_group(group: BangumiEpisodeGroup, req: RequestContent):
            key = (group.official_title, group.season, language)
            try:
                info = await tmdb_parser(group.official_title, language)
                if info is None:
                    _air_date_cache[key] = (time.monotonic(), None)
                    return
                air_dates = await get_season_episode_air_dates(
                    info.id, group.season, language, req
                )
                date_map = {
                    d["episode_number"]: d["air_date"].isoformat()
                    for d in air_dates
                }
                _air_date_cache[key] = (time.monotonic(), date_map)
                for entry in group.episodes:
                    entry.air_date = date_map.get(int(entry.episode))
            except Exception as e:
                logger.warning(
                    "Failed to fetch air dates for %s: %s",
                    group.official_title,
                    e,
                )
                _air_date_cache[key] = (time.monotonic(), None)

        try:
            async with asyncio.timeout(_AIR_DATE_BUDGET):
                async with RequestContent() as req:
                    for group in pending:
                        await _fetch_group(group, req)
        except TimeoutError:
            # 预算耗尽：被取消的分组记入失败缓存，避免每次打开都重试。
            # 注意不能用 finally 标记"已完成"——超时取消同样会触发 finally。
            for group in pending:
                key = (group.official_title, group.season, language)
                _air_date_cache.setdefault(key, (time.monotonic(), None))
            logger.warning(
                "Air date fetch exceeded %.1fs budget; showing unknown dates.",
                _AIR_DATE_BUDGET,
            )

    @staticmethod
    def _jellyfin_client() -> JellyfinClient | None:
        conf = settings.media_library
        if not conf.configured():
            return None
        return JellyfinClient(conf.host, conf.api_key)

    # ---------- 下载前按 Jellyfin 过滤（订阅/追新共用） ----------

    async def filter_in_library(
        self, torrents: list[Torrent]
    ) -> tuple[list[Torrent], list[Torrent]]:
        """把种子分成 (不在库, 已在库)。

        按番剧分组查一次 Jellyfin 分集集合再整组比对；任何失败
        （未启用/未配置/找不到剧集/接口错误）都按"不在库"处理，
        对应种子照常下载——宁可重复下载也不漏。
        """
        client = self._jellyfin_client()
        if client is None:
            return torrents, []

        bangumi_ids = {t.bangumi_id for t in torrents if t.bangumi_id}
        ep_sets: dict[int, set[tuple[int, int]]] = {}
        for bid in bangumi_ids:
            bangumi = await self.db.bangumi.search_id(bid)
            if bangumi is None or not bangumi.official_title:
                continue
            try:
                ep_sets[bid] = await client.get_episode_set(bangumi.official_title)
            except Exception as e:
                logger.warning(
                    "Jellyfin lookup failed for %s: %s",
                    bangumi.official_title,
                    e,
                )

        def _in_library(t: Torrent) -> bool:
            if t.bangumi_id is None or t.bangumi_id not in ep_sets:
                return False
            ep_set = ep_sets[t.bangumi_id]
            if not ep_set:
                return False
            parsed = raw_parser(t.name)
            if parsed is None or parsed.episode is None:
                return False
            ep_int = int(parsed.episode)
            # 与剧集总览相同的比对规则：季+集精确，季号不符按集号兜底
            return (parsed.season, ep_int) in ep_set or any(
                ep == ep_int for _, ep in ep_set
            )

        keep = [t for t in torrents if not _in_library(t)]
        skipped = [t for t in torrents if _in_library(t)]
        if skipped:
            logger.info(
                "Skipped %s torrents already in Jellyfin: %s",
                len(skipped),
                ", ".join(t.name[:40] for t in skipped[:5]),
            )
        return keep, skipped

    # ---------- 对外接口 ----------

    @staticmethod
    def _cache_stale(
        bangumis: list[Bangumi], built_at: datetime, now: datetime
    ) -> bool:
        """缓存是否到期：按各番剧的检查计划（last = 缓存构建时间）判断。

        无检查计划的番剧跟随全局轮询周期（program.rss_time）。
        """
        ttl = settings.program.rss_time
        for bangumi in bangumis:
            weekdays = _parse_check_weekdays(bangumi.check_weekdays)
            check_hm = _parse_check_time(bangumi.check_time)
            if weekdays and check_hm is not None:
                if _weekly_due(now, weekdays, check_hm, built_at):
                    return True
            elif bangumi.check_interval and bangumi.check_interval > 0:
                if _interval_due(now, bangumi.check_interval, built_at):
                    return True
            elif _interval_due(now, ttl, built_at):
                return True
        return False

    async def overview(
        self, rss_id: int, force: bool = False
    ) -> EpisodeOverview | None:
        """剧集总览：优先读缓存。

        缓存在该订阅的检查计划（间隔/每周定时，无计划则全局轮询周期）
        到期后自动重建；``force=True``（手动刷新）立即重建并更新缓存。
        """
        rss = await self.db.rss.search_id(rss_id)
        if not rss:
            return None
        now = datetime.now(timezone.utc)

        if not force:
            cache = await self.db.episode_cache.get(rss_id)
            if cache and cache.payload:
                try:
                    cached = EpisodeOverview.parse_raw(cache.payload)
                    built_at = datetime.fromisoformat(cache.built_at)
                    if built_at.tzinfo is None:
                        built_at = built_at.replace(tzinfo=timezone.utc)
                except ValueError:
                    cached = None
                    built_at = None
                if cached is not None and built_at is not None:
                    ids = [
                        g.bangumi_id
                        for g in cached.groups
                        if g.bangumi_id is not None
                    ]
                    bangumis = (
                        await self.db.bangumi.search_ids(ids) if ids else []
                    )
                    if not self._cache_stale(bangumis, built_at, now):
                        cached.cached_at = cache.built_at
                        return cached

        overview = await self._build_overview(rss)
        if overview is None:
            return None
        built_iso = now.isoformat()
        overview.cached_at = built_iso
        await self.db.episode_cache.save(rss_id, overview.json(), built_iso)
        return overview

    async def _build_overview(self, rss) -> EpisodeOverview | None:
        merged, _ = await self._live_and_stored(rss)
        bangumi_list = await self.db.bangumi.search_all()
        bangumi_by_id = {b.id: b for b in bangumi_list if b.id is not None}

        groups: dict[int, BangumiEpisodeGroup] = {}
        orphan_group = BangumiEpisodeGroup(bangumi_id=None, official_title=None)

        for torrent in merged:
            parsed = raw_parser(torrent.name)
            info = EpisodeTorrentInfo(
                id=torrent.id,
                name=torrent.name,
                url=torrent.url,
                group=parsed.group if parsed else None,
                resolution=parsed.resolution if parsed else None,
                downloaded=torrent.downloaded,
            )
            bangumi = bangumi_by_id.get(torrent.bangumi_id)
            # 未匹配番剧、或解析不出集数的种子进入 unparsed 列表
            if bangumi is None or parsed is None or parsed.episode is None:
                if bangumi is not None:
                    group = groups.setdefault(bangumi.id, self._new_group(bangumi))
                    group.unparsed.append(info)
                else:
                    orphan_group.unparsed.append(info)
                continue

            group = groups.get(bangumi.id)
            if group is None:
                group = groups[bangumi.id] = self._new_group(bangumi)
            key = (parsed.season, parsed.episode)
            entry = next(
                (e for e in group.episodes if (e.season, e.episode) == key), None
            )
            if entry is None:
                entry = EpisodeEntry(season=parsed.season, episode=parsed.episode)
                group.episodes.append(entry)
            entry.torrents.append(info)
            if torrent.downloaded:
                entry.downloaded = True

        jellyfin_available = False
        if groups:
            await self._apply_air_dates(groups)
            jf_client = self._jellyfin_client()
            if jf_client is not None:
                jellyfin_available = True
                for group in groups.values():
                    if not group.official_title:
                        continue
                    ep_set = await jf_client.get_episode_set(group.official_title)
                    if not ep_set:
                        continue
                    for entry in group.episodes:
                        ep_int = int(entry.episode)
                        # 精确匹配季+集；季号对不上时按集号兜底
                        entry.in_library = (entry.season, ep_int) in ep_set or any(
                            ep == ep_int for _, ep in ep_set
                        )
                        entry.auto_in_library = entry.in_library

        # 手动覆盖优先于 Jellyfin 自动比对结果
        overrides = await self.db.episode_override.search_all()
        if overrides:
            override_map = {
                (o.bangumi_id, o.season, float(o.episode)): o.in_library
                for o in overrides
            }
            for group in groups.values():
                if group.bangumi_id is None:
                    continue
                for entry in group.episodes:
                    key = (group.bangumi_id, entry.season, float(entry.episode))
                    if key in override_map:
                        entry.in_library = override_map[key]
                        entry.manual = True

        for group in list(groups.values()) + [orphan_group]:
            group.episodes.sort(key=lambda e: (e.season, e.episode))

        result_groups = list(groups.values())
        if orphan_group.unparsed:
            result_groups.append(orphan_group)
        return EpisodeOverview(
            jellyfin_available=jellyfin_available, groups=result_groups
        )

    async def set_status(self, rss_id: int, req: EpisodeStatusRequest) -> ResponseModel:
        """手动修改剧集标签。

        - ``in_library``：写入/更新覆盖值（按番剧+季+集）；
        - ``reset_in_library``：清除单集覆盖，恢复自动比对；
        - ``reset_all``：清除该订阅下所有番剧的覆盖；
        - ``set_downloaded`` + ``urls``：直接改种子记录的已下载标记。
        """
        rss = await self.db.rss.search_id(rss_id)
        if not rss:
            return ResponseModel(
                status_code=404,
                status=False,
                msg_en="RSS not found.",
                msg_zh="未找到该 RSS 订阅。",
            )
        if (
            req.in_library is None
            and not req.reset_in_library
            and not req.reset_all
            and not req.reset_urls
            and not req.reset_episodes
            and (req.set_downloaded is None or not req.urls)
        ):
            return ResponseModel(
                status_code=406,
                status=False,
                msg_en="Nothing to update.",
                msg_zh="没有需要更新的内容。",
            )

        if req.reset_all:
            merged, _ = await self._live_and_stored(rss)
            bangumi_ids = {t.bangumi_id for t in merged if t.bangumi_id}
            await self.db.episode_override.delete_by_bangumi_ids(list(bangumi_ids))
        elif req.reset_episodes:
            # 前端直接给出番剧+季+集，纯数据库操作，无需拉取报文
            for ref in req.reset_episodes:
                await self.db.episode_override.delete_one(
                    ref.bangumi_id, ref.season, ref.episode
                )
        elif req.reset_urls:
            # 只重置勾选种子对应的剧集覆盖
            merged, _ = await self._live_and_stored(rss)
            url_set = set(req.reset_urls)
            seen: set[tuple[int, int, float]] = set()
            for torrent in merged:
                if torrent.url not in url_set or torrent.bangumi_id is None:
                    continue
                parsed = raw_parser(torrent.name)
                if parsed is None or parsed.episode is None:
                    continue
                key = (torrent.bangumi_id, parsed.season, parsed.episode)
                if key in seen:
                    continue
                seen.add(key)
                await self.db.episode_override.delete_one(*key)
        elif req.reset_in_library and req.bangumi_id and req.episode is not None:
            await self.db.episode_override.delete_one(
                req.bangumi_id, req.season, req.episode
            )
        elif req.in_library is not None and req.bangumi_id and req.episode is not None:
            await self.db.episode_override.upsert(
                req.bangumi_id, req.season, req.episode, req.in_library
            )

        if req.set_downloaded is not None and req.urls:
            merged, _ = await self._live_and_stored(rss)
            url_set = set(req.urls)
            targets = [t for t in merged if t.url in url_set]
            for torrent in targets:
                torrent.downloaded = req.set_downloaded
            # 按 URL 批量更新：同 URL 的重复历史行一并改写，
            # 否则标签刚翻转就会被旧行拉回
            await self.db.torrent.update_downloaded_by_urls(
                req.urls, req.set_downloaded
            )

        # 标签/下载状态已变化，缓存过期，下次读取时重建
        await self.db.episode_cache.delete(rss_id)
        return ResponseModel(
            status_code=200,
            status=True,
            msg_en="Episode status updated.",
            msg_zh="已更新剧集标签。",
        )

    async def _dispatch(self, torrents: list[Torrent]) -> tuple[int, int]:
        """把种子逐个投递到下载器，返回 (成功, 失败)。

        未匹配番剧的种子没有规则/路径/重命名信息，构造占位 Bangumi
        落到下载器根目录，保证手动下载仍然可用。
        """
        ok = failed = 0
        async with DownloadClient() as client:
            for torrent in torrents:
                bangumi = (
                    await self.db.bangumi.search_id(torrent.bangumi_id)
                    if torrent.bangumi_id
                    else None
                )
                if bangumi is None:
                    bangumi = Bangumi(official_title=torrent.name)
                    bangumi.save_path = settings.downloader.path
                result = await client.add_torrent(torrent, bangumi)
                if result is AddResult.FAILED:
                    failed += 1
                else:
                    torrent.downloaded = True
                    ok += 1
        return ok, failed

    async def download_torrents(self, torrent_ids: list[int]) -> ResponseModel:
        """按种子 id 手动（单个/批量）下载已入库的种子。"""
        if not torrent_ids:
            return ResponseModel(
                status=False,
                status_code=406,
                msg_en="No torrent selected.",
                msg_zh="未选择任何种子。",
            )
        torrents = await self.db.torrent.search_by_ids(torrent_ids)
        targets = [t for t in torrents if not t.downloaded]
        if not targets:
            return ResponseModel(
                status=True,
                status_code=200,
                msg_en="All torrents already downloaded.",
                msg_zh="所选种子均已下载。",
            )
        ok, failed = await self._dispatch(targets)
        await self.db.torrent.upsert_all(targets)
        # 清除对应订阅的总览缓存，让下次打开看到最新下载状态
        for rid in {t.rss_id for t in targets if t.rss_id}:
            await self.db.episode_cache.delete(rid)
        if failed:
            return ResponseModel(
                status=False,
                status_code=502,
                msg_en=f"Downloaded {ok}, failed {failed}.",
                msg_zh=f"成功下载 {ok} 个，失败 {failed} 个。",
            )
        return ResponseModel(
            status=True,
            status_code=200,
            msg_en=f"Downloaded {ok} torrents successfully.",
            msg_zh=f"成功下载 {ok} 个种子。",
        )

    async def download_by_url(self, rss_id: int, urls: list[str]) -> ResponseModel:
        """按 URL 手动（单个/批量）下载实时报文中的种子。"""
        if not urls:
            return ResponseModel(
                status=False,
                status_code=406,
                msg_en="No torrent selected.",
                msg_zh="未选择任何种子。",
            )
        rss = await self.db.rss.search_id(rss_id)
        if not rss:
            return ResponseModel(
                status=False,
                status_code=404,
                msg_en="RSS not found.",
                msg_zh="未找到该 RSS 订阅。",
            )
        merged, stored_by_url = await self._live_and_stored(rss)
        url_set = set(urls)
        candidates: list[Torrent] = []
        for torrent in merged:
            if torrent.url not in url_set:
                continue
            if torrent.downloaded:
                continue
            candidates.append(torrent)
        if not candidates:
            return ResponseModel(
                status=True,
                status_code=200,
                msg_en="No downloadable torrent matched.",
                msg_zh="没有可下载的种子（可能均已下载）。",
            )
        ok, failed = await self._dispatch(candidates)
        await self.db.torrent.upsert_all(candidates)
        await self.db.episode_cache.delete(rss_id)
        if failed:
            return ResponseModel(
                status=False,
                status_code=502,
                msg_en=f"Downloaded {ok}, failed {failed}.",
                msg_zh=f"成功下载 {ok} 个，失败 {failed} 个。",
            )
        return ResponseModel(
            status=True,
            status_code=200,
            msg_en=f"Downloaded {ok} torrents successfully.",
            msg_zh=f"成功下载 {ok} 个种子。",
        )
