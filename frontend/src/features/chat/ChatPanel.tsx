import './chat.css'
import { ArrowLeft, MessageCirclePlus, MessagesSquare, Search, SendHorizontal, Users, X } from 'lucide-react'
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { api, ApiError } from '../../lib/api'
import { initials } from '../../lib/format'

export interface ConversationRow {
  id: string
  kind: 'team' | 'direct'
  title: string
  other_user: string | null
  unread: number
  last_message: { body: string; sender_name: string; created_at: string } | null
  updated_at: string
}

interface Message {
  id: string
  body: string
  sender: string
  sender_name: string
  mine: boolean
  created_at: string
  pending?: boolean
}

interface Person {
  id: string
  name: string
  role: string
}

const LIST_POLL_OPEN = 6_000
const LIST_POLL_CLOSED = 20_000
const THREAD_POLL = 3_500

/** Loads the thread list and unread total; polls faster while the panel is open. */
export function useConversations(open: boolean) {
  const [rows, setRows] = useState<ConversationRow[]>([])
  const [unread, setUnread] = useState(0)
  const load = useCallback(() => {
    api
      .get<{ unread: number; results: ConversationRow[] }>('/chat/conversations/')
      .then((data) => {
        setRows(data.results)
        setUnread(data.unread)
      })
      .catch(() => undefined)
  }, [])
  useEffect(() => {
    load()
    const timer = window.setInterval(
      () => {
        if (document.visibilityState === 'visible') load()
      },
      open ? LIST_POLL_OPEN : LIST_POLL_CLOSED,
    )
    return () => window.clearInterval(timer)
  }, [load, open])
  return { rows, unread, reload: load, setRows }
}

function timeLabel(iso: string) {
  const date = new Date(iso)
  const now = new Date()
  if (date.toDateString() === now.toDateString()) return new Intl.DateTimeFormat('en', { hour: 'numeric', minute: '2-digit' }).format(date)
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return new Intl.DateTimeFormat('en', { month: 'short', day: 'numeric' }).format(date)
}

function dayLabel(iso: string) {
  const date = new Date(iso)
  const now = new Date()
  if (date.toDateString() === now.toDateString()) return 'Today'
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return new Intl.DateTimeFormat('en', { weekday: 'long', month: 'long', day: 'numeric' }).format(date)
}

function ChatAvatar({ row, size = 'md' }: { row: Pick<ConversationRow, 'kind' | 'title'>; size?: 'md' | 'lg' }) {
  if (row.kind === 'team')
    return (
      <span className={`chat-avatar chat-avatar-team chat-avatar-${size}`} aria-hidden="true">
        <Users size={size === 'lg' ? 20 : 17} />
      </span>
    )
  return (
    <span className={`chat-avatar chat-avatar-${size}`} aria-hidden="true">
      {initials(row.title)}
    </span>
  )
}

