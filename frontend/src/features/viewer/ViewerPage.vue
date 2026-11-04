<script setup lang="ts">
import { computed, ref, useTemplateRef } from 'vue'

import { MeasurePanel, distanceUnit, formatLength, useMeasure } from '@/features/measure'
import { apiBaseUrl } from '@/shared/config'

import MetadataPanel from './MetadataPanel.vue'
import ViewerCanvas from './ViewerCanvas.vue'
import ViewerControls from './ViewerControls.vue'
import type { ColorMode } from './potreeViewer'
import { usePointCloudMetadata } from './usePointCloudMetadata'

const props = defineProps<{ id: string }>()

const pointSize = ref(1)
const colorMode = ref<ColorMode>('rgb')
const canvas = useTemplateRef('canvas')
const { active, points, coordinates, measurement, confirmingClear, ...measure } = useMeasure()
const { pointCloud } = usePointCloudMetadata(() => props.id)
const crs = computed(() => pointCloud.value?.metadata.crs ?? null)
const measureLabel = computed(() =>
  measurement.value && !distanceUnit(crs.value).geographic
    ? formatLength(measurement.value.distance, crs.value)
    : null,
)
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
      :measuring="active"
      :measure-points="points"
      :measure-label="measureLabel"
      @pick="measure.addPoint"
    />
    <MeasurePanel
      :active="active"
      :coordinates="coordinates"
      :measurement="measurement"
      :confirming-clear="confirmingClear"
      :crs="crs"
      @toggle="active ? measure.stop() : measure.start()"
      @request-clear="measure.requestClear"
      @confirm-clear="measure.confirmClear"
      @cancel-clear="measure.cancelClear"
    />
    <MetadataPanel :id="id" />
  </section>
</template>
