import { useState, useEffect, useMemo } from 'react'
import { Plus, Trash2, Copy, Check, X, Package, Search, ArrowRight, Minus, Upload } from 'lucide-react'
import {
  API_BASE, ItemSlot, RichTextEditor, FormattedLine, textureUrl, baseTextureUrl, resolveColor,
  buildGivePayload, fetchItems, villagerGiveCommand, villagerImport,
  manifestStem, manifestName, manifestLore, manifestLabel, manifestTextures,
  plainText, lineToComponent,
} from './mc'

let _uid = 0
const uid = () => `v${++_uid}`

const DEFAULT_MAX_USES = 99999999

// Biome dropdown — key is the VillagerData `type`.
const BIOMES = [
  { key: 'desert', label: 'Desert' },
  { key: 'jungle', label: 'Jungle' },
  { key: 'plains', label: 'Plains' },
  { key: 'savanna', label: 'Savanna' },
  { key: 'snow', label: 'Snow' },
  { key: 'swamp', label: 'Swamp' },
  { key: 'taiga', label: 'Taiga' },
]

// Profession dropdown — key is the VillagerData `profession`.
const PROFESSIONS = [
  { key: 'none', label: 'Unemployed' },
  { key: 'nitwit', label: 'Nitwit' },
  { key: 'armorer', label: 'Armorer' },
  { key: 'butcher', label: 'Butcher' },
  { key: 'cartographer', label: 'Cartographer' },
  { key: 'cleric', label: 'Cleric' },
  { key: 'farmer', label: 'Farmer' },
  { key: 'fisherman', label: 'Fisherman' },
  { key: 'fletcher', label: 'Fletcher' },
  { key: 'leatherworker', label: 'Leatherworker' },
  { key: 'librarian', label: 'Librarian' },
  { key: 'mason', label: 'Mason' },
  { key: 'shepherd', label: 'Shepherd' },
  { key: 'toolsmith', label: 'Toolsmith' },
  { key: 'weaponsmith', label: 'Weaponsmith' },
]

// Preview renders are mirrored from the wiki and served by the backend as
// <biome>_<profession>.webp (see web/backend/villager_textures/).
const villagerImageUrl = (biomeKey, professionKey) =>
  `${API_BASE}/api/villager-textures/${biomeKey}_${professionKey}.webp`

// A library manifest → a trade-slot item carrying the give-payload plus the
// display-only _stem/_label used for the thumbnail. Count is the trade quantity.
function slotItemFromManifest(item) {
  const payload = buildGivePayload(item) // { base_item, components }
  return {
    base_item: payload.base_item,
    count: payload.count || 1,
    components: payload.components || {},
    _stem: manifestStem(item.manifest),
    _label: manifestLabel(item.manifest),
  }
}

const slotToJson = (s) => (s ? { base_item: s.base_item, count: s.count, components: s.components } : null)

// A give-payload from an imported command → a trade-slot item, deriving the
// display-only _stem/_label from its components (mirrors slotItemFromManifest).
function slotItemFromJson(it) {
  if (!it || !it.base_item) return null
  const comps = it.components || {}
  const stem = String(comps['minecraft:item_model'] || '').replace(/^minecraft:custom\//, '')
  const label = plainText(comps['minecraft:custom_name']) || stem || it.base_item || 'item'
  return { base_item: it.base_item, count: it.count || 1, components: comps, _stem: stem || null, _label: label }
}

// Imported backend state → editor state.
const stateFromImport = (data) => ({
  villager_name: [data.name || []],
  biome: data.biome || 'plains',
  profession: data.profession || 'none',
  trades: (data.trades || []).map((t) => ({
    id: uid(),
    buy: slotItemFromJson(t.buy),
    buyB: slotItemFromJson(t.buyB),
    sell: slotItemFromJson(t.sell),
    maxUses: t.max_uses || DEFAULT_MAX_USES,
  })),
})

const newTrade = () => ({ id: uid(), buy: null, buyB: null, sell: null, maxUses: DEFAULT_MAX_USES })

const blankState = () => ({
  villager_name: [[]],
  biome: 'plains',
  profession: 'none',
  trades: [newTrade()],
})

// One draggable / clearable trade slot with a quantity stepper.
function TradeSlot({ item, label, onDrop, onClear, onCount }) {
  const [over, setOver] = useState(false)
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setOver(true) }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget)) setOver(false) }}
        onDrop={(e) => { e.preventDefault(); setOver(false); onDrop(e) }}
        className={`relative rounded transition-all ${over ? 'ring-2 ring-amber-400 dark:ring-amber-500' : ''}`}
      >
        {item ? (
          <div className="relative">
            <ItemSlot
              texture={item._stem ? textureUrl(item._stem) : null}
              fallbackTexture={baseTextureUrl(item.base_item)}
              name={item.components['minecraft:custom_name'] || { text: item._label }}
              lore={item.components['minecraft:lore'] || []}
              size={48}
              title={item._label}
            />
            {item.count > 1 && (
              <span className="absolute bottom-0 right-0 text-[11px] font-bold px-0.5 bg-black/70 text-white leading-none">
                {item.count}
              </span>
            )}
            <button
              onClick={onClear}
              className="absolute -top-1.5 -right-1.5 p-0.5 rounded bg-red-600 text-white hover:bg-red-500"
              title="Clear slot"
            >
              <X size={10} />
            </button>
          </div>
        ) : (
          <div
            className={`flex items-center justify-center border-2 border-dashed text-[9px] leading-tight text-center px-1 transition-colors ${
              over
                ? 'border-amber-400 bg-amber-50/60 dark:bg-amber-950/30 text-amber-600'
                : 'border-zinc-300 dark:border-zinc-600 text-zinc-400'
            }`}
            style={{ width: 48, height: 48 }}
          >
            {label}
          </div>
        )}
      </div>
      {item && (
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => onCount(Math.max(1, item.count - 1))}
            className="p-0.5 rounded text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700"
          >
            <Minus size={11} />
          </button>
          <span className="text-xs w-4 text-center tabular-nums">{item.count}</span>
          <button
            onClick={() => onCount(Math.min(64, item.count + 1))}
            className="p-0.5 rounded text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700"
          >
            <Plus size={11} />
          </button>
        </div>
      )}
    </div>
  )
}

