/**
 * @type backend/src/module/models/episode_overview.py
 */
export interface EpisodeTorrentInfo {
  id: number | null;
  name: string;
  url: string;
  group: string | null;
  resolution: string | null;
  downloaded: boolean;
}

export interface EpisodeEntry {
  season: number;
  episode: number;
  air_date: string | null;
  downloaded: boolean;
  in_library: boolean;
  /** 自动比对原始结果（覆盖前），供前端重置后本地恢复 */
  auto_in_library: boolean;
  /** "已在库"为手动指定（覆盖自动比对结果） */
  manual: boolean;
  torrents: EpisodeTorrentInfo[];
}

export interface BangumiEpisodeGroup {
  bangumi_id: number | null;
  official_title: string | null;
  season: number;
  poster_link: string | null;
  check_interval: number | null;
  episodes: EpisodeEntry[];
  unparsed: EpisodeTorrentInfo[];
}

export interface EpisodeOverview {
  jellyfin_available: boolean;
  groups: BangumiEpisodeGroup[];
  /** 缓存构建时间（UTC ISO 8601），null = 刚构建 */
  cached_at: string | null;
}
