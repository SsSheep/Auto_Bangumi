import type { Config, LLMProviderId } from '#/config';
import type { ApiSuccess } from '#/api';

export const apiConfig = {
  /**
   * 获取 config 数据
   */
  async getConfig() {
    const { data } = await axios.get<Config>('api/v1/config/get');
    return data;
  },

  /**
   * 更新 config 数据
   * @param newConfig - 需要更新的 config
   */
  async updateConfig(newConfig: Config) {
    const { data } = await axios.patch<ApiSuccess>(
      'api/v1/config/update',
      newConfig
    );
    return data;
  },

  /**
   * 拉取所选 LLM 提供商的可用模型列表
   * （api_key 传掩码时后端回退到已保存的密钥）
   */
  async getLLMModels(payload: {
    provider: LLMProviderId;
    api_key: string;
    base_url: string;
  }) {
    const { data } = await axios.post<{ models: string[] }>(
      'api/v1/config/llm/models',
      payload,
      { silent: true }
    );
    return data.models;
  },

  /**
   * 设置页连通性测试（TMDB / 下载器 / Jellyfin）。
   * 密码、密钥为掩码或空时，后端回退到已保存配置再测。
   */
  async testConnection(
    target: 'tmdb' | 'bgm' | 'downloader' | 'jellyfin',
    payload: Record<string, string>
  ) {
    const { data } = await axios.post<{
      ok: boolean;
      latency_ms: number;
      msg_zh: string;
      msg_en: string;
      detail: string | null;
    }>(`api/v1/config/test/${target}`, payload, { silent: true });
    return data;
  },
};
