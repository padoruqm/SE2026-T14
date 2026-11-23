import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'

import { expect, test, type Page, type Route } from '@playwright/test'

// Same approach as measure.spec.ts: the backend is intercepted, Potree is real, and the
// octree is the generated fixture (40 x 40 grid at UTM 500000/2000000).
const FIXTURE_DIR = fileURLToPath(new URL('./fixtures/potree/', import.meta.url))
const ID = 'pc_e2e'
const RESULT_ID = 'pc_crop'
const BOUNDS = {
  minX: 500000,
  minY: 2000000,
  minZ: 100,
  maxX: 500097.5,
  maxY: 2000097.5,
  maxZ: 109.75,
}

function json(route: Route, body: unknown, status = 200) {
  return route.fulfill({ status, json: body })
}

async function serveViewerFile(route: Route, name: string) {
  const body = await readFile(`${FIXTURE_DIR}${name}`).catch(() => null)
  if (!body) return route.fulfill({ status: 404, json: { error: { code: 'NOT_FOUND' } } })
  const contentType = name.endsWith('.json') ? 'application/json' : 'application/octet-stream'
  const range = /^bytes=(\d+)-(\d*)$/.exec(route.request().headers()['range'] ?? '')
  if (!range) return route.fulfill({ status: 200, body, contentType })
  const start = Number(range[1])
  const end = range[2] ? Math.min(Number(range[2]), body.length - 1) : body.length - 1
  return route.fulfill({
    status: 206,
    body: body.subarray(start, end + 1),
    headers: {
      'content-type': contentType,
      'content-range': `bytes ${start}-${end}/${body.length}`,
    },
  })
}

function job(state: string, extra: Record<string, unknown> = {}) {
  return {
    id: 'job_crop',
    type: 'crop',
    state,
    progress: null,
    resultId: null,
    error: null,
    ...extra,
  }
}

async function mockBackend(page: Page) {
  const cropRequests: unknown[] = []
  let polls = 0
  await page.route(`**/api/pointcloud/${ID}`, (route) =>
    json(route, {
      id: ID,
      filename: 'survey.las',
      status: 'ready',
      metadata: { pointCount: 1600, bounds: BOUNDS, crs: 'EPSG:32648' },
      viewerUrl: `/api/pointcloud/${ID}/viewer/metadata.json`,
      sourceId: null,
    }),
  )
  await page.route(`**/api/pointcloud/${ID}/viewer/*`, (route) =>
    serveViewerFile(route, new URL(route.request().url()).pathname.split('/').pop() ?? ''),
  )
  await page.route(`**/api/pointcloud/${ID}/crop`, (route) => {
    cropRequests.push(route.request().postDataJSON())
    return json(route, job('queued'), 202)
  })
  await page.route('**/api/job/job_crop', (route) => {
    polls += 1
    return json(
      route,
      polls < 2
        ? job('running', { progress: 50 })
        : job('succeeded', { progress: 100, resultId: RESULT_ID }),
    )
  })
  return cropRequests
}

function numbers(text: string | null): number[] {
  return (text ?? '').split(',').map((part) => Number(part.trim()))
}

test('select a region in the viewer and send it to be cropped', async ({ page }) => {
  const cropRequests = await mockBackend(page)
  await page.goto(`/viewer/${ID}`)
  const canvas = page.locator('.viewer-canvas canvas')
  await expect(canvas).toBeVisible()
  const box = (await canvas.boundingBox())!
  const cropButton = page.getByRole('button', { name: 'Crop point cloud' })
  await expect(cropButton).toBeDisabled()

  // Pick two corners. Points load asynchronously, so retry until the first one lands.
  const result = page.locator('.crop-panel [role="status"]')
  await page.getByRole('button', { name: 'Pick region' }).click()
  await expect(async () => {
    await canvas.click({ position: { x: box.width * 0.42, y: box.height * 0.45 }, timeout: 1000 })
    await expect(page.getByText('Click the opposite corner.')).toBeVisible({ timeout: 1000 })
  }).toPass({ timeout: 30_000 })
  await canvas.click({ position: { x: box.width * 0.6, y: box.height * 0.58 } })
  await expect(result.getByText('Min', { exact: true })).toBeVisible()

  const shownMin = numbers(await result.locator('dt:text-is("Min") + dd').textContent())
  const shownMax = numbers(await result.locator('dt:text-is("Max") + dd').textContent())

  // Send it and follow the job to the result.
  await expect(cropButton).toBeEnabled()
  await cropButton.click()
  const status = page.locator('.crop-request [role="status"]')
  await expect(status).toContainText('Crop complete', { timeout: 10_000 })
  await expect(page.getByRole('link', { name: 'Open the cropped point cloud' })).toHaveAttribute(
    'href',
    `/viewer/${RESULT_ID}`,
  )

  // What was sent is exactly the box on screen, in world coordinates, inside the data.
  expect(cropRequests).toHaveLength(1)
  const sent = cropRequests[0] as { bounds: Record<string, number>; outputFormat: string }
  expect(sent.outputFormat).toBe('laz')
  const { minX, minY, minZ, maxX, maxY, maxZ } = sent.bounds
  expect([minX, minY, minZ]).toEqual(shownMin)
  expect([maxX, maxY, maxZ]).toEqual(shownMax)
  expect(minX).toBeGreaterThanOrEqual(BOUNDS.minX)
  expect(maxX).toBeLessThanOrEqual(BOUNDS.maxX)
  expect(minY).toBeGreaterThanOrEqual(BOUNDS.minY)
  expect(maxY).toBeLessThanOrEqual(BOUNDS.maxY)
  expect(maxX - minX).toBeGreaterThan(1)
  expect(maxY - minY).toBeGreaterThan(1)
})

test('a region outside the point cloud cannot be sent', async ({ page }) => {
  const cropRequests = await mockBackend(page)
  await page.goto(`/viewer/${ID}`)
  await expect(page.locator('.viewer-canvas canvas')).toBeVisible()

  const fields = page.locator('.crop-fields input')
  const outside = [600000, 600010, 3000000, 3000010, 0, 5]
  for (const [index, value] of outside.entries()) {
    await fields.nth(index).fill(String(value))
    await fields.nth(index).dispatchEvent('change')
  }

  await expect(page.locator('.crop-panel [role="alert"]')).toHaveText(
    'The region does not overlap the point cloud.',
  )
  await expect(page.getByRole('button', { name: 'Crop point cloud' })).toBeDisabled()
  expect(cropRequests).toEqual([])
})
