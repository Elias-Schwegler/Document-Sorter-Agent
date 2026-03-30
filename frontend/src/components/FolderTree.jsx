import { useState, useEffect, useCallback, useContext } from 'react'
import { Folder, FolderOpen, ChevronRight, ChevronDown, Plus, FolderPlus } from 'lucide-react'
import { folders as foldersApi } from '../api'
import { ToastContext } from '../App'
import './FolderTree.css'

function FolderItem({ folder, activeFolder, onSelect, level = 0 }) {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = folder.children && folder.children.length > 0
  const isActive = activeFolder === folder.name || activeFolder === folder.id

  return (
    <div className="folder-item">
      <button
        className={`folder-item-btn ${isActive ? 'active' : ''}`}
        style={{ paddingLeft: `${12 + level * 20}px` }}
        onClick={() => onSelect(folder.name || folder.id)}
      >
        {hasChildren ? (
          <span
            className="folder-chevron"
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded) }}
          >
            {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          </span>
        ) : (
          <span className="folder-chevron-spacer" />
        )}
        {isActive ? <FolderOpen size={16} /> : <Folder size={16} />}
        <span className="folder-name">{folder.name}</span>
        {folder.doc_count != null && (
          <span className="folder-count">{folder.doc_count}</span>
        )}
      </button>
      {hasChildren && expanded && (
        <div className="folder-children">
          {folder.children.map((child) => (
            <FolderItem
              key={child.id || child.name}
              folder={child}
              activeFolder={activeFolder}
              onSelect={onSelect}
              level={level + 1}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function FolderTree({ activeFolder, onSelectFolder }) {
  const [folderList, setFolderList] = useState([])
  const [creating, setCreating] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const { addToast } = useContext(ToastContext)

  const loadFolders = useCallback(async () => {
    try {
      const result = await foldersApi.list()
      const raw = result.folders || result || []
      // API returns strings, normalize to objects
      setFolderList(raw.map(f => typeof f === 'string' ? { name: f } : f))
    } catch {
      // Folders endpoint may not be available
    }
  }, [])

  useEffect(() => {
    loadFolders()
  }, [loadFolders])

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return
    try {
      await foldersApi.create(newFolderName.trim())
      addToast('Folder created', 'success')
      setNewFolderName('')
      setCreating(false)
      loadFolders()
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  return (
    <div className="folder-tree">
      <div className="folder-tree-header">
        <h3>Folders</h3>
        <button
          className="btn-icon"
          title="New folder"
          onClick={() => setCreating(!creating)}
        >
          <FolderPlus size={16} />
        </button>
      </div>

      {creating && (
        <div className="folder-create">
          <input
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreateFolder()
              if (e.key === 'Escape') setCreating(false)
            }}
            placeholder="Folder name"
            autoFocus
          />
          <button className="btn btn-sm btn-primary" onClick={handleCreateFolder}>
            <Plus size={14} />
          </button>
        </div>
      )}

      <div className="folder-list">
        <button
          className={`folder-item-btn ${!activeFolder ? 'active' : ''}`}
          onClick={() => onSelectFolder(null)}
        >
          <span className="folder-chevron-spacer" />
          <Folder size={16} />
          <span className="folder-name">All Documents</span>
        </button>

        {folderList.map((folder) => (
          <FolderItem
            key={folder.id || folder.name}
            folder={folder}
            activeFolder={activeFolder}
            onSelect={onSelectFolder}
          />
        ))}
      </div>
    </div>
  )
}
