// Shared Minecraft helpers: color constants, the color picker, text-format
// toggles, the item slot + in-game-style tooltip, give-payload building, and
// the Item Library API client. Used by both ItemLibrary and NpcMaker.
import { useState, useRef, useEffect, useLayoutEffect, useCallback, useMemo } from 'react'
import { ChevronDown, Check, Hash, Bold, Italic, Underline, Strikethrough, Shuffle, Type } from 'lucide-react'

export const API_BASE = ''

// In-game tooltips render up-and-to-the-right of the cursor. These are the
// offsets (px) from the mouse pointer to the tooltip's top-left corner.
export const TOOLTIP_OFFSET_X = 14 // → to the right of the cursor
export const TOOLTIP_OFFSET_Y = 26 // ↑ above the cursor

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
  ['strikethrough', Strikethrough], ['obfuscated', Shuffle],
]
// Just the flag keys, in order — used by the segment/rich-text machinery.
const FMT_KEYS = FORMAT_FLAGS.map(([k]) => k)

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
  const cycle = (flag) => {
    const cur = fmt[flag]
    const next = cur === undefined ? true : cur === true ? false : undefined
    const f = { ...fmt }
    if (next === undefined) delete f[flag]
    else f[flag] = next
    onChange(f)
  }
  return (
    <div className="flex items-center gap-0.5">
      {FORMAT_FLAGS.map(([flag, Icon]) => {
        const state = fmt[flag]
        const cls = state === true
          ? 'bg-green-600 text-white'
          : state === false
          ? 'bg-red-600 text-white'
          : 'text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700'
        return (
          <button key={flag} type="button" title={flag} onClick={() => cycle(flag)}
            className={`p-1.5 rounded-md transition-colors ${cls}`}>
            <Icon size={14} />
          </button>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Segment model
//
// A run of styled text is a "segment": { text, color?, bold?, … }. A "line" is
// an array of segments. The name is one line; lore is an array of lines. This
// is the in-memory shape the rich-text editor produces and the tooltip renders.
// ---------------------------------------------------------------------------

// The format-only part of a segment (no text), with empty/false keys dropped.
function segFmt(s) {
  const f = {}
  if (s.color) f.color = s.color
  for (const k of FMT_KEYS) {
    if (s[k] === true) f[k] = true
    else if (s[k] === false) f[k] = false
  }
  return f
}
function sameFmt(a, b) {
  if ((a.color || '') !== (b.color || '')) return false
  for (const k of FMT_KEYS) if (a[k] !== b[k]) return false
  return true
}
// Append text to a segment list, merging into the last run if the format matches.
function pushRun(segs, text, fmt) {
  if (!text) return
  const last = segs[segs.length - 1]
  if (last && sameFmt(last, fmt)) last.text += text
  else segs.push({ ...fmt, text })
}

// Normalize anything (Minecraft text component, plain string, segment array,
// legacy {text,…} object) into a flat array of segments. `extra` children
// inherit the parent's format, matching the game.
export function asSegments(value, inherited = {}) {
  if (value == null) return []
  if (typeof value === 'string') return value ? [{ ...inherited, text: value }] : []
  if (Array.isArray(value)) return value.flatMap((v) => asSegments(v, inherited))
  const fmt = { ...inherited }
  if (value.color != null) fmt.color = value.color
  for (const k of FMT_KEYS) if (value[k] != null) fmt[k] = value[k]
  const out = []
  if (value.text) out.push({ ...segFmt(fmt), text: value.text })
  if (Array.isArray(value.extra)) for (const e of value.extra) out.push(...asSegments(e, fmt))
  return out
}

// Plain text of any formatted value.
export const plainText = (value) => asSegments(value).map((s) => s.text).join('')

// A line (segment array) → a Minecraft text component. One segment collapses to
// a flat component; many become a base with an `extra` array.
export function lineToComponent(line) {
  const segs = asSegments(line).filter((s) => s.text)
  const comp = (s) => ({ text: s.text, ...segFmt(s) })
  if (!segs.length) return { text: '' }
  if (segs.length === 1) return comp(segs[0])
  return { text: '', extra: segs.map(comp) }
}

// ---------------------------------------------------------------------------
// Preview rendering
// ---------------------------------------------------------------------------
function segStyle(s, defaultItalic = false) {
  const deco = [s.underlined && 'underline', s.strikethrough && 'line-through']
    .filter(Boolean).join(' ')
  return {
    color: resolveColor(s.color) || undefined,
    fontWeight: s.bold === true ? 700 : s.bold === false ? 400 : undefined,
    fontStyle: s.italic === true ? 'italic' : s.italic === false ? 'normal' : (defaultItalic ? 'italic' : undefined),
    textDecoration: deco || undefined,
  }
}

const OBF_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
function scramble(text) {
  return text.replace(/\S/g, () => OBF_CHARS[Math.floor(Math.random() * OBF_CHARS.length)])
}

// One obfuscated segment, scrambling its glyphs on a timer like the game does.
function ObfuscatedRun({ s, defaultItalic = false }) {
  const [shown, setShown] = useState(() => scramble(s.text))
  useEffect(() => {
    setShown(scramble(s.text))
    const id = setInterval(() => setShown(scramble(s.text)), 70)
    return () => clearInterval(id)
  }, [s.text])
  return <span style={segStyle(s, defaultItalic)}>{shown}</span>
}

// Renders a line (array of segments / any formatted value) as styled spans.
export function FormattedLine({ value, fallback = '', defaultItalic = false }) {
  const segs = asSegments(value).filter((s) => s.text)
  if (!segs.length) return <span className="opacity-40">{fallback}</span>
  return segs.map((s, i) => (s.obfuscated
    ? <ObfuscatedRun key={i} s={s} defaultItalic={defaultItalic} />
    : <span key={i} style={segStyle(s, defaultItalic)}>{s.text}</span>))
}

// In-game-style tooltip: dark box, formatted name on top, lore lines below.
// Custom names default to cyan/italic; lore defaults to light_purple/italic —
// matching Minecraft's default rendering for these components.
export function ItemTooltip({ name, lore, nameItalic = true }) {
  return (
    <div
      className="pointer-events-none whitespace-nowrap px-2 py-1.5 text-sm leading-tight border-2"
      style={{ background: '#100010F0', borderColor: '#280050', fontFamily: 'inherit' }}
    >
      <div style={{ color: resolveColor('white') }}>
        <FormattedLine value={name} fallback="Unnamed item" defaultItalic={nameItalic} />
      </div>
      {(lore || []).map((line, i) => (
        <div key={i} style={{ color: resolveColor('light_purple') }}>
          <FormattedLine value={line} fallback=" " defaultItalic={true} />
        </div>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Animated texture renderer
//
// Minecraft's animated texture format stacks all frames vertically in a
// single PNG: a W×W sprite sheet where the image is W px wide and N*W px
// tall (N frames). Frame count is probed once per src via a hidden Image
// object so detection is independent of the render phase.
//
// Timing behaviour differs by frame count:
//   N == 2  →  crossfade: two copies of the image are stacked; the top
//              layer's opacity oscillates 0↔1 via a CSS transition, toggled
//              by a 1 000 ms setInterval. The CSS transition duration also
//              equals 1 s, so the two frames continuously blend into each
//              other with no hard cut.
//   N  > 2  →  hard-cut: a single image sheet scrolls upward by one frame
//              height every 250 ms (4 fps ≈ Minecraft's default frame time
//              of 1 tick at 20 tps).
//   N == 1  →  plain image, no animation.
// ---------------------------------------------------------------------------
export function AnimatedTexture({ src, size, onError, draggable = false }) {
  const [nFrames, setNFrames] = useState(1)
  const [frame, setFrame] = useState(0)
  const [crossActive, setCrossActive] = useState(false)
  const [visible, setVisible] = useState(false)
  const containerRef = useRef(null)

  // Defer all network work until the slot scrolls near the viewport. Without
  // this, the dimension probe below fires for every slot on mount — off-screen
  // included — which would hit Dropbox once per item the moment a grid renders.
  // The empty container is always mounted so the observer has something to watch.
  useEffect(() => {
    if (visible) return
    const el = containerRef.current
    if (!el) return
    if (typeof IntersectionObserver === 'undefined') { setVisible(true); return }
    const obs = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) { setVisible(true); obs.disconnect() }
    }, { rootMargin: '200px' })
    obs.observe(el)
    return () => obs.disconnect()
  }, [visible])

  // Once visible, this is the src we actually load; before that it's null so
  // neither the probe nor the <img> touches the network.
  const activeSrc = visible ? src : null

  // Probe dimensions with a hidden Image so we know the frame count before
  // the visible <img> elements need to paint. Also resets all animation state
  // when src changes so a new texture never inherits stale timing.
  useEffect(() => {
    setNFrames(1); setFrame(0); setCrossActive(false)
    if (!activeSrc) return
    const probe = new Image()
    probe.onload = () => {
      const n = probe.naturalHeight / probe.naturalWidth
      if (Number.isInteger(n) && n > 1) setNFrames(n)
    }
    probe.src = activeSrc
  }, [activeSrc])

  // 2-frame crossfade: toggle the overlay opacity every 1 000 ms. The CSS
  // transition on the overlay also runs for 1 000 ms, producing a continuous
  // blend with no stationary hold at either extreme.
  useEffect(() => {
    if (nFrames !== 2) return
    const id = setInterval(() => setCrossActive((v) => !v), 1000)
    return () => clearInterval(id)
  }, [nFrames])

  // N>2 hard-cut: advance one frame every 250 ms.
  useEffect(() => {
    if (nFrames <= 2) return
    const id = setInterval(() => setFrame((f) => (f + 1) % nFrames), 250)
    return () => clearInterval(id)
  }, [nFrames])

  const sheet = (frameIndex) => ({
    width: size,
    height: size * nFrames,
    position: 'absolute',
    top: -frameIndex * size,
    imageRendering: 'pixelated',
  })

  const boxStyle = { width: size, height: size, overflow: 'hidden', position: 'relative', flexShrink: 0 }

  if (nFrames === 2) {
    return (
      <div ref={containerRef} style={boxStyle}>
        {/* Frame 0 — base layer, always fully opaque */}
        <img src={activeSrc} alt="" draggable={draggable} onError={onError} style={sheet(0)} />
        {/* Frame 1 — overlay whose opacity the 1 000 ms interval drives */}
        <img src={activeSrc} alt="" draggable={draggable}
          style={{ ...sheet(1), opacity: crossActive ? 1 : 0, transition: 'opacity 1s ease-in-out' }} />
      </div>
    )
  }

  return (
    <div ref={containerRef} style={boxStyle}>
      {activeSrc && (
        <img src={activeSrc} alt="" loading="lazy" draggable={draggable} onError={onError} style={sheet(frame)} />
      )}
    </div>
  )
}

// A mock inventory slot showing a texture. Falls back from the custom texture
// to the vanilla base-item texture (items inheriting the base game look), then
// hides if neither resolves. The tooltip follows the mouse, anchored
// up-and-to-the-right of the cursor (TOOLTIP_OFFSET_*). `hoverActions` is an
// overlay rendered only while hovering; `children` renders always.
export function ItemSlot({
  texture, fallbackTexture, name, lore, size = 48, nameItalic = true,
  draggable = false, onDragStart, title, children, hoverActions, onClick,
}) {
  const [hover, setHover] = useState(false)
  const [pos, setPos] = useState({ x: 0, y: 0 })
  const [primaryFailed, setPrimaryFailed] = useState(false)
  useEffect(() => setPrimaryFailed(false), [texture])

  const src = texture && !primaryFailed ? texture : (fallbackTexture || null)
  const hasContent = plainText(name).length > 0 || (lore || []).some((l) => plainText(l).length > 0)
  return (
    <div
      className="relative shrink-0"
      onClick={onClick}
      onMouseEnter={(e) => { setHover(true); setPos({ x: e.clientX, y: e.clientY }) }}
      onMouseMove={(e) => setPos({ x: e.clientX, y: e.clientY })}
      onMouseLeave={() => setHover(false)}
    >
      <div
        draggable={draggable}
        onDragStart={onDragStart}
        // title={title}
        className="relative flex items-center justify-center border-2 border-zinc-400 dark:border-zinc-600 bg-zinc-300/70 dark:bg-zinc-700/70"
        style={{ width: size, height: size, cursor: onClick ? 'pointer' : draggable ? 'grab' : 'default' }}
      >
        {src ? (
          <AnimatedTexture
            key={src}
            src={src}
            size={size - 10}
            draggable={false}
            onError={(e) => {
              if (texture && !primaryFailed) setPrimaryFailed(true)
              else e.currentTarget.style.visibility = 'hidden'
            }}
          />
        ) : null}
        {onClick && hover && <div className="absolute inset-0 bg-white/20 pointer-events-none" />}
      </div>
      {children}
      {hover && hoverActions}
      {hover && hasContent && (
        <div
          className="fixed z-50"
          style={{ left: pos.x + TOOLTIP_OFFSET_X, top: pos.y - TOOLTIP_OFFSET_Y }}
        >
          <ItemTooltip name={name} lore={lore} nameItalic={nameItalic} />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Data helpers
// ---------------------------------------------------------------------------

// A blank formatted-text object (legacy single-run shape; kept for callers that
// still want one styled run). Format flags are omitted so they default to the
// Minecraft default rendering (italic for names/lore, etc.) rather than forcing
// a state.
export const blankFmt = (text = '') => ({ text, color: '' })

// Texture URL for a custom model stem. Resolves to the Dropbox-backed thumb
// endpoint (a 302 to a short-lived Dropbox link, browser-cached), so uploaded
// textures are live without a redeploy.
export const textureUrl = (stem) =>
  `${API_BASE}/api/texture/thumb/${encodeURIComponent(stem)}`
// Vanilla base-item texture, used when an item inherits the base game look.
export const baseTextureUrl = (baseItem) =>
  baseItem ? `${API_BASE}/api/base-textures/${String(baseItem).replace(/^minecraft:/, '')}.png` : null

// ---------------------------------------------------------------------------
// Base-item combobox — a text field that live-filters the list of valid vanilla
// base items as you type and only commits a value when one is picked, so the
// result is always a real Minecraft item. `options` is the id list from
// fetchBaseItems(); `onChange` fires with the chosen id.
// ---------------------------------------------------------------------------
export function BaseItemPicker({
  value, onChange, options, disabled = false,
  placeholder = 'search base items…', autoFocus = false, startOpen = false,
}) {
  const [open, setOpen] = useState(startOpen)
  const [query, setQuery] = useState(startOpen ? '' : null) // null → mirror `value`
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) { setOpen(false); setQuery(null) } }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  // While editing (query !== null) show what's typed; otherwise show the value.
  const shown = query === null ? (value || '') : query

  const results = useMemo(() => {
    const q = (query || '').trim().toLowerCase()
    const list = q ? options.filter((o) => o.includes(q)) : options
    return list.slice(0, 100)
  }, [options, query])

  const commit = (name) => { onChange(name); setQuery(null); setOpen(false) }

  return (
    <div className="relative" ref={ref}>
      <input
        value={shown}
        disabled={disabled}
        autoFocus={autoFocus}
        onFocus={() => { setQuery(value || ''); setOpen(true) }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && results.length) { e.preventDefault(); commit(results[0]) }
          if (e.key === 'Escape') { setOpen(false); setQuery(null) }
        }}
        placeholder={placeholder}
        className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600 disabled:opacity-50"
      />
      {open && !disabled && (
        <div className="absolute z-40 mt-1 w-full max-h-64 overflow-auto bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg shadow-2xl p-1">
          {results.length ? (
            results.map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => commit(name)}
                className={`w-full flex items-center gap-2 px-2 py-1 text-sm rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors ${
                  value === name ? 'bg-zinc-100 dark:bg-zinc-700' : ''
                }`}
              >
                <img
                  src={baseTextureUrl(name)}
                  alt=""
                  loading="lazy"
                  onError={(e) => { e.currentTarget.style.visibility = 'hidden' }}
                  style={{ width: 20, height: 20, imageRendering: 'pixelated' }}
                />
                <span className="truncate">{name}</span>
              </button>
            ))
          ) : (
            <p className="px-2 py-3 text-xs text-zinc-400 text-center">
              No items match{query ? ` “${query}”` : ''}.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Item manifest helpers
//
// A saved item row is { id, manifest, created_at }. The manifest is the full
// give-payload — { base_item, count, components:{...} } — so arbitrary
// components (enchantments, attribute modifiers, …) round-trip untouched even
// though the editor only surfaces name / lore / tags.
// ---------------------------------------------------------------------------
export const EDITABLE_COMPONENTS = [
  'minecraft:item_model', 'minecraft:custom_name', 'minecraft:lore', 'minecraft:custom_data',
]

export const manifestComponents = (m) => (m && m.components) || {}
// Custom-model stem from minecraft:item_model (`minecraft:custom/<stem>`), or null.
export function manifestStem(m) {
  const im = manifestComponents(m)['minecraft:item_model']
  if (typeof im !== 'string') return null
  const i = im.indexOf('custom/')
  return i >= 0 ? im.slice(i + 'custom/'.length) : null
}
export const manifestName = (m) => manifestComponents(m)['minecraft:custom_name'] || null
export const manifestLore = (m) => manifestComponents(m)['minecraft:lore'] || []
export const manifestTags = (m) => Object.keys(manifestComponents(m)['minecraft:custom_data'] || {})
// Component keys beyond the editable few — the "additional data" the editor locks.
export const manifestExtraKeys = (m) =>
  Object.keys(manifestComponents(m)).filter((k) => !EDITABLE_COMPONENTS.includes(k))
// Turn a snake_case item id into a Title Cased label: lapis_lazuli → Lapis Lazuli.
export const prettifyId = (id) =>
  String(id || '')
    .replace(/^minecraft:/, '')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())

// A human label for an item: its custom name if it has one, otherwise a
// prettified form of its model stem / base item (lapis_lazuli → Lapis Lazuli).
export const manifestLabel = (m) =>
  plainText(manifestName(m)) || prettifyId(manifestStem(m) || (m && m.base_item)) || 'item'

// Custom + vanilla-fallback texture URLs for an item's slot.
export function manifestTextures(m) {
  const stem = manifestStem(m)
  return { texture: stem ? textureUrl(stem) : null, fallbackTexture: baseTextureUrl(m && m.base_item) }
}

// The give-payload for an item is simply its manifest.
export function buildGivePayload(item) {
  return item.manifest || item
}

// ---------------------------------------------------------------------------
// Rich-text editor — type freely, highlight a span, and a floating toolbar
// applies bold / italic / underline / strikethrough / obfuscated / color to
// just that selection. The value is an array of lines (each a segment array);
// `singleLine` keeps Enter from creating new lines (used for the item name).
// ---------------------------------------------------------------------------

// Explode a line into per-character {ch, fmt} so a range can be re-styled, then
// rejoin equal-format neighbours back into segments.
function lineToChars(line) {
  const out = []
  for (const s of asSegments(line)) for (const ch of s.text) out.push({ ch, fmt: segFmt(s) })
  return out
}
function charsToLine(chars) {
  const segs = []
  for (const { ch, fmt } of chars) pushRun(segs, ch, fmt)
  return segs
}

const escapeHtml = (s) => s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))

// lines → HTML. One <div> per line; one <span data-fmt> per segment.
function linesToHtml(lines, defaultItalic = false) {
  const list = lines.length ? lines : [[]]
  return list.map((line) => {
    const segs = asSegments(line).filter((s) => s.text)
    if (!segs.length) return '<div><br></div>'
    const inner = segs.map((s) => {
      const fmt = segFmt(s)
      const style = Object.entries(segStyle(s, defaultItalic))
        .filter(([, v]) => v != null)
        .map(([k, v]) => `${k.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase())}:${v}`)
        .join(';')
      return `<span data-fmt='${escapeHtml(JSON.stringify(fmt))}' style="${style}">${escapeHtml(s.text)}</span>`
    }).join('')
    return `<div>${inner}</div>`
  }).join('')
}

// Format carried by an element: an explicit data-fmt wins; otherwise infer from
// tags the browser may inject (b/i/u/s) merged with the inherited format.
function fmtFromEl(el, inherited) {
  if (el.dataset && el.dataset.fmt) {
    try { return JSON.parse(el.dataset.fmt) } catch { /* fall through */ }
  }
  const f = { ...inherited }
  const tag = el.tagName
  if (tag === 'B' || tag === 'STRONG') f.bold = true
  if (tag === 'I' || tag === 'EM') f.italic = true
  if (tag === 'U') f.underlined = true
  if (tag === 'S' || tag === 'STRIKE' || tag === 'DEL') f.strikethrough = true
  return f
}

// Parse a single inline node (text or element) into segments.
function parseInline(node, fmt, out) {
  if (node.nodeType === 3) { pushRun(out, node.nodeValue, fmt); return }
  if (node.nodeType !== 1 || node.tagName === 'BR') return
  const nf = fmtFromEl(node, fmt)
  for (const c of node.childNodes) parseInline(c, nf, out)
}

// contentEditable DOM → lines. Each top-level <div>/<p> (or <br>) is a line.
function domToLines(root) {
  const lines = []
  let pending = null
  const flush = () => { if (pending !== null) { lines.push(pending); pending = null } }
  for (const child of root.childNodes) {
    if (child.nodeType === 1 && (child.tagName === 'DIV' || child.tagName === 'P')) {
      flush()
      const segs = []
      for (const c of child.childNodes) parseInline(c, {}, segs)
      lines.push(segs)
    } else if (child.nodeType === 1 && child.tagName === 'BR') {
      if (pending === null) pending = []
      flush()
    } else {
      if (pending === null) pending = []
      parseInline(child, {}, pending)
    }
  }
  flush()
  return lines.length ? lines : [[]]
}

// --- selection <-> {line, char} offsets ----------------------------------
function lineIndexOf(root, node) {
  if (node === root) return -1
  let el = node.nodeType === 3 ? node.parentNode : node
  while (el && el.parentNode !== root) el = el.parentNode
  if (!el) return -1
  return Array.prototype.indexOf.call(root.children, el)
}
function charOffsetIn(container, node, offset) {
  const r = document.createRange()
  r.selectNodeContents(container)
  try { r.setEnd(node, offset) } catch { return container.textContent.length }
  return r.toString().length
}
function readSelection(root) {
  const sel = window.getSelection()
  if (!sel || !sel.rangeCount) return null
  const r = sel.getRangeAt(0)
  if (r.collapsed || !root.contains(r.startContainer) || !root.contains(r.endContainer)) return null
  let sLine = lineIndexOf(root, r.startContainer)
  let eLine = lineIndexOf(root, r.endContainer)
  if (sLine < 0 || eLine < 0) return null
  const sCh = charOffsetIn(root.children[sLine], r.startContainer, r.startOffset)
  const eCh = charOffsetIn(root.children[eLine], r.endContainer, r.endOffset)
  return { startLine: sLine, startCh: sCh, endLine: eLine, endCh: eCh }
}
function locateChar(lineEl, ch) {
  let remaining = ch
  const walker = document.createTreeWalker(lineEl, NodeFilter.SHOW_TEXT)
  let n, last = null
  while ((n = walker.nextNode())) {
    last = n
    if (remaining <= n.nodeValue.length) return { node: n, offset: remaining }
    remaining -= n.nodeValue.length
  }
  if (last) return { node: last, offset: last.nodeValue.length }
  return { node: lineEl, offset: 0 }
}
function restoreSelection(root, range) {
  if (!range || !root.children[range.startLine] || !root.children[range.endLine]) return
  const a = locateChar(root.children[range.startLine], range.startCh)
  const b = locateChar(root.children[range.endLine], range.endCh)
  const r = document.createRange()
  r.setStart(a.node, a.offset)
  r.setEnd(b.node, b.offset)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(r)
}

// The floating format toolbar shown over an active selection.
const TOOLBAR_COLORS = MC_COLOR_LIST

function RichToolbar({ pos, active, onToggle, onColor }) {
  return (
    <div
      className="fixed z-[60] flex items-center gap-0.5 p-1 bg-zinc-900 border border-zinc-700 rounded-lg shadow-2xl"
      style={{ left: pos.left, top: pos.top, transform: 'translate(-50%, -100%)' }}
      onMouseDown={(e) => e.preventDefault()} /* keep the text selection alive */
    >
      {FORMAT_FLAGS.map(([flag, Icon]) => {
        const state = active[flag]
        const cls = state === true
          ? 'bg-green-700 text-white'
          : state === false
          ? 'bg-red-700 text-white'
          : 'text-zinc-300 hover:bg-zinc-700'
        return (
          <button key={flag} type="button" title={flag} onClick={() => onToggle(flag)}
            className={`p-1.5 rounded-md transition-colors ${cls}`}>
            <Icon size={14} />
          </button>
        )
      })}
      <div className="w-px h-5 bg-zinc-700 mx-0.5" />
      {TOOLBAR_COLORS.map(([name, hex]) => (
        <button
          key={name}
          type="button"
          title={name}
          onClick={() => onColor(name)}
          className={`w-4 h-4 rounded-sm border ${active.color === name ? 'border-white' : 'border-white/20'}`}
          style={{ backgroundColor: hex }}
        />
      ))}
      <button
        type="button"
        title="default color"
        onClick={() => onColor('')}
        className="p-1 rounded-md text-zinc-300 hover:bg-zinc-700"
      >
        <Type size={13} />
      </button>
    </div>
  )
}

export function RichTextEditor({ value, onChange, singleLine = false, placeholder = '', defaultItalic = false, defaultColor = '#FFFFFF' }) {
  const ref = useRef(null)
  const lastEmitted = useRef(null)
  const [toolbar, setToolbar] = useState(null)
  const lines = value && value.length ? value : [[]]
  const isEmpty = !lines.some((l) => asSegments(l).some((s) => s.text))

  const emit = useCallback((next) => { lastEmitted.current = next; onChange(next) }, [onChange])

  // Sync DOM from value only on external changes (load/reset) — never while the
  // user types, so the caret stays put.
  useLayoutEffect(() => {
    if (value === lastEmitted.current) return
    if (ref.current) ref.current.innerHTML = linesToHtml(lines, defaultItalic)
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps

  const refreshToolbar = useCallback(() => {
    const root = ref.current
    if (!root) return
    const range = readSelection(root)
    if (!range) { setToolbar(null); return }
    const domRange = window.getSelection().getRangeAt(0)
    const rect = domRange.getBoundingClientRect()
    // Active state = format shared by every selected character.
    const cur = domToLines(root)
    let active = null
    for (let li = range.startLine; li <= range.endLine; li++) {
      const chars = lineToChars(cur[li] || [])
      const from = li === range.startLine ? range.startCh : 0
      const to = li === range.endLine ? range.endCh : chars.length
      for (let i = from; i < to; i++) {
        const f = chars[i].fmt
        if (active === null) active = { ...f }
        else {
          for (const k of FMT_KEYS) if (active[k] !== f[k]) active[k] = undefined
          if ((f.color || '') !== (active.color || '')) active.color = undefined
        }
      }
    }
    setToolbar({ left: rect.left + rect.width / 2, top: rect.top - 6, active: active || {} })
  }, [])

  useEffect(() => {
    const onSel = () => refreshToolbar()
    document.addEventListener('selectionchange', onSel)
    return () => document.removeEventListener('selectionchange', onSel)
  }, [refreshToolbar])

  const onInput = () => { if (ref.current) emit(domToLines(ref.current)) }

  // Apply a transform to every character in the live selection, then re-render
  // the DOM and restore the selection so further edits stack.
  const applyToSelection = (transform) => {
    const root = ref.current
    if (!root) return
    const range = readSelection(root)
    if (!range) return
    const cur = domToLines(root)
    const next = cur.map((line, li) => {
      if (li < range.startLine || li > range.endLine) return line
      const chars = lineToChars(line)
      const from = li === range.startLine ? range.startCh : 0
      const to = li === range.endLine ? range.endCh : chars.length
      for (let i = from; i < to; i++) chars[i].fmt = transform(chars[i].fmt)
      return charsToLine(chars)
    })
    root.innerHTML = linesToHtml(next, defaultItalic)
    restoreSelection(root, range)
    emit(next)
    refreshToolbar()
  }

  const cycleFlag = (flag) => {
    const cur = toolbar?.active?.[flag]
    const next = cur === undefined ? true : cur === true ? false : undefined
    applyToSelection((fmt) => {
      const f = { ...fmt }
      if (next === undefined) delete f[flag]
      else f[flag] = next
      return f
    })
  }
  const setColor = (color) => applyToSelection((fmt) => {
    const f = { ...fmt }
    if (color) f.color = color
    else delete f.color
    return f
  })

  const onKeyDown = (e) => {
    if (singleLine && e.key === 'Enter') { e.preventDefault(); return }
    // Route the browser's native bold/italic/underline shortcuts to our model.
    if ((e.ctrlKey || e.metaKey) && !e.altKey) {
      const k = e.key.toLowerCase()
      const map = { b: 'bold', i: 'italic', u: 'underlined' }
      if (map[k]) { e.preventDefault(); cycleFlag(map[k]) }
    }
  }

  return (
    <div className="relative">
      <div
        ref={ref}
        contentEditable
        suppressContentEditableWarning
        spellCheck={false}
        onInput={onInput}
        onKeyDown={onKeyDown}
        onBlur={() => setToolbar(null)}
        style={{ background: '#100010', color: defaultColor }}
        className="w-full min-h-[2.25rem] px-3 py-1.5 text-sm rounded-lg border-2 border-[#280050] focus:outline-none focus:ring-2 focus:ring-zinc-500 whitespace-pre-wrap break-words"
      />
      {isEmpty && (
        <span className="pointer-events-none absolute left-[16px] top-2.5 text-sm text-zinc-400 select-none">
          {placeholder}
        </span>
      )}
      {toolbar && (
        <RichToolbar pos={toolbar} active={toolbar.active} onToggle={cycleFlag} onColor={setColor} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Item Library API client
// ---------------------------------------------------------------------------
export async function jsonOrThrow(res) {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`)
  return data
}

export const fetchModels = () =>
  fetch(`${API_BASE}/api/items/models`).then(jsonOrThrow).then((d) => d.models)

// The set of valid vanilla base-item ids (those we have a base texture for).
export const fetchBaseItems = () =>
  fetch(`${API_BASE}/api/base-items`).then(jsonOrThrow).then((d) => d.items)

export const fetchItems = () =>
  fetch(`${API_BASE}/api/items`).then(jsonOrThrow).then((d) => d.items)

export const createItem = (manifest) =>
  fetch(`${API_BASE}/api/items`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ manifest }),
  }).then(jsonOrThrow).then((d) => d.item)

export const updateItem = (id, manifest) =>
  fetch(`${API_BASE}/api/items/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ manifest }),
  }).then(jsonOrThrow).then((d) => d.item)

export const deleteItem = (id) =>
  fetch(`${API_BASE}/api/items/${id}`, { method: 'DELETE' }).then(jsonOrThrow)

// Import items from a /give command (text) and/or a .schem file. Returns the
// list of newly-saved rows.
export const importItems = ({ text, file }) => {
  const body = new FormData()
  if (text) body.append('text', text)
  if (file) body.append('file', file)
  return fetch(`${API_BASE}/api/items/import`, { method: 'POST', body })
    .then(jsonOrThrow).then((d) => d.items)
}

// Render a manifest as a copy-pasteable /give command.
export const giveCommand = (manifest) =>
  fetch(`${API_BASE}/api/items/give-command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ manifest }),
  }).then(jsonOrThrow).then((d) => d.command)

// Render a trading-villager spawn egg as a /give command from editor state.
export const villagerGiveCommand = (payload) =>
  fetch(`${API_BASE}/api/villager/give-command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(jsonOrThrow).then((d) => d.command)

// Parse a villager /give command back into editor state (name/biome/profession/trades).
export const villagerImport = (command) =>
  fetch(`${API_BASE}/api/villager/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command }),
  }).then(jsonOrThrow)

// ---------------------------------------------------------------------------
// Texture Pack (Dropbox) API client
// ---------------------------------------------------------------------------
// Names of custom textures currently in the Unzipped pack: { textures, count }.
export const fetchTextures = () =>
  fetch(`${API_BASE}/api/texture/list`).then(jsonOrThrow)

// Upload PNG File objects; the server derives each name and writes the model +
// item-def JSON alongside. `parent` is 'generated' (flat) or 'handheld' (tool).
export const uploadTextures = ({ files, parent, overwrite = true }) => {
  const body = new FormData()
  files.forEach((f) => body.append('files', f))
  body.append('parent', parent)
  body.append('overwrite', overwrite ? 'true' : 'false')
  return fetch(`${API_BASE}/api/texture/upload`, { method: 'POST', body }).then(jsonOrThrow)
}

// Repack the Unzipped pack into pack.zip and return { link } for Apex.
export const syncTexturePack = () =>
  fetch(`${API_BASE}/api/texture/sync`, { method: 'POST' }).then(jsonOrThrow)

// Preview URL for a custom texture — same Dropbox-backed thumb endpoint as
// textureUrl (kept as a named alias for the Texture Pack tab's call sites).
export const textureThumbUrl = textureUrl
