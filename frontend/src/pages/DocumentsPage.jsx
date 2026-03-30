import { useEffect, useState, useCallback } from 'react'
import { Search, ArrowUpDown, Loader2, FileText, Image, FolderPlus, Check, X, Download, Trash2, Pencil, ArrowRight, Eye } from 'lucide-react'
import useDocuments from '../hooks/useDocuments'
import useWebSocket from '../hooks/useWebSocket'
import { documents as docsApi } from '../api'
import FileUpload from '../components/FileUpload'
import FolderTree from '../components/FolderTree'
import './DocumentsPage.css'

function formatFileSize(bytes) {
  if (!bytes) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}

const IMAGE_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'tiff', 'tif']
function isImage(filename) {
  return IMAGE_EXTS.includes((filename || '').split('.').pop().toLowerCase())
}

export default function DocumentsPage({ onDocCountChange }) {
  const {
    docs, loading, folder, search,
    setFolder, setSearch,
    uploadFiles, deleteDocument, sortDocument, renameDocument, bulkSort,
  } = useDocuments()
  const { status: wsStatus } = useWebSocket()
  const [pendingFiles, setPendingFiles] = useState([])
  const [currentlyProcessing, setCurrentlyProcessing] = useState('')
  const [pendingFolders, setPendingFolders] = useState([])
  const [selectedDoc, setSelectedDoc] = useState(null)

  const loadPending = useCallback(async () => {
    try {
      const result = await docsApi.pending()
      setPendingFiles(result.files || [])
      setCurrentlyProcessing(result.currently_processing || '')
    } catch {}
    try {
      const folders = await docsApi.pendingFolders()
      setPendingFolders(folders.documents || [])
    } catch {}
  }, [])

  const handleApproveFolder = async (docId, folderName) => {
    try {
      await docsApi.approveFolder(docId, folderName)
      setPendingFolders(prev => prev.filter(d => d.doc_id !== docId))
    } catch {}
  }

  const handleRejectFolder = async (docId) => {
    try {
      await docsApi.rejectFolder(docId)
      setPendingFolders(prev => prev.filter(d => d.doc_id !== docId))
    } catch {}
  }

  useEffect(() => {
    loadPending()
    const interval = setInterval(loadPending, 5000)
    return () => clearInterval(interval)
  }, [loadPending])

  useEffect(() => {
    onDocCountChange?.(docs.length)
  }, [docs.length, onDocCountChange])

  const docId = selectedDoc?.doc_id || selectedDoc?.id

  return (
    <div className="documents-page page">
      <div className="section-header">
        <h1 className="section-title">Documents</h1>
        <button className="btn btn-secondary" onClick={bulkSort}>
          <ArrowUpDown size={16} />
          Bulk Sort
        </button>
      </div>

      <FileUpload onUpload={uploadFiles} wsStatus={wsStatus} />

      {/* Pending files */}
      {pendingFiles.length > 0 && (
        <details className="pending-section" open={pendingFiles.length <= 10}>
          <summary className="pending-title">
            <Loader2 size={16} className="pending-spinner" />
            Pending ({pendingFiles.length} file{pendingFiles.length !== 1 ? 's' : ''} awaiting processing)
          </summary>
          <div className="pending-list">
            {pendingFiles.slice(0, 20).map((file) => {
              const isActive = currentlyProcessing === file.filename
              return (
                <div key={file.filename} className={`pending-item ${isActive ? 'active' : ''}`}>
                  <FileText size={14} className="pending-icon" />
                  <span className="pending-filename">{file.filename}</span>
                  <span className="pending-size">{formatFileSize(file.size)}</span>
                  {isActive ? (
                    <span className="pending-badge active">
                      <Loader2 size={10} className="pending-spinner-inline" /> Processing
                    </span>
                  ) : (
                    <span className="pending-badge">Queued</span>
                  )}
                </div>
              )
            })}
            {pendingFiles.length > 20 && (
              <div className="pending-more">...and {pendingFiles.length - 20} more</div>
            )}
          </div>
        </details>
      )}

      {/* Folder approval proposals */}
      {pendingFolders.length > 0 && (
        <div className="folder-approvals card">
          <h3 className="folder-approvals-title">
            <FolderPlus size={16} />
            New Folder Proposals ({pendingFolders.length})
          </h3>
          <div className="folder-approvals-list">
            {pendingFolders.map((item) => (
              <div key={item.doc_id} className="folder-approval-item">
                <div className="folder-approval-info">
                  <span className="folder-approval-filename">{item.filename}</span>
                  <span className="folder-approval-proposed">
                    AI suggests: <strong>{item.proposed_folder}</strong>
                  </span>
                </div>
                <div className="folder-approval-actions">
                  <button className="btn btn-sm btn-primary" onClick={() => handleApproveFolder(item.doc_id, item.proposed_folder)}>
                    <Check size={14} /> Approve
                  </button>
                  <button className="btn btn-sm btn-ghost" onClick={() => handleRejectFolder(item.doc_id)}>
                    <X size={14} /> Reject
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Main layout: sidebar + documents + preview */}
      <div className="documents-layout">
        <aside className="documents-sidebar">
          <FolderTree activeFolder={folder} onSelectFolder={setFolder} />
        </aside>

        <div className="documents-main">
          <div className="documents-search">
            <Search size={18} className="documents-search-icon" />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search documents..."
              className="documents-search-input"
            />
          </div>

          {loading ? (
            <div className="documents-loading"><div className="spinner" /><span>Loading...</span></div>
          ) : docs.length === 0 ? (
            <div className="documents-empty">
              <p>No documents found.</p>
              <p>Upload files above or adjust your filters.</p>
            </div>
          ) : (
            <div className="documents-list">
              {docs.map((doc) => {
                const id = doc.doc_id || doc.id
                const isSelected = docId === id
                return (
                  <div
                    key={id}
                    className={`doc-row ${isSelected ? 'selected' : ''}`}
                    onClick={() => setSelectedDoc(doc)}
                  >
                    <div className="doc-row-icon">
                      {isImage(doc.filename) ? <Image size={18} /> : <FileText size={18} />}
                    </div>
                    <div className="doc-row-info">
                      <span className="doc-row-name">{doc.filename}</span>
                      <span className="doc-row-meta">
                        {doc.folder && <span className="badge badge-sm">{doc.folder}</span>}
                        <span>{formatFileSize(doc.file_size)}</span>
                      </span>
                    </div>
                    <div className="doc-row-actions" onClick={e => e.stopPropagation()}>
                      <button className="btn-icon" title="Download" onClick={() => window.open(`/api/documents/${id}/download`, '_blank')}>
                        <Download size={14} />
                      </button>
                      <button className="btn-icon" title="Delete" onClick={() => { deleteDocument(id); if (isSelected) setSelectedDoc(null) }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* Preview panel */}
        {selectedDoc && (
          <div className="documents-preview card">
            <div className="doc-preview-header">
              <h3>Preview</h3>
              <button className="btn-icon" onClick={() => setSelectedDoc(null)}>
                <X size={16} />
              </button>
            </div>
            <div className="doc-preview-name">{selectedDoc.filename}</div>
            <div className="doc-preview-meta">
              {selectedDoc.folder && <span className="badge">{selectedDoc.folder}</span>}
              <span>{formatFileSize(selectedDoc.file_size)}</span>
              <span>{selectedDoc.file_type}</span>
            </div>
            <div className="doc-preview-image">
              <img
                src={`/api/documents/${docId}/preview`}
                alt={selectedDoc.filename}
                onError={(e) => {
                  e.target.style.display = 'none'
                  if (e.target.nextSibling) e.target.nextSibling.style.display = 'flex'
                }}
              />
              <div className="doc-preview-fallback" style={{ display: 'none' }}>
                <Eye size={32} />
                <p>Preview not available</p>
              </div>
            </div>
            <div className="doc-preview-actions">
              <button className="btn btn-sm btn-primary" onClick={() => window.open(`/api/documents/${docId}/download`, '_blank')}>
                <Download size={14} /> Download
              </button>
              <button className="btn btn-sm btn-secondary" onClick={() => sortDocument(docId)}>
                <ArrowRight size={14} /> Re-sort
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
