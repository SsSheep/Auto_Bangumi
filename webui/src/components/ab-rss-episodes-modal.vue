<script lang="ts" setup>
/**
 * 剧集总览弹窗：薄包装，内容复用 ab-rss-episodes-content
 * （主页/日历的"剧集总览"页签共用同一内容组件）。
 */
const show = defineModel('show', { default: false });
const props = defineProps<{
  rssId: number | null;
  rssName: string;
}>();
</script>

<template>
  <ab-modal
    v-model:show="show"
    size="lg"
    :title="`${rssName} · ${$t('rss.episodes_title')}`"
    mobile-fullscreen
  >
    <ab-rss-episodes-content
      v-if="show"
      class="modal-episodes"
      :rss-id="props.rssId"
      :rss-name="''"
    />
  </ab-modal>
</template>

<style lang="scss" scoped>
// 弹窗内限制内容高度，页签中则自然撑开由页面滚动
.modal-episodes :deep(.episodes-body) {
  max-height: 56vh;
  overflow-y: auto;
}
</style>
