import { useEffect, useState, useCallback } from 'react'
import { Search, ArrowUpDown, Loader2, FileText, FolderPlus, Check, X } from 'lucide-react'
import useDocuments from '../hooks/useDocuments'
import useWebSocket from '../hooks/useWebSocket'
import { documents as docsApi } from '../api'
import FileUpload from '../components/FileUpload'
import DocumentCard from '../components/DocumentCard'
import FolderTree from '../components/FolderTree'
import './DocumentsPage.css'

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
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

  const handleApproveFolder = async (docId, folder) => {
    try {
      await docsApi.approveFolder(docId, folder)
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

      {pendingFiles.length > 0 && (
        <div className="pending-section">
          <h3 className="pending-title">
            <Loader2 size={16} className="pending-spinner" />
            Pending ({pendingFiles.length} file{pendingFiles.length !== 1 ? 's' : ''} awaiting processing)
          </h3>
          <div className="pending-list">
            {pendingFiles.map((file) => {
              const isActive = currentlyProcessing === file.filename
              return (
                <div key={file.filename} className={`pending-item ${isActive ? 'active' : ''}`}>
                  <FileText size={16} className="pending-icon" />
                  <span className="pending-filename">{file.filename}</span>
                  <span className="pending-size">{formatFileSize(file.size)}</span>
                  {isActive ? (
                    <span className="pending-badge active">
                      <Loader2 size={12} className="pending-spinner-inline" /> Processing...
                    </span>
                  ) : (
                    <span className="pending-badge">Queued</span>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      )}

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
                  {item.text_preview && (
                    <span className="folder-approval-preview">{item.text_preview.slice(0, 100)}...</span>
                  )}
                </div>
                <div className="folder-approval-actions">
                  <button
                    className="btn btn-sm btn-primary"
                    onClick={() => handleApproveFolder(item.doc_id, item.proposed_folder)}
                    title="Approve this folder"
                  >
                    <Check size={14} /> Approve
                  </button>
                  <button
                    className="btn btn-sm btn-ghost"
                    onClick={() => handleRejectFolder(item.doc_id)}
                    title="Keep in _review"
                  >
                    <X size={14} /> Keep in Review
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

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
            <div className="documents-loading">
              <div className="spinner" />
              <span>Loading documents...</span>
            </div>
          ) : docs.length === 0 ? (
            <div className="documents-empty">
              <p>No documents found.</p>
              <p>Upload files above or adjust your filters.</p>
            </div>
          ) : (
            <div className="documents-grid">
              {docs.map((doc) => (
                <DocumentCard
                  key={doc.id}
                  doc={doc}
                  onSort={sortDocument}
                  onRename={renameDocument}
                  onDelete={deleteDocument}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
