<script lang="ts" setup>
// 连通性测试行：按钮 + 内联结果反馈，放在设置面板底部。
// payload 是 getter：点击瞬间取最新表单值；密码/key 字段可能是掩码，
// 由后端回退到已保存值再测。
import { apiConfig } from '@/api/config';

export interface ConnTestResult {
  ok: boolean;
  latency_ms: number;
  msg_zh: string;
  msg_en: string;
  detail?: string | null;
}

const props = defineProps<{
  target: 'tmdb' | 'bgm' | 'downloader' | 'jellyfin';
  label: string;
  payload: () => Record<string, string>;
}>();

const { returnUserLangMsg } = useMyI18n();

const running = ref(false);
const result = ref<ConnTestResult | null>(null);

async function run() {
  running.value = true;
  result.value = null;
  try {
    result.value = await apiConfig.testConnection(
      props.target,
      props.payload()
    );
  } catch {
    result.value = {
      ok: false,
      latency_ms: 0,
      msg_zh: '请求失败，请确认服务本身在运行',
      msg_en: 'Request failed; make sure the service is running',
    };
  } finally {
    running.value = false;
  }
}

const resultText = computed(() => {
  if (!result.value) return '';
  const base = returnUserLangMsg(result.value);
  const detail = result.value.detail ? ` · ${result.value.detail}` : '';
  return `${base} (${result.value.latency_ms}ms)${detail}`;
});
</script>

<template>
  <div class="conn-test" flex="~ wrap items-center justify-end" gap-8>
    <span
      v-if="result"
      class="conn-test__msg"
      :class="result.ok ? 'text-success' : 'text-danger'"
    >
      {{ resultText }}
    </span>
    <AbButton size="sm" :loading="running" @click="run">
      {{ label }}
    </AbButton>
  </div>
</template>

<style lang="scss" scoped>
.conn-test {
  padding-top: 8px;

  &__msg {
    font-size: 12px;
    max-width: 100%;
    word-break: break-all;
  }
}
</style>
