const API_BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }))
    const detail = typeof error.detail === 'string' ? error.detail : JSON.stringify(error.detail)
    throw new Error(detail || `Request failed: ${res.status}`)
  }
  return res.json()
}

// Documents
export const documents = {
  list: (folder = null, search = null) => {
    const params = new URLSearchParams()
    if (folder) params.set('folder', folder)
    if (search) params.set('search', search)
    const qs = params.toString()
    return request(`/documents${qs ? '?' + qs : ''}`)
  },

  pending: () => request('/documents/pending'),

  get: (id) => request(`/documents/${id}`),

  upload: async (files, folder = null) => {
    const formData = new FormData()
    for (const file of files) {
      formData.append('files', file)
    }
    if (folder) formData.append('folder', folder)
    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      body: formData,
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(error.detail || 'Upload failed')
    }
    return res.json()
  },

  delete: (id) => request(`/documents/${id}`, { method: 'DELETE' }),

  sort: (id) => request(`/documents/${id}/sort`, { method: 'POST' }),

  rename: (id, newName) =>
    request(`/documents/${id}/rename`, {
      method: 'POST',
      body: JSON.stringify({ new_name: newName }),
    }),

  bulkSort: () => request('/documents/bulk-sort', { method: 'POST' }),
}

// Chat
export const chat = {
  sendMessage: async (message, onChunk, onSources, onDone, onError) => {
    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message }),
      })
      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(error.detail || 'Chat request failed')
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') {
              onDone?.()
              return
            }
            try {
              const parsed = JSON.parse(data)
              if (parsed.type === 'token') {
                onChunk?.(parsed.content)
              } else if (parsed.type === 'sources') {
                onSources?.(parsed.sources)
              } else if (parsed.type === 'error') {
                onError?.(parsed.content)
              }
            } catch {
              onChunk?.(data)
            }
          }
        }
      }
      onDone?.()
    } catch (err) {
      onError?.(err.message)
    }
  },

  getHistory: () => request('/chat/history'),

  clearHistory: () => request('/chat/history', { method: 'DELETE' }),
}

// Models
export const models = {
  list: () => request('/models'),

  pull: async (name, onProgress) => {
    const res = await fetch(`${API_BASE}/models/pull`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    })
    if (!res.ok) {
      const error = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(error.detail || 'Pull failed')
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const parsed = JSON.parse(line.slice(6))
            onProgress?.(parsed)
          } catch { /* skip */ }
        }
      }
    }
  },

  getActive: () => request('/models/active'),

  setActive: (name) =>
    request('/models/active', {
      method: 'PUT',
      body: JSON.stringify({ name }),
    }),
}

// Folders
export const folders = {
  list: () => request('/folders'),

  create: (name, parent = null) =>
    request('/folders', {
      method: 'POST',
      body: JSON.stringify({ name, parent }),
    }),

  rename: (id, newName) =>
    request(`/folders/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ name: newName }),
    }),

  delete: (id) => request(`/folders/${id}`, { method: 'DELETE' }),
}

// Telegram
export const telegram = {
  startAuth: (phoneNumber) =>
    request('/telegram/auth/start', {
      method: 'POST',
      body: JSON.stringify({ phone_number: phoneNumber }),
    }),

  verifyAuth: (code) =>
    request('/telegram/auth/verify', {
      method: 'POST',
      body: JSON.stringify({ code }),
    }),

  getStatus: () => request('/telegram/status'),

  fetchMessages: (params = {}) =>
    request('/telegram/fetch', {
      method: 'POST',
      body: JSON.stringify(params),
    }),

  importMessages: async (messageIds, onProgress) => {
    const res = await fetch(`${API_BASE}/telegram/import`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message_ids: messageIds }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `Import failed: ${res.status}`)
    }
    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalResult = null
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'complete' || data.type === 'stopped') finalResult = data
            if (onProgress) onProgress(data)
          } catch {}
        }
      }
    }
    return finalResult || { total: messageIds.length, completed: 0, errors: 0 }
  },

  stopImport: () => request('/telegram/import/stop', { method: 'POST' }),

  getMessages: () => request('/telegram/messages'),
}

// Backup
export const backup = {
  triggerSnapshot: () => request('/backup/snapshot', { method: 'POST' }),

  listSnapshots: () => request('/backup/snapshots'),
}

// Bot
export const bot = {
  status: () => request('/bot/status'),
  instances: () => request('/bot/instances'),
}

// Settings
export const settings = {
  get: () => request('/settings'),

  update: (data) =>
    request('/settings', {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
}
