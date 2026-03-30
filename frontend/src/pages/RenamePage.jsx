import { useState, useEffect, useContext, useMemo } from 'react'
import { FileText, Image, Pencil, RefreshCw, CheckCircle, Loader, Check, Trash2, Filter } from 'lucide-react'
import { documents, settings as settingsApi } from '../api'
import { ToastContext } from '../App'
import { useI18n } from '../i18n'
import './RenamePage.css'

const IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'tif']

function isImageFile(filename) {
  const ext = (filename || '').split('.').pop().toLowerCase()
  return IMAGE_EXTS.includes(ext)
}

export default function RenamePage({ onRenameCountChange }) {
  const [docs, setDocs] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [selectedName, setSelectedName] = useState('')
  const [customName, setCustomName] = useState('')
  const [loading, setLoading] = useState(true)
  const [generatingId, setGeneratingId] = useState(null) // track WHICH doc is generating
  const [suggestionsOverride, setSuggestionsOverride] = useState({}) // doc_id -> suggestions
  const [applying, setApplying] = useState(false)
  const [bulkApplying, setBulkApplying] = useState(false)
  const [autoRename, setAutoRename] = useState(false)
  const [filter, setFilter] = useState('all') // 'all' | 'documents' | 'images'
  const { addToast } = useContext(ToastContext)
  const { t } = useI18n()

  useEffect(() => { loadDocs(); loadSettings() }, [])

  const loadDocs = async () => {
    try {
      const res = await documents.needsRename()
      setDocs(res.documents || [])
      onRenameCountChange?.(res.total || 0)
    } catch { } finally { setLoading(false) }
  }

  const loadSettings = async () => {
    try {
      const res = await settingsApi.get()
      setAutoRename(res.auto_rename || false)
    } catch { }
  }

  // Filter docs by type
  const filteredDocs = useMemo(() => {
    if (filter === 'documents') return docs.filter(d => !isImageFile(d.filename))
    if (filter === 'images') return docs.filter(d => isImageFile(d.filename))
    return docs
  }, [docs, filter])

  const docCount = docs.filter(d => !isImageFile(d.filename)).length
  const imgCount = docs.filter(d => isImageFile(d.filename)).length

  const selected = docs.find(d => d.doc_id === selectedId)

  // Get suggestions for a doc (check override first, then original data)
  const getSuggestions = (doc) => {
    return suggestionsOverride[doc.doc_id] || doc.rename_suggestions || []
  }

  const handleSelect = async (doc) => {
    setSelectedId(doc.doc_id)
    setSelectedName('')
    setCustomName('')
    // If no suggestions yet, generate them — but only for THIS doc
    const existing = getSuggestions(doc)
    if (existing.length === 0) {
      setGeneratingId(doc.doc_id)
      try {
        const res = await documents.generateSuggestions(doc.doc_id)
        setSuggestionsOverride(prev => ({ ...prev, [doc.doc_id]: res.suggestions }))
      } catch (err) {
        addToast('Failed to generate suggestions', 'error')
      } finally { setGeneratingId(null) }
    }
  }

  const handleApply = async () => {
    const name = selectedName || customName
    if (!name || !selectedId) return
    setApplying(true)
    try {
      await documents.applyRename(selectedId, name)
      addToast(`Renamed to ${name}`, 'success')
      const remaining = docs.filter(d => d.doc_id !== selectedId)
      setDocs(remaining)
      setSelectedId(remaining.length > 0 ? remaining[0].doc_id : null)
      setSelectedName('')
      setCustomName('')
      onRenameCountChange?.(remaining.length)
    } catch (err) {
      addToast('Rename failed', 'error')
    } finally { setApplying(false) }
  }

  const handleRegenerate = async () => {
    if (!selectedId) return
    setGeneratingId(selectedId)
    try {
      const res = await documents.generateSuggestions(selectedId)
      setSuggestionsOverride(prev => ({ ...prev, [selectedId]: res.suggestions }))
      setSelectedName('')
      setCustomName('')
    } catch { addToast('Regeneration failed', 'error') }
    finally { setGeneratingId(null) }
  }

  const handleBulkApprove = async () => {
    const items = filteredDocs
      .filter(d => getSuggestions(d).length > 0)
      .map(d => ({ doc_id: d.doc_id, new_name: getSuggestions(d)[0] }))
    if (items.length === 0) {
      addToast('No documents with suggestions to approve', 'info')
      return
    }
    setBulkApplying(true)
    try {
      const res = await documents.bulkRename(items)
      const ok = res.results.filter(r => r.status === 'ok').length
      addToast(`Renamed ${ok} document(s)`, 'success')
      await loadDocs()
      setSelectedId(null)
    } catch (err) {
      addToast('Bulk rename failed', 'error')
    } finally { setBulkApplying(false) }
  }

  const handleDiscard = async () => {
    if (!selectedId) return
    try {
      await documents.dismissRename(selectedId)
      addToast('Document removed from rename queue', 'info')
      const remaining = docs.filter(d => d.doc_id !== selectedId)
      setDocs(remaining)
      setSelectedId(remaining.length > 0 ? remaining[0].doc_id : null)
      setSelectedName('')
      setCustomName('')
      onRenameCountChange?.(remaining.length)
    } catch {
      addToast('Failed to discard', 'error')
    }
  }

  const handleAutoToggle = async (val) => {
    setAutoRename(val)
    try {
      await settingsApi.update({ auto_rename: val })
    } catch { }
  }

  if (loading) {
    return (
      <div className="rename-page page">
        <div className="rename-loading"><Loader size={20} className="spinning" /> Loading...</div>
      </div>
    )
  }

  return (
    <div className="rename-page page">
      <div className="section-header">
        <h1 className="section-title">
          <Pencil size={22} />
          {t('rename.title')}
          {docs.length > 0 && <span className="rename-count-badge">{docs.length}</span>}
        </h1>
        <div className="rename-header-actions">
          <label className="toggle-label">
            <span>{t('rename.auto_mode')}</span>
            <label className="toggle">
              <input type="checkbox" checked={autoRename} onChange={e => handleAutoToggle(e.target.checked)} />
              <span className="toggle-slider" />
            </label>
          </label>
          {filteredDocs.length > 0 && (
            <button className="btn btn-primary" onClick={handleBulkApprove} disabled={bulkApplying}>
              {bulkApplying ? <Loader size={14} className="spinning" /> : <Check size={14} />}
              {t('rename.approve_all')}
            </button>
          )}
        </div>
      </div>

      {/* Filter tabs */}
      {docs.length > 0 && (
        <div className="rename-filters">
          <button
            className={`rename-filter-btn ${filter === 'all' ? 'active' : ''}`}
            onClick={() => setFilter('all')}
          >
            <Filter size={14} />
            All ({docs.length})
          </button>
          <button
            className={`rename-filter-btn ${filter === 'documents' ? 'active' : ''}`}
            onClick={() => setFilter('documents')}
          >
            <FileText size={14} />
            Documents ({docCount})
          </button>
          <button
            className={`rename-filter-btn ${filter === 'images' ? 'active' : ''}`}
            onClick={() => setFilter('images')}
          >
            <Image size={14} />
            Images ({imgCount})
          </button>
        </div>
      )}

      {docs.length === 0 ? (
        <div className="rename-empty card">
          <CheckCircle size={48} />
          <h2>{t('rename.no_docs')}</h2>
          <p>{t('rename.no_docs_desc')}</p>
        </div>
      ) : (
        <div className="rename-layout">
          <div className="rename-list card">
            {filteredDocs.map(doc => (
              <div
                key={doc.doc_id}
                className={`rename-item ${doc.doc_id === selectedId ? 'selected' : ''}`}
                onClick={() => handleSelect(doc)}
              >
                <div className="rename-item-icon">
                  {isImageFile(doc.filename) ? <Image size={16} /> : <FileText size={16} />}
                </div>
                <div className="rename-item-info">
                  <span className="rename-item-name">{doc.filename}</span>
                  <span className="rename-item-meta">
                    {doc.folder && <span className="badge badge-sm">{doc.folder}</span>}
                    {generatingId === doc.doc_id && (
                      <span className="rename-generating-badge">
                        <Loader size={10} className="spinning" /> generating...
                      </span>
                    )}
                    {generatingId !== doc.doc_id && getSuggestions(doc).length > 0 && (
                      <span className="rename-suggestion-count">{getSuggestions(doc).length} suggestions</span>
                    )}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div className="rename-preview card">
            {!selected ? (
              <div className="rename-preview-empty">
                <Pencil size={32} />
                <p>{t('rename.select_doc')}</p>
              </div>
            ) : (
              <>
                <div className="rename-preview-header">
                  <h2>{t('rename.preview')}</h2>
                </div>

                <div className="rename-current">
                  <label>{t('rename.current_name')}</label>
                  <div className="rename-current-name">{selected.filename}</div>
                </div>

                <div className="rename-doc-preview">
                  <img
                    src={`/api/documents/${selected.doc_id}/preview`}
                    alt={selected.filename}
                    onError={(e) => { e.target.style.display = 'none'; if (e.target.nextSibling) e.target.nextSibling.style.display = 'block' }}
                  />
                  <div className="rename-text-fallback" style={{ display: 'none' }}>
                    {selected.text_preview ? (
                      <pre>{selected.text_preview}</pre>
                    ) : (
                      <p>Preview not available</p>
                    )}
                  </div>
                </div>

                <div className="rename-suggestions-section">
                  <div className="rename-suggestions-header">
                    <label>{t('rename.suggestions')}</label>
                    <button className="btn btn-ghost btn-sm" onClick={handleRegenerate} disabled={generatingId === selectedId}>
                      <RefreshCw size={14} className={generatingId === selectedId ? 'spinning' : ''} />
                      {t('rename.regenerate')}
                    </button>
                  </div>

                  {generatingId === selectedId ? (
                    <div className="rename-generating">
                      <Loader size={16} className="spinning" />
                      <span>{t('rename.generating')}</span>
                    </div>
                  ) : (
                    <div className="rename-suggestion-pills">
                      {getSuggestions(selected).map((s, i) => (
                        <button
                          key={i}
                          className={`rename-pill ${selectedName === s ? 'active' : ''}`}
                          onClick={() => { setSelectedName(s); setCustomName('') }}
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  )}
                </div>

                <div className="rename-custom">
                  <input
                    type="text"
                    value={customName}
                    onChange={e => { setCustomName(e.target.value); setSelectedName('') }}
                    placeholder={t('rename.custom_name')}
                  />
                </div>

                <div className="rename-actions">
                  <button
                    className="btn btn-primary"
                    onClick={handleApply}
                    disabled={(!selectedName && !customName) || applying}
                  >
                    {applying ? <Loader size={14} className="spinning" /> : <Check size={14} />}
                    {t('rename.apply')}
                  </button>
                  <button
                    className="btn btn-danger"
                    onClick={handleDiscard}
                  >
                    <Trash2 size={14} />
                    Discard
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
