<script lang="ts" setup>
import { NCheckbox, NRadioButton, NRadioGroup, NSpin } from 'naive-ui';
import type { EpisodeOverview } from '#/episode';

/**
 * 剧集总览内容（弹窗与主页/日历的"剧集总览"页签共用）。
 *
 * 数据优先来自后端缓存（订阅的检查计划到期才重建）；
 * 点"刷新"强制重拉实时报文并更新缓存。
 */
const props = defineProps<{
  rssId: number | null;
  rssName: string;
}>();

const { t } = useMyI18n();
const message = useMessage();

const loading = ref(false);
const downloading = ref(false);
const overview = ref<EpisodeOverview | null>(null);
// 选中的种子 URL（实时报文里的种子按 URL 下载，已入库的按 id）
const selectedUrls = ref<Set<string>>(new Set());
// 展示方式：按识别后的集数聚合 / 按原始文件名逐条列出
const viewMode = ref<'episode' | 'file'>('episode');

async function load(force = false) {
  if (props.rssId == null) return;
  loading.value = true;
  if (force) overview.value = null;
  selectedUrls.value = new Set();
  try {
    overview.value = await apiRSS.getEpisodes(props.rssId, force);
    // 方案 A：比对结果变化导致的手动覆盖自动失效，主动告知
    if (overview.value?.overrides_updated) {
      message.info(
        t('rss.overrides_updated_hint', {
          n: overview.value.overrides_updated,
        })
      );
    }
  } catch (e) {
    console.error('Failed to load episode overview:', e);
    message.error(t('rss.episodes_empty'));
  } finally {
    loading.value = false;
  }
}

onMounted(() => load());

/** 缓存构建时间（本地 HH:MM），用于提示数据新鲜度 */
const cachedAtText = computed(() => {
  const raw = overview.value?.cached_at;
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return '';
  return `${String(d.getHours()).padStart(2, '0')}:${String(
    d.getMinutes()
  ).padStart(2, '0')}`;
});

function episodeLabel(ep: number) {
  return Number.isInteger(ep) ? `E${String(ep).padStart(2, '0')}` : `E${ep}`;
}

/** 一集是否有可勾选的候选种子 */
function selectableTorrents(ep: { torrents: { url: string; downloaded: boolean }[] }) {
  return ep.torrents.filter((torrent) => !torrent.downloaded);
}

function toggleEpisode(ep: { torrents: { url: string; downloaded: boolean }[] }) {
  const candidates = selectableTorrents(ep);
  if (!candidates.length) return;
  const allSelected = candidates.every((torrent) =>
    selectedUrls.value.has(torrent.url)
  );
  const next = new Set(selectedUrls.value);
  for (const torrent of candidates) {
    if (allSelected) next.delete(torrent.url);
    else next.add(torrent.url);
  }
  selectedUrls.value = next;
}

function toggleTorrent(url: string) {
  const next = new Set(selectedUrls.value);
  if (next.has(url)) next.delete(url);
  else next.add(url);
  selectedUrls.value = next;
}

// ---------- 按原始文件名展示的扁平列表 ----------

interface RawFileRow {
  name: string;
  url: string;
  downloaded: boolean;
  /** 识别出的集数（如 E02），识别失败为 null */
  episode: string | null;
  /** 集数数值（用于"已在库"手动覆盖），识别失败为 null */
  episodeNum: number | null;
  season: number;
  bangumiId: number | null;
  /** 该集在 Jellyfin 媒体库中是否已存在（按剧集+集数判断，与资源版本无关） */
  inLibrary: boolean;
  /** "已在库"是否为手动指定 */
  manual: boolean;
  /** Jellyfin 自动比对结果（手动覆盖的失效基准） */
  autoInLibrary: boolean;
  /** 是否匹配到了番剧（决定能否手动下载） */
  matched: boolean;
}

const rawFiles = computed<RawFileRow[]>(() => {
  const rows: RawFileRow[] = [];
  if (!overview.value) return rows;
  for (const group of overview.value.groups) {
    for (const ep of group.episodes) {
      for (const torrent of ep.torrents) {
        rows.push({
          name: torrent.name,
          url: torrent.url,
          downloaded: torrent.downloaded,
          episode: episodeLabel(ep.episode),
          episodeNum: ep.episode,
          season: ep.season,
          bangumiId: group.bangumi_id,
          inLibrary: ep.in_library,
          manual: ep.manual,
          autoInLibrary: ep.auto_in_library,
          matched: true,
        });
      }
    }
    for (const torrent of group.unparsed) {
      rows.push({
        name: torrent.name,
        url: torrent.url,
        downloaded: torrent.downloaded,
        episode: null,
        episodeNum: null,
        season: group.season,
        bangumiId: group.bangumi_id,
        inLibrary: false,
        manual: false,
        autoInLibrary: false,
        // orphan 分组的 bangumi_id 为空，视为未匹配
        matched: group.bangumi_id != null,
      });
    }
  }
  return rows;
});

