import { useState, useEffect } from 'react'
import ChatPanel from '../components/ChatPanel'
import useChat from '../hooks/useChat'
import { models as modelsApi } from '../api'
import { Pin, FileText, X } from 'lucide-react'
import './ChatPage.css'

export default function ChatPage() {
  const { messages, isStreaming, sendMessage, clearHistory } = useChat()
  const [activeModel, setActiveModel] = useState(null)
  const [pinnedDocs, setPinnedDocs] = useState([])
  const [showPinned, setShowPinned] = useState(false)

  useEffect(() => {
    modelsApi.getActive()
      .then((res) => setActiveModel(res.model || res.name || res))
      .catch(() => {})
  }, [])

  return (
    <div className="chat-page">
      <div className="chat-page-main">
        <ChatPanel
          messages={messages}
          isStreaming={isStreaming}
          onSend={sendMessage}
          onClear={clearHistory}
          activeModel={activeModel}
        />
      </div>

      {pinnedDocs.length > 0 && (
        <aside className={`chat-page-pinned ${showPinned ? 'open' : ''}`}>
          <div className="pinned-header">
            <Pin size={16} />
            <h3>Pinned Documents</h3>
            <button className="btn-icon" onClick={() => setShowPinned(false)}>
              <X size={16} />
            </button>
          </div>
          <div className="pinned-list">
            {pinnedDocs.map((doc, i) => (
              <div key={i} className="pinned-item">
                <FileText size={14} />
                <span>{doc.filename || doc.name}</span>
              </div>
            ))}
          </div>
        </aside>
      )}

      {pinnedDocs.length > 0 && !showPinned && (
        <button
          className="pinned-toggle"
          onClick={() => setShowPinned(true)}
        >
          <Pin size={16} />
          <span>{pinnedDocs.length}</span>
        </button>
      )}
    </div>
  )
}
