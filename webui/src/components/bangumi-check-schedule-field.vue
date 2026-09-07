<script lang="ts" setup>
import { NRadioButton, NRadioGroup, NSelect, NTimePicker } from 'naive-ui';

/**
 * 检查订阅计划（双模式）：
 * - interval：固定间隔（跟随全局 / N 分钟~N 小时），写 check_interval；
 * - weekly：按星期几 + 每日时刻检查（24 小时制，精确到分钟），
 *   写 check_weekdays（"0,3,6"）+ check_time（"20:30"）。
 *
 * ab-edit-rule 与 ab-add-rss 共用。
 */
const interval = defineModel<number | null>('interval', { default: null });
const weekdays = defineModel<string | null>('weekdays', { default: null });
const time = defineModel<string | null>('time', { default: null });

const { t } = useMyI18n();

const WEEKDAY_KEYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const;

const mode = computed<'interval' | 'weekly'>({
  get: () => (weekdays.value && time.value ? 'weekly' : 'interval'),
  set: (val) => {
    if (val === 'weekly') {
      // 默认：今天 + 20:00
      if (!weekdays.value) {
        weekdays.value = String(new Date().getDay() === 0 ? 6 : new Date().getDay() - 1);
      }
      if (!time.value) time.value = '20:00';
    } else {
      weekdays.value = null;
      time.value = null;
    }
  },
});

const weekdayOptions = computed(() =>
  WEEKDAY_KEYS.map((key, index) => ({
    label: t(`calendar.days.${key}`),
    value: index,
  }))
);

// check_weekdays（"0,3"）↔ number[]
const selectedDays = computed<number[]>({
  get: () =>
    (weekdays.value || '')
      .split(',')
      .map((s) => Number(s.trim()))
      .filter((n) => Number.isInteger(n) && n >= 0 && n <= 6),
  set: (val) => {
    weekdays.value = val.length ? [...val].sort().join(',') : null;
  },
});

// "HH:MM" ↔ NTimePicker 的 formatted-value
const timeValue = computed({
  get: () => time.value || null,
  set: (val: string | null) => {
    time.value = val || null;
  },
});

// 常见间隔作预设
const CHECK_INTERVAL_CHOICES: Array<[number, 'minutes' | 'hours']> = [
  [5, 'minutes'],
  [10, 'minutes'],
  [15, 'minutes'],
  [30, 'minutes'],
  [60, 'minutes'],
  [2, 'hours'],
  [6, 'hours'],
  [12, 'hours'],
  [24, 'hours'],
];
const checkIntervalOptions = computed(() => [
  { label: t('homepage.rule.check_interval_default'), value: null },
  ...CHECK_INTERVAL_CHOICES.map(([n, unit]) => ({
    label: `${n} ${t(`homepage.rule.${unit}`)}`,
    value: n * (unit === 'minutes' ? 60 : 3600),
  })),
]) as unknown as Array<{ label: string; value: number | null }>;
</script>

<template>
  <div class="schedule-field">
    <div class="weekday-row">
      <label class="weekday-label">{{
        $t('homepage.rule.check_schedule')
      }}</label>
      <NRadioGroup v-model:value="mode" size="small">
        <NRadioButton value="interval">
          {{ $t('homepage.rule.check_mode_interval') }}
        </NRadioButton>
        <NRadioButton value="weekly">
          {{ $t('homepage.rule.check_mode_weekly') }}
        </NRadioButton>
      </NRadioGroup>
    </div>

    <div v-if="mode === 'interval'" class="weekday-row">
      <label class="weekday-label">{{
        $t('homepage.rule.check_interval')
      }}</label>
      <NSelect
        :value="interval ?? null"
        :options="checkIntervalOptions as any"
        size="small"
        :aria-label="$t('homepage.rule.check_interval')"
        class="weekday-select"
        @update:value="interval = $event"
      />
    </div>

    <template v-else>
      <div class="weekday-row">
        <label class="weekday-label">{{
          $t('homepage.rule.check_weekdays')
        }}</label>
        <NSelect
          v-model:value="selectedDays"
          :options="weekdayOptions"
          multiple
          size="small"
          :aria-label="$t('homepage.rule.check_weekdays')"
          class="weekday-select wide"
        />
      </div>
      <div class="weekday-row">
        <label class="weekday-label">{{
          $t('homepage.rule.check_time')
        }}</label>
        <NTimePicker
          v-model:formatted-value="timeValue"
          value-format="HH:mm"
          format="HH:mm"
          size="small"
          :aria-label="$t('homepage.rule.check_time')"
          class="weekday-select"
        />
      </div>
    </template>
  </div>
</template>

<style lang="scss" scoped>
.schedule-field {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

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

  &.wide {
    width: 240px;
  }
}
</style>
