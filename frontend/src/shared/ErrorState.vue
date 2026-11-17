<script setup lang="ts">
withDefaults(defineProps<{ message: string; title?: string; retryable?: boolean }>(), {
  title: undefined,
  retryable: false,
})

defineEmits<{ retry: [] }>()
</script>

<template>
  <section role="alert" class="error-state">
    <h2 v-if="title">{{ title }}</h2>
    <p>{{ message }}</p>
    <button v-if="retryable" type="button" @click="$emit('retry')">Try again</button>
    <slot />
  </section>
</template>

<style scoped>
.error-state {
  color: #b00020;
}
</style>
