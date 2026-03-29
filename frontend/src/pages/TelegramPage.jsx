import { useState, useEffect, useContext } from 'react'
import { Send, Phone, Shield, Download, CheckSquare, Square, Loader, CheckCircle, StopCircle } from 'lucide-react'
import { telegram } from '../api'
import { ToastContext } from '../App'
import './TelegramPage.css'

export default function TelegramPage() {
  const [step, setStep] = useState(1)
  const [phone, setPhone] = useState('')
  const [code, setCode] = useState('')
  const [status, setStatus] = useState(null)
  const [messages, setMessages] = useState([])
  const [selected, setSelected] = useState(new Set())
  const [loading, setLoading] = useState(false)
  const [importing, setImporting] = useState(false)
  const [importDone, setImportDone] = useState(false)
  const [importPhase, setImportPhase] = useState(null) // 'downloading' | 'processing'
  const [downloads, setDownloads] = useState([])
  const [processItems, setProcessItems] = useState([])
  const [importSummary, setImportSummary] = useState(null)
  const [importStopped, setImportStopped] = useState(false)
  const [phaseTotal, setPhaseTotal] = useState(0)
  const { addToast } = useContext(ToastContext)

  useEffect(() => {
    checkStatus()
  }, [])

  const checkStatus = async () => {
    try {
      const res = await telegram.getStatus()
      setStatus(res)
      if (res.authenticated) {
        setStep(3)
      }
    } catch {
      // Telegram not configured
    }
  }

  const handleStartAuth = async (e) => {
    e.preventDefault()
    if (!phone.trim()) return
    setLoading(true)
    try {
      await telegram.startAuth(phone.trim())
      setStep(2)
      addToast('Verification code sent', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleVerify = async (e) => {
    e.preventDefault()
    if (!code.trim()) return
    setLoading(true)
    try {
      await telegram.verifyAuth(code.trim())
      setStep(3)
      addToast('Authenticated successfully', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleFetch = async () => {
    setLoading(true)
    try {
      const res = await telegram.fetchMessages()
      setMessages(res.messages || res || [])
      setSelected(new Set())
      addToast(`Found ${(res.messages || res || []).length} messages`, 'info')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const toggleSelect = (id) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAll = () => {
    if (selected.size === messages.length) {
      setSelected(new Set())
    } else {
      setSelected(new Set(messages.map(m => m.message_id)))
    }
  }

  const handleImport = async () => {
    if (selected.size === 0) return
    setImporting(true)
    setDownloads([])
    setProcessItems([])
    setImportSummary(null)
    setImportStopped(false)
    setImportPhase(null)
    setStep(4)
    try {
      const result = await telegram.importMessages(Array.from(selected), (data) => {
        if (data.type === 'phase') {
          setImportPhase(data.phase)
          setPhaseTotal(data.total)
        } else if (data.type === 'download') {
          setDownloads(prev => {
            const updated = [...prev]
            updated[data.index] = data
            return updated
          })
        } else if (data.type === 'process') {
          setProcessItems(prev => {
            const updated = [...prev]
            updated[data.index] = data
            return updated
          })
        } else if (data.type === 'complete') {
          setImportSummary(data)
          setImportDone(true)
        } else if (data.type === 'stopped') {
          setImportSummary(data)
          setImportStopped(true)
          setImportDone(true)
        }
      })
      if (result?.type === 'stopped') {
        addToast(`Import stopped. ${result.completed || 0} document(s) saved.`, 'info')
      } else if (result) {
        addToast(`Imported ${result.completed} of ${result.total} document(s)`, 'success')
      }
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setImporting(false)
    }
  }

  const handleStop = async () => {
    try {
      await telegram.stopImport()
      addToast('Stopping import after current item...', 'info')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const stageLabels = {
    downloading: 'Downloading...', downloaded: 'Downloaded', exists: 'Already exists',
    parsing: 'Parsing...', embedding: 'Embedding...', storing: 'Storing...',
    sorting: 'Sorting...', done: 'Done', error: 'Failed', skipped: 'Skipped',
  }

  const stageColors = {
    downloading: 'var(--accent)', downloaded: 'var(--success)', exists: 'var(--text-secondary)',
    parsing: 'var(--warning)', embedding: 'var(--accent)', storing: 'var(--accent)',
    sorting: 'var(--accent)', done: 'var(--success)', error: 'var(--error)',
    skipped: 'var(--text-secondary)',
  }

  return (
    <div className="telegram-page page">
      <div className="section-header">
        <h1 className="section-title">Telegram Import</h1>
      </div>

      <div className="telegram-steps">
        <div className={`telegram-step-indicator ${step >= 1 ? 'active' : ''} ${step > 1 ? 'done' : ''}`}>
          <div className="step-circle">{step > 1 ? <CheckCircle size={16} /> : '1'}</div>
          <span>Phone</span>
        </div>
        <div className="step-line" />
        <div className={`telegram-step-indicator ${step >= 2 ? 'active' : ''} ${step > 2 ? 'done' : ''}`}>
          <div className="step-circle">{step > 2 ? <CheckCircle size={16} /> : '2'}</div>
          <span>Verify</span>
        </div>
        <div className="step-line" />
        <div className={`telegram-step-indicator ${step >= 3 ? 'active' : ''} ${step > 3 ? 'done' : ''}`}>
          <div className="step-circle">{step > 3 ? <CheckCircle size={16} /> : '3'}</div>
          <span>Fetch</span>
        </div>
        <div className="step-line" />
        <div className={`telegram-step-indicator ${step >= 4 ? 'active' : ''} ${importDone ? 'done' : ''}`}>
          <div className="step-circle">{importDone ? <CheckCircle size={16} /> : '4'}</div>
          <span>Import</span>
        </div>
      </div>

      <div className="telegram-content card">
        {step === 1 && (
          <form className="telegram-form" onSubmit={handleStartAuth}>
            <div className="telegram-form-icon">
              <Phone size={32} />
            </div>
            <h2>Enter your phone number</h2>
            <p>We will send a verification code via Telegram.</p>
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+1234567890"
              disabled={loading}
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!phone.trim() || loading}
            >
              {loading ? <Loader size={16} className="spinning" /> : <Send size={16} />}
              Send Code
            </button>
          </form>
        )}

        {step === 2 && (
          <form className="telegram-form" onSubmit={handleVerify}>
            <div className="telegram-form-icon">
              <Shield size={32} />
            </div>
            <h2>Enter verification code</h2>
            <p>Check your Telegram app for the code.</p>
            <input
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="12345"
              disabled={loading}
              autoFocus
            />
            <button
              type="submit"
              className="btn btn-primary"
              disabled={!code.trim() || loading}
            >
              {loading ? <Loader size={16} className="spinning" /> : <Shield size={16} />}
              Verify
            </button>
          </form>
        )}

        {step === 3 && !messages.length && (
          <div className="telegram-fetch">
            <div className="telegram-form-icon">
              <Download size={32} />
            </div>
            <h2>Fetch Messages</h2>
            <p>Retrieve recent saved messages and documents from Telegram.</p>
            <button
              className="btn btn-primary"
              onClick={() => { handleFetch(); setStep(3) }}
              disabled={loading}
            >
              {loading ? <Loader size={16} className="spinning" /> : <Download size={16} />}
              Fetch Messages
            </button>
          </div>
        )}

        {step >= 3 && messages.length > 0 && !importDone && (
          <div className="telegram-messages">
            <div className="telegram-messages-header">
              <button className="btn btn-ghost btn-sm" onClick={toggleAll}>
                {selected.size === messages.length
                  ? <CheckSquare size={16} />
                  : <Square size={16} />}
                {selected.size === messages.length ? 'Deselect All' : 'Select All'}
              </button>
              <span className="telegram-selected-count">
                {selected.size} of {messages.length} selected
              </span>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleImport}
                disabled={selected.size === 0 || importing}
              >
                {importing ? <Loader size={14} className="spinning" /> : <Download size={14} />}
                Import Selected
              </button>
            </div>

            <div className="telegram-messages-list">
              {messages.map((msg) => (
                <div
                  key={msg.message_id}
                  className={`telegram-msg ${selected.has(msg.message_id) ? 'selected' : ''}`}
                  onClick={() => toggleSelect(msg.message_id)}
                >
                  <div className="telegram-msg-check">
                    {selected.has(msg.message_id) ? <CheckSquare size={18} /> : <Square size={18} />}
                  </div>
                  <div className="telegram-msg-content">
                    <span className="telegram-msg-text">
                      {msg.text || msg.filename || 'Document'}
                    </span>
                    {msg.date && (
                      <span className="telegram-msg-date">
                        {new Date(msg.date).toLocaleString()}
                      </span>
                    )}
                  </div>
                  {msg.file_type && (
                    <span className="badge">{msg.file_type}</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {step === 4 && (importing || importDone) && (
          <div className="telegram-import-progress">

            {/* Phase 1: Downloads */}
            {(importPhase === 'downloading' || importPhase === 'processing' || importDone) && downloads.length > 0 && (
              <div className="import-phase">
                <div className="import-overall-header">
                  <h2>{importPhase === 'downloading' ? 'Downloading from Telegram...' : 'Downloads complete'}</h2>
                  <span className="import-counter">
                    {downloads.filter(d => d && (d.stage === 'downloaded' || d.stage === 'skipped' || d.stage === 'exists')).length} / {selected.size}
                  </span>
                </div>
                <div className="import-progress-bar">
                  <div className="import-progress-fill" style={{
                    width: `${(downloads.filter(d => d && d.stage !== 'downloading').length / selected.size) * 100}%`,
                    background: importPhase !== 'downloading' ? 'var(--success)' : 'var(--accent)',
                  }} />
                </div>
                {importPhase === 'downloading' && (
                  <div className="import-items-list">
                    {downloads.slice(-5).filter(Boolean).map((item, idx) => (
                      <div key={idx} className={`import-item ${item.stage}`}>
                        <div className="import-item-icon">
                          {(item.stage === 'downloaded' || item.stage === 'exists') ? <CheckCircle size={16} /> :
                           item.stage === 'error' ? <span className="import-error-icon">!</span> :
                           item.stage === 'skipped' ? <span className="import-skip-icon">-</span> :
                           <Loader size={16} className="spinning" />}
                        </div>
                        <div className="import-item-name">{item.filename}</div>
                        <div className="import-item-stage" style={{ color: stageColors[item.stage] }}>
                          {stageLabels[item.stage] || item.stage}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Phase 2: Processing */}
            {(importPhase === 'processing' || importDone) && (
              <div className="import-phase">
                <div className="import-overall-header">
                  <h2>{importDone ? 'Import Complete' : 'Processing documents...'}</h2>
                  <span className="import-counter">
                    {processItems.filter(p => p && (p.stage === 'done' || p.stage === 'error')).length} / {phaseTotal}
                  </span>
                </div>
                <div className="import-progress-bar">
                  <div className="import-progress-fill" style={{
                    width: `${phaseTotal > 0 ? (processItems.filter(p => p && (p.stage === 'done' || p.stage === 'error')).length / phaseTotal) * 100 : 0}%`,
                    background: importDone ? 'var(--success)' : 'var(--warning)',
                  }} />
                </div>
                <div className="import-items-list">
                  {processItems.filter(Boolean).map((item, idx) => (
                    <div key={idx} className={`import-item ${item.stage}`}>
                      <div className="import-item-icon">
                        {item.stage === 'done' ? <CheckCircle size={16} /> :
                         item.stage === 'error' ? <span className="import-error-icon">!</span> :
                         <Loader size={16} className="spinning" />}
                      </div>
                      <div className="import-item-name">{item.filename}</div>
                      <div className="import-item-stage" style={{ color: stageColors[item.stage] }}>
                        {stageLabels[item.stage] || item.stage}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Stop button during import */}
            {importing && !importDone && (
              <button className="btn btn-danger" onClick={handleStop}>
                <StopCircle size={16} />
                Stop Import
              </button>
            )}

            {/* Summary */}
            {importSummary && (
              <div className="import-summary">
                {importStopped && <span className="import-stat warning">Import stopped</span>}
                <span className="import-stat success">{importSummary.completed || 0} imported</span>
                {(importSummary.errors || 0) > 0 && <span className="import-stat error">{importSummary.errors} failed</span>}
                {(importSummary.remaining || 0) > 0 && <span className="import-stat warning">{importSummary.remaining} remaining</span>}
              </div>
            )}

            {importDone && (
              <button
                className="btn btn-secondary"
                onClick={() => {
                  setImportDone(false)
                  setImportStopped(false)
                  setDownloads([])
                  setProcessItems([])
                  setImportSummary(null)
                  setImportPhase(null)
                  setMessages([])
                  setSelected(new Set())
                  setStep(3)
                }}
              >
                Import More
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