const rawFilesSelectedCount = computed(
  () => rawFiles.value.filter((row) => selectedUrls.value.has(row.url)).length
);

function toggleRawFile(row: RawFileRow) {
  if (row.downloaded) return;
  toggleTorrent(row.url);
}

async function downloadSelected() {
  if (!selectedUrls.value.size || props.rssId == null) {
    message.info(t('rss.download_nothing'));
    return;
  }
  downloading.value = true;
  try {
    await apiRSS.downloadEpisodes(props.rssId, {
      urls: [...selectedUrls.value],
    });
    message.success(t('rss.download_success'));
    await load();
  } catch (e) {
    console.error('Failed to download:', e);
  } finally {
    downloading.value = false;
  }
}

// ---------- 手动修改剧集标签（已在库 / 已下载） ----------

const hasManual = computed(() =>
  (overview.value?.groups ?? []).some((g) =>
    g.episodes.some((ep) => ep.manual)
  )
);

/** 切换"已在库"：写入手动覆盖（乐观更新） */
async function toggleLibrary(
  bangumiId: number | null,
  season: number,
  episodeNum: number | null,
  current: boolean,
  currentAuto: boolean
) {
  if (bangumiId == null || episodeNum == null || props.rssId == null) return;
  try {
    await apiRSS.setEpisodeStatus(props.rssId, {
      bangumi_id: bangumiId,
      season,
      episode: episodeNum,
      in_library: !current,
      // 记录写入时的自动结果：Jellyfin 之后变化时该覆盖自动失效
      auto_in_library: currentAuto,
    });
    for (const g of overview.value?.groups ?? []) {
      if (g.bangumi_id !== bangumiId) continue;
      for (const ep of g.episodes) {
        if (ep.season === season && ep.episode === episodeNum) {
          ep.in_library = !current;
          ep.manual = true;
        }
      }
    }
  } catch (e) {
    console.error('Failed to toggle in_library:', e);
  }
}

/** 修改"已下载"：直接写种子记录（乐观更新，两个视图共享数据） */
async function setDownloadedUrls(urls: string[], value: boolean) {
  if (!urls.length || props.rssId == null) return;
  const urlSet = new Set(urls);
  try {
    await apiRSS.setEpisodeStatus(props.rssId, {
      set_downloaded: value,
      urls,
    });
    for (const g of overview.value?.groups ?? []) {
      for (const ep of g.episodes) {
        for (const torrent of ep.torrents) {
          if (urlSet.has(torrent.url)) torrent.downloaded = value;
        }
        ep.downloaded = ep.torrents.some((torrent) => torrent.downloaded);
      }
      for (const torrent of g.unparsed) {
        if (urlSet.has(torrent.url)) torrent.downloaded = value;
      }
    }
    if (!value) {
      const next = new Set(selectedUrls.value);
      for (const url of urls) next.delete(url);
      selectedUrls.value = next;
    }
  } catch (e) {
    console.error('Failed to toggle downloaded:', e);
  }
}

/** 重置勾选剧集的手动"已在库"覆盖，本地恢复自动判断值（不重新加载） */
async function resetTags() {
  if (props.rssId == null) return;
  const urlSet = new Set(selectedUrls.value);
  if (!urlSet.size) {
    message.info(t('rss.reset_tags_none'));
    return;
  }
  // 从勾选种子反查带手动标记的剧集，直接把番剧+季+集发给后端（免拉报文）
  const targets: Array<{
    bangumi_id: number;
    season: number;
    episode: number;
  }> = [];
  for (const g of overview.value?.groups ?? []) {
    if (g.bangumi_id == null) continue;
    for (const ep of g.episodes) {
      if (!ep.manual) continue;
      if (!ep.torrents.some((torrent) => urlSet.has(torrent.url))) continue;
      targets.push({
        bangumi_id: g.bangumi_id,
        season: ep.season,
        episode: ep.episode,
      });
    }
  }
  if (!targets.length) {
    message.info(t('rss.reset_tags_nothing'));
    return;
  }
  try {
    await apiRSS.setEpisodeStatus(props.rssId, {
      reset_episodes: targets,
    });
    for (const g of overview.value?.groups ?? []) {
      for (const ep of g.episodes) {
        if (!ep.torrents.some((torrent) => urlSet.has(torrent.url))) continue;
        ep.in_library = ep.auto_in_library;
        ep.manual = false;
      }
    }
    message.success(t('rss.reset_tags_done'));
  } catch (e) {
    console.error('Failed to reset tags:', e);
  }
}
</script>

