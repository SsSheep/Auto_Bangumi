"""RSS 订阅剧集总览的响应模型。"""

from typing import Optional

from pydantic import BaseModel


class EpisodeTorrentInfo(BaseModel):
    """总览里的一个候选种子（同一集可能有多个字幕组/分辨率版本）。"""

    id: Optional[int] = None
    name: str
    url: str
    group: Optional[str] = None
    resolution: Optional[str] = None
    downloaded: bool = False


class EpisodeEntry(BaseModel):
    """按 (季, 集) 聚合后的一个剧集条目。"""

    season: int
    episode: float
    air_date: Optional[str] = None  # TMDB 放送日期，YYYY-MM-DD
    downloaded: bool = False
    in_library: bool = False  # Jellyfin 已有（含手动覆盖）
    auto_in_library: bool = False  # 自动比对原始结果（覆盖前），供前端本地恢复
    manual: bool = False  # "已在库"为手动指定（覆盖了自动比对结果）
    torrents: list[EpisodeTorrentInfo] = []


class BangumiEpisodeGroup(BaseModel):
    """一个订阅源里按番剧聚合的分组（聚合 RSS 会有多个分组）。"""

    bangumi_id: Optional[int] = None
    official_title: Optional[str] = None
    season: int = 1
    poster_link: Optional[str] = None
    check_interval: Optional[int] = None
    episodes: list[EpisodeEntry] = []
    unparsed: list[EpisodeTorrentInfo] = []  # 解析不出集数的种子


class EpisodeOverview(BaseModel):
    """GET /rss/{rss_id}/episodes 的响应。"""

    jellyfin_available: bool = False
    groups: list[BangumiEpisodeGroup] = []
    cached_at: Optional[str] = None  # 缓存构建时间（UTC ISO 8601）
    # 本次构建中因"比对结果已变化"而自动失效的手动覆盖数（方案 A）
    overrides_updated: int = 0


class EpisodeRef(BaseModel):
    """定位一个剧集条目（番剧+季+集）。"""

    bangumi_id: int
    season: int = 1
    episode: float


class EpisodeStatusRequest(BaseModel):
    """POST /rss/{rss_id}/episodes/status 的请求：手动修改剧集标签。"""

    bangumi_id: Optional[int] = None
    season: int = 1
    episode: Optional[float] = None
    in_library: Optional[bool] = None  # 覆盖"已在库"
    auto_in_library: Optional[bool] = None  # 写入时的自动比对结果（失效基准）
    reset_in_library: bool = False  # 清除单集覆盖，恢复自动比对
    reset_all: bool = False  # 清除该订阅下全部覆盖
    reset_urls: list[str] = []  # 只清除勾选种子对应剧集的覆盖（需拉报文反查）
    reset_episodes: list[EpisodeRef] = []  # 直接按番剧+季+集清除（免拉报文）
    set_downloaded: Optional[bool] = None  # 配合 urls 修改"已下载"
    urls: list[str] = []
