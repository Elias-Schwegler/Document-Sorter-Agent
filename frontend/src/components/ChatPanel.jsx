import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import { Send, Trash2, FileText, Bot, User, Loader } from 'lucide-react'
import './ChatPanel.css'

export default function ChatPanel({ messages, isStreaming, onSend, onClear, activeModel }) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || isStreaming) return
    onSend(input.trim())
    setInput('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <div className="chat-panel">
      <div className="chat-header">
        <div className="chat-header-left">
          <Bot size={20} />
          <h2>Chat</h2>
          {activeModel && (
            <span className="chat-model-badge badge badge-accent">
              {activeModel}
            </span>
          )}
        </div>
        <button
          className="btn btn-ghost btn-sm"
          onClick={onClear}
          title="Clear history"
        >
          <Trash2 size={16} />
          Clear
        </button>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <Bot size={48} />
            <h3>Ask anything about your documents</h3>
            <p>Your uploaded documents are used as context for answers.</p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`chat-message ${msg.role}`}>
            <div className="chat-message-avatar">
              {msg.role === 'user' ? <User size={18} /> : <Bot size={18} />}
            </div>
            <div className="chat-message-content">
              {msg.role === 'assistant' ? (
                <ReactMarkdown>{msg.content}</ReactMarkdown>
              ) : (
                <p>{msg.content}</p>
              )}
              {msg.sources && msg.sources.length > 0 && (
                <div className="chat-sources">
                  <span className="chat-sources-label">Sources:</span>
                  <div className="chat-sources-list">
                    {msg.sources.map((source, j) => (
                      <div key={j} className="chat-source-card">
                        <FileText size={14} />
                        <span className="chat-source-name">
                          {source.filename || source.name || `Source ${j + 1}`}
                        </span>
                        {source.score && (
                          <span className="chat-source-score">
                            {Math.round(source.score * 100)}%
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {isStreaming && (
          <div className="chat-streaming-indicator">
            <Loader size={14} className="spinning" />
            <span>Generating...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      <form className="chat-input-area" onSubmit={handleSubmit}>
        <div className="chat-input-wrapper">
          <textarea
            ref={inputRef}
            className="chat-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a question about your documents..."
            rows={1}
            disabled={isStreaming}
          />
          <button
            type="submit"
            className="chat-send-btn"
            disabled={!input.trim() || isStreaming}
          >
            <Send size={18} />
          </button>
        </div>
      </form>
    </div>
  )
}
