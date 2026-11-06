import { describe, expect, it } from 'vitest'

import { projectToScreen, type CameraLike } from '../projection'

const NEAR = 0.1
const FAR = 1000

/** Column-major perspective matrix with a 90 degree field of view and aspect 1. */
function perspective(): number[] {
  const a = -(FAR + NEAR) / (FAR - NEAR)
  const b = (-2 * FAR * NEAR) / (FAR - NEAR)
  return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, a, -1, 0, 0, b, 0]
}

function translation(x: number, y: number, z: number): number[] {
  return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, x, y, z, 1]
}

/** A camera at `position`, looking down -z, so the view matrix moves the world by -position. */
function cameraAt(x: number, y: number, z: number): CameraLike {
  return {
    matrixWorldInverse: { elements: translation(-x, -y, -z) },
    projectionMatrix: { elements: perspective() },
  }
}

describe('projectToScreen', () => {
  it('puts a point straight ahead in the middle of the canvas', () => {
    const result = projectToScreen({ x: 0, y: 0, z: -10 }, cameraAt(0, 0, 0), 800, 600)

    expect(result.visible).toBe(true)
    expect(result.x).toBeCloseTo(400, 6)
    expect(result.y).toBeCloseTo(300, 6)
  })

  it('maps the edges of the view to the edges of the canvas', () => {
    const camera = cameraAt(0, 0, 0)

    const right = projectToScreen({ x: 10, y: 0, z: -10 }, camera, 800, 600)
    const top = projectToScreen({ x: 0, y: 10, z: -10 }, camera, 800, 600)

    expect(right.x).toBeCloseTo(800, 6)
    expect(top.y).toBeCloseTo(0, 6)
  })

  it('has y growing downwards like screen pixels', () => {
    const camera = cameraAt(0, 0, 0)

    const above = projectToScreen({ x: 0, y: 5, z: -10 }, camera, 800, 600)
    const below = projectToScreen({ x: 0, y: -5, z: -10 }, camera, 800, 600)

    expect(above.y).toBeLessThan(below.y)
  })

  it('is not visible behind the camera', () => {
    const result = projectToScreen({ x: 0, y: 0, z: 10 }, cameraAt(0, 0, 0), 800, 600)

    expect(result.visible).toBe(false)
    expect(result.x).toBeNaN()
  })

  it('is not visible outside the frustum but still gives its position', () => {
    const result = projectToScreen({ x: 30, y: 0, z: -10 }, cameraAt(0, 0, 0), 800, 600)

    expect(result.visible).toBe(false)
    expect(result.x).toBeGreaterThan(800)
  })

  it('is not visible beyond the far plane or in front of the near plane', () => {
    const camera = cameraAt(0, 0, 0)

    expect(projectToScreen({ x: 0, y: 0, z: -2000 }, camera, 800, 600).visible).toBe(false)
    expect(projectToScreen({ x: 0, y: 0, z: -0.01 }, camera, 800, 600).visible).toBe(false)
  })

  it('keeps sub-pixel accuracy at survey-scale world coordinates', () => {
    const camera = cameraAt(500000, 2000000, 100)

    const centre = projectToScreen({ x: 500000, y: 2000000, z: 90 }, camera, 800, 600)
    const offset = projectToScreen({ x: 500001, y: 2000000, z: 90 }, camera, 800, 600)

    expect(centre.x).toBeCloseTo(400, 6)
    expect(centre.y).toBeCloseTo(300, 6)
    expect(offset.x).toBeCloseTo(400 + 40, 6)
  })

  it('works with an orthographic-style projection where w is 1', () => {
    const camera: CameraLike = {
      matrixWorldInverse: { elements: translation(0, 0, 0) },
      projectionMatrix: { elements: [0.1, 0, 0, 0, 0, 0.1, 0, 0, 0, 0, -0.002, 0, 0, 0, -1, 1] },
    }

    const result = projectToScreen({ x: 5, y: 0, z: -10 }, camera, 800, 600)

    expect(result.visible).toBe(true)
    expect(result.x).toBeCloseTo(600, 6)
  })
})
