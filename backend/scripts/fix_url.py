import asyncio
import sys

sys.path.insert(0, r"H:\project\backend\src")


async def main():
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlmodel import select
    from module.database import Database
    from module.models import Torrent

    engine = create_async_engine("sqlite+aiosqlite:///./data/data.db")
    db = Database(engine=engine)
    result = await db.session.execute(select(Torrent))
    torrents = list(result.scalars().all())
    for t in torrents:
        if t.url.startswith("https://example.com/"):
            name_part = t.url.rsplit("/", 1)[-1].replace(".torrent", "")
            t.url = f"magnet:?xt=urn:btih:{hash(name_part) & 0xFFFFFFFFFFFFFFFF:016x}&dn={name_part}"
    await db.torrent.update_all(torrents)
    await engine.dispose()
    print("updated", len(torrents))


asyncio.run(main())
