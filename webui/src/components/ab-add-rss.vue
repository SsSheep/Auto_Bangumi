<script lang="ts" setup>
import { Link } from '@icon-park/vue-next';
import { NSelect, NSpin, NSwitch, NTooltip } from 'naive-ui';
import type { BangumiRule } from '#/bangumi';
import type { RSS } from '#/rss';
import { rssTemplate } from '#/rss';
import { ruleTemplate } from '#/bangumi';

/** v-model show */
const show = defineModel('show', { default: false });

const message = useMessage();
const { getAll } = useBangumiStore();
const { t } = useMyI18n();

const rss = ref<RSS>({ ...rssTemplate });
const rule = defineModel<BangumiRule>('rule', {
  default: () => ({ ...ruleTemplate }),
});
const parserTypes = ['tmdb', 'mikan', 'parser'] as const;

// UI state
const step = ref<'input' | 'confirm'>('input');
const offsetLoading = ref(false);
const offsetReason = ref('');

const { posterSrc, infoTags, showAdvanced, copied, copyRssLink } =
  useBangumiRuleForm(rule);

const loading = reactive({
  analyze: false,
  collect: false,
  subscribe: false,
});

const { execute: addRssAggregate } = useApi(apiRSS.add, {
  showMessage: true,
  onBeforeExecute() {
    loading.analyze = true;
  },
  onSuccess() {
    show.value = false;
  },
  onFinally() {
    loading.analyze = false;
  },
});

const { execute: analyzeRss } = useApi(apiDownload.analysis, {
  showMessage: true,
  onBeforeExecute() {
    loading.analyze = true;
  },
  onSuccess(res) {
    rule.value = res;
    step.value = 'confirm';
  },
  onFinally() {
    loading.analyze = false;
  },
});

const { execute: executeCollect } = useApi(apiDownload.collection, {
  showMessage: true,
  onBeforeExecute() {
    loading.collect = true;
  },
  onSuccess() {
    getAll();
    show.value = false;
  },
  onFinally() {
    loading.collect = false;
  },
});

const { execute: executeSubscribe } = useApi(apiDownload.subscribe, {
  showMessage: true,
  onBeforeExecute() {
    loading.subscribe = true;
  },
  onSuccess() {
    getAll();
    show.value = false;
  },
  onFinally() {
    loading.subscribe = false;
  },
});

// Watchers
watch(show, (val) => {
  if (!val) {
    // Reset state when closing
    rss.value = { ...rssTemplate };
    step.value = 'input';
    offsetReason.value = '';
  } else if (val && rule.value.official_title !== '') {
    // If rule already has data, go to confirm step
    step.value = 'confirm';
  }
});

// Methods
function close() {
  show.value = false;
}

function addRss() {
  if (rss.value.url === '') {
    message.error(t('notify.please_enter', [t('notify.rss_link')]));
    return;
  }

  if (rss.value.aggregate) {
    addRssAggregate(rss.value);
  } else {
    analyzeRss(rss.value);
  }
}

function goBack() {
  step.value = 'input';
}

const rssLink = computed(() => rule.value.rss_link?.[0] || rss.value.url || '');

// ---- 与 ab-edit-rule 保持一致的高级设置选项 ----

// 放送星期
const WEEKDAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;
const weekdayOptions = computed(() =>
  WEEKDAY_KEYS.map((key, index) => ({
    label: t(`calendar.days.${key}`),
    value: index,
  }))
);

function onWeekdayChange(value: number | null) {
  rule.value.air_weekday = value;
  rule.value.weekday_locked = value !== null;
}

const weekdayLoading = ref(false);

async function fetchWeekday() {
  if (!rule.value.id) return;
  weekdayLoading.value = true;
  try {
    await apiBangumi.refreshWeekday(rule.value.id);
    const fresh = await apiBangumi.getOne(rule.value.id);
    if (fresh.air_weekday != null) {
      rule.value.air_weekday = fresh.air_weekday;
      rule.value.weekday_locked = false;
      message.success(t('homepage.rule.weekday_fetched'));
    } else {
      message.error(t('homepage.rule.weekday_fetch_none'));
    }
  } catch (e) {
    console.error('Failed to fetch weekday:', e);
    message.error(t('homepage.rule.weekday_fetch_none'));
  } finally {
    weekdayLoading.value = false;
  }
}

// 内容类型
const episodeTypeOptions = computed(() => [
  { label: t('homepage.rule.type_episode'), value: 'episode' },
  { label: t('homepage.rule.type_movie'), value: 'movie' },
  { label: t('homepage.rule.type_special'), value: 'special' },
]);

// 订阅时是否立即下载当前报文里的种子（默认开启，保持旧行为）
const downloadNow = ref(true);

// 偏好分辨率预设，filterable+tag 允许输入任意值
const resolutionOptions = ['2160p', '1080p', '720p'].map((r) => ({
  label: r,
  value: r,
}));

