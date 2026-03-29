import { useState, useEffect, useCallback, useContext } from 'react'
import { Download, Check, Cpu, Loader } from 'lucide-react'
import { models as modelsApi } from '../api'
import { ToastContext } from '../App'
import './ModelSelector.css'

export default function ModelSelector() {
  const [modelList, setModelList] = useState([])
  const [activeModel, setActiveModel] = useState(null)
  const [pullName, setPullName] = useState('')
  const [pulling, setPulling] = useState(false)
  const [pullProgress, setPullProgress] = useState(null)
  const [loading, setLoading] = useState(true)
  const { addToast } = useContext(ToastContext)

  const loadModels = useCallback(async () => {
    try {
      setLoading(true)
      const [list, active] = await Promise.all([
        modelsApi.list(),
        modelsApi.getActive(),
      ])
      setModelList(list.models || list || [])
      setActiveModel(active.model || active.name || active)
    } catch {
      // API may not be available
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadModels()
  }, [loadModels])

  const handleSetActive = async (name) => {
    try {
      await modelsApi.setActive(name)
      setActiveModel(name)
      addToast(`Switched to ${name}`, 'success')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handlePull = async () => {
    if (!pullName.trim() || pulling) return
    setPulling(true)
    setPullProgress({ status: 'Starting...', percent: 0 })

    try {
      await modelsApi.pull(pullName.trim(), (data) => {
        if (data.total && data.completed) {
          const percent = Math.round((data.completed / data.total) * 100)
          setPullProgress({ status: data.status || 'Downloading', percent })
        } else {
          setPullProgress({ status: data.status || 'Pulling...', percent: pullProgress?.percent || 0 })
        }
      })
      addToast(`Model ${pullName} pulled successfully`, 'success')
      setPullName('')
      loadModels()
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setPulling(false)
      setPullProgress(null)
    }
  }

  function formatSize(bytes) {
    if (!bytes) return ''
    const gb = bytes / (1024 * 1024 * 1024)
    if (gb >= 1) return `${gb.toFixed(1)} GB`
    return `${(bytes / (1024 * 1024)).toFixed(0)} MB`
  }

  return (
    <div className="model-selector">
      <div className="model-selector-header">
        <Cpu size={18} />
        <h3>Models</h3>
      </div>

      {loading ? (
        <div className="model-selector-loading">
          <div className="spinner" />
          <span>Loading models...</span>
        </div>
      ) : (
        <div className="model-list">
          {modelList.map((model) => {
            const name = model.name || model.model || model
            const isActive = name === activeModel
            return (
              <button
                key={name}
                className={`model-item ${isActive ? 'active' : ''}`}
                onClick={() => handleSetActive(name)}
              >
                <div className="model-item-info">
                  <span className="model-item-name">{name}</span>
                  {model.size && (
                    <span className="model-item-size">{formatSize(model.size)}</span>
                  )}
                </div>
                {isActive && <Check size={16} className="model-item-check" />}
              </button>
            )
          })}
          {modelList.length === 0 && (
            <p className="model-empty">No models found. Pull one below.</p>
          )}
        </div>
      )}

      <div className="model-pull">
        <div className="model-pull-input">
          <input
            type="text"
            value={pullName}
            onChange={(e) => setPullName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handlePull()}
            placeholder="Model name (e.g. llama3.2)"
            disabled={pulling}
          />
          <button
            className="btn btn-primary btn-sm"
            onClick={handlePull}
            disabled={!pullName.trim() || pulling}
          >
            {pulling ? <Loader size={14} className="spinning" /> : <Download size={14} />}
            Pull
          </button>
        </div>

        {pullProgress && (
          <div className="model-pull-progress">
            <div className="progress-bar">
              <div
                className="progress-bar-fill"
                style={{ width: `${pullProgress.percent}%` }}
              />
            </div>
            <span className="model-pull-status">
              {pullProgress.status} - {pullProgress.percent}%
            </span>
          </div>
        )}
      </div>
    </div>
  )
}
