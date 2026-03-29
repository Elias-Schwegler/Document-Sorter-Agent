import { useState, useCallback, useEffect } from 'react'
import { chat as chatApi } from '../api'

export default function useChat() {
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [sources, setSources] = useState([])
  const [error, setError] = useState(null)

  useEffect(() => {
    loadHistory()
  }, [])

  const loadHistory = useCallback(async () => {
    try {
      const history = await chatApi.getHistory()
      if (history?.messages) {
        setMessages(history.messages)
      }
    } catch {
      // History may not be available yet
    }
  }, [])

  const sendMessage = useCallback(async (content) => {
    if (!content.trim() || isStreaming) return

    const userMessage = { role: 'user', content }
    setMessages(prev => [...prev, userMessage])
    setIsStreaming(true)
    setError(null)
    setSources([])

    let assistantContent = ''
    setMessages(prev => [...prev, { role: 'assistant', content: '' }])

    await chatApi.sendMessage(
      content,
      (token) => {
        assistantContent += token
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            role: 'assistant',
            content: assistantContent,
          }
          return updated
        })
      },
      (newSources) => {
        setSources(newSources)
        setMessages(prev => {
          const updated = [...prev]
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            sources: newSources,
          }
          return updated
        })
      },
      () => {
        setIsStreaming(false)
      },
      (errMsg) => {
        setError(errMsg)
        setIsStreaming(false)
        setMessages(prev => {
          const updated = [...prev]
          if (updated[updated.length - 1]?.role === 'assistant' && !updated[updated.length - 1].content) {
            updated.pop()
          }
          return updated
        })
      }
    )
  }, [isStreaming])

  const clearHistory = useCallback(async () => {
    try {
      await chatApi.clearHistory()
      setMessages([])
      setSources([])
      setError(null)
    } catch (err) {
      setError(err.message)
    }
  }, [])

  return {
    messages,
    isStreaming,
    sources,
    error,
    sendMessage,
    clearHistory,
    loadHistory,
  }
}
