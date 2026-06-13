import { useState, useMemo, useRef, useEffect } from 'react'
import {
  Plus, Trash2, Crosshair, Download, Copy, Upload, X, MessageSquare, ChevronRight,
  ChevronDown, Check, Hash,
} from 'lucide-react'

const API_BASE = ''

// Standard Minecraft named text colors → hex. Order matches the in-game list.
const MC_COLOR_LIST = [
  ['black', '#000000'], ['dark_blue', '#0000AA'], ['dark_green', '#00AA00'],
  ['dark_aqua', '#00AAAA'], ['dark_red', '#AA0000'], ['dark_purple', '#AA00AA'],
  ['gold', '#FFAA00'], ['gray', '#AAAAAA'], ['dark_gray', '#555555'],
  ['blue', '#5555FF'], ['green', '#55FF55'], ['aqua', '#55FFFF'],
  ['red', '#FF5555'], ['light_purple', '#FF55FF'], ['yellow', '#FFFF55'],
  ['white', '#FFFFFF'],
]
const MC_COLORS = Object.fromEntries(MC_COLOR_LIST)

// Resolve a color string to a hex for preview. Returns null if invalid.
function resolveColor(c) {
  if (!c) return null
  if (/^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/.test(c)) return c
  return MC_COLORS[c] || null
}