export default function VillagerMaker() {
  const [state, setState] = useState(() => {
    try {
      const saved = sessionStorage.getItem('villager_draft')
      if (saved) return JSON.parse(saved)
    } catch { /* ignore parse errors */ }
    return blankState()
  })
  const [library, setLibrary] = useState([])
  const [libQuery, setLibQuery] = useState('')
  const [command, setCommand] = useState('')
  const [cmdError, setCmdError] = useState('')
  const [copied, setCopied] = useState(false)
  const [imgFailed, setImgFailed] = useState(false)
  const [showImport, setShowImport] = useState(false)
  const [importText, setImportText] = useState('')
  const [importError, setImportError] = useState('')
  const [importing, setImporting] = useState(false)

  useEffect(() => {
    fetchItems().then(setLibrary).catch(() => setLibrary([]))
  }, [])

  useEffect(() => {
    try { sessionStorage.setItem('villager_draft', JSON.stringify(state)) } catch { /* quota */ }
  }, [state])

  useEffect(() => setImgFailed(false), [state.biome, state.profession])

  // Build the backend payload from the current editor state.
  const buildPayload = () => ({
    name: plainText(state.villager_name[0] || []) ? lineToComponent(state.villager_name[0]) : null,
    biome: state.biome,
    profession: state.profession,
    trades: state.trades.map((t) => ({
      buy: slotToJson(t.buy),
      buyB: slotToJson(t.buyB),
      sell: slotToJson(t.sell),
      max_uses: t.maxUses,
    })),
  })

  // Live-render the /give command (debounced) whenever the villager changes.
  useEffect(() => {
    const h = setTimeout(() => {
      villagerGiveCommand(buildPayload())
        .then((cmd) => { setCommand(cmd); setCmdError('') })
        .catch((e) => setCmdError(e.message))
    }, 350)
    return () => clearTimeout(h)
  }, [state]) // eslint-disable-line react-hooks/exhaustive-deps

  const filteredLibrary = useMemo(() => {
    const q = libQuery.trim().toLowerCase()
    if (!q) return library
    return library.filter((it) =>
      manifestLabel(it.manifest).toLowerCase().includes(q) ||
      (it.manifest.base_item || '').toLowerCase().includes(q))
  }, [library, libQuery])

  // --- state mutation helpers -------------------------------------------
  const setField = (k, v) => setState((s) => ({ ...s, [k]: v }))
  const updateTrade = (id, patch) =>
    setState((s) => ({ ...s, trades: s.trades.map((t) => (t.id === id ? { ...t, ...patch } : t)) }))
  const setSlot = (id, key, value) => updateTrade(id, { [key]: value })
  const setSlotCount = (id, key, count) =>
    setState((s) => ({
      ...s,
      trades: s.trades.map((t) => (t.id === id ? { ...t, [key]: { ...t[key], count } } : t)),
    }))
  const addTrade = () => setState((s) => ({ ...s, trades: [...s.trades, newTrade()] }))
  const deleteTrade = (id) => setState((s) => ({ ...s, trades: s.trades.filter((t) => t.id !== id) }))

  const onDropSlot = (id, key, e) => {
    const raw = e.dataTransfer.getData('application/x-mc-item')
    if (!raw) return
    try { setSlot(id, key, slotItemFromManifest(JSON.parse(raw))) } catch { /* malformed drop */ }
  }

  const copyCommand = async () => {
    await navigator.clipboard.writeText(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 1600)
  }

  const doImport = async () => {
    setImportError('')
    setImporting(true)
    try {
      const data = await villagerImport(importText.trim())
      setState(stateFromImport(data))
      setShowImport(false)
      setImportText('')
    } catch (e) {
      setImportError(e.message)
    } finally {
      setImporting(false)
    }
  }

  const validTrades = state.trades.filter((t) => t.buy && t.sell).length
  const namePreview = state.villager_name[0] || []
  const hasName = plainText(namePreview).length > 0

  // ----------------------------------------------------------------------
  return (
    <>
    {/* Reserve room on the right for the fixed Item Library panel. */}
    <div className="lg:pr-64">
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-5xl leading-none">Villager Maker</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-2">
            Drag items from the library into the trade slots to build a custom trading villager.
          </p>
        </div>
        <button
          onClick={() => { setShowImport(true); setImportError('') }}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors shrink-0"
        >
          <Upload size={14} /> Import command
        </button>
      </div>

      {/* Import modal — paste a villager /give command to continue editing it. */}
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
              <p className="text-sm font-semibold">Import villager command</p>
              <button
                onClick={() => setShowImport(false)}
                className="p-1 rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
                aria-label="Close"
              >
                <X size={16} />
              </button>
            </div>
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Paste a <code>/give … villager_spawn_egg[…]</code> command to load its name, biome,
              profession, and trades back into the editor.
            </p>
            <textarea
              value={importText}
              onChange={(e) => setImportText(e.target.value)}
              rows={8}
              spellCheck={false}
              autoFocus
              placeholder="/give @p minecraft:villager_spawn_egg[…] 1"
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
                disabled={!importText.trim() || importing}
                className="px-4 py-1.5 border border-transparent bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 transition-colors"
              >
                {importing ? 'Importing…' : 'Load into editor'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Name — rich text, like item names */}
      <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 space-y-1">
        <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Villager name</span>
        <RichTextEditor
          value={state.villager_name}
          onChange={(lines) => setField('villager_name', lines)}
          singleLine
          placeholder="Archaeologist"
          defaultItalic={false}
          defaultColor={resolveColor('white')}
        />
      </div>

      <div className="flex flex-col lg:flex-row gap-5 items-start">
        {/* ---- Trade box (Minecraft villager GUI layout) ---- */}
        <div className="flex-1 min-w-0 bg-[#c6c6c6] dark:bg-zinc-800 border border-zinc-300 dark:border-zinc-700 rounded-xl overflow-hidden">
          <div className="px-4 py-2 bg-zinc-200 dark:bg-zinc-900/60 border-b border-zinc-300 dark:border-zinc-700">
            <div className="text-sm font-semibold text-zinc-700 dark:text-zinc-200">
              {hasName ? <FormattedLine value={namePreview} /> : 'Villager'}
            </div>
            <div className="text-[11px] text-zinc-500 dark:text-zinc-400">Trades</div>
          </div>

          <div className="p-4 space-y-2">
            {state.trades.map((t, i) => (
              <div
                key={t.id}
                className="flex items-center gap-2 sm:gap-3 bg-zinc-100 dark:bg-zinc-900/50 border border-zinc-300 dark:border-zinc-700 rounded-lg px-3 py-2.5"
              >
                <span className="text-xs font-semibold text-zinc-400 dark:text-zinc-500 w-5 shrink-0 text-center">{i + 1}</span>
                <TradeSlot
                  item={t.buy}
                  label="buy"
                  onDrop={(e) => onDropSlot(t.id, 'buy', e)}
                  onClear={() => setSlot(t.id, 'buy', null)}
                  onCount={(c) => setSlotCount(t.id, 'buy', c)}
                />
                <TradeSlot
                  item={t.buyB}
                  label="buy 2"
                  onDrop={(e) => onDropSlot(t.id, 'buyB', e)}
                  onClear={() => setSlot(t.id, 'buyB', null)}
                  onCount={(c) => setSlotCount(t.id, 'buyB', c)}
                />
                <ArrowRight size={20} className="text-zinc-400 shrink-0" />
                <TradeSlot
                  item={t.sell}
                  label="sell"
                  onDrop={(e) => onDropSlot(t.id, 'sell', e)}
                  onClear={() => setSlot(t.id, 'sell', null)}
                  onCount={(c) => setSlotCount(t.id, 'sell', c)}
                />
                <button
                  onClick={() => deleteTrade(t.id)}
                  className="ml-auto p-1 rounded-md text-zinc-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950 transition-colors shrink-0"
                  title="Remove trade"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}

            <button
              onClick={addTrade}
              className="w-full flex items-center justify-center gap-2 py-3 text-sm font-medium text-zinc-500 dark:text-zinc-400 border-2 border-dashed border-zinc-300 dark:border-zinc-700 rounded-lg hover:border-zinc-400 dark:hover:border-zinc-600 hover:text-zinc-700 dark:hover:text-zinc-200 transition-colors"
            >
              <Plus size={16} /> Add trade
            </button>
          </div>
        </div>

        {/* ---- Villager preview + biome/profession dropdowns ---- */}
        <div className="w-full lg:w-56 shrink-0 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 space-y-3">
          <div className="flex items-center justify-center h-48 bg-zinc-100 dark:bg-zinc-900 rounded-lg overflow-hidden">
            {imgFailed ? (
              <span className="text-xs text-zinc-400 px-3 text-center">Preview unavailable</span>
            ) : (
              <img
                src={villagerImageUrl(state.biome, state.profession)}
                alt="villager preview"
                referrerPolicy="no-referrer"
                onError={() => setImgFailed(true)}
                className="h-full w-auto object-contain"
                style={{ imageRendering: 'pixelated' }}
              />
            )}
          </div>
          {hasName && (
            <div className="text-center text-sm">
              <FormattedLine value={namePreview} />
            </div>
          )}
          <label className="block space-y-1">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Biome</span>
            <select
              value={state.biome}
              onChange={(e) => setField('biome', e.target.value)}
              className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
            >
              {BIOMES.map((b) => <option key={b.key} value={b.key}>{b.label}</option>)}
            </select>
          </label>
          <label className="block space-y-1">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Profession</span>
            <select
              value={state.profession}
              onChange={(e) => setField('profession', e.target.value)}
              className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
            >
              {PROFESSIONS.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
            </select>
          </label>
        </div>
      </div>

      {/* Generated /give command */}
      <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
            /give command <span className="text-zinc-400">({validTrades} trade{validTrades === 1 ? '' : 's'})</span>
          </span>
          <button
            onClick={copyCommand}
            disabled={!command}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-40 transition-colors"
          >
            {copied ? <Check size={14} /> : <Copy size={14} />} {copied ? 'Copied!' : 'Copy command'}
          </button>
        </div>
        {cmdError ? (
          <p className="text-xs text-red-600 dark:text-red-400 font-mono">{cmdError}</p>
        ) : (
          <pre className="max-h-40 overflow-auto text-[11px] font-mono text-zinc-600 dark:text-zinc-300 bg-zinc-50 dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-700 rounded-lg p-3 whitespace-pre-wrap break-all">
            {command || 'Add a trade (buy + sell) to generate a command.'}
          </pre>
        )}
      </div>
    </div>
    </div>

    {/* Item Library — fixed right panel; drag an item onto any trade slot. */}
    <aside className="hidden lg:flex fixed top-0 right-0 h-screen z-30 flex-col border-l border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 px-3 py-4">
      <span className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400 mb-2">
        <Package size={14} /> Item Library <span className="text-zinc-400 font-normal">({library.length})</span>
      </span>
      <div className="relative mb-2">
        <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400" />
        <input
          value={libQuery}
          onChange={(e) => setLibQuery(e.target.value)}
          placeholder="Search items…"
          className="w-full pl-7 pr-2 py-1 text-xs rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
        />
      </div>
      {library.length === 0 ? (
        <p className="text-xs text-zinc-400 py-2">No saved items — create some in the Item Library tab.</p>
      ) : filteredLibrary.length === 0 ? (
        <p className="text-xs text-zinc-400 py-2">No items match “{libQuery}”.</p>
      ) : (
        <div className="grid grid-cols-5 gap-1.5 flex-1 min-h-0 overflow-y-auto pr-1 -mr-1 content-start">
          {filteredLibrary.map((item) => {
            const { texture, fallbackTexture } = manifestTextures(item.manifest)
            return (
              <ItemSlot
                key={item.id}
                texture={texture}
                fallbackTexture={fallbackTexture}
                name={manifestName(item.manifest)}
                lore={manifestLore(item.manifest)}
                size={40}
                draggable
                title={`Drag “${manifestLabel(item.manifest)}” into a trade slot`}
                onDragStart={(e) => {
                  e.dataTransfer.setData('application/x-mc-item', JSON.stringify(item))
                  e.dataTransfer.effectAllowed = 'copy'
                }}
              />
            )
          })}
        </div>
      )}
    </aside>
    </>
  )
}
