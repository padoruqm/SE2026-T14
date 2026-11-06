<script setup lang="ts">
import { computed, toRef, useTemplateRef } from 'vue'

import { apiBaseUrl } from '@/shared/config'

import MetadataPanel from './MetadataPanel.vue'
import ViewerCanvas from './ViewerCanvas.vue'
import ViewerControls from './ViewerControls.vue'
import { useViewerDraft } from './useViewerDraft'

const props = defineProps<{ id: string }>()

const { pointSize, colorMode, status, ready, retry, reload } = useViewerDraft(toRef(props, 'id'))
const canvas = useTemplateRef('canvas')
const url = computed(() => `${apiBaseUrl}/api/pointcloud/${props.id}/viewer/metadata.json`)
</script>

<template>
  <section>
    <h1>Viewer</h1>
    <p>Point cloud: {{ id }}</p>
    <fieldset :disabled="!ready || status === 'conflict'" class="draft-controls">
      <legend>Viewer settings</legend>
      <ViewerControls
        v-model:point-size="pointSize"
        v-model:color-mode="colorMode"
        @reset-view="canvas?.resetView()"
      />
    </fieldset>
    <p v-if="status === 'loading'" role="status">Loading saved draft…</p>
    <p v-else-if="status === 'dirty'" role="status">Unsaved viewer changes.</p>
    <p v-else-if="status === 'saving'" role="status">Saving viewer draft…</p>
    <p v-else-if="status === 'saved'" role="status">Viewer draft saved.</p>
    <div v-else-if="status === 'error'" role="alert">
      Draft could not be saved or loaded. Your current settings are kept here.
      <button type="button" @click="retry">Retry draft</button>
    </div>
    <div v-else-if="status === 'conflict'" role="alert">
      A newer draft exists. Your current settings are kept here.
      <button type="button" @click="reload">Load latest saved draft</button>
    </div>
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

<style scoped>
.draft-controls {
  border: 0;
  margin: 0;
  padding: 0;
}
</style>
