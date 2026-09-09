"""Tests for per-subscription check interval and episode overview service."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from module.database import Database
from module.manager.episode_overview import EpisodeOverviewService
from module.rss.engine import (
    RSSEngine,
    _bangumi_check_due,
    _rss_fetch_due,
)
from test.factories import make_bangumi, make_rss_item, make_torrent


@pytest_asyncio.fixture
async def db(db_engine):
    return Database(engine=db_engine)


# ---------------------------------------------------------------------------
# per-subscription check interval
# ---------------------------------------------------------------------------


class TestBangumiCheckDue:
    def test_no_interval_follows_global(self, monkeypatch):
        from datetime import datetime, timedelta, timezone

        from module.conf import settings

        monkeypatch.setattr(
            settings.program, "rss_time", 900, raising=False
        )
        now = datetime.now(timezone.utc)
        # 从未检查过 → 到期
        b = make_bangumi(check_interval=None, last_check_time=None)
        assert _bangumi_check_due(b, now) is True
        # 刚检查过（间隔未满）→ 未到期
        b = make_bangumi(
            check_interval=None,
            last_check_time=(now - timedelta(seconds=60)).isoformat(),
        )
        assert _bangumi_check_due(b, now) is False
        # 距上次检查超过 rss_time → 到期
        b = make_bangumi(
            check_interval=None,
            last_check_time=(now - timedelta(seconds=901)).isoformat(),
        )
        assert _bangumi_check_due(b, now) is True

    def test_interval_not_elapsed(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        b = make_bangumi(
            check_interval=3600, last_check_time=now.isoformat()
        )
        assert _bangumi_check_due(b, now) is False

    def test_interval_elapsed(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        b = make_bangumi(
            check_interval=600,
            last_check_time=(now - timedelta(seconds=601)).isoformat(),
        )
        assert _bangumi_check_due(b, now) is True

    def test_invalid_last_check_treated_as_due(self):
        from datetime import datetime, timezone

        b = make_bangumi(check_interval=600, last_check_time="not-a-date")
        assert _bangumi_check_due(b, datetime.now(timezone.utc)) is True

    def test_weekly_due_on_matching_weekday_after_time(self):
        from datetime import datetime, timezone

        # 2026-09-06 是周日（local weekday=6）；本地时区取系统时区
        now_local = datetime(2026, 9, 6, 21, 0).astimezone()
        now_utc = now_local.astimezone(timezone.utc)
        b = make_bangumi(
            check_weekdays="6",
            check_time="20:00",
            last_check_time=None,
        )
        assert _bangumi_check_due(b, now_utc) is True

    def test_weekly_not_due_before_time(self):
        from datetime import datetime, timezone

        now_local = datetime(2026, 9, 6, 10, 0).astimezone()
        now_utc = now_local.astimezone(timezone.utc)
        b = make_bangumi(check_weekdays="6", check_time="20:00")
        assert _bangumi_check_due(b, now_utc) is False

    def test_weekly_not_due_on_other_weekday(self):
        from datetime import datetime, timezone

        # 周日，但计划只查周一（0）
        now_local = datetime(2026, 9, 6, 21, 0).astimezone()
        now_utc = now_local.astimezone(timezone.utc)
        b = make_bangumi(check_weekdays="0", check_time="20:00")
        assert _bangumi_check_due(b, now_utc) is False

    def test_weekly_checked_today_not_due_again(self):
        from datetime import datetime, timezone

        # 今天 20:30 已检查过，21:00 不再到期
        now_local = datetime(2026, 9, 6, 21, 0).astimezone()
        last_local = datetime(2026, 9, 6, 20, 30).astimezone()
        b = make_bangumi(
            check_weekdays="6",
            check_time="20:00",
            last_check_time=last_local.astimezone(timezone.utc).isoformat(),
        )
        assert _bangumi_check_due(b, now_local.astimezone(timezone.utc)) is False

    def test_weekly_invalid_values_fall_back_to_interval(self):
        from datetime import datetime, timezone

        # 星期/时间非法 → 回退为间隔模式（interval 为空 = 跟随全局，恒到期）
        b = make_bangumi(check_weekdays="9", check_time="25:99")
        assert _bangumi_check_due(b, datetime.now(timezone.utc)) is True


# ---------------------------------------------------------------------------
# RSS feed fetch skip by check schedule
# ---------------------------------------------------------------------------

FEED_URL = "https://mikanani.me/RSS/Bangumi?bangumiId=1&subgroupId=2"


class TestRssFetchDue:
    def test_aggregate_feed_always_fetched(self):
        from datetime import datetime, timezone

        # 聚合源无法归属单一计划，恒抓取
        item = make_rss_item(aggregate=True)
        assert _rss_fetch_due(item, [], datetime.now(timezone.utc)) is True

    def test_feed_without_linked_bangumi_always_fetched(self):
        from datetime import datetime, timezone

        item = make_rss_item(url=FEED_URL, aggregate=False)
        bangumi = make_bangumi(rss_link="https://example.com/other.rss")
        assert _rss_fetch_due(item, [bangumi], datetime.now(timezone.utc)) is True

    def test_weekly_not_due_skips_fetch(self):
        from datetime import datetime, timezone

        now_local = datetime(2026, 9, 7, 12, 0).astimezone()  # 周一午间
        item = make_rss_item(url=FEED_URL, aggregate=False)
        # 计划周日 20:30，周一 12:00 未到计划日 → 跳过抓取
        bangumi = make_bangumi(
            rss_link=FEED_URL, check_weekdays="6", check_time="20:30"
        )
        assert _rss_fetch_due(item, [bangumi], now_local.astimezone(timezone.utc)) is False

    def test_weekly_due_fetches(self):
        from datetime import datetime, timezone

        now_local = datetime(2026, 9, 6, 21, 0).astimezone()  # 周日 21:00
        item = make_rss_item(url=FEED_URL, aggregate=False)
        bangumi = make_bangumi(
            rss_link=FEED_URL, check_weekdays="6", check_time="20:30"
        )
        assert _rss_fetch_due(item, [bangumi], now_local.astimezone(timezone.utc)) is True

    def test_interval_not_elapsed_skips_fetch(self):
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        item = make_rss_item(url=FEED_URL, aggregate=False)
        bangumi = make_bangumi(
            rss_link=FEED_URL,
            check_interval=3600,
            last_check_time=(now - timedelta(minutes=10)).isoformat(),
        )
        assert _rss_fetch_due(item, [bangumi], now) is False

    def test_deleted_rule_not_counted_as_linked(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        item = make_rss_item(url=FEED_URL, aggregate=False)
        bangumi = make_bangumi(
            rss_link=FEED_URL,
            deleted=True,
            check_interval=3600,
            last_check_time=now.isoformat(),
        )
        # 唯一关联规则已删除 → 视为无关联，保持抓取
        assert _rss_fetch_due(item, [bangumi], now) is True

    def test_mixed_rules_fetch_if_any_due(self):
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        item = make_rss_item(url=FEED_URL, aggregate=False)
        not_due = make_bangumi(
            rss_link=FEED_URL,
            check_interval=3600,
            last_check_time=now.isoformat(),
        )
        due = make_bangumi(rss_link=FEED_URL)
        assert _rss_fetch_due(item, [not_due, due], now) is True


# ---------------------------------------------------------------------------
# episode overview
# ---------------------------------------------------------------------------


def _feed_torrents():
    return [
        make_torrent(
            name="[TestGroup] Test Anime Raw - 01 [1080p].mkv",
            url="https://example.com/ep1.torrent",
        ),
        make_torrent(
            name="[TestGroup] Test Anime Raw - 02 [1080p].mkv",
            url="https://example.com/ep2.torrent",
        ),
        make_torrent(
            name="[TestGroup] Test Anime Raw - 02 [720p].mkv",
            url="https://example.com/ep2-720.torrent",
        ),
    ]


class TestEpisodeOverview:
    async def test_overview_groups_and_statuses(self, db):
        await db.rss.add(make_rss_item())
        bangumi = make_bangumi(filter="")
        await db.bangumi.add(bangumi)

        with patch.object(
            RSSEngine, "_get_torrents", new_callable=AsyncMock
        ) as mock_get, patch.object(
            EpisodeOverviewService, "_apply_air_dates", new_callable=AsyncMock
        ):
            mock_get.return_value = _feed_torrents()
            service = EpisodeOverviewService(db)
            overview = await service.overview(1)
            assert overview is not None

        assert overview is not None
        assert len(overview.groups) == 1
        group = overview.groups[0]
        assert group.official_title == "Test Anime"
        episodes = {(e.season, e.episode): e for e in group.episodes}
        assert (1, 1) in episodes and (1, 2) in episodes
        # 同一集的 1080p/720p 两个版本聚合到一个条目
        assert len(episodes[(1, 2)].torrents) == 2
        assert overview.jellyfin_available is False

    async def test_downloaded_flag_merged_from_db(self, db):
        await db.rss.add(make_rss_item())
        await db.bangumi.add(make_bangumi(filter=""))
        stored = make_torrent(
            name="[TestGroup] Test Anime Raw - 01 [1080p].mkv",
            url="https://example.com/ep1.torrent",
            rss_id=1,
            bangumi_id=1,
            downloaded=True,
        )
        await db.torrent.add(stored)

        with patch.object(
            RSSEngine, "_get_torrents", new_callable=AsyncMock
        ) as mock_get, patch.object(
            EpisodeOverviewService, "_apply_air_dates", new_callable=AsyncMock
        ):
            mock_get.return_value = _feed_torrents()
            service = EpisodeOverviewService(db)
            overview = await service.overview(1)
            assert overview is not None

        group = overview.groups[0]
        ep1 = next(e for e in group.episodes if e.episode == 1)
        assert ep1.downloaded is True
        ep2 = next(e for e in group.episodes if e.episode == 2)
        assert ep2.downloaded is False

    async def test_missing_rss_returns_none(self, db):
        service = EpisodeOverviewService(db)
        assert await service.overview(999) is None


# ---------------------------------------------------------------------------
# manual episode tag overrides
# ---------------------------------------------------------------------------


class TestEpisodeStatusOverride:
    async def test_set_and_apply_in_library_override(self, db):
        from module.models import EpisodeStatusRequest

        await db.rss.add(make_rss_item())
        await db.bangumi.add(make_bangumi(filter=""))

        with patch.object(
            RSSEngine, "_get_torrents", new_callable=AsyncMock
        ) as mock_get, patch.object(
            EpisodeOverviewService, "_apply_air_dates", new_callable=AsyncMock
        ):
            mock_get.return_value = _feed_torrents()
            service = EpisodeOverviewService(db)

            # 手动标记第 2 集为"已在库"
            resp = await service.set_status(
                1,
                EpisodeStatusRequest(
                    bangumi_id=1, season=1, episode=2, in_library=True
                ),
            )
            assert resp.status is True

            overview = await service.overview(1)

            assert overview is not None

        group = overview.groups[0]
        ep2 = next(e for e in group.episodes if e.episode == 2)
        assert ep2.in_library is True
        assert ep2.manual is True
        ep1 = next(e for e in group.episodes if e.episode == 1)
        assert ep1.in_library is False
        assert ep1.manual is False

    async def test_toggle_downloaded_by_urls(self, db):
        from module.models import EpisodeStatusRequest

        await db.rss.add(make_rss_item())
        await db.bangumi.add(make_bangumi(filter=""))

        with patch.object(
            RSSEngine, "_get_torrents", new_callable=AsyncMock
        ) as mock_get, patch.object(
            EpisodeOverviewService, "_apply_air_dates", new_callable=AsyncMock
        ):
            mock_get.return_value = _feed_torrents()
            service = EpisodeOverviewService(db)

            # 手动标记第 1 集为已下载（并未真正投递下载器）
            resp = await service.set_status(
                1,
                EpisodeStatusRequest(
                    set_downloaded=True, urls=["https://example.com/ep1.torrent"]
                ),
            )
            assert resp.status is True
            overview = await service.overview(1)
            assert overview is not None

        group = overview.groups[0]
        ep1 = next(e for e in group.episodes if e.episode == 1)
        assert ep1.downloaded is True

    async def test_reset_all_overrides(self, db):
        from module.models import EpisodeStatusRequest

        await db.rss.add(make_rss_item())
        await db.bangumi.add(make_bangumi(filter=""))

        with patch.object(
            RSSEngine, "_get_torrents", new_callable=AsyncMock
        ) as mock_get, patch.object(
            EpisodeOverviewService, "_apply_air_dates", new_callable=AsyncMock
        ):
            mock_get.return_value = _feed_torrents()
            service = EpisodeOverviewService(db)
            await service.set_status(
                1,
                EpisodeStatusRequest(
                    bangumi_id=1, season=1, episode=1, in_library=True
                ),
            )
            resp = await service.set_status(
                1, EpisodeStatusRequest(reset_all=True)
            )
            assert resp.status is True
            overview = await service.overview(1)
            assert overview is not None

        ep1 = next(
            e for e in overview.groups[0].episodes if e.episode == 1
        )
        assert ep1.manual is False
        assert ep1.in_library is False

    async def test_reset_by_selected_urls_only(self, db):
        from module.models import EpisodeStatusRequest

        await db.rss.add(make_rss_item())
        await db.bangumi.add(make_bangumi(filter=""))

        with patch.object(
            RSSEngine, "_get_torrents", new_callable=AsyncMock
        ) as mock_get, patch.object(
            EpisodeOverviewService, "_apply_air_dates", new_callable=AsyncMock
        ):
            mock_get.return_value = _feed_torrents()
            service = EpisodeOverviewService(db)
            # 第 1、2 集都手动覆盖
            await service.set_status(
                1,
                EpisodeStatusRequest(
                    bangumi_id=1, season=1, episode=1, in_library=True
                ),
            )
            await service.set_status(
                1,
                EpisodeStatusRequest(
                    bangumi_id=1, season=1, episode=2, in_library=True
                ),
            )
            # 只重置第 1 集对应的种子
            resp = await service.set_status(
                1,
                EpisodeStatusRequest(
                    reset_urls=["https://example.com/ep1.torrent"]
                ),
            )
            assert resp.status is True
            overview = await service.overview(1)
            assert overview is not None

        episodes = {e.episode: e for e in overview.groups[0].episodes}
        # 第 1 集恢复自动（未覆盖），第 2 集的手动覆盖保留
        assert episodes[1].manual is False
        assert episodes[1].in_library is False
        assert episodes[2].manual is True
        assert episodes[2].in_library is True

    async def test_empty_request_rejected(self, db):
        from module.models import EpisodeStatusRequest

        await db.rss.add(make_rss_item())
        service = EpisodeOverviewService(db)
        resp = await service.set_status(1, EpisodeStatusRequest())
        assert resp.status is False


# ---------------------------------------------------------------------------
# Jellyfin download-skip filter
# ---------------------------------------------------------------------------


class TestFilterInLibrary:
    async def test_skips_episodes_found_in_library(self, db, monkeypatch):
        from module.manager import episode_overview as eo

        await db.bangumi.add(make_bangumi(filter=""))
        torrents = [
            make_torrent(
                name="[TestGroup] Test Anime Raw - 01 [1080p].mkv",
                url="https://example.com/ep1.torrent",
                bangumi_id=1,
            ),
            make_torrent(
                name="[TestGroup] Test Anime Raw - 02 [1080p].mkv",
                url="https://example.com/ep2.torrent",
                bangumi_id=1,
            ),
        ]

        async def fake_episode_set(title):
            # 库里已有第 1 集
            return {(1, 1)}

        class FakeClient:
            get_episode_set = staticmethod(fake_episode_set)

        monkeypatch.setattr(
            eo.EpisodeOverviewService, "_jellyfin_client", lambda _: FakeClient()
        )
        keep, skipped = await EpisodeOverviewService(db).filter_in_library(torrents)
        # E01 在库被跳过，E02 保留
        assert {t.name for t in skipped} == {
            "[TestGroup] Test Anime Raw - 01 [1080p].mkv"
        }
        assert len(keep) == 1
        assert keep[0].name == "[TestGroup] Test Anime Raw - 02 [1080p].mkv"

    async def test_no_client_returns_all(self, db, monkeypatch):
        from module.manager import episode_overview as eo

        monkeypatch.setattr(
            eo.EpisodeOverviewService, "_jellyfin_client", lambda _: None
        )
        torrents = _feed_torrents()
        keep, skipped = await EpisodeOverviewService(db).filter_in_library(torrents)
        assert keep == torrents and skipped == []

    async def test_unmatched_bangumi_treated_as_not_in_library(self, db, monkeypatch):
        from module.manager import episode_overview as eo

        # 种子没有 bangumi_id（未匹配番剧）
        torrents = [make_torrent(name="raw", url="https://x/1")]
        monkeypatch.setattr(
            eo.EpisodeOverviewService, "_jellyfin_client", lambda _: object()
        )
        keep, skipped = await EpisodeOverviewService(db).filter_in_library(torrents)
        assert keep == torrents and skipped == []
