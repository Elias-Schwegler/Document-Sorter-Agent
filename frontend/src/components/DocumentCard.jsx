import { useState } from 'react'
import {
  FileText, FileImage, FileCode, File,
  FolderOpen, Pencil, ArrowDownToLine, Trash2,
  ArrowUpDown, Check, X, Lightbulb,
} from 'lucide-react'
import './DocumentCard.css'

const fileIcons = {
  pdf: FileText,
  doc: FileText,
  docx: FileText,
  txt: FileText,
  md: FileCode,
  png: FileImage,
  jpg: FileImage,
  jpeg: FileImage,
  gif: FileImage,
  webp: FileImage,
}

function getFileIcon(filename) {
  const ext = filename?.split('.').pop()?.toLowerCase()
  return fileIcons[ext] || File
}

function formatSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function DocumentCard({ doc, onSort, onRename, onDelete }) {
  const [isRenaming, setIsRenaming] = useState(false)
  const [newName, setNewName] = useState(doc.filename || doc.name || '')
  const [showSuggestion, setShowSuggestion] = useState(false)

  const FileIcon = getFileIcon(doc.filename || doc.name)

  const handleRenameSubmit = () => {
    if (newName.trim() && newName !== (doc.filename || doc.name)) {
      onRename(doc.id, newName.trim())
    }
    setIsRenaming(false)
  }

  const handleSort = async () => {
    const result = await onSort(doc.id)
    if (result?.suggested_name) {
      setNewName(result.suggested_name)
      setShowSuggestion(true)
    }
  }

  const approveSuggestion = () => {
    onRename(doc.id, newName)
    setShowSuggestion(false)
  }

  return (
    <div className="doc-card">
      <div className="doc-card-icon">
        <FileIcon size={24} />
      </div>

      <div className="doc-card-info">
        {isRenaming ? (
          <div className="doc-card-rename">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleRenameSubmit()
                if (e.key === 'Escape') setIsRenaming(false)
              }}
              autoFocus
            />
            <button className="btn-icon" onClick={handleRenameSubmit}><Check size={14} /></button>
            <button className="btn-icon" onClick={() => setIsRenaming(false)}><X size={14} /></button>
          </div>
        ) : (
          <span className="doc-card-name" title={doc.filename || doc.name}>
            {doc.filename || doc.name}
          </span>
        )}

        <div className="doc-card-meta">
          {doc.folder && (
            <span className="badge">
              <FolderOpen size={10} />
              {doc.folder}
            </span>
          )}
          {doc.size != null && (
            <span className="doc-card-size">{formatSize(doc.size)}</span>
          )}
          {(doc.created_at || doc.date) && (
            <span className="doc-card-date">{formatDate(doc.created_at || doc.date)}</span>
          )}
        </div>
      </div>

      {showSuggestion && (
        <div className="doc-card-suggestion">
          <Lightbulb size={14} />
          <span className="doc-card-suggestion-name">{newName}</span>
          <button className="btn btn-sm btn-primary" onClick={approveSuggestion}>
            <Check size={12} /> Approve
          </button>
          <button className="btn btn-sm btn-ghost" onClick={() => setShowSuggestion(false)}>
            <X size={12} />
          </button>
        </div>
      )}

      <div className="doc-card-actions">
        <button className="btn-icon" title="Sort / Classify" onClick={handleSort}>
          <ArrowUpDown size={16} />
        </button>
        <button className="btn-icon" title="Rename" onClick={() => {
          setNewName(doc.filename || doc.name)
          setIsRenaming(true)
        }}>
          <Pencil size={16} />
        </button>
        <a
          className="btn-icon"
          title="Download"
          href={`/api/documents/${doc.id}/download`}
          download
          onClick={(e) => e.stopPropagation()}
        >
          <ArrowDownToLine size={16} />
        </a>
        <button className="btn-icon doc-card-delete" title="Delete" onClick={() => onDelete(doc.id)}>
          <Trash2 size={16} />
        </button>
      </div>
    </div>
  )
}
