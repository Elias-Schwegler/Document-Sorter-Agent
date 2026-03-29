import { useState, useCallback, useEffect, useContext } from 'react'
import { documents as docsApi } from '../api'
import { ToastContext } from '../App'

export default function useDocuments() {
  const [docs, setDocs] = useState([])
  const [loading, setLoading] = useState(true)
  const [folder, setFolder] = useState(null)
  const [search, setSearch] = useState('')
  const { addToast } = useContext(ToastContext)

  const loadDocuments = useCallback(async () => {
    try {
      setLoading(true)
      const result = await docsApi.list(folder, search || null)
      setDocs(result.documents || result || [])
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }, [folder, search, addToast])

  useEffect(() => {
    loadDocuments()
  }, [loadDocuments])

  const uploadFiles = useCallback(async (files) => {
    try {
      const result = await docsApi.upload(files, folder)
      addToast(`Uploaded ${files.length} file(s)`, 'success')
      await loadDocuments()
      return result
    } catch (err) {
      addToast(err.message, 'error')
      throw err
    }
  }, [folder, loadDocuments, addToast])

  const deleteDocument = useCallback(async (id) => {
    try {
      await docsApi.delete(id)
      addToast('Document deleted', 'success')
      await loadDocuments()
    } catch (err) {
      addToast(err.message, 'error')
    }
  }, [loadDocuments, addToast])

  const sortDocument = useCallback(async (id) => {
    try {
      const result = await docsApi.sort(id)
      addToast('Document sorted', 'success')
      await loadDocuments()
      return result
    } catch (err) {
      addToast(err.message, 'error')
    }
  }, [loadDocuments, addToast])

  const renameDocument = useCallback(async (id, newName) => {
    try {
      await docsApi.rename(id, newName)
      addToast('Document renamed', 'success')
      await loadDocuments()
    } catch (err) {
      addToast(err.message, 'error')
    }
  }, [loadDocuments, addToast])

  const bulkSort = useCallback(async () => {
    try {
      const result = await docsApi.bulkSort()
      addToast('Bulk sort started', 'success')
      await loadDocuments()
      return result
    } catch (err) {
      addToast(err.message, 'error')
    }
  }, [loadDocuments, addToast])

  return {
    docs,
    loading,
    folder,
    search,
    setFolder,
    setSearch,
    uploadFiles,
    deleteDocument,
    sortDocument,
    renameDocument,
    bulkSort,
    refresh: loadDocuments,
  }
}
