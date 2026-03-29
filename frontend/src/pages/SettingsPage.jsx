import { useState, useEffect, useContext } from 'react'
import {
  Save, RefreshCw, Database, Loader, CheckCircle,
  AlertCircle, Clock, HardDrive,
} from 'lucide-react'
import ModelSelector from '../components/ModelSelector'
import { settings as settingsApi, backup as backupApi } from '../api'
import { ToastContext } from '../App'
import './SettingsPage.css'

export default function SettingsPage() {
  const [config, setConfig] = useState({
    auto_sort: false,
    auto_rename: false,
    confidence_threshold: 0.7,
    ocr_language: 'eng',
  })
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [snapshots, setSnapshots] = useState([])
  const [snapshotLoading, setSnapshotLoading] = useState(false)
  const [ollamaStatus, setOllamaStatus] = useState(null)
  const { addToast } = useContext(ToastContext)

  useEffect(() => {
    loadSettings()
    loadSnapshots()
    checkOllama()
  }, [])

  const loadSettings = async () => {
    try {
      setLoading(true)
      const res = await settingsApi.get()
      setConfig(prev => ({ ...prev, ...res }))
    } catch {
      // Settings may not be available
    } finally {
      setLoading(false)
    }
  }

  const loadSnapshots = async () => {
    try {
      const res = await backupApi.listSnapshots()
      setSnapshots(res.snapshots || res || [])
    } catch {
      // Backup may not be available
    }
  }

  const checkOllama = async () => {
    try {
      const res = await fetch('/health')
      const data = await res.json()
      setOllamaStatus(data.ollama || (res.ok ? 'connected' : 'disconnected'))
    } catch {
      setOllamaStatus('disconnected')
    }
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      await settingsApi.update(config)
      addToast('Settings saved', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleSnapshot = async () => {
    setSnapshotLoading(true)
    try {
      await backupApi.triggerSnapshot()
      addToast('Snapshot created', 'success')
      loadSnapshots()
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setSnapshotLoading(false)
    }
  }

  const updateConfig = (key, value) => {
    setConfig(prev => ({ ...prev, [key]: value }))
  }

  if (loading) {
    return (
      <div className="settings-page page">
        <div className="settings-loading">
          <div className="spinner" />
          <span>Loading settings...</span>
        </div>
      </div>
    )
  }

  return (
    <div className="settings-page page">
      <div className="section-header">
        <h1 className="section-title">Settings</h1>
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? <Loader size={16} className="spinning" /> : <Save size={16} />}
          Save Changes
        </button>
      </div>

      <div className="settings-grid">
        <section className="settings-section card">
          <h2 className="settings-section-title">Model Configuration</h2>
          <ModelSelector />
        </section>

        <section className="settings-section card">
          <h2 className="settings-section-title">Document Processing</h2>

          <div className="settings-row">
            <div className="settings-row-info">
              <span className="settings-label">Auto-sort on upload</span>
              <span className="settings-desc">
                Automatically classify and sort documents when uploaded.
              </span>
            </div>
            <label className="toggle">
              <input
                type="checkbox"
                checked={config.auto_sort}
                onChange={(e) => updateConfig('auto_sort', e.target.checked)}
              />
              <span className="toggle-slider" />
            </label>
          </div>

          <div className="settings-row">
            <div className="settings-row-info">
              <span className="settings-label">Auto-rename</span>
              <span className="settings-desc">
                Suggest descriptive filenames based on document content.
              </span>
            </div>
            <label className="toggle">
              <input
                type="checkbox"
                checked={config.auto_rename}
                onChange={(e) => updateConfig('auto_rename', e.target.checked)}
              />
              <span className="toggle-slider" />
            </label>
          </div>

          <div className="settings-row vertical">
            <div className="settings-row-info">
              <span className="settings-label">
                Confidence threshold: {Math.round(config.confidence_threshold * 100)}%
              </span>
              <span className="settings-desc">
                Minimum confidence for automatic sort/rename actions.
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={config.confidence_threshold}
              onChange={(e) => updateConfig('confidence_threshold', parseFloat(e.target.value))}
            />
          </div>

          <div className="settings-row vertical">
            <div className="settings-row-info">
              <span className="settings-label">OCR Language</span>
              <span className="settings-desc">
                Tesseract language code for OCR (e.g. eng, deu, fra).
              </span>
            </div>
            <input
              type="text"
              value={config.ocr_language}
              onChange={(e) => updateConfig('ocr_language', e.target.value)}
              placeholder="eng"
              style={{ maxWidth: '200px' }}
            />
          </div>
        </section>

        <section className="settings-section card">
          <h2 className="settings-section-title">Backup</h2>

          <div className="settings-row">
            <div className="settings-row-info">
              <span className="settings-label">Create Snapshot</span>
              <span className="settings-desc">
                Backup current state of all documents and settings.
              </span>
            </div>
            <button
              className="btn btn-secondary"
              onClick={handleSnapshot}
              disabled={snapshotLoading}
            >
              {snapshotLoading ? (
                <Loader size={14} className="spinning" />
              ) : (
                <HardDrive size={14} />
              )}
              Snapshot
            </button>
          </div>

          {snapshots.length > 0 && (
            <div className="snapshots-list">
              <h3 className="snapshots-title">Recent Snapshots</h3>
              {snapshots.slice(0, 5).map((snap, i) => (
                <div key={i} className="snapshot-item">
                  <Database size={14} />
                  <span className="snapshot-name">{snap.name || snap.id || `Snapshot ${i + 1}`}</span>
                  {snap.created_at && (
                    <span className="snapshot-date">
                      <Clock size={12} />
                      {new Date(snap.created_at).toLocaleString()}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="settings-section card">
          <h2 className="settings-section-title">Connection Status</h2>

          <div className="settings-row">
            <div className="settings-row-info">
              <span className="settings-label">Ollama</span>
              <span className="settings-desc">
                Local LLM inference server.
              </span>
            </div>
            <div className="status-indicator">
              {ollamaStatus === 'connected' || ollamaStatus === true ? (
                <>
                  <CheckCircle size={16} className="status-connected" />
                  <span className="status-text connected">Connected</span>
                </>
              ) : (
                <>
                  <AlertCircle size={16} className="status-disconnected" />
                  <span className="status-text disconnected">Disconnected</span>
                </>
              )}
              <button className="btn-icon" onClick={checkOllama} title="Refresh">
                <RefreshCw size={14} />
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
