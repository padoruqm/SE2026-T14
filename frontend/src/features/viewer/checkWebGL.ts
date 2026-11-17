/** True when the browser can create a WebGL context, which the Potree viewer needs. */
export function checkWebGL(): boolean {
  try {
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('webgl2') ?? canvas.getContext('webgl')
    context?.getExtension('WEBGL_lose_context')?.loseContext()
    return context !== null
  } catch {
    return false
  }
}