<template>
  <div class="episodes-content">
    <header v-if="rssName" class="content-header">
      <h3 class="content-title">{{ rssName }}</h3>
    </header>

    <div class="episodes-body">
      <div v-if="loading" class="episodes-loading">
        <NSpin :size="20" />
        <span>{{ $t('rss.loading') }}</span>
      </div>

      <template v-else-if="overview">
        <div class="episodes-toolbar">
          <NRadioGroup v-model:value="viewMode" size="small">
            <NRadioButton value="episode">
              <span class="toolbar-icon i-carbon-list-numbered" />
              {{ $t('rss.view_by_episode') }}
            </NRadioButton>
            <NRadioButton value="file">
              <span class="toolbar-icon i-carbon-document" />
              {{ $t('rss.view_by_file') }}
            </NRadioButton>
          </NRadioGroup>
          <span class="toolbar-legend">
            <span
              v-if="cachedAtText"
              class="cache-time"
              :title="$t('rss.cached_at_hint')"
            >
              {{ $t('rss.cached_at', { time: cachedAtText }) }}
            </span>
            <ab-tag type="success">{{ $t('rss.in_library') }}</ab-tag>
            <ab-tag type="info">{{ $t('rss.downloaded') }}</ab-tag>
            <ab-tag type="neutral">{{ $t('rss.available') }}</ab-tag>
          </span>
        </div>

        <p v-if="!overview.jellyfin_available" class="jellyfin-hint">
          {{ $t('rss.jellyfin_unavailable') }}
        </p>
        <p v-else class="jellyfin-hint">
          {{ $t('rss.in_library_hint') }}
        </p>

        <ab-empty
          v-if="!overview.groups.length"
          :title="$t('rss.episodes_empty')"
        />

        <!-- 视图一：按识别后的集数聚合 -->
        <template v-if="viewMode === 'episode'">
          <section
            v-for="group in overview.groups"
            :key="group.bangumi_id ?? 'unmatched'"
            class="episode-group"
          >
            <header class="group-header">
              <h4 class="group-title">
                {{ group.official_title ?? $t('rss.unparsed') }}
              </h4>
              <span class="group-season">{{ $t('rss.season', { season: group.season }) }}</span>
            </header>

            <ul class="episode-list">
              <li
                v-for="ep in group.episodes"
                :key="`${ep.season}-${ep.episode}`"
                class="episode-row"
                :class="{
                  selected: selectableTorrents(ep).some((torrent) =>
                    selectedUrls.has(torrent.url)
                  ),
                }"
                @click="toggleEpisode(ep)"
              >
                <div class="episode-main">
                  <NCheckbox
                    :checked="
                      selectableTorrents(ep).some((torrent) =>
                        selectedUrls.has(torrent.url)
                      )
                    "
                    :disabled="!selectableTorrents(ep).length"
                    @click.stop
                    @update:checked="toggleEpisode(ep)"
                  />
                  <span class="episode-label">{{ episodeLabel(ep.episode) }}</span>
                  <span class="episode-air">
                    {{ ep.air_date ?? $t('calendar.unknown') }}
                  </span>
                  <span class="episode-tags">
                    <ab-tag
                      v-if="overview.jellyfin_available || ep.manual"
                      :type="ep.in_library ? 'success' : 'warning'"
                      :title="$t('rss.tag_toggle_hint')"
                      class="tag-toggle"
                      @click.stop="
                        toggleLibrary(
                          group.bangumi_id,
                          ep.season,
                          ep.episode,
                          ep.in_library,
                          ep.auto_in_library
                        )
                      "
                    >
                      <span
                        :class="ep.in_library ? 'i-carbon-checkmark-filled' : 'i-carbon-close-outline'"
                        class="tag-icon"
                      />
                      {{ ep.in_library ? $t('rss.in_library') : $t('rss.not_in_library') }}
                      <sup v-if="ep.manual" class="manual-mark">{{
                        $t('rss.manual_tag')
                      }}</sup>
                    </ab-tag>
                    <ab-tag
                      v-if="ep.downloaded"
                      type="info"
                      :title="$t('rss.tag_toggle_hint')"
                      class="tag-toggle"
                      @click.stop="
                        setDownloadedUrls(
                          ep.torrents.map((torrent) => torrent.url),
                          false
                        )
                      "
                    >
                      {{ $t('rss.downloaded') }}
                    </ab-tag>
                    <ab-tag
                      v-else
                      type="neutral"
                      :title="$t('rss.tag_toggle_hint')"
                      class="tag-toggle"
                      @click.stop="
                        setDownloadedUrls(
                          ep.torrents.map((torrent) => torrent.url),
                          true
                        )
                      "
                    >
                      {{ $t('rss.available') }}
                    </ab-tag>
                  </span>
                </div>

                <!-- 同一集的多个候选版本 -->
                <ul
                  v-if="ep.torrents.length > 1"
                  class="torrent-options"
                  @click.stop
                >
                  <li
                    v-for="torrent in ep.torrents"
                    :key="torrent.url"
                    class="torrent-option"
                    :class="{
                      selected: selectedUrls.has(torrent.url),
                      downloaded: torrent.downloaded,
                    }"
                    @click="!torrent.downloaded && toggleTorrent(torrent.url)"
                  >
                    <NCheckbox
                      :checked="selectedUrls.has(torrent.url)"
                      :disabled="torrent.downloaded"
                      @update:checked="toggleTorrent(torrent.url)"
                    />
                    <span class="torrent-name" :title="torrent.name">
                      {{ torrent.name }}
                    </span>
                    <span v-if="torrent.downloaded" class="torrent-done">
                      {{ $t('rss.downloaded') }}
                    </span>
                  </li>
                </ul>
              </li>
            </ul>

            <details v-if="group.unparsed.length" class="unparsed-block">
              <summary>{{ $t('rss.unparsed') }} ({{ group.unparsed.length }})</summary>
              <ul class="torrent-options">
                <li
                  v-for="torrent in group.unparsed"
                  :key="torrent.url"
                  class="torrent-option"
                  :class="{
                    selected: selectedUrls.has(torrent.url),
                    downloaded: torrent.downloaded,
                  }"
                  :title="torrent.name"
                  @click="!torrent.downloaded && toggleTorrent(torrent.url)"
                >
                  <NCheckbox
                    :checked="selectedUrls.has(torrent.url)"
                    :disabled="torrent.downloaded"
                    @click.stop
                    @update:checked="toggleTorrent(torrent.url)"
                  />
                  <span class="torrent-name">{{ torrent.name }}</span>
                </li>
              </ul>
            </details>
          </section>
        </template>

        <!-- 视图二：按原始文件名逐条列出 -->
        <ul v-else class="file-list">
          <li
            v-for="row in rawFiles"
            :key="row.url"
            class="file-row"
            :class="{
              selected: selectedUrls.has(row.url),
              disabled: row.downloaded,
            }"
            @click="toggleRawFile(row)"
          >
            <NCheckbox
              :checked="selectedUrls.has(row.url)"
              :disabled="row.downloaded"
              @click.stop
              @update:checked="toggleRawFile(row)"
            />
            <div class="file-main">
              <div class="file-name" :title="row.name">{{ row.name }}</div>
              <div class="file-meta">
                <span class="file-episode" :class="{ unknown: !row.episode }">
                  {{ $t('rss.parsed_episode') }}：{{ row.episode ?? $t('rss.unparsed') }}
                </span>
                <span class="episode-tags">
                  <ab-tag
                    v-if="row.episodeNum != null && (overview.jellyfin_available || row.manual)"
                    :type="row.inLibrary ? 'success' : 'warning'"
                    :title="$t('rss.tag_toggle_hint')"
                    class="tag-toggle"
                    @click.stop="
                      toggleLibrary(
                        row.bangumiId,
                        row.season,
                        row.episodeNum,
                        row.inLibrary,
                        row.autoInLibrary
                      )
                    "
                  >
                    <span
                      :class="row.inLibrary ? 'i-carbon-checkmark-filled' : 'i-carbon-close-outline'"
                      class="tag-icon"
                    />
                    {{ row.inLibrary ? $t('rss.in_library') : $t('rss.not_in_library') }}
                    <sup v-if="row.manual" class="manual-mark">{{
                      $t('rss.manual_tag')
                    }}</sup>
                  </ab-tag>
                  <ab-tag
                    v-if="row.downloaded"
                    type="info"
                    :title="$t('rss.tag_toggle_hint')"
                    class="tag-toggle"
                    @click.stop="setDownloadedUrls([row.url], false)"
                  >
                    {{ $t('rss.downloaded') }}
                  </ab-tag>
                  <ab-tag
                    v-else-if="!row.matched"
                    type="warning"
                    :title="$t('rss.tag_toggle_hint')"
                    class="tag-toggle"
                    @click.stop="setDownloadedUrls([row.url], true)"
                  >
                    {{ $t('rss.unmatched') }}
                  </ab-tag>
                  <ab-tag
                    v-else
                    type="neutral"
                    :title="$t('rss.tag_toggle_hint')"
                    class="tag-toggle"
                    @click.stop="setDownloadedUrls([row.url], true)"
                  >
                    {{ $t('rss.available') }}
                  </ab-tag>
                </span>
              </div>
            </div>
          </li>
        </ul>
      </template>
    </div>

    <footer class="content-footer">
      <span class="footer-count">
        {{ $t('rss.selected_count', { count: viewMode === 'file' ? rawFilesSelectedCount : selectedUrls.size }) }}
      </span>
      <ab-button
        v-if="hasManual"
        size="sm"
        :title="$t('rss.reset_tags_hint')"
        @click="resetTags"
      >
        {{ $t('rss.reset_tags') }}
      </ab-button>
      <ab-button size="sm" :title="$t('rss.refresh_hint')" @click="load(true)">
        {{ $t('rss.refresh') }}
      </ab-button>
      <ab-button
        variant="primary"
        size="sm"
        :disabled="downloading || !selectedUrls.size"
        @click="downloadSelected"
      >
        <NSpin v-if="downloading" :size="12" />
        <template v-else>
          <span class="i-carbon-download" />
          {{ $t('rss.download_selected') }}
        </template>
      </ab-button>
    </footer>
  </div>
