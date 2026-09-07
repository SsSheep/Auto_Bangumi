<script lang="ts" setup>
import { NTooltip } from 'naive-ui';
/**
 * 单个数字 offset 行：标签 + 数字输入 + 可选的操作插槽（如"自动检测"按钮）。
 * ab-add-rss 用它承载 episode_offset + 检测按钮，ab-edit-rule 用它承载
 * season_offset / episode_offset。
 * hint 属性会在标签旁渲染一个感叹号图标，悬停显示解释文字。
 */
const props = defineProps<{
  label: string;
  modelValue: number;
  hint?: string;
}>();

const emit = defineEmits<{
  (e: 'update:modelValue', value: number): void;
}>();

// v-model.number 代理：保持与原生 input[type=number] + .number 修饰符完全一致的解析行为
const proxyValue = computed({
  get: () => props.modelValue,
  set: (value: number) => emit('update:modelValue', value),
});
</script>

<template>
  <div class="advanced-row">
    <label class="advanced-label">
      {{ label }}
      <NTooltip
        v-if="hint"
        trigger="hover"
        placement="top"
        :style="{
          maxWidth: '280px',
          borderRadius: '8px',
          fontSize: '12px',
          lineHeight: '1.6',
          padding: '8px 12px',
        }"
      >
        <template #trigger>
          <span class="hint-icon" role="img" :aria-label="hint">
            <svg
              class="hint-glyph"
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden="true"
            >
              <circle cx="8" cy="8" r="6.4" stroke="currentColor" stroke-width="1.4" />
              <line x1="8" y1="4.6" x2="8" y2="9.2" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
              <circle cx="8" cy="11.5" r="0.95" fill="currentColor" />
            </svg>
          </span>
        </template>
        {{ hint }}
      </NTooltip>
    </label>
    <div class="advanced-control offset-controls">
      <ab-input
        v-model="proxyValue"
        type="number"
        class="offset-input"
        :aria-label="label"
      />
      <slot name="action" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
.advanced-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 32px;
}

.advanced-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
  line-height: 32px;
}

// 圆圈感叹号提示图标：默认灰色安静地待着，悬停时主色 + 圆形底 + 微放大
.hint-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  cursor: pointer;
  transition:
    background-color var(--transition-fast),
    transform var(--transition-fast);

  &:hover {
    background: var(--color-primary-light);
    transform: scale(1.12);
  }
}

// 内联 SVG 圆圈感叹号：颜色走 currentColor，默认灰、悬停主色
.hint-glyph {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  transition: color var(--transition-fast);

  .hint-icon:hover & {
    color: var(--color-primary);
  }
}

.advanced-control {
  display: flex;
  justify-content: flex-end;
}

.offset-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  min-height: 32px;
}

.offset-input {
  width: 70px;
  height: 32px;
  text-align: center;

  @include forTouch {
    width: 84px;
    height: var(--touch-target);
  }
}
</style>