/** Staff messaging: one team thread for everyone plus one-to-one chats. Opens as a side drawer. */
export function ChatPanel({ rows, reload, onClose }: { rows: ConversationRow[]; reload: () => void; onClose: () => void }) {
  const [chosenId, setActiveId] = useState<string | null>(null)
  const [picking, setPicking] = useState(false)
  // On small screens only one column shows at a time.
  const [showThread, setShowThread] = useState(false)
  // Until someone picks a thread, show the first one (the team chat).
  const activeId = chosenId ?? rows[0]?.id ?? null
  const active = rows.find((r) => r.id === activeId) ?? null

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function choose(id: string) {
    setActiveId(id)
    setPicking(false)
    setShowThread(true)
  }

  return (
    <div className="chat-layer" role="presentation" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <section className={`chat-drawer ${showThread ? 'is-thread' : ''}`} role="dialog" aria-modal="true" aria-label="Team messages">
        <header className="chat-head">
          <span className="chat-head-icon" aria-hidden="true">
            <MessagesSquare size={18} />
          </span>
          <div>
            <b>Messages</b>
            <small>Chat with your team</small>
          </div>
          <button type="button" className="chat-icon-button" onClick={onClose} aria-label="Close messages">
            <X size={18} />
          </button>
        </header>
        <div className="chat-body">
          <aside className="chat-list" aria-label="Conversations">
            {picking ? (
              <PeoplePicker
                onCancel={() => setPicking(false)}
                onPick={async (person) => {
                  const row = await api.post<ConversationRow>('/chat/conversations/', { user: person.id })
                  reload()
                  choose(row.id)
                }}
              />
            ) : (
              <>
                <button type="button" className="chat-new" onClick={() => setPicking(true)}>
                  <MessageCirclePlus size={17} aria-hidden="true" />
                  New message
                </button>
                <ul>
                  {rows.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        className={`chat-row ${row.id === activeId ? 'is-active' : ''} ${row.unread ? 'is-unread' : ''}`}
                        onClick={() => choose(row.id)}
                        aria-current={row.id === activeId ? 'true' : undefined}
                      >
                        <ChatAvatar row={row} />
                        <span className="chat-row-text">
                          <span className="chat-row-top">
                            <b>{row.title}</b>
                            {row.last_message && <time>{timeLabel(row.last_message.created_at)}</time>}
                          </span>
                          <span className="chat-row-bottom">
                            <small>
                              {row.last_message
                                ? `${row.kind === 'team' || row.last_message.sender_name === 'You' ? `${row.last_message.sender_name}: ` : ''}${row.last_message.body}`
                                : row.kind === 'team'
                                  ? 'Everyone on the team'
                                  : 'Say hello'}
                            </small>
                            {row.unread > 0 && <span className="chat-unread">{row.unread > 99 ? '99+' : row.unread}</span>}
                          </span>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </aside>
          {active ? (
            <Thread key={active.id} conversation={active} onBack={() => setShowThread(false)} onActivity={reload} />
          ) : (
            <div className="chat-thread chat-empty">
              <MessagesSquare size={36} aria-hidden="true" />
              <p>Pick a conversation to start chatting.</p>
            </div>
          )}
        </div>
      </section>
    </div>
  )
}

function PeoplePicker({ onPick, onCancel }: { onPick: (person: Person) => Promise<void>; onCancel: () => void }) {
  const [people, setPeople] = useState<Person[] | null>(null)
  const [query, setQuery] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    api
      .get<Person[]>('/chat/people/')
      .then(setPeople)
      .catch(() => setError('Could not load your team.'))
  }, [])
  const shown = useMemo(
    () => (people ?? []).filter((p) => `${p.name} ${p.role}`.toLowerCase().includes(query.trim().toLowerCase())),
    [people, query],
  )
  return (
    <div className="chat-picker">
      <div className="chat-picker-head">
        <button type="button" className="chat-icon-button" onClick={onCancel} aria-label="Back to conversations">
          <ArrowLeft size={18} />
        </button>
        <b>New message</b>
      </div>
      <label className="chat-search">
        <Search size={16} aria-hidden="true" />
        <input
          autoFocus
          placeholder="Search your team"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search your team"
        />
      </label>
      {error && <p className="chat-note">{error}</p>}
      {people && shown.length === 0 && <p className="chat-note">{people.length ? 'No one matches.' : 'No one else is on the team yet.'}</p>}
      <ul>
        {shown.map((person) => (
          <li key={person.id}>
            <button
              type="button"
              className="chat-row"
              onClick={() => void onPick(person).catch(() => setError('Could not start that chat. Try again.'))}
            >
              <ChatAvatar row={{ kind: 'direct', title: person.name }} />
              <span className="chat-row-text">
                <b>{person.name}</b>
                <small>{person.role}</small>
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function Thread({ conversation, onBack, onActivity }: { conversation: ConversationRow; onBack: () => void; onActivity: () => void }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [loaded, setLoaded] = useState(false)
  const [draft, setDraft] = useState('')
  const [error, setError] = useState('')
  const scroller = useRef<HTMLDivElement>(null)
  const stick = useRef(true)
  const latest = useRef<Message[]>([])
  const base = `/chat/conversations/${conversation.id}`

  useEffect(() => {
    latest.current = messages
  }, [messages])

  const markRead = useCallback(() => {
    void api
      .post(`${base}/read/`)
      .then(onActivity)
      .catch(() => undefined)
  }, [base, onActivity])

  useEffect(() => {
    let cancelled = false
    api
      .get<{ results: Message[] }>(`${base}/messages/`)
      .then((data) => {
        if (cancelled) return
        setMessages(data.results)
        setLoaded(true)
        markRead()
      })
      .catch(() => setError('Could not load messages.'))
    return () => {
      cancelled = true
    }
  }, [base, markRead])

  // Poll for newer messages while the thread is open.
  useEffect(() => {
    if (!loaded) return
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      const last = [...latest.current].reverse().find((m) => !m.pending)
      api
        .get<{ results: Message[] }>(`${base}/messages/`, last ? { after: last.created_at } : undefined)
        .then((data) => {
          if (!data.results.length) return
          setMessages((now) => {
            const known = new Set(now.map((m) => m.id))
            const fresh = data.results.filter((m) => !known.has(m.id))
            return fresh.length ? [...now, ...fresh] : now
          })
          if (data.results.some((m) => !m.mine)) markRead()
        })
        .catch(() => undefined)
    }, THREAD_POLL)
    return () => window.clearInterval(timer)
  }, [base, loaded, markRead])

  useLayoutEffect(() => {
    const el = scroller.current
    if (el && stick.current) el.scrollTop = el.scrollHeight
  }, [messages])

  async function send(event?: FormEvent) {
    event?.preventDefault()
    const body = draft.trim()
    if (!body) return
    const temp: Message = {
      id: `temp-${Date.now()}`,
      body,
      sender: 'me',
      sender_name: 'You',
      mine: true,
      created_at: new Date().toISOString(),
      pending: true,
    }
    stick.current = true
    setDraft('')
    setError('')
    setMessages((list) => [...list, temp])
    try {
      const saved = await api.post<Message>(`${base}/messages/`, { body })
      setMessages((list) => {
        const without = list.filter((m) => m.id !== temp.id)
        return without.some((m) => m.id === saved.id) ? without : [...without, saved]
      })
      onActivity()
    } catch (err) {
      setMessages((list) => list.filter((m) => m.id !== temp.id))
      setDraft(body)
      setError(err instanceof ApiError && err.status === 429 ? 'You are sending too fast. Wait a moment.' : 'Message not sent. Try again.')
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void send()
    }
  }

  return (
    <div className="chat-thread">
      <div className="chat-thread-head">
        <button type="button" className="chat-icon-button chat-back" onClick={onBack} aria-label="Back to conversations">
          <ArrowLeft size={18} />
        </button>
        <ChatAvatar row={conversation} size="lg" />
        <div>
          <b>{conversation.title}</b>
          <small>{conversation.kind === 'team' ? 'Everyone on the team can see this' : 'Only the two of you can see this'}</small>
        </div>
      </div>
      <div
        className="chat-messages"
        ref={scroller}
        onScroll={(e) => {
          const el = e.currentTarget
          stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 60
        }}
        aria-live="polite"
      >
        {loaded && messages.length === 0 && (
          <div className="chat-empty">
            <MessagesSquare size={32} aria-hidden="true" />
            <p>No messages yet. Say hello!</p>
          </div>
        )}
        {messages.map((message, index) => {
          const prev = messages[index - 1]
          const newDay = !prev || new Date(prev.created_at).toDateString() !== new Date(message.created_at).toDateString()
          const grouped =
            !newDay && prev && prev.sender === message.sender && Date.parse(message.created_at) - Date.parse(prev.created_at) < 5 * 60_000
          return (
            <div key={message.id} className="chat-message-wrap">
              {newDay && (
                <div className="chat-day">
                  <span>{dayLabel(message.created_at)}</span>
                </div>
              )}
              <div className={`chat-message ${message.mine ? 'is-mine' : ''} ${grouped ? 'is-grouped' : ''}`}>
                {!message.mine && !grouped && conversation.kind === 'team' && <span className="chat-sender">{message.sender_name}</span>}
                <div className={`chat-bubble ${message.pending ? 'is-pending' : ''}`}>
                  <p>{message.body}</p>
                  <time dateTime={message.created_at}>{message.pending ? 'Sending…' : timeLabel(message.created_at)}</time>
                </div>
              </div>
            </div>
          )
        })}
      </div>
      <form className="chat-compose" onSubmit={(e) => void send(e)}>
        {error && (
          <p className="chat-error" role="alert">
            {error}
          </p>
        )}
        <textarea
          rows={1}
          value={draft}
          maxLength={2000}
          placeholder={conversation.kind === 'team' ? 'Message the team…' : `Message ${conversation.title}…`}
          aria-label="Message"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="chat-send" disabled={!draft.trim()} aria-label="Send message">
          <SendHorizontal size={18} />
        </button>
      </form>
    </div>
  )
}
