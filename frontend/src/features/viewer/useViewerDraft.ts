import { onScopeDispose, ref, watch, type Ref } from 'vue'
import type { ColorMode } from './potreeViewer'
import { DraftApiError, viewerDraftApi, type DraftApi, type SaveDraft } from './viewerDraftApi'

type DraftStatus = 'loading' | 'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'conflict'
interface Session {
  id: string
  controller: AbortController
  revision: number
  edits: number
  writing: boolean
  blocked: boolean
  pending: { command: SaveDraft; edit: number } | null
  timer?: ReturnType<typeof setTimeout>
}

export function useViewerDraft(datasetId: Ref<string>, api: DraftApi = viewerDraftApi) {
  const pointSize = ref(1)
  const colorMode = ref<ColorMode>('rgb')
  const status = ref<DraftStatus>('loading')
  const ready = ref(false)
  let session: Session | undefined

  function stop() {
    session?.controller.abort()
    clearTimeout(session?.timer)
  }
  function schedule(s: Session) {
    clearTimeout(s.timer)
    s.timer = setTimeout(() => void save(s), 300)
  }
  async function reload() {
    stop()
    const s: Session = {
      id: datasetId.value,
      controller: new AbortController(),
      revision: 0,
      edits: 0,
      writing: false,
      blocked: false,
      pending: null,
    }
    session = s
    ready.value = false
    status.value = 'loading'
    try {
      const draft = await api.load(s.id, s.controller.signal)
      if (session !== s || s.controller.signal.aborted) return
      s.revision = draft.revision
      pointSize.value = draft.state.pointSize
      colorMode.value = draft.state.colorMode
      ready.value = true
      status.value = 'idle'
    } catch {
      if (session === s && !s.controller.signal.aborted) status.value = 'error'
    }
  }
  async function save(s: Session) {
    if (session !== s || s.writing || s.blocked || !ready.value) return
    s.pending ??= {
      command: {
        expectedRevision: s.revision,
        operationId: crypto.randomUUID(),
        state: { pointSize: pointSize.value, colorMode: colorMode.value },
      },
      edit: s.edits,
    }
    const pending = s.pending
    s.writing = true
    status.value = 'saving'
    try {
      const acknowledged = await api.save(s.id, pending.command, s.controller.signal)
      if (session !== s || s.controller.signal.aborted) return
      if (
        acknowledged.revision !== pending.command.expectedRevision + 1 ||
        acknowledged.state.pointSize !== pending.command.state.pointSize ||
        acknowledged.state.colorMode !== pending.command.state.colorMode
      ) {
        throw new Error('The saved draft acknowledgement did not match this edit.')
      }
      s.revision = acknowledged.revision
      s.pending = null
      if (s.edits === pending.edit) status.value = 'saved'
      else {
        status.value = 'dirty'
        schedule(s)
      }
    } catch (error) {
      if (session !== s || s.controller.signal.aborted) return
      s.blocked = error instanceof DraftApiError && error.status === 409
      status.value = s.blocked ? 'conflict' : 'error'
    } finally {
      s.writing = false
    }
  }

  watch(
    [pointSize, colorMode],
    () => {
      const s = session
      if (!s || !ready.value || s.blocked) return
      s.edits += 1
      if (s.pending && !s.writing) return
      status.value = 'dirty'
      if (!s.writing && !s.pending) schedule(s)
    },
    { flush: 'sync' },
  )
  watch(datasetId, () => void reload(), { immediate: true })
  onScopeDispose(stop)

  return {
    pointSize,
    colorMode,
    status,
    ready,
    reload,
    retry: () => (ready.value && session ? save(session) : reload()),
  }
}