// Name-color dropdown: lists the 16 Minecraft colors (each name shown in its
// own color, on a dark tooltip-like panel) plus a "Hex code" option that opens
// an MCStacker-style popover for a custom hex.
function ColorPicker({ value, onChange }) {
  const [open, setOpen] = useState(false)
  const [hexMode, setHexMode] = useState(false)
  const [hexDraft, setHexDraft] = useState(value.startsWith('#') ? value : '#FFAA00')
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) {
        setOpen(false)
        setHexMode(false)
      }
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const isHex = value.startsWith('#')
  const swatch = resolveColor(value)
  const applyHex = () => {
    if (/^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/.test(hexDraft)) {
      onChange(hexDraft)
      setOpen(false)
      setHexMode(false)
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`w-full flex items-center gap-2 px-3 py-1.5 text-sm border bg-zinc-50 dark:bg-zinc-900 rounded-lg transition-colors ${
          swatch ? 'border-zinc-200 dark:border-zinc-700' : 'border-red-400 dark:border-red-700'
        }`}
      >
        <span
          className="w-4 h-4 border border-black/20 shrink-0"
          style={{ backgroundColor: swatch || 'transparent' }}
        />
        <span className="truncate" style={swatch && isHex ? { color: swatch } : undefined}>
          {value || 'pick a color'}
        </span>
        <ChevronDown size={14} className="ml-auto text-zinc-400 shrink-0" />
      </button>

      {open && (
        <div className="absolute z-40 mt-1 w-full max-h-72 overflow-auto bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl p-1">
          {MC_COLOR_LIST.map(([name, hex]) => (
            <button
              key={name}
              type="button"
              onClick={() => { onChange(name); setOpen(false); setHexMode(false) }}
              className="w-full flex items-center gap-2 px-2 py-1 text-sm rounded-md hover:bg-zinc-800 transition-colors"
            >
              <span className="w-4 h-4 border border-white/20 shrink-0" style={{ backgroundColor: hex }} />
              <span style={{ color: hex }}>{name}</span>
              {value === name && <Check size={13} className="ml-auto text-zinc-400" />}
            </button>
          ))}

          <div className="my-1 border-t border-zinc-700" />
          <button
            type="button"
            onClick={() => setHexMode((h) => !h)}
            className="w-full flex items-center gap-2 px-2 py-1 text-sm rounded-md text-zinc-200 hover:bg-zinc-800 transition-colors"
          >
            <Hash size={14} className="text-zinc-400" />
            Hex code…
            {isHex && <Check size={13} className="ml-auto text-zinc-400" />}
          </button>

          {hexMode && (
            <div className="mt-1 p-2 bg-zinc-800 rounded-md space-y-2">
              <div className="flex items-center gap-2">
                <input
                  type="color"
                  value={/^#[0-9a-fA-F]{6}$/.test(hexDraft) ? hexDraft : '#FFAA00'}
                  onChange={(e) => setHexDraft(e.target.value.toUpperCase())}
                  className="w-8 h-8 bg-transparent cursor-pointer shrink-0"
                />
                <input
                  value={hexDraft}
                  onChange={(e) => setHexDraft(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && applyHex()}
                  placeholder="#FFAA00"
                  className="flex-1 min-w-0 px-2 py-1 text-sm font-mono bg-zinc-900 border border-zinc-700 rounded-md text-zinc-100 focus:outline-none focus:ring-2 focus:ring-zinc-600"
                />
              </div>
              <button
                type="button"
                onClick={applyHex}
                className="w-full px-3 py-1 text-sm bg-zinc-100 text-zinc-900 rounded-md hover:bg-white transition-colors"
              >
                Apply
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

let _uid = 0
const uid = () => `n${++_uid}`

// Migrate any builder JSON (1.0 legacy or 1.1) to the editor's in-memory model.
// Mirrors npc-maker/builder.py: normalize().
function migrate(data) {
  const version = String(data.builder_version ?? '1.0')
  const convs = Array.isArray(data.conversations) ? data.conversations : []
  let npcName = ''
  let nameColor = 'gold'
  if (version === '1.1') {
    npcName = data.npc_name || ''
    nameColor = data.name_color || 'gold'
  } else {
    npcName = (convs.find((c) => c.npc_name)?.npc_name) || ''
  }
  return {
    npc_variable_initial: data.npc_variable_initial || 'npc',
    npc_name: npcName,
    name_color: nameColor,
    conversations: convs.map((c) => ({
      id: uid(),
      scoreboard_tag: String(c.scoreboard_tag ?? ''),
      message: c.message || '',
      choices: (c.choices || []).map((ch) => ({
        id: uid(),
        text: ch.text || '',
        direct: String(ch.direct ?? ''),
      })),
    })),
  }
}

// Editor model → exportable 1.1 JSON (drops internal ids).
function toJson(state) {
  return {
    builder_version: '1.1',
    npc_variable_initial: state.npc_variable_initial,
    npc_name: state.npc_name,
    name_color: state.name_color,
    conversations: state.conversations.map((c) => ({
      scoreboard_tag: c.scoreboard_tag,
      message: c.message,
      choices: c.choices.map((ch) => ({ text: ch.text, direct: ch.direct })),
    })),
  }
}

const blankState = () => ({
  npc_variable_initial: 'npc',
  npc_name: '',
  name_color: 'gold',
  conversations: [
    { id: uid(), scoreboard_tag: '1', message: '', choices: [] },
  ],
})

export default function NpcMaker() {
  const [state, setState] = useState(blankState)
  // linking = { messageId, choiceId } when the user is picking a link target.
  const [linking, setLinking] = useState(null)
  const [showImport, setShowImport] = useState(false)
  const [importText, setImportText] = useState('')
  const [importError, setImportError] = useState('')
  const [status, setStatus] = useState('idle') // idle | loading | error
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const fileRef = useRef(null)

  const tagSet = useMemo(
    () => new Set(state.conversations.map((c) => c.scoreboard_tag).filter(Boolean)),
    [state.conversations],
  )
  const swatch = resolveColor(state.name_color)

  // --- state mutation helpers -------------------------------------------
  const setField = (k, v) => setState((s) => ({ ...s, [k]: v }))

  const updateMessage = (messageId, patch) =>
    setState((s) => ({
      ...s,
      conversations: s.conversations.map((c) => (c.id === messageId ? { ...c, ...patch } : c)),
    }))

  const addMessage = () =>
    setState((s) => {
      // Default the new message's number to the next free integer.
      const nums = s.conversations.map((c) => parseInt(c.scoreboard_tag, 10)).filter((n) => !isNaN(n))
      const next = (nums.length ? Math.max(...nums) : 0) + 1
      return {
        ...s,
        conversations: [
          ...s.conversations,
          { id: uid(), scoreboard_tag: String(next), message: '', choices: [] },
        ],
      }
    })

  const deleteMessage = (messageId) =>
    setState((s) => ({
      ...s,
      conversations: s.conversations.filter((c) => c.id !== messageId),
    }))

  const addChoice = (messageId) =>
    updateMessageChoices(messageId, (choices) => [...choices, { id: uid(), text: '', direct: '' }])

  const deleteChoice = (messageId, choiceId) =>
    updateMessageChoices(messageId, (choices) => choices.filter((ch) => ch.id !== choiceId))

  const updateChoice = (messageId, choiceId, patch) =>
    updateMessageChoices(messageId, (choices) =>
      choices.map((ch) => (ch.id === choiceId ? { ...ch, ...patch } : ch)))

  function updateMessageChoices(messageId, fn) {
    setState((s) => ({
      ...s,
      conversations: s.conversations.map((c) =>
        c.id === messageId ? { ...c, choices: fn(c.choices) } : c),
    }))
  }

  // --- link picker -------------------------------------------------------
  const startLinking = (messageId, choiceId) => {
    setLinking((cur) =>
      cur && cur.messageId === messageId && cur.choiceId === choiceId ? null : { messageId, choiceId })
  }

  const onMessageClick = (targetMessage) => {
    if (!linking) return
    updateChoice(linking.messageId, linking.choiceId, { direct: targetMessage.scoreboard_tag })
    setLinking(null)
  }

  // --- import / export ---------------------------------------------------
  const doImport = () => {
    setImportError('')
    let parsed
    try {
      parsed = JSON.parse(importText)
    } catch (e) {
      setImportError('Invalid JSON: ' + e.message)
      return
    }
    try {
      setState(migrate(parsed))
      setShowImport(false)
      setImportText('')
    } catch (e) {
      setImportError('Could not read NPC data: ' + e.message)
    }
  }

  const onFilePicked = (e) => {
    const f = e.target.files[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => {
      setImportText(String(reader.result))
      setShowImport(true)
    }
    reader.readAsText(f)
  }

  const jsonString = () => JSON.stringify(toJson(state), null, 2)

  const copyJson = async () => {
    await navigator.clipboard.writeText(jsonString())
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const downloadJson = () => {
    const blob = new Blob([jsonString()], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${state.npc_variable_initial || 'npc'}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  const generateSchem = async () => {
    setStatus('loading')
    setError('')
    try {
      const res = await fetch(`${API_BASE}/api/npc/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(toJson(state)),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Generation failed')
      const bytes = atob(data.schem_base64)
      const arr = new Uint8Array(bytes.length)
      for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
      const blob = new Blob([arr], { type: 'application/octet-stream' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = data.filename
      a.click()
      URL.revokeObjectURL(url)
      setStatus('idle')
    } catch (err) {
      setError(err.message)
      setStatus('error')
    }
  }

  const canGenerate =
    state.npc_variable_initial.trim() &&
    state.conversations.length > 0 &&
    state.conversations.every((c) => c.scoreboard_tag.trim())

  // ----------------------------------------------------------------------
  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-5xl leading-none">NPC Maker</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-2">
            Build a break-safe dialogue NPC and export a 1.21.11 schematic
          </p>
        </div>
        <button
          onClick={() => { setShowImport((v) => !v); setImportError('') }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors shrink-0"
        >
          <Upload size={14} /> Import JSON
        </button>
      </div>

      {/* Import modal */}
      {showImport && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
          onClick={() => setShowImport(false)}
        >
          <div
            className="w-full max-w-xl bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl shadow-2xl p-5 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold">Import NPC JSON</p>
              <button
                onClick={() => setShowImport(false)}
                className="p-1 rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <p className="text-xs text-zinc-500 dark:text-zinc-400">Paste builder 1.0 or 1.1 JSON</p>
              <button
                onClick={() => fileRef.current?.click()}
                className="text-xs text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200"
              >
                or load a file
              </button>
              <input ref={fileRef} type="file" accept=".json" className="hidden" onChange={onFilePicked} />
            </div>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              rows={10}
              spellCheck={false}
              autoFocus
              placeholder='{ "npc_variable_initial": "onk", "conversations": [ … ] }'
              className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600 resize-y"
            />
            {importError && <p className="text-xs text-red-600 dark:text-red-400 font-mono">{importError}</p>}
            <div className="flex items-center justify-end gap-2">
              <button
                onClick={() => setShowImport(false)}
                className="px-4 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={doImport}
                disabled={!importText.trim()}
                className="px-4 py-1.5 border border-transparent bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 transition-colors"
              >
                Load into editor
              </button>
            </div>
          </div>
        </div>
      )}

      {/* General info */}
      <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
        <label className="space-y-1">
          <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Scoreboard prefix</span>
          <input
            value={state.npc_variable_initial}
            onChange={(e) => setField('npc_variable_initial', e.target.value.replace(/\s+/g, ''))}
            placeholder="onk"
            className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">NPC name</span>
          <input
            value={state.npc_name}
            onChange={(e) => setField('npc_name', e.target.value)}
            placeholder="Onk the Explorer"
            className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
          />
        </label>
        <label className="space-y-1">
          <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Name color</span>
          <ColorPicker value={state.name_color} onChange={(c) => setField('name_color', c)} />
        </label>
      </div>

      {/* Linking hint */}
      {linking && (
        <div className="flex items-center gap-2 text-sm text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-950 border border-indigo-200 dark:border-indigo-900 rounded-lg px-3 py-2">
          <Crosshair size={15} />
          Click a message below to link this choice to it.
          <button onClick={() => setLinking(null)} className="ml-auto hover:opacity-70">
            <X size={15} />
          </button>
        </div>
      )}

      {/* Message list */}
      <div className="space-y-4">
        {state.conversations.map((message) => {
          const isLinkTarget = !!linking
          return (
            <div
              key={message.id}
              onClick={isLinkTarget ? () => onMessageClick(message) : undefined}
              className={`bg-white dark:bg-zinc-800 border rounded-xl p-4 space-y-3 transition-all ${
                isLinkTarget
                  ? 'cursor-pointer border-indigo-400 dark:border-indigo-600 ring-2 ring-indigo-300/50 dark:ring-indigo-700/40 hover:bg-indigo-50/50 dark:hover:bg-indigo-950/30'
                  : 'border-zinc-200 dark:border-zinc-700'
              }`}
            >
              {/* Message header */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-zinc-400 dark:text-zinc-500">Chat Message</span>
                <input
                  value={message.scoreboard_tag}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => updateMessage(message.id, { scoreboard_tag: e.target.value.replace(/\s+/g, '') })}
                  className="w-16 px-2 py-1 text-sm font-semibold rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
                />
                <div className="ml-auto flex items-center gap-2">
                  {swatch && state.npc_name && (
                    <span className="text-xs hidden sm:inline">
                      <span style={{ color: swatch }}>[{state.npc_name}]</span>
                    </span>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); deleteMessage(message.id) }}
                    className="p-1.5 rounded-md text-zinc-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
                    title="Delete message"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>

              {/* Message */}
              <div className="flex gap-2">
                <MessageSquare size={15} className="mt-2 text-zinc-400 shrink-0" />
                <textarea
                  value={message.message}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => updateMessage(message.id, { message: e.target.value })}
                  rows={2}
                  placeholder="What the NPC says on this message…"
                  className="w-full px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600 resize-y"
                />
              </div>

              {/* Choices */}
              <div className="space-y-2 pl-6">
                {message.choices.map((ch) => {
                  const linked = ch.direct && tagSet.has(ch.direct)
                  const invalid = ch.direct && !tagSet.has(ch.direct)
                  const isThisLinking =
                    linking && linking.messageId === message.id && linking.choiceId === ch.id
                  return (
                    <div key={ch.id} className="flex items-center gap-2">
                      <ChevronRight size={14} className="text-zinc-400 shrink-0" />
                      <input
                        value={ch.text}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => updateChoice(message.id, ch.id, { text: e.target.value })}
                        placeholder="Choice the player can click…"
                        className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
                      />
                      <div className="flex items-center gap-1 shrink-0">
                        <span className="text-xs text-zinc-400">→</span>
                        <input
                          value={ch.direct}
                          onClick={(e) => e.stopPropagation()}
                          onChange={(e) => updateChoice(message.id, ch.id, { direct: e.target.value.replace(/\s+/g, '') })}
                          placeholder="message"
                          title={invalid ? 'No message has this number (will be wired in-game)' : 'Target message'}
                          className={`w-16 px-2 py-1.5 text-sm rounded-lg border bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 ${
                            invalid
                              ? 'border-red-400 dark:border-red-600 text-red-600 dark:text-red-400 focus:ring-red-300'
                              : linked
                              ? 'border-emerald-400 dark:border-emerald-700 focus:ring-emerald-300'
                              : 'border-zinc-200 dark:border-zinc-700 focus:ring-zinc-300 dark:focus:ring-zinc-600'
                          }`}
                        />
                        <button
                          onClick={(e) => { e.stopPropagation(); startLinking(message.id, ch.id) }}
                          className={`p-1.5 rounded-md transition-colors ${
                            isThisLinking
                              ? 'bg-indigo-100 dark:bg-indigo-900 text-indigo-600 dark:text-indigo-300'
                              : 'text-zinc-400 hover:text-indigo-600 hover:bg-indigo-50 dark:hover:bg-indigo-950'
                          }`}
                          title="Pick response message"
                        >
                          <Crosshair size={15} />
                        </button>
                        <button
                          onClick={(e) => { e.stopPropagation(); deleteChoice(message.id, ch.id) }}
                          className="p-1.5 rounded-md text-zinc-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
                          title="Remove choice"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </div>
                  )
                })}
                <button
                  onClick={(e) => { e.stopPropagation(); addChoice(message.id) }}
                  className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 transition-colors pl-0.5"
                >
                  <Plus size={14} /> Add choice
                </button>
              </div>
            </div>
          )
        })}

        {/* Add message */}
        <button
          onClick={addMessage}
          className="w-full flex items-center justify-center gap-2 py-4 text-sm font-medium text-zinc-400 dark:text-zinc-500 border-2 border-dashed border-zinc-200 dark:border-zinc-700 rounded-xl hover:border-zinc-300 dark:hover:border-zinc-600 hover:text-zinc-600 dark:hover:text-zinc-300 transition-colors"
        >
          <Plus size={16} /> Add message
        </button>
      </div>

      {/* Actions */}
      <div className="flex flex-wrap items-center gap-3 pt-1">
        <button
          onClick={generateSchem}
          disabled={!canGenerate || status === 'loading'}
          className="flex items-center gap-2 px-5 py-2 border border-transparent bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {status === 'loading' ? (
            <>
              <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 dark:border-zinc-900/30 border-t-white dark:border-t-zinc-900 rounded-full animate-spin" />
              Generating…
            </>
          ) : (
            <><Download size={15} /> Generate .schem</>
          )}
        </button>
        <button
          onClick={copyJson}
          className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <Copy size={14} /> {copied ? 'Copied!' : 'Copy JSON'}
        </button>
        <button
          onClick={downloadJson}
          className="flex items-center gap-1.5 px-4 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
        >
          <Download size={14} /> Download JSON
        </button>
      </div>

      {status === 'error' && (
        <div className="border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 text-sm rounded-xl px-4 py-3 font-mono">
          {error}
        </div>
      )}
      {!canGenerate && (
        <p className="text-xs text-zinc-400 dark:text-zinc-500">
          Set a scoreboard prefix and give every message a number to generate the schematic.
        </p>
      )}
    </div>
  )
}