</template>

<style lang="scss" scoped>
.episodes-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.content-header {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.content-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.cache-time {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--color-text-muted);
}

.content-footer {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--color-border);
}

.episodes-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.episodes-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px 0;
  color: var(--color-text-secondary);
}

.jellyfin-hint {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.episodes-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.toolbar-icon {
  margin-right: 4px;
  vertical-align: -2px;
  width: 13px;
  height: 13px;
  font-size: 13px;
}

.toolbar-legend {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.tag-icon {
  display: inline-block;
  margin-right: 3px;
  vertical-align: -2px;
  width: 11px;
  height: 11px;
  font-size: 11px;
}

// 可点击切换的标签
.tag-toggle {
  cursor: pointer;
  transition: transform var(--transition-fast), opacity var(--transition-fast);

  &:hover {
    transform: scale(1.06);
    opacity: 0.85;
  }
}

// 手动覆盖标记（"已在库"角标）
.manual-mark {
  margin-left: 2px;
  font-size: 9px;
  line-height: 1;
  color: var(--color-warning);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.file-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;

  &:hover:not(.disabled) {
    background: var(--color-surface-2);
  }

  &.selected {
    background: var(--color-primary-light);
  }

  &.disabled {
    cursor: default;
    opacity: 0.6;
  }
}

.file-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.file-name {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.file-episode {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-text-secondary);

  &.unknown {
    color: var(--color-text-muted);
  }
}

.footer-count {
  margin-right: auto;
  font-size: 12px;
  color: var(--color-text-secondary);
}

.episode-group {
  .group-header {
    display: flex;
    align-items: baseline;
    gap: 8px;
    margin-bottom: 8px;
  }

  .group-title {
    margin: 0;
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text);
  }

  .group-season {
    font-size: 12px;
    color: var(--color-text-secondary);
  }
}

.episode-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.episode-row {
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;

  &:hover {
    background: var(--color-surface-2);
  }

  &.selected {
    background: var(--color-primary-light);
  }
}

.episode-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.episode-label {
  min-width: 48px;
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
  font-weight: 600;
  color: var(--color-text);
}

.episode-air {
  min-width: 90px;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--color-text-secondary);
}

.episode-tags {
  display: flex;
  gap: 6px;
}

.torrent-options {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin: 4px 0 0 26px;
  padding: 0;
  list-style: none;
}

.torrent-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px;
  font-size: 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;

  &:hover:not(.downloaded) {
    background: var(--color-surface-2);
  }

  &.selected {
    background: var(--color-primary-light);
  }

  &.downloaded {
    cursor: default;
    opacity: 0.6;
  }
}

.torrent-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-family: var(--font-mono);
}

.torrent-done {
  flex-shrink: 0;
  color: var(--color-text-secondary);
}

.unparsed-block {
  font-size: 12px;
  color: var(--color-text-secondary);

  summary {
    cursor: pointer;
    margin-bottom: 4px;
  }
}
</style>
