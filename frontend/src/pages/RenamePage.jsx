import { useState, useEffect, useContext } from 'react'
import { FileText, Pencil, RefreshCw, CheckCircle, Loader, Check } from 'lucide-react'
import { documents, settings as settingsApi } from '../api'
import { ToastContext } from '../App'
import { useI18n } from '../i18n'
import './RenamePage.css'

export default function RenamePage({ onRenameCountChange }) {
  const [docs, setDocs] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [selectedName, setSelectedName] = useState('')
  const [customName, setCustomName] = useState('')
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [applying, setApplying] = useState(false)
  const [bulkApplying, setBulkApplying] = useState(false)
  const [autoRename, setAutoRename] = useState(false)
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

  const selected = docs.find(d => d.doc_id === selectedId)

  const handleSelect = async (doc) => {
    setSelectedId(doc.doc_id)
    setSelectedName('')
    setCustomName('')
    // If no suggestions yet, generate them
    if (!doc.rename_suggestions || doc.rename_suggestions.length === 0) {
      setGenerating(true)
      try {
        const res = await documents.generateSuggestions(doc.doc_id)
        setDocs(prev => prev.map(d =>
          d.doc_id === doc.doc_id ? { ...d, rename_suggestions: res.suggestions } : d
        ))
      } catch (err) {
        addToast('Failed to generate suggestions', 'error')
      } finally { setGenerating(false) }
    }
  }

  const handleApply = async () => {
    const name = selectedName || customName
    if (!name || !selectedId) return
    setApplying(true)
    try {
      await documents.applyRename(selectedId, name)
      addToast(`Renamed to ${name}`, 'success')
      setDocs(prev => prev.filter(d => d.doc_id !== selectedId))
      // Select next doc
      const remaining = docs.filter(d => d.doc_id !== selectedId)
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
    setGenerating(true)
    try {
      const res = await documents.generateSuggestions(selectedId)
      setDocs(prev => prev.map(d =>
        d.doc_id === selectedId ? { ...d, rename_suggestions: res.suggestions } : d
      ))
      setSelectedName('')
      setCustomName('')
    } catch { addToast('Regeneration failed', 'error') }
    finally { setGenerating(false) }
  }

  const handleBulkApprove = async () => {
    const items = docs
      .filter(d => d.rename_suggestions && d.rename_suggestions.length > 0)
      .map(d => ({ doc_id: d.doc_id, new_name: d.rename_suggestions[0] }))
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

  const handleAutoToggle = async (val) => {
    setAutoRename(val)
    try {
      await settingsApi.update({ auto_rename: val })
    } catch { }
  }

  const getFileIcon = (type) => {
    return <FileText size={16} />
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
          {docs.length > 0 && (
            <button className="btn btn-primary" onClick={handleBulkApprove} disabled={bulkApplying}>
              {bulkApplying ? <Loader size={14} className="spinning" /> : <Check size={14} />}
              {t('rename.approve_all')}
            </button>
          )}
        </div>
      </div>

      {docs.length === 0 ? (
        <div className="rename-empty card">
          <CheckCircle size={48} />
          <h2>{t('rename.no_docs')}</h2>
          <p>{t('rename.no_docs_desc')}</p>
        </div>
      ) : (
        <div className="rename-layout">
          <div className="rename-list card">
            {docs.map(doc => (
              <div
                key={doc.doc_id}
                className={`rename-item ${doc.doc_id === selectedId ? 'selected' : ''}`}
                onClick={() => handleSelect(doc)}
              >
                <div className="rename-item-icon">{getFileIcon(doc.file_type)}</div>
                <div className="rename-item-info">
                  <span className="rename-item-name">{doc.filename}</span>
                  <span className="rename-item-meta">
                    {doc.folder && <span className="badge badge-sm">{doc.folder}</span>}
                    {(doc.rename_suggestions?.length || 0) > 0 && (
                      <span className="rename-suggestion-count">{doc.rename_suggestions.length} suggestions</span>
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
                    onError={(e) => { e.target.style.display = 'none'; e.target.nextSibling.style.display = 'block' }}
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
                    <button className="btn btn-ghost btn-sm" onClick={handleRegenerate} disabled={generating}>
                      <RefreshCw size={14} className={generating ? 'spinning' : ''} />
                      {t('rename.regenerate')}
                    </button>
                  </div>

                  {generating ? (
                    <div className="rename-generating">
                      <Loader size={16} className="spinning" />
                      <span>{t('rename.generating')}</span>
                    </div>
                  ) : (
                    <div className="rename-suggestion-pills">
                      {(selected.rename_suggestions || []).map((s, i) => (
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
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
