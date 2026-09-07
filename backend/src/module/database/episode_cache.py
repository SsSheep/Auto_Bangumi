import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from module.models import EpisodeOverviewCache

logger = logging.getLogger(__name__)


class EpisodeCacheDatabase:
    """剧集总览缓存的读写。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, rss_id: int) -> EpisodeOverviewCache | None:
        result = await self.session.execute(
            select(EpisodeOverviewCache).where(EpisodeOverviewCache.rss_id == rss_id)
        )
        return result.scalar_one_or_none()

    async def save(self, rss_id: int, payload: str, built_at: str) -> None:
        existing = await self.get(rss_id)
        if existing is not None:
            existing.payload = payload
            existing.built_at = built_at
            obj = existing
        else:
            obj = EpisodeOverviewCache(
                rss_id=rss_id, payload=payload, built_at=built_at
            )
        self.session.add(obj)
        await self.session.commit()

    async def delete(self, rss_id: int) -> None:
        existing = await self.get(rss_id)
        if existing is not None:
            await self.session.delete(existing)
            await self.session.commit()
