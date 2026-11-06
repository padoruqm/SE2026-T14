import { apiBaseUrl } from '@/shared/config'
import type { SaveViewerDraft, ViewerDraft } from '@/api/generated'

export type { ViewerState, ViewerDraft } from '@/api/generated'
export type SaveDraft = SaveViewerDraft
export interface DraftApi {
  load(id: string, signal: AbortSignal): Promise<ViewerDraft>
  save(id: string, command: SaveDraft, signal: AbortSignal): Promise<ViewerDraft>
}
export class DraftApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
  }
}

async function request(id: string, signal: AbortSignal, command?: SaveDraft): Promise<ViewerDraft> {
  const response = await fetch(`${apiBaseUrl}/api/pointcloud/${encodeURIComponent(id)}/draft`, {
    method: command ? 'PUT' : 'GET',
    signal,
    ...(command && {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(command),
    }),
  })
  if (!response.ok) {
    throw new DraftApiError(response.status, `Draft request failed (${response.status}).`)
  }
  const draft = (await response.json()) as ViewerDraft
  if (
    !draft ||
    !Number.isSafeInteger(draft.revision) ||
    draft.revision < 0 ||
    !draft.state ||
    !Number.isFinite(draft.state.pointSize) ||
    draft.state.pointSize < 1 ||
    draft.state.pointSize > 5 ||
    draft.state.pointSize % 0.5 !== 0 ||
    !['rgb', 'elevation', 'intensity'].includes(draft.state.colorMode)
  )
    throw new Error('Invalid draft response; saved state could not be verified.')
  return draft
}

export const viewerDraftApi: DraftApi = {
  load: (id, signal) => request(id, signal),
  save: (id, command, signal) => request(id, signal, command),
}
