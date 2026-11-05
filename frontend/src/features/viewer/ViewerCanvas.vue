<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import ErrorState from '@/shared/ErrorState.vue'

import { mountPotreeViewer, type ColorMode, type PotreeViewerHandle } from './potreeViewer'

const props = defineProps<{ url: string; pointSize: number; colorMode: ColorMode }>()

const element = ref<HTMLElement | null>(null)
const error = ref<string | null>(null)
let handle: PotreeViewerHandle | null = null
let unmounted = false
let attempt = 0

defineExpose({ resetView: () => handle?.resetView() })

watch(
  () => props.pointSize,
  (size) => handle?.setPointSize(size),
)
watch(
  () => props.colorMode,
  (mode) => handle?.setColorMode(mode),
)

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
  } catch {
    if (current === attempt) error.value = 'The 3D viewer could not be loaded.'
  }
}

onMounted(load)

onBeforeUnmount(() => {
  unmounted = true
  handle?.dispose()
})
</script>

<template>
  <div>
    <ErrorState v-if="error" :message="error" retryable @retry="load" />
    <div ref="element" class="viewer-canvas" />
  </div>
</template>

<style scoped>
.viewer-canvas {
  position: relative;
  width: 100%;
  height: 70vh;
}
</style>
