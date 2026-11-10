<script setup lang="ts">
import { computed, ref, useTemplateRef } from 'vue'

import { CropPanel, useCropSelection, type CropBounds } from '@/features/crop'
import type { Vec3 } from '@/features/measure'
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
const datasetBounds = computed<CropBounds | null>(() => pointCloud.value?.metadata.bounds ?? null)
const crop = useCropSelection(datasetBounds)
// Both tools pick points in the viewer, so only one is on at a time.
const cropOutline = computed(() => crop.bounds.value ?? crop.selection.value)

function toggleMeasure(): void {
  if (active.value) {
    measure.stop()
    return
  }
  crop.stopPicking()
  measure.start()
}

function toggleCropPicking(): void {
  if (crop.picking.value) {
    crop.stopPicking()
    return
  }
  measure.stop()
  crop.startPicking()
}

function onPick(point: Vec3): void {
  if (active.value) measure.addPoint(point)
  else crop.addCorner(point)
}
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
      :picking="crop.picking.value"
      :crop-bounds="cropOutline"
      :crop-corners="crop.corners.value"
      :measure-points="points"
      :measure-label="measureLabel"
      @pick="onPick"
    />
    <MeasurePanel
      :active="active"
      :coordinates="coordinates"
      :measurement="measurement"
      :confirming-clear="confirmingClear"
      :crs="crs"
      @toggle="toggleMeasure"
      @request-clear="measure.requestClear"
      @confirm-clear="measure.confirmClear"
      @cancel-clear="measure.cancelClear"
    />
    <CropPanel
      :picking="crop.picking.value"
      :corner-count="crop.corners.value.length"
      :selection="crop.selection.value"
      :bounds="crop.bounds.value"
      :error="crop.error.value"
      :crs="crs"
      @toggle-picking="toggleCropPicking"
      @change="crop.setBounds"
      @clear="crop.clear"
    />
    <MetadataPanel :id="id" />
  </section>
</template>
