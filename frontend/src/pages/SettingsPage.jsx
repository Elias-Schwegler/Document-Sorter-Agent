import { useState, useEffect, useContext } from 'react'
import {
  Save, RefreshCw, Database, Loader, CheckCircle,
  AlertCircle, Clock, HardDrive, Bot, Monitor, Globe,
} from 'lucide-react'
import ModelSelector from '../components/ModelSelector'
import { settings as settingsApi, backup as backupApi, bot as botApi, documents as documentsApi } from '../api'
import { ToastContext } from '../App'
import { useI18n, LANGUAGES } from '../i18n'
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
  const [reconcileLoading, setReconcileLoading] = useState(false)
  const [ollamaStatus, setOllamaStatus] = useState(null)
  const [botStatus, setBotStatus] = useState(null)
  const [botInstances, setBotInstances] = useState([])
  const { addToast } = useContext(ToastContext)
  const { lang, setLanguage, t } = useI18n()

  useEffect(() => {
    loadSettings()
    loadSnapshots()
    checkOllama()
    checkBot()
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

  const checkBot = async () => {
    try {
      const status = await botApi.status()
      setBotStatus(status)
      if (status.running) {
        const instRes = await botApi.instances()
        setBotInstances(instRes.instances || [])
      }
    } catch {
      setBotStatus(null)
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

  const handleReconcile = async () => {
    setReconcileLoading(true)
    try {
      const result = await documentsApi.reconcile()
      const parts = []
      if (result.ok) parts.push(`${result.ok} ok`)
      if (result.moved) parts.push(`${result.moved} moved`)
      if (result.deleted) parts.push(`${result.deleted} deleted`)
      if (result.updated) parts.push(`${result.updated} updated`)
      addToast(`Reconciliation complete: ${parts.join(', ')}`, 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setReconcileLoading(false)
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
        <h1 className="section-title">{t('settings.title')}</h1>
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
          <h2 className="settings-section-title">
            <Globe size={18} />
            {t('lang.language')}
          </h2>
          <div className="lang-setting-buttons">
            {LANGUAGES.map(l => (
              <button
                key={l.code}
                className={`lang-setting-btn ${l.code === lang ? 'active' : ''}`}
                onClick={() => setLanguage(l.code)}
              >
                <span className="lang-setting-flag">{l.flag}</span>
                <span>{l.label}</span>
              </button>
            ))}
          </div>
        </section>

        <section className="settings-section card">
          <h2 className="settings-section-title">{t('settings.models')}</h2>
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

          <div className="settings-row">
            <div className="settings-row-info">
              <span className="settings-label">Reconcile Filesystem</span>
              <span className="settings-desc">
                Scan for moved, renamed, or deleted files and update the database.
              </span>
            </div>
            <button
              className="btn btn-secondary"
              onClick={handleReconcile}
              disabled={reconcileLoading}
            >
              {reconcileLoading ? (
                <Loader size={14} className="spinning" />
              ) : (
                <RefreshCw size={14} />
              )}
              Reconcile
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

          <div className="settings-row">
            <div className="settings-row-info">
              <span className="settings-label">
                <Bot size={14} style={{ marginRight: 6, verticalAlign: 'middle' }} />
                Telegram Bot
              </span>
              <span className="settings-desc">
                {botStatus?.token_configured
                  ? `Instance: ${botStatus?.instance_name || 'Default'}`
                  : 'Not configured (set TELEGRAM_BOT_TOKEN in .env)'}
              </span>
            </div>
            <div className="status-indicator">
              {botStatus?.running ? (
                <>
                  <CheckCircle size={16} className="status-connected" />
                  <span className="status-text connected">Running</span>
                </>
              ) : botStatus?.token_configured ? (
                <>
                  <AlertCircle size={16} className="status-disconnected" />
                  <span className="status-text disconnected">Stopped</span>
                </>
              ) : (
                <>
                  <AlertCircle size={16} className="status-disconnected" />
                  <span className="status-text disconnected">Not configured</span>
                </>
              )}
              <button className="btn-icon" onClick={checkBot} title="Refresh">
                <RefreshCw size={14} />
              </button>
            </div>
          </div>

          {botInstances.length > 0 && (
            <div className="bot-instances-list">
              <h3 className="snapshots-title">Registered Instances</h3>
              {botInstances.map((inst, i) => (
                <div key={i} className="snapshot-item">
                  <Monitor size={14} />
                  <span className="snapshot-name">
                    {inst.instance_name}
                    {inst.is_current && ' (this)'}
                  </span>
                  {inst.last_seen && (
                    <span className="snapshot-date">
                      <Clock size={12} />
                      {new Date(inst.last_seen).toLocaleString()}
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
