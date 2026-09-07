"""剧集总览缓存（RSS 检查计划到期或手动刷新时才重建）。"""

from sqlmodel import Field, SQLModel


class EpisodeOverviewCache(SQLModel, table=True):
    """单个 RSS 订阅的剧集总览缓存。"""

    __tablename__ = "episode_overview_cache"

    rss_id: int = Field(primary_key=True, alias="rss_id")
    payload: str = Field("", alias="payload")  # EpisodeOverview JSON
    built_at: str = Field("", alias="built_at")  # UTC ISO 8601
