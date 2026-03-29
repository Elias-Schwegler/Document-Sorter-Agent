import { useState, useRef, useCallback } from 'react'
import { Upload, FileUp, CheckCircle, AlertCircle } from 'lucide-react'
import './FileUpload.css'

export default function FileUpload({ onUpload, wsStatus }) {
  const [isDragging, setIsDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadResult, setUploadResult] = useState(null)
  const fileInputRef = useRef(null)

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }, [])

  const handleDrop = useCallback(async (e) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)

    const files = Array.from(e.dataTransfer.files)
    if (files.length > 0) {
      await processUpload(files)
    }
  }, [onUpload])

  const handleFileSelect = useCallback(async (e) => {
    const files = Array.from(e.target.files)
    if (files.length > 0) {
      await processUpload(files)
    }
    e.target.value = ''
  }, [onUpload])

  const processUpload = async (files) => {
    setUploading(true)
    setUploadResult(null)
    try {
      await onUpload(files)
      setUploadResult({ type: 'success', count: files.length })
      setTimeout(() => setUploadResult(null), 3000)
    } catch {
      setUploadResult({ type: 'error' })
      setTimeout(() => setUploadResult(null), 3000)
    } finally {
      setUploading(false)
    }
  }

  return (
    <div
      className={`file-upload ${isDragging ? 'dragging' : ''} ${uploading ? 'uploading' : ''}`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => fileInputRef.current?.click()}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="file-upload-input"
        onChange={handleFileSelect}
      />

      <div className="file-upload-content">
        {uploading ? (
          <>
            <div className="spinner" />
            <p className="file-upload-text">Uploading...</p>
            {wsStatus === 'connected' && (
              <p className="file-upload-hint">Processing with ingestion pipeline</p>
            )}
          </>
        ) : uploadResult ? (
          <>
            {uploadResult.type === 'success' ? (
              <CheckCircle size={32} className="file-upload-success" />
            ) : (
              <AlertCircle size={32} className="file-upload-error" />
            )}
            <p className="file-upload-text">
              {uploadResult.type === 'success'
                ? `${uploadResult.count} file(s) uploaded`
                : 'Upload failed'}
            </p>
          </>
        ) : (
          <>
            {isDragging ? (
              <FileUp size={32} className="file-upload-icon active" />
            ) : (
              <Upload size={32} className="file-upload-icon" />
            )}
            <p className="file-upload-text">
              {isDragging ? 'Drop files here' : 'Drag & drop files or click to browse'}
            </p>
            <p className="file-upload-hint">
              PDF, DOCX, TXT, MD, images, and more
            </p>
          </>
        )}
      </div>
    </div>
  )
}
