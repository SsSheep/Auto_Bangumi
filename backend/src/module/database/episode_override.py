import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from module.models import EpisodeStatusOverride

logger = logging.getLogger(__name__)


class EpisodeOverrideDatabase:
    """剧集标签手动覆盖的读写。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def search_all(self) -> list[EpisodeStatusOverride]:
        result = await self.session.execute(select(EpisodeStatusOverride))
        return list(result.scalars().all())

    async def upsert(
        self, bangumi_id: int, season: int, episode: float, in_library: bool
    ) -> EpisodeStatusOverride:
        existing = await self.search_one(bangumi_id, season, episode)
        if existing is not None:
            existing.in_library = in_library
            obj = existing
        else:
            obj = EpisodeStatusOverride(
                bangumi_id=bangumi_id,
                season=season,
                episode=episode,
                in_library=in_library,
            )
        self.session.add(obj)
        await self.session.commit()
        return obj

    async def search_one(
        self, bangumi_id: int, season: int, episode: float
    ) -> EpisodeStatusOverride | None:
        result = await self.session.execute(
            select(EpisodeStatusOverride).where(
                EpisodeStatusOverride.bangumi_id == bangumi_id,
                EpisodeStatusOverride.season == season,
                EpisodeStatusOverride.episode == episode,
            )
        )
        return result.scalar_one_or_none()

    async def delete_one(self, bangumi_id: int, season: int, episode: float) -> bool:
        obj = await self.search_one(bangumi_id, season, episode)
        if obj is None:
            return False
        await self.session.delete(obj)
        await self.session.commit()
        return True

    async def delete_by_bangumi_ids(self, bangumi_ids: list[int]) -> int:
        if not bangumi_ids:
            return 0
        result = await self.session.execute(
            select(EpisodeStatusOverride).where(
                EpisodeStatusOverride.bangumi_id.in_(bangumi_ids)  # type: ignore[attr-defined]
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            await self.session.delete(row)
        if rows:
            await self.session.commit()
        return len(rows)
