"""剧集标签手动覆盖（已在库状态的手动修正）。"""

from typing import Optional

from sqlmodel import Field, SQLModel


class EpisodeStatusOverride(SQLModel, table=True):
    """手动覆盖某一集的"已在库"标签（按 番剧+季+集 唯一）。

    Jellyfin 比对失败或结果不符时，用户可以在剧集总览里手动指定；
    "已下载"不走此表——它直接写种子的 downloaded 字段。

    ``auto_value`` 记录写入覆盖**当时**的自动比对结果。方案 A：
    后续刷新时若 Jellyfin 的比对结果相对它发生了变化（说明媒体库
    状态变了，覆盖的"纠错"使命已完成），该覆盖自动失效、回到自动
    结果；结果未变化则覆盖继续生效（仍可纠正持续性误判）。旧记录
    为 NULL——首次构建时以当时的比对结果回填为基准，不失效。
    """

    __tablename__ = "episode_status_override"

    id: int = Field(default=None, primary_key=True, alias="id")
    bangumi_id: int = Field(..., alias="bangumi_id", index=True)
    season: int = Field(1, alias="season")
    episode: float = Field(..., alias="episode")
    in_library: bool = Field(False, alias="in_library")
    auto_value: Optional[bool] = Field(default=None, alias="auto_value")
