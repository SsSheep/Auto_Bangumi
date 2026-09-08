<script lang="ts" setup>
import type { MediaLibrary } from '#/config';
import type { SettingItem } from '#/components';

const { t } = useMyI18n();
const { getSettingGroup } = useConfigStore();

const mediaLibrary = getSettingGroup('media_library');

const items: SettingItem<MediaLibrary>[] = [
  {
    configKey: 'jellyfin_enable',
    label: () => t('config.media_set.enable'),
    type: 'switch',
  },
  {
    configKey: 'jellyfin_host',
    label: () => t('config.media_set.host'),
    type: 'input',
    prop: {
      type: 'text',
      placeholder: 'http://192.168.1.10:8096',
    },
  },
  {
    configKey: 'jellyfin_api_key',
    label: () => t('config.media_set.api_key'),
    type: 'input',
    prop: {
      type: 'password',
      autocomplete: 'off',
    },
  },
  {
    configKey: 'skip_on_subscribe',
    label: () => t('config.media_set.skip_on_subscribe'),
    type: 'switch',
    description: t('config.media_set.skip_on_subscribe_hint'),
  },
  {
    configKey: 'skip_on_refresh',
    label: () => t('config.media_set.skip_on_refresh'),
    type: 'switch',
    description: t('config.media_set.skip_on_refresh_hint'),
  },
];
</script>

<template>
  <ab-fold-panel :title="$t('config.media_set.title')">
    <div space-y-8>
      <ab-setting
        v-for="i in items"
        :key="i.configKey"
        v-bind="i"
        v-model:data="mediaLibrary[i.configKey]"
      ></ab-setting>
      <ConnTestRow
        :label="t('config.media_set.test_conn')"
        target="jellyfin"
        :payload="() => ({
          jellyfin_host: mediaLibrary.jellyfin_host,
          jellyfin_api_key: mediaLibrary.jellyfin_api_key,
        })"
      />
    </div>
  </ab-fold-panel>
</template>
