<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import { mountPotreeViewer, type ColorMode, type PotreeViewerHandle } from './potreeViewer'

const props = defineProps<{ url: string; pointSize: number; colorMode: ColorMode }>()

const element = ref<HTMLElement | null>(null)
const error = ref<string | null>(null)
let handle: PotreeViewerHandle | null = null
let unmounted = false

defineExpose({ resetView: () => handle?.resetView() })

watch(
  () => props.pointSize,
  (size) => handle?.setPointSize(size),
)
watch(
  () => props.colorMode,
  (mode) => handle?.setColorMode(mode),
)

onMounted(async () => {
  try {
    const mounted = await mountPotreeViewer(element.value!, props.url)
    if (unmounted) return mounted.dispose()
    handle = mounted
    handle.setPointSize(props.pointSize)
    handle.setColorMode(props.colorMode)
  } catch {
    error.value = 'The 3D viewer could not be loaded.'
  }
})

onBeforeUnmount(() => {
  unmounted = true
  handle?.dispose()
})
</script>

<template>
  <div>
    <p v-if="error" role="alert">{{ error }}</p>
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
