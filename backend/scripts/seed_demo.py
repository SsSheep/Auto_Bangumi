# -*- coding: utf-8 -*-
"""Seed demo data into the dev database for UI demonstration."""
import asyncio
import sys

sys.path.insert(0, r"H:\project\backend\src")

from module.database import Database
from module.models import Bangumi, RSSItem, Torrent


async def main():
    engine_url = "sqlite+aiosqlite:///./data/data.db"
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import SQLModel
    import module.models  # noqa

    engine = create_async_engine(engine_url)
    db = Database(engine=engine)

    rss = RSSItem(
        name="Lilith-Raws 偶像幻想记",
        url="https://mikanani.me/RSS/demo.json",
        aggregate=False,
        parser="mikan",
        enabled=True,
    )
    await db.rss.add(rss)
    rss_saved = await db.rss.search_all()
    rss_id = rss_saved[0].id

    bangumi = Bangumi(
        official_title="Kakkou no Iinazuke",
        title_raw="[Lilith-Raws] Kakkou no Iinazuke",
        season=1,
        group_name="Lilith-Raws",
        dpi="1080p",
        filter="",
        rss_link="https://mikanani.me/RSS/demo.json",
        added=True,
        poster_link=None,
    )
    bangumi2 = Bangumi(
        official_title="Demon Slayer: Kimetsu no Yaiba",
        title_raw="[SubsPlease] Kimetsu no Yaiba",
        season=4,
        group_name="SubsPlease",
        dpi="1080p",
        filter="",
        rss_link="https://mikanani.me/RSS/demo.json",
        added=True,
        poster_link=None,
        check_interval=3600,
    )
    db.add(bangumi)
    db.add(bangumi2)
    await db.commit()

    all_bg = await db.bangumi.search_all()
    bg1 = next(b for b in all_bg if b.official_title == "Kakkou no Iinazuke")
    bg2 = next(b for b in all_bg if "Kimetsu" in b.official_title)

    torrents = []
    # 番剧1：E01-E04 可下载，E05 已下载
    for ep in range(1, 6):
        torrents.append(
            Torrent(
                name=f"[Lilith-Raws] Kakkou no Iinazuke - {ep:02d} [Baha][WEB-DL][1080p][AVC AAC][CHT][MP4].mp4",
                url=f"https://example.com/kakkou-{ep:02d}.torrent",
                homepage="https://mikanani.me/Home/Episode/demo",
                rss_id=rss_id,
                bangumi_id=bg1.id,
                downloaded=(ep == 5),
            )
        )
    # 番剧1 E02 的另一个 720p 版本（同集多版本演示）
    torrents.append(
        Torrent(
            name="[Lilith-Raws] Kakkou no Iinazuke - 02 [Baha][WEB-DL][720p][AVC AAC][CHT][MP4].mp4",
            url="https://example.com/kakkou-02-720p.torrent",
            homepage="https://mikanani.me/Home/Episode/demo",
            rss_id=rss_id,
            bangumi_id=bg1.id,
            downloaded=False,
        )
    )
    # 番剧2：E01-E02 已下载，E03 可下载
    for ep in range(1, 4):
        torrents.append(
            Torrent(
                name=f"[SubsPlease] Kimetsu no Yaiba - {ep:02d} [1080p].mkv",
                url=f"https://example.com/kimetsu-{ep:02d}.torrent",
                homepage="https://mikanani.me/Home/Episode/demo",
                rss_id=rss_id,
                bangumi_id=bg2.id,
                downloaded=(ep <= 2),
            )
        )
    await db.torrent.add_all(torrents)
    await engine.dispose()
    print(f"Seeded: rss_id={rss_id}, bangumi={bg1.id},{bg2.id}, torrents={len(torrents)}")


asyncio.run(main())