async function autoDetectOffset() {
  if (!rule.value.id) return;
  offsetLoading.value = true;
  offsetReason.value = '';
  try {
    const result = await apiBangumi.suggestOffset(rule.value.id);
    rule.value.episode_offset = result.suggested_offset;
    offsetReason.value = result.reason;
  } catch (e) {
    console.error('Failed to detect offset:', e);
    message.error(t('offset.detect_failed'));
  } finally {
    offsetLoading.value = false;
  }
}

function collect() {
  if (!rule.value) return;
  executeCollect(rule.value);
}

function subscribe() {
  if (!rule.value) return;
  executeSubscribe(rule.value, rss.value, downloadNow.value);
}
</script>

<template>
  <ab-modal v-model:show="show" :title="$t('topbar.add.title')">
    <!-- Step 1: Input RSS -->
    <div v-if="step === 'input'" class="form-section">
      <!-- RSS Link -->
      <div class="form-group">
        <label class="form-label">{{ $t('topbar.add.rss_link') }}</label>
        <div class="input-wrapper">
          <Link theme="outline" size="16" class="input-icon" />
          <input
            v-model="rss.url"
            type="text"
            class="form-input form-input--with-icon"
            :placeholder="$t('topbar.add.placeholder_link')"
          />
        </div>
      </div>

      <!-- Name -->
      <div class="form-group">
        <label class="form-label">{{ $t('topbar.add.name') }}</label>
        <input
          v-model="rss.name"
          type="text"
          class="form-input"
          :placeholder="$t('topbar.add.placeholder_name')"
        />
      </div>

      <!-- Options row -->
      <div class="options-row">
        <!-- Aggregate Switch -->
        <div class="option-item">
          <label class="option-label">{{ $t('topbar.add.aggregate') }}</label>
          <NSwitch v-model:value="rss.aggregate" />
        </div>

        <!-- Parser Select -->
        <div class="option-item">
          <label class="option-label">{{ $t('topbar.add.parser') }}</label>
          <NSelect
            v-model:value="rss.parser"
            :options="parserTypes.map((p) => ({ label: p, value: p }))"
            class="parser-select"
          />
        </div>
      </div>
    </div>

    <!-- Step 2: Confirm -->
    <div v-else class="confirm-section">
      <bangumi-preview v-model:rule="rule" :poster-src="posterSrc" />

      <bangumi-info-tags :tags="infoTags" />

      <bangumi-rss-link-row
        :link="rssLink"
        :copied="copied"
        @copy="copyRssLink(rssLink)"
      />

      <!-- Advanced settings：与编辑规则弹窗保持同一套字段 -->
      <advanced-section v-model:open="showAdvanced">
        <bangumi-filter-field v-model="rule.filter" />

        <bangumi-offset-field
          v-model="rule.season_offset"
          :label="$t('homepage.rule.season_offset')"
          :hint="$t('homepage.rule.season_offset_hint')"
        />

        <bangumi-offset-field
          v-model="rule.episode_offset"
          :label="$t('homepage.rule.episode_offset')"
          :hint="$t('homepage.rule.episode_offset_hint')"
        >
          <template #action>
            <button
              class="detect-btn"
              :disabled="offsetLoading || !rule.id"
              @click="autoDetectOffset"
            >
              <NSpin v-if="offsetLoading" :size="14" />
              <span v-else>{{ $t('homepage.rule.auto_detect') }}</span>
            </button>
          </template>
        </bangumi-offset-field>
        <div v-if="offsetReason" class="offset-reason">
          {{ offsetReason }}
        </div>

        <div class="weekday-row">
          <label class="weekday-label">{{
            $t('homepage.rule.air_weekday')
          }}</label>
          <div class="weekday-controls">
            <NSelect
              :value="rule.air_weekday ?? null"
              :options="weekdayOptions"
              clearable
              size="small"
              :placeholder="$t('calendar.unknown')"
              :aria-label="$t('homepage.rule.air_weekday')"
              class="weekday-select"
              @update:value="onWeekdayChange"
            />
            <ab-button
              size="sm"
              :disabled="weekdayLoading || !rule.id"
              :title="$t('homepage.rule.weekday_fetch')"
              @click="fetchWeekday"
            >
              <NSpin v-if="weekdayLoading" :size="12" />
              <span v-else>{{ $t('homepage.rule.weekday_fetch') }}</span>
            </ab-button>
          </div>
        </div>

        <div class="weekday-row">
          <label class="weekday-label">{{
            $t('homepage.rule.episode_type')
          }}</label>
          <NSelect
            v-model:value="rule.episode_type"
            :options="episodeTypeOptions"
            size="small"
            :aria-label="$t('homepage.rule.episode_type')"
            class="weekday-select"
          />
        </div>

        <div class="weekday-row">
          <label class="weekday-label">{{
            $t('topbar.add.download_now')
          }}</label>
          <NSwitch v-model:value="downloadNow" size="small" />
        </div>
        <p class="preferred-hint">
          {{ $t('topbar.add.download_now_hint') }}
        </p>

        <bangumi-check-schedule-field
          v-model:interval="rule.check_interval"
          v-model:weekdays="rule.check_weekdays"
          v-model:time="rule.check_time"
        />

        <div class="weekday-row">
          <label class="weekday-label">{{
            $t('homepage.rule.preferred_group')
          }}</label>
          <ab-input
            :model-value="rule.preferred_group ?? ''"
            type="text"
            class="preferred-input"
            placeholder="ANi"
            :aria-label="$t('homepage.rule.preferred_group')"
            @update:model-value="rule.preferred_group = String($event)"
          />
        </div>

        <div class="weekday-row">
          <label class="weekday-label">{{
            $t('homepage.rule.preferred_resolution')
          }}</label>
          <NSelect
            v-model:value="rule.preferred_resolution"
            :options="resolutionOptions"
            clearable
            filterable
            tag
            size="small"
            :placeholder="$t('homepage.rule.auto_detect')"
            :aria-label="$t('homepage.rule.preferred_resolution')"
            class="weekday-select"
          />
        </div>

        <p class="preferred-hint">
          {{ $t('homepage.rule.preferred_hint') }}
        </p>
      </advanced-section>
    </div>

    <template #footer>
      <template v-if="step === 'input'">
        <ab-button
          variant="primary"
          size="sm"
          :loading="loading.analyze"
          @click="addRss"
        >
          {{ $t('topbar.add.button') }}
        </ab-button>
      </template>
      <template v-else>
        <ab-button
          variant="secondary"
          size="sm"
          class="footer-prev"
          @click="goBack"
        >
          {{ $t('setup.nav.previous') }}
        </ab-button>
        <NTooltip placement="top" :style="{ maxWidth: '260px' }">
          <template #trigger>
            <ab-button
              variant="secondary"
              size="sm"
              :loading="loading.collect"
              @click="collect"
            >
              <span class="i-carbon-download" />
              {{ $t('topbar.add.collect') }}
            </ab-button>
          </template>
          {{ $t('topbar.add.collect_hint') }}
        </NTooltip>
        <ab-button
          variant="primary"
          size="sm"
          :loading="loading.subscribe"
          @click="subscribe"
        >
          {{ $t('topbar.add.subscribe') }}
        </ab-button>
      </template>
    </template>
  </ab-modal>
