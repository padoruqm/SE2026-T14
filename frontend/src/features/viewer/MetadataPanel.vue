<script setup lang="ts">
import { computed } from 'vue'

import { boundsRows, formatPointCount } from './formatMetadata'
import { usePointCloudMetadata } from './usePointCloudMetadata'

const props = defineProps<{ id: string }>()

const { state, pointCloud, error, reload } = usePointCloudMetadata(() => props.id)

const metadata = computed(() => pointCloud.value?.metadata ?? null)
const rows = computed(() => (metadata.value?.bounds ? boundsRows(metadata.value.bounds) : []))
</script>

<template>
  <section
    class="metadata-panel"
    aria-labelledby="metadata-heading"
    :aria-busy="state === 'loading'"
  >
    <h2 id="metadata-heading">Metadata</h2>

    <p v-if="state === 'loading'" role="status">Loading metadata…</p>

    <div v-else-if="state === 'error'">
      <p role="alert" class="metadata-error">{{ error }}</p>
      <button type="button" @click="reload">Try again</button>
    </div>

    <p v-else-if="state === 'empty'" role="status">
      No metadata is available for this point cloud yet.
    </p>

    <template v-else-if="pointCloud && metadata">
      <dl class="metadata-summary">
        <dt>File</dt>
        <dd>{{ pointCloud.filename }}</dd>
        <dt>Points</dt>
        <dd>
          {{
            metadata.pointCount === null ? 'Not available' : formatPointCount(metadata.pointCount)
          }}
        </dd>
        <dt>CRS</dt>
        <dd>{{ metadata.crs ?? 'Not available' }}</dd>
      </dl>

      <table v-if="rows.length > 0" class="metadata-bounds">
        <caption>
          Bounds
        </caption>
        <thead>
          <tr>
            <th scope="col">Axis</th>
            <th scope="col">Min</th>
            <th scope="col">Max</th>
            <th scope="col">Extent</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.axis">
            <th scope="row">{{ row.axis }}</th>
            <td>{{ row.min }}</td>
            <td>{{ row.max }}</td>
            <td>{{ row.extent }}</td>
          </tr>
        </tbody>
      </table>
      <p v-else>Bounds: Not available</p>
    </template>
  </section>
</template>

<style scoped>
.metadata-summary {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.25rem 1rem;
}

.metadata-summary dt {
  font-weight: 600;
}

.metadata-summary dd {
  margin: 0;
}

.metadata-bounds {
  border-collapse: collapse;
  margin-top: 0.75rem;
  font-variant-numeric: tabular-nums;
}

.metadata-bounds caption {
  text-align: left;
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.metadata-bounds th,
.metadata-bounds td {
  padding: 0.25rem 0.75rem;
  text-align: right;
  border-bottom: 1px solid #ddd;
}

.metadata-bounds th[scope='row'],
.metadata-bounds th[scope='col']:first-child {
  text-align: left;
}

.metadata-error {
  color: #b00020;
}
</style>
