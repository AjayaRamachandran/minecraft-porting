// Shared Minecraft helpers: color constants, the color picker, text-format
// toggles, the item slot + in-game-style tooltip, give-payload building, and
// the Item Library API client. Used by both ItemLibrary and NpcMaker.
import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Check, Hash, Bold, Italic, Underline, Strikethrough, Sparkles } from 'lucide-react'

export const API_BASE = ''

// Standard Minecraft named text colors → hex. Order matches the in-game list.
export const MC_COLOR_LIST = [
  ['black', '#000000'], ['dark_blue', '#0000AA'], ['dark_green', '#00AA00'],
  ['dark_aqua', '#00AAAA'], ['dark_red', '#AA0000'], ['dark_purple', '#AA00AA'],
  ['gold', '#FFAA00'], ['gray', '#AAAAAA'], ['dark_gray', '#555555'],
  ['blue', '#5555FF'], ['green', '#55FF55'], ['aqua', '#55FFFF'],
  ['red', '#FF5555'], ['light_purple', '#FF55FF'], ['yellow', '#FFFF55'],
  ['white', '#FFFFFF'],
]
export const MC_COLORS = Object.fromEntries(MC_COLOR_LIST)

// Resolve a color string to a hex for preview. Returns null if invalid.
export function resolveColor(c) {
  if (!c) return null
  if (/^#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$/.test(c)) return c
  return MC_COLORS[c] || null
}

// The five vanilla text-format flags, keyed by their Minecraft component name.
export const FORMAT_FLAGS = [
  ['bold', Bold], ['italic', Italic], ['underlined', Underline],
  ['strikethrough', Strikethrough], ['obfuscated', Sparkles],
]

// ---------------------------------------------------------------------------
// Color picker — lists the 16 Minecraft colors plus an MCStacker-style hex
// popover. (Lifted out of NpcMaker so the Item Library can reuse it.)
// ---------------------------------------------------------------------------
export function ColorPicker({ value, onChange }) {
  const [open, setOpen] = useState(false)
  const [hexMode, setHexMode] = useState(false)
  const [hexDraft, setHexDraft] = useState(value?.startsWith('#') ? value : '#FFAA00')
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

  const isHex = !!value?.startsWith('#')
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

// ---------------------------------------------------------------------------
// Text-format controls: B / I / U / S / obfuscated toggles. `fmt` carries the
// boolean flags (and is mutated immutably via onChange).
// ---------------------------------------------------------------------------
export function FormatToggles({ fmt, onChange }) {
  return (
    <div className="flex items-center gap-0.5">
      {FORMAT_FLAGS.map(([flag, Icon]) => (
        <button
          key={flag}
          type="button"
          title={flag}
          onClick={() => onChange({ ...fmt, [flag]: !fmt[flag] })}
          className={`p-1.5 rounded-md transition-colors ${
            fmt[flag]
              ? 'bg-zinc-800 text-white dark:bg-zinc-200 dark:text-zinc-900'
              : 'text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700'
          }`}
        >
          <Icon size={14} />
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Preview rendering of a formatted-text object.
// ---------------------------------------------------------------------------
function formatStyle(ft) {
  const deco = [ft.underlined && 'underline', ft.strikethrough && 'line-through']
    .filter(Boolean).join(' ')
  return {
    color: resolveColor(ft.color) || undefined,
    fontWeight: ft.bold ? 700 : undefined,
    fontStyle: ft.italic ? 'italic' : undefined,
    textDecoration: deco || undefined,
  }
}

const OBF_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
function scramble(text) {
  return text.replace(/\S/g, () => OBF_CHARS[Math.floor(Math.random() * OBF_CHARS.length)])
}

// Renders one formatted-text line, animating obfuscated text like the game.
export function FormattedText({ ft, fallback = '' }) {
  const text = ft?.text ?? ''
  const [shown, setShown] = useState(text)
  useEffect(() => {
    if (!ft?.obfuscated) { setShown(text); return }
    setShown(scramble(text))
    const id = setInterval(() => setShown(scramble(text)), 70)
    return () => clearInterval(id)
  }, [text, ft?.obfuscated])
  if (!text) return <span className="opacity-40">{fallback}</span>
  return <span style={formatStyle(ft)}>{ft?.obfuscated ? shown : text}</span>
}

// In-game-style hover tooltip: dark box with the (formatted) name on top and
// formatted lore lines below.
export function ItemTooltip({ name, lore }) {
  return (
    <div
      className="pointer-events-none whitespace-nowrap px-2 py-1.5 text-sm leading-tight border-2"
      style={{ background: '#100010F0', borderColor: '#280050', fontFamily: 'inherit' }}
    >
      <div style={{ color: '#FFFFFF' }}><FormattedText ft={name} fallback="Unnamed item" /></div>
      {(lore || []).map((line, i) => (
        <div key={i} style={{ color: resolveColor('gray') }}>
          <FormattedText ft={line} fallback=" " />
        </div>
      ))}
    </div>
  )
}

// A mock inventory slot showing a texture, with a hovercard tooltip. Optional
// drag support and overlay actions (e.g. a remove button).
export function ItemSlot({
  texture, name, lore, size = 48, draggable = false, onDragStart, title, children,
}) {
  const [hover, setHover] = useState(false)
  return (
    <div
      className="relative shrink-0"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div
        draggable={draggable}
        onDragStart={onDragStart}
        title={title}
        className="flex items-center justify-center border-2 border-zinc-400 dark:border-zinc-600 bg-zinc-300/70 dark:bg-zinc-700/70"
        style={{ width: size, height: size, cursor: draggable ? 'grab' : 'default' }}
      >
        {texture ? (
          <img
            src={texture}
            alt={name?.text || ''}
            draggable={false}
            style={{ width: size - 10, height: size - 10, imageRendering: 'pixelated' }}
            onError={(e) => { e.currentTarget.style.visibility = 'hidden' }}
          />
        ) : null}
      </div>
      {children}
      {hover && (name?.text || (lore && lore.length)) && (
        <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-1 z-50">
          <ItemTooltip name={name} lore={lore} />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Data helpers
// ---------------------------------------------------------------------------

// A blank formatted-text object.
export const blankFmt = (text = '') => ({
  text, color: '', bold: false, italic: false,
  underlined: false, strikethrough: false, obfuscated: false,
})

// Formatted-text object → Minecraft text-component JSON (only set keys).
export function textComponent(ft) {
  const c = { text: ft.text || '' }
  if (ft.color) c.color = ft.color
  for (const [flag] of FORMAT_FLAGS) if (ft[flag]) c[flag] = true
  return c
}

// Texture URL for a custom model stem.
export const textureUrl = (stem) => `${API_BASE}/api/textures/custom/${stem}.png`

// Saved item manifest → the give-payload the NPC builder expects:
// { base_item, count, components:{ item_model, custom_name?, lore?, custom_data? } }.
export function buildGivePayload(item) {
  const components = {
    'minecraft:item_model': `minecraft:custom/${item.model_stem}`,
  }
  if (item.custom_name?.text) components['minecraft:custom_name'] = textComponent(item.custom_name)
  const lore = (item.lore || []).filter((l) => l.text)
  if (lore.length) components['minecraft:lore'] = lore.map(textComponent)
  if (item.custom_data && Object.keys(item.custom_data).length) {
    components['minecraft:custom_data'] = item.custom_data
  }
  return { base_item: item.base_item, count: item.count || 1, components }
}

// ---------------------------------------------------------------------------
// Item Library API client
// ---------------------------------------------------------------------------
async function jsonOrThrow(res) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}

export const fetchModels = () =>
  fetch(`${API_BASE}/api/items/models`).then(jsonOrThrow).then((d) => d.models)

export const fetchItems = () =>
  fetch(`${API_BASE}/api/items`).then(jsonOrThrow).then((d) => d.items)

export const createItem = (item) =>
  fetch(`${API_BASE}/api/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item),
  }).then(jsonOrThrow).then((d) => d.item)

export const updateItem = (id, item) =>
  fetch(`${API_BASE}/api/items/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(item),
  }).then(jsonOrThrow).then((d) => d.item)

export const deleteItem = (id) =>
  fetch(`${API_BASE}/api/items/${id}`, { method: 'DELETE' }).then(jsonOrThrow)
