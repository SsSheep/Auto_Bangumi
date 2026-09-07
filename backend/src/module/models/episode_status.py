"""剧集标签手动覆盖（已在库状态的手动修正）。"""

from sqlmodel import Field, SQLModel


class EpisodeStatusOverride(SQLModel, table=True):
    """手动覆盖某一集的"已在库"标签（按 番剧+季+集 唯一）。

    Jellyfin 比对失败或结果不符时，用户可以在剧集总览里手动指定；
    "已下载"不走此表——它直接写种子的 downloaded 字段。
    """

    __tablename__ = "episode_status_override"

    id: int = Field(default=None, primary_key=True, alias="id")
    bangumi_id: int = Field(..., alias="bangumi_id", index=True)
    season: int = Field(1, alias="season")
    episode: float = Field(..., alias="episode")
    in_library: bool = Field(False, alias="in_library")