</template>

<style lang="scss" scoped>
// Step 2 confirm content spacing
.confirm-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

// step-2 footer: “上一步” 靠左，其余动作靠右
.footer-prev {
  margin-right: auto;
}

// Form Section (Step 1)
.form-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
}

.input-icon {
  position: absolute;
  left: 12px;
  color: var(--color-text-muted);
  pointer-events: none;
}

.form-input {
  width: 100%;
  height: 40px;
  padding: 0 12px;
  font-size: 14px;
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  outline: none;
  transition: border-color var(--transition-fast),
    box-shadow var(--transition-fast);

  &:focus {
    border-color: var(--color-primary);
    box-shadow: 0 0 0 3px
      color-mix(in srgb, var(--color-primary) 15%, transparent);
  }

  &::placeholder {
    color: var(--color-text-muted);
  }

  &--with-icon {
    padding-left: 40px;
  }
}

.parser-select {
  width: 140px;
}

.options-row {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: var(--color-surface-hover);
  border-radius: var(--radius-md);
}

.option-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.option-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

// Footer
.footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

// Offset detect button + reason (specific to the add-rss flow;
// shared preview/tags/rss-link/filter/offset-row styles live in the
// bangumi-* / advanced-section sub-components)
.detect-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 80px;
  height: 32px;
  padding: 0 14px;
  font-size: 13px;
  font-family: inherit;
  font-weight: 500;
  color: #fff;
  background: var(--color-primary);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;
  white-space: nowrap;
  transition: background-color var(--transition-fast);

  &:hover:not(:disabled) {
    background: var(--color-primary-hover);
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
}

.offset-reason {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: -4px;
}

// 高级设置下拉/输入行（与 ab-edit-rule 同一套布局）
.weekday-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
}

.weekday-label {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
}

.weekday-select {
  width: 160px;
  flex-shrink: 0;
}

.weekday-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.preferred-input {
  width: 160px;
  flex-shrink: 0;
}

.preferred-hint {
  margin: 0;
  font-size: 11px;
  color: var(--color-text-secondary);
}

// Modal transition
// Responsive
@media (max-width: 480px) {
  .options-row {
    flex-direction: column;
    gap: 16px;
  }

  .option-item {
    justify-content: space-between;
    width: 100%;
  }
}
</style>
