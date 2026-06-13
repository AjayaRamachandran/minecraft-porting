import { useState, useMemo, useRef, useEffect } from 'react'
import {
  Plus, Trash2, Crosshair, Download, Copy, Upload, X, MessageSquare, ChevronRight, Package,
} from 'lucide-react'
import {
  API_BASE, ColorPicker, resolveColor, ItemSlot, textureUrl, buildGivePayload, fetchItems,
} from './mc'

let _uid = 0
const uid = () => `n${++_uid}`

// A give-item attached to a choice carries the builder give-payload
// (base_item, count, components) plus display-only fields (_stem for the
// texture thumbnail, _label for the chip/tooltip). The underscore fields are
// stripped on export.
function choiceItemFromManifest(item) {
  const payload = buildGivePayload(item)
  return { ...payload, _stem: item.model_stem, _label: item.custom_name?.text || item.name || item.model_stem }
}

function choiceItemFromJson(it) {
  const comps = it.components || {}
  const stem = String(comps['minecraft:item_model'] || '').replace(/^minecraft:custom\//, '')
  const label = comps['minecraft:custom_name']?.text || stem || it.base_item || 'item'
  return { base_item: it.base_item, count: it.count || 1, components: comps, _stem: stem, _label: label }
}

const choiceItemToJson = ({ _stem, _label, ...payload }) => payload // drop display fields

// Migrate any builder JSON (1.0 / 1.1 / 1.2) to the editor's in-memory model.
// Mirrors npc-maker/builder.py: normalize().
function migrate(data) {
  const version = String(data.builder_version ?? '1.0')
  const convs = Array.isArray(data.conversations) ? data.conversations : []
  let npcName = ''
  let nameColor = 'gold'
  if (version === '1.1' || version === '1.2') {
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
        items: (ch.items || []).map(choiceItemFromJson),
      })),
    })),
  }
}

// Editor model → exportable 1.2 JSON (drops internal ids and display fields).
function toJson(state) {
  return {
    builder_version: '1.2',
    npc_variable_initial: state.npc_variable_initial,
    npc_name: state.npc_name,
    name_color: state.name_color,
    conversations: state.conversations.map((c) => ({
      scoreboard_tag: c.scoreboard_tag,
      message: c.message,
      choices: c.choices.map((ch) => {
        const out = { text: ch.text, direct: ch.direct }
        if (ch.items?.length) out.items = ch.items.map(choiceItemToJson)
        return out
      }),
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
  // Saved custom items shown in the inventory strip, draggable onto choices.
  const [library, setLibrary] = useState([])
  const [dragOverChoice, setDragOverChoice] = useState(null)

  useEffect(() => {
    fetchItems().then(setLibrary).catch(() => setLibrary([]))
  }, [])

  const onDropOnChoice = (e, messageId, choiceId) => {
    e.preventDefault()
    setDragOverChoice(null)
    const raw = e.dataTransfer.getData('application/x-mc-item')
    if (!raw) return
    try {
      dropItemOnChoice(messageId, choiceId, JSON.parse(raw))
    } catch { /* ignore malformed drops */ }
  }

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
    updateMessageChoices(messageId, (choices) => [...choices, { id: uid(), text: '', direct: '', items: [] }])

  const dropItemOnChoice = (messageId, choiceId, manifest) =>
    updateMessageChoices(messageId, (choices) =>
      choices.map((ch) =>
        ch.id === choiceId ? { ...ch, items: [...(ch.items || []), choiceItemFromManifest(manifest)] } : ch))

  const removeChoiceItem = (messageId, choiceId, idx) =>
    updateMessageChoices(messageId, (choices) =>
      choices.map((ch) =>
        ch.id === choiceId ? { ...ch, items: ch.items.filter((_, i) => i !== idx) } : ch))

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
    <>
    <div className="max-w-3xl mx-auto px-6 py-8 pb-28 space-y-5">
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
                  const dragOver = dragOverChoice === ch.id
                  return (
                    <div
                      key={ch.id}
                      onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setDragOverChoice(ch.id) }}
                      onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setDragOverChoice((c) => (c === ch.id ? null : c)) }}
                      onDrop={(e) => onDropOnChoice(e, message.id, ch.id)}
                      className={`rounded-lg transition-all ${
                        dragOver ? 'ring-2 ring-amber-400 dark:ring-amber-500 bg-amber-50/60 dark:bg-amber-950/30 p-1.5 -m-1.5' : ''
                      }`}
                    >
                      <div className="flex items-center gap-2">
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
                            placeholder={ch.items?.length ? 'none' : 'message'}
                            title={invalid ? 'No message has this number (will be wired in-game)' : 'Target message (optional when the choice gives an item)'}
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

                      {/* Items this choice gives (dragged from the library strip) */}
                      {ch.items?.length > 0 && (
                        <div className="flex flex-wrap items-center gap-1.5 mt-1.5 pl-5">
                          <span className="text-[10px] uppercase tracking-wide text-zinc-400">gives</span>
                          {ch.items.map((it, i) => (
                            <div key={i} className="relative">
                              <ItemSlot
                                texture={it._stem ? textureUrl(it._stem) : null}
                                name={it.components['minecraft:custom_name'] || { text: it._label }}
                                lore={it.components['minecraft:lore'] || []}
                                size={32}
                                title={it._label}
                              />
                              {it.count > 1 && (
                                <span className="absolute bottom-0 right-0 text-[10px] font-bold px-0.5 bg-black/70 text-white leading-none">{it.count}</span>
                              )}
                              <button
                                onClick={(e) => { e.stopPropagation(); removeChoiceItem(message.id, ch.id, i) }}
                                className="absolute -top-1 -right-1 p-0.5 rounded bg-red-600 text-white hover:bg-red-500"
                                title="Remove item"
                              >
                                <X size={9} />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
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

    {/* Item Library inventory strip — drag an item onto any choice to give it. */}
    <div className="fixed bottom-0 left-52 right-0 z-30 border-t border-zinc-200 dark:border-zinc-800 bg-white/95 dark:bg-zinc-950/95 backdrop-blur px-4 py-2">
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400 shrink-0">
          <Package size={14} /> Item Library
        </span>
        <div className="flex items-center gap-1.5 overflow-x-auto py-1">
          {library.length === 0 ? (
            <span className="text-xs text-zinc-400">No saved items — create some in the Item Library tab.</span>
          ) : (
            library.map((item) => (
              <ItemSlot
                key={item.id}
                texture={textureUrl(item.model_stem)}
                name={item.custom_name}
                lore={item.lore}
                size={40}
                draggable
                title={`Drag “${item.name}” onto a choice`}
                onDragStart={(e) => {
                  e.dataTransfer.setData('application/x-mc-item', JSON.stringify(item))
                  e.dataTransfer.effectAllowed = 'copy'
                }}
              />
            ))
          )}
        </div>
      </div>
    </div>
    </>
  )
}
