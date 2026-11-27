<script setup lang="ts">
import { computed, ref, useTemplateRef, watch } from 'vue'
import { RouterLink } from 'vue-router'

import {
  CropPanel,
  CropRequest,
  useCropRequest,
  useCropSelection,
  type CropBounds,
  type CropOutputFormat,
} from '@/features/crop'
import type { Vec3 } from '@/features/measure'
import { MeasurePanel, distanceUnit, formatLength, useMeasure } from '@/features/measure'
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
const { active, points, coordinates, measurement, confirmingClear, ...measure } = useMeasure()
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

const cropRequest = useCropRequest(() => props.id)

// Opening another point cloud (such as a crop result) reuses this page, so the
// region and measurement picked on the previous one must not carry over.
watch(
  () => props.id,
  () => {
    measure.reset()
    crop.stopPicking()
    crop.clear()
  },
)

function submitCrop(format: CropOutputFormat): void {
  if (crop.bounds.value) void cropRequest.submit(crop.bounds.value, format)
}

function onPick(point: Vec3): void {
  if (active.value) measure.addPoint(point)
  else crop.addCorner(point)
}
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
      <CropRequest
        :bounds="crop.bounds.value"
        :state="cropRequest.state.value"
        :progress="cropRequest.progress.value"
        :result-id="cropRequest.resultId.value"
        :error="cropRequest.error.value"
        :retryable="cropRequest.retryable.value"
        @submit="submitCrop"
        @retry="cropRequest.retry"
      />
      <MetadataPanel :id="id" />
    </template>
  </section>
</template>
