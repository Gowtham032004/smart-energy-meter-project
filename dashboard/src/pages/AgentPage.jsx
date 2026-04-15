import { useState, useRef, useEffect } from 'react'
import axios from 'axios'
import { Bot, Send, Zap, RefreshCw } from 'lucide-react'

const API    = '/api'
const DEVICE = 'METER_001'

const SUGGESTIONS = [
  'How much energy did I use today?',
  'When will my balance run out?',
  'Why is my usage high?',
  'Give me energy saving tips',
  'Show my meter status',
  'Any anomalies detected?',
  'How much did I use this week?',
]

function TypingIndicator() {
  return (
    <div className="chat-bubble ai" style={{ display: 'flex', gap: 5, alignItems: 'center', width: 60 }}>
      {[0,1,2].map(i => (
        <div key={i} style={{
          width: 7, height: 7, borderRadius: '50%', background: 'var(--accent)',
          animation: `bounce 1.2s ${i * 0.2}s ease-in-out infinite`,
        }} />
      ))}
      <style>{`@keyframes bounce{0%,80%,100%{transform:translateY(0)}40%{transform:translateY(-6px)}}`}</style>
    </div>
  )
}

function parseMarkdown(text) {
  // Simple bold + newline renderer
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')
}

export default function AgentPage() {
  const [messages, setMessages] = useState([
    {
      from: 'ai',
      text: "👋 Hello! I'm your **Smart Energy AI Assistant**.\n\nAsk me anything about your energy usage, balance, anomalies, or get saving tips!\n\nTry: *\"How much energy did I use today?\"*",
    }
  ])
  const [input,   setInput]   = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)
  const inputRef  = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async (text) => {
    const q = (text ?? input).trim()
    if (!q) return

    setMessages(m => [...m, { from: 'user', text: q }])
    setInput('')
    setLoading(true)

    try {
      const { data } = await axios.post(`${API}/agent/chat`, {
        device_id: DEVICE,
        message:   q,
      })
      setMessages(m => [...m, { from: 'ai', text: data.reply, intent: data.intent }])
    } catch {
      setMessages(m => [...m, { from: 'ai', text: '⚠️ Connection error. Is the backend running?\n`uvicorn backend.main:app --reload`' }])
    } finally {
      setLoading(false)
      inputRef.current?.focus()
    }
  }

  const onKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">AI Energy Agent</h1>
          <p className="page-subtitle">Conversational assistant for your smart meter</p>
        </div>
        <button className="btn btn-ghost" onClick={() => setMessages([{
          from: 'ai',
          text: "👋 Chat cleared! Ask me anything about your energy system.",
        }])}>
          <RefreshCw size={13} /> Clear Chat
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 260px', gap: 20, alignItems: 'start' }}>
        {/* ── Chat window ── */}
        <div className="chat-container">
          {/* Chat header */}
          <div className="chat-header">
            <div style={{
              width: 40, height: 40, borderRadius: '50%',
              background: 'linear-gradient(135deg, var(--accent), var(--accent-2))',
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20,
            }}>
              🤖
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: 15 }}>EnergyBot</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: 5 }}>
                <span className="live-dot" style={{ width: 6, height: 6 }} />
                AI-powered · METER_001
              </div>
            </div>
          </div>

          {/* Messages */}
          <div className="chat-messages">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`chat-bubble ${m.from} animate-in`}
                style={{ animationDelay: `${i * 0.03}s` }}
                dangerouslySetInnerHTML={{
                  __html: m.from === 'ai' ? parseMarkdown(m.text) : m.text
                }}
              />
            ))}
            {loading && <TypingIndicator />}
            <div ref={bottomRef} />
          </div>

          {/* Input area */}
          <div className="chat-input-area">
            <textarea
              ref={inputRef}
              className="chat-input"
              rows={2}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="Ask about usage, balance, anomalies, saving tips…"
            />
            <button
              className="btn btn-primary"
              onClick={() => send()}
              disabled={loading || !input.trim()}
              style={{ alignSelf: 'flex-end', paddingLeft: 16, paddingRight: 16, opacity: loading || !input.trim() ? 0.5 : 1 }}
            >
              <Send size={15} />
            </button>
          </div>
        </div>

        {/* ── Suggestion pills ── */}
        <div className="card animate-in" style={{ position: 'sticky', top: 20 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text-secondary)', marginBottom: 14 }}>
            💬 Quick Questions
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {SUGGESTIONS.map((s, i) => (
              <button
                key={i}
                className="btn btn-ghost"
                style={{ textAlign: 'left', fontSize: 12, padding: '8px 12px', justifyContent: 'flex-start' }}
                onClick={() => send(s)}
                disabled={loading}
              >
                {s}
              </button>
            ))}
          </div>

          <div style={{ marginTop: 20, padding: '14px', background: 'var(--surface-2)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 }}>
              🧠 AI Capabilities
            </div>
            {['Energy usage queries','Balance & forecasting','Anomaly explanation','Saving recommendations','Live meter status','Weekly / daily analysis'].map((c,i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--text-secondary)', marginBottom: 5 }}>
                <Zap size={10} color="var(--accent)" /> {c}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
