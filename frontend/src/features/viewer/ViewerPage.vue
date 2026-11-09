<script setup lang="ts">
import { computed, ref, useTemplateRef } from 'vue'
import { RouterLink } from 'vue-router'

import EmptyState from '@/shared/EmptyState.vue'
import ErrorState from '@/shared/ErrorState.vue'
import LoadingState from '@/shared/LoadingState.vue'
import { apiBaseUrl } from '@/shared/config'

import MetadataPanel from './MetadataPanel.vue'
import ViewerCanvas from './ViewerCanvas.vue'
import ViewerControls from './ViewerControls.vue'
import { checkWebGL } from './checkWebGL'
import type { ColorMode } from './potreeViewer'
import { usePointCloudMetadata } from './usePointCloudMetadata'

const props = defineProps<{ id: string }>()

const webgl = checkWebGL()
const { state, pointCloud, error, errorKind, reload } = usePointCloudMetadata(() => props.id)

const pointSize = ref(1)
const colorMode = ref<ColorMode>('rgb')
const canvas = useTemplateRef('canvas')
const url = computed(() => `${apiBaseUrl}/api/pointcloud/${props.id}/viewer/metadata.json`)
const notFound = computed(() => state.value === 'error' && errorKind.value === 'notFound')
const conversionFailed = computed(() => pointCloud.value?.status === 'failed')
</script>

<template>
  <section>
    <h1>Viewer</h1>
    <p>Point cloud: {{ id }}</p>

    <ErrorState
      v-if="!webgl"
      title="3D view is not available"
      message="Your browser could not start WebGL, which the viewer needs. Turn on hardware acceleration or try another browser, such as a current version of Chrome, Edge or Firefox."
    >
      <RouterLink to="/upload">Back to upload</RouterLink>
    </ErrorState>

    <LoadingState v-else-if="state === 'loading'" label="Loading point cloud…" />

    <ErrorState
      v-else-if="notFound"
      title="Point cloud not found"
      message="This point cloud does not exist or was removed."
    >
      <RouterLink to="/upload">Back to upload</RouterLink>
    </ErrorState>

    <ErrorState v-else-if="state === 'error'" :message="error ?? ''" retryable @retry="reload">
      <RouterLink to="/upload">Back to upload</RouterLink>
    </ErrorState>

    <ErrorState
      v-else-if="conversionFailed"
      title="Processing failed"
      message="This point cloud could not be prepared for viewing. Upload the file again."
    >
      <RouterLink to="/upload">Back to upload</RouterLink>
    </ErrorState>

    <template v-else>
      <EmptyState
        v-if="state === 'empty'"
        title="No details yet"
        message="The file has no readable header information, but you can still try to view it."
      />
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
    </template>
  </section>
</template>
