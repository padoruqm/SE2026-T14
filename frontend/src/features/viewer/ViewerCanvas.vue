<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { MeasureOverlay, type Vec3 } from '@/features/measure'
import ErrorState from '@/shared/ErrorState.vue'

import { mountPotreeViewer, type ColorMode, type PotreeViewerHandle } from './potreeViewer'

const props = withDefaults(
  defineProps<{
    url: string
    pointSize: number
    colorMode: ColorMode
    measuring?: boolean
    measurePoints?: Vec3[]
    measureLabel?: string | null
  }>(),
  { measuring: false, measurePoints: () => [], measureLabel: null },
)
const emit = defineEmits<{ pick: [point: Vec3] }>()

const element = ref<HTMLElement | null>(null)
const error = ref<string | null>(null)
const viewVersion = ref(0)
let handle: PotreeViewerHandle | null = null
let unmounted = false
let stopMeasuring: (() => void) | null = null
let stopUpdates: (() => void) | null = null
let attempt = 0

function project(point: Vec3) {
  return handle?.project(point) ?? { x: NaN, y: NaN, visible: false }
}

// Picking only runs while the tool is on, and markers are only placed again after
// each frame while there is something to draw.
function syncMeasuring(): void {
  stopMeasuring?.()
  stopMeasuring = null
  if (handle && props.measuring)
    stopMeasuring = handle.enableMeasure((point) => emit('pick', point))
}

function syncUpdates(): void {
  stopUpdates?.()
  stopUpdates = null
  if (handle && props.measurePoints.length > 0) {
    stopUpdates = handle.onUpdate(() => (viewVersion.value += 1))
  }
}

defineExpose({ resetView: () => handle?.resetView() })

watch(
  () => props.pointSize,
  (size) => handle?.setPointSize(size),
)
watch(
  () => props.colorMode,
  (mode) => handle?.setColorMode(mode),
)
watch(() => props.measuring, syncMeasuring)
watch(() => props.measurePoints.length > 0, syncUpdates)

async function load(): Promise<void> {
  const current = ++attempt
  error.value = null
  handle?.dispose()
  handle = null
  try {
    const mounted = await mountPotreeViewer(element.value!, props.url)
    if (unmounted || current !== attempt) return mounted.dispose()
    handle = mounted
    handle.setPointSize(props.pointSize)
    handle.setColorMode(props.colorMode)
    syncMeasuring()
    syncUpdates()
  } catch {
    if (current === attempt) error.value = 'The 3D viewer could not be loaded.'
  }
}

onMounted(load)

onBeforeUnmount(() => {
  unmounted = true
  stopMeasuring?.()
  stopUpdates?.()
  handle?.dispose()
})
</script>

<template>
  <div>
    <ErrorState v-if="error" :message="error" retryable @retry="load" />
    <div class="viewer-frame">
      <div ref="element" class="viewer-canvas" />
      <MeasureOverlay
        :points="measurePoints"
        :project="project"
        :version="viewVersion"
        :label="measureLabel"
      />
    </div>
  </div>
</template>

<style scoped>
.viewer-frame {
  position: relative;
}

.viewer-canvas {
  position: relative;
  width: 100%;
  height: 70vh;
}
</style>
