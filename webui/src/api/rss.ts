import type { RSS } from '#/rss';
import type { Torrent } from '#/torrent';
import type { EpisodeOverview } from '#/episode';
import type { ApiSuccess } from '#/api';

export const apiRSS = {
  async get() {
    const { data } = await axios.get<RSS[]>('api/v1/rss');
    return data!;
  },

  async add(rss: RSS) {
    const { data } = await axios.post<ApiSuccess>('api/v1/rss/add', rss);
    return data;
  },

  async delete(rss_id: number) {
    const { data } = await axios.delete<ApiSuccess>(
      `api/v1/rss/delete/${rss_id}`
    );
    return data!;
  },

  async deleteMany(rss_list: number[]) {
    const { data } = await axios.post<ApiSuccess>(
      `api/v1/rss/delete/many`,
      rss_list
    );
    return data!;
  },

  async disable(rss_id: number) {
    const { data } = await axios.patch<ApiSuccess>(
      `api/v1/rss/disable/${rss_id}`
    );
    return data!;
  },

  async disableMany(rss_list: number[]) {
    const { data } = await axios.post<ApiSuccess>(
      `api/v1/rss/disable/many`,
      rss_list
    );
    return data!;
  },

  async update(rss_id: number, rss: RSS) {
    const { data } = await axios.patch<ApiSuccess>(
      `api/v1/rss/update/${rss_id}`,
      rss
    );
    return data!;
  },

  async enableMany(rss_list: number[]) {
    const { data } = await axios.post<ApiSuccess>(
      `api/v1/rss/enable/many`,
      rss_list
    );
    return data!;
  },

  async refreshAll() {
    const { data } = await axios.post<ApiSuccess>('api/v1/rss/refresh/all');
    return data!;
  },

  async refresh(rss_id: number) {
    const { data } = await axios.post<ApiSuccess>(
      `api/v1/rss/refresh/${rss_id}`
    );
    return data!;
  },

  async getTorrent(rss_id: number) {
    const { data } = await axios.get<Torrent[]>(`api/v1/rss/torrent/${rss_id}`);
    return data!;
  },

  async getEpisodes(rss_id: number, force = false) {
    const { data } = await axios.get<EpisodeOverview>(
      `api/v1/rss/${rss_id}/episodes`,
      { params: force ? { refresh: true } : undefined }
    );
    return data!;
  },

  async downloadEpisodes(
    rss_id: number,
    payload: { torrent_ids?: number[]; urls?: string[] }
  ) {
    const { data } = await axios.post<ApiSuccess>(
      `api/v1/rss/${rss_id}/episodes/download`,
      { torrent_ids: payload.torrent_ids ?? [], urls: payload.urls ?? [] }
    );
    return data!;
  },

  async setEpisodeStatus(
    rss_id: number,
    payload: {
      bangumi_id?: number | null;
      season?: number;
      episode?: number | null;
      in_library?: boolean | null;
      /** 写入时的自动比对结果（覆盖失效基准） */
      auto_in_library?: boolean | null;
      reset_in_library?: boolean;
      reset_all?: boolean;
      reset_urls?: string[];
      reset_episodes?: Array<{
        bangumi_id: number;
        season: number;
        episode: number;
      }>;
      set_downloaded?: boolean | null;
      urls?: string[];
    }
  ) {
    const { data } = await axios.post<ApiSuccess>(
      `api/v1/rss/${rss_id}/episodes/status`,
      payload
    );
    return data!;
  },
};
