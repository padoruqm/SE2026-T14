<script setup lang="ts">
import { computed, ref, useTemplateRef } from 'vue'

import { apiBaseUrl } from '@/shared/config'

import MetadataPanel from './MetadataPanel.vue'
import ViewerCanvas from './ViewerCanvas.vue'
import ViewerControls from './ViewerControls.vue'
import type { ColorMode } from './potreeViewer'

const props = defineProps<{ id: string }>()

const pointSize = ref(1)
const colorMode = ref<ColorMode>('rgb')
const canvas = useTemplateRef('canvas')
const url = computed(() => `${apiBaseUrl}/api/pointcloud/${props.id}/viewer/metadata.json`)
</script>

<template>
  <section>
    <h1>Viewer</h1>
    <p>Point cloud: {{ id }}</p>
    <ViewerControls
      v-model:point-size="pointSize"
      v-model:color-mode="colorMode"
      @reset-view="canvas?.resetView()"
    />
    <ViewerCanvas
      :key="url"
      ref="canvas"
      :url="url"
      :point-size="pointSize"
      :color-mode="colorMode"
    />
    <MetadataPanel :id="id" />
  </section>
</template>
