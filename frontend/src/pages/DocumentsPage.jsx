import { useEffect, useState, useCallback } from 'react'
import { Search, ArrowUpDown, Loader2, FileText } from 'lucide-react'
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

  const loadPending = useCallback(async () => {
    try {
      const result = await docsApi.pending()
      setPendingFiles(result.files || [])
    } catch {
      // silently ignore - endpoint may not be available
    }
  }, [])

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
            {pendingFiles.map((file) => (
              <div key={file.filename} className="pending-item">
                <FileText size={16} className="pending-icon" />
                <span className="pending-filename">{file.filename}</span>
                <span className="pending-size">{formatFileSize(file.size)}</span>
                <span className="pending-badge">Processing...</span>
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
