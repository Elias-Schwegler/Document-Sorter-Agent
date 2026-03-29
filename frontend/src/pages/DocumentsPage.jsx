import { useEffect } from 'react'
import { Search, ArrowUpDown } from 'lucide-react'
import useDocuments from '../hooks/useDocuments'
import useWebSocket from '../hooks/useWebSocket'
import FileUpload from '../components/FileUpload'
import DocumentCard from '../components/DocumentCard'
import FolderTree from '../components/FolderTree'
import './DocumentsPage.css'

export default function DocumentsPage({ onDocCountChange }) {
  const {
    docs, loading, folder, search,
    setFolder, setSearch,
    uploadFiles, deleteDocument, sortDocument, renameDocument, bulkSort,
  } = useDocuments()
  const { status: wsStatus } = useWebSocket()

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
