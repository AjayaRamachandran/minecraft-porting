import { useState, useEffect, useMemo, useRef } from 'react'
import { Plus, Trash2, X, Search, Save, Package, Pencil } from 'lucide-react'
import {
  ColorPicker, FormatToggles, ItemSlot, blankFmt, textureUrl,
  fetchModels, fetchItems, createItem, updateItem, deleteItem,
} from './mc'

// A blank editor draft for a new custom item.
const blankDraft = () => ({
  id: null,
  model_stem: '',
  base_item: '',
  count: 1,
  custom_name: blankFmt(''),
  lore: [],
  flags: '', // comma-separated custom_data flag names (advanced)
})

// Convert a saved item row → editor draft.
function itemToDraft(item) {
  return {
    id: item.id,
    model_stem: item.model_stem || '',
    base_item: item.base_item || '',
    count: item.count || 1,
    custom_name: { ...blankFmt(''), ...(item.custom_name || {}) },
    lore: (item.lore || []).map((l) => ({ ...blankFmt(''), ...l })),
    flags: Object.keys(item.custom_data || {}).join(', '),
  }
}

// Editor draft → the manifest row sent to the backend.
function draftToItem(d) {
  const flags = d.flags.split(',').map((s) => s.trim()).filter(Boolean)
  const custom_data = {}
  for (const f of flags) custom_data[f] = true
  return {
    name: d.custom_name.text || d.model_stem,
    model_stem: d.model_stem,
    base_item: d.base_item,
    count: Number(d.count) || 1,
    custom_name: d.custom_name,
    lore: d.lore.filter((l) => l.text),
    custom_data,
  }
}

// Live-search popover for picking a texture/model from the resource pack.
function TexturePicker({ models, value, onPick }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    const list = q ? models.filter((m) => m.stem.toLowerCase().includes(q)) : models
    return list.slice(0, 120)
  }, [models, query])

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 rounded-lg"
      >
        {value ? (
          <>
            <img src={textureUrl(value)} alt="" style={{ width: 20, height: 20, imageRendering: 'pixelated' }} />
            <span className="truncate">{value}</span>
          </>
        ) : (
          <span className="text-zinc-400">Choose a texture…</span>
        )}
        <Search size={14} className="ml-auto text-zinc-400 shrink-0" />
      </button>

      {open && (
        <div className="absolute z-40 mt-1 w-full bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg shadow-2xl p-2">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search textures…"
            className="w-full px-2 py-1.5 text-sm rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
          />
          <div className="mt-2 grid grid-cols-5 gap-1 max-h-64 overflow-auto">
            {results.map((m) => (
              <button
                key={m.stem}
                type="button"
                title={`${m.stem} (${m.base_item})`}
                onClick={() => { onPick(m); setOpen(false) }}
                className={`flex flex-col items-center gap-0.5 p-1 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors ${
                  value === m.stem ? 'bg-zinc-100 dark:bg-zinc-700' : ''
                }`}
              >
                <img src={textureUrl(m.stem)} alt="" loading="lazy"
                  style={{ width: 28, height: 28, imageRendering: 'pixelated' }} />
                <span className="text-[10px] leading-none truncate w-full text-center text-zinc-500 dark:text-zinc-400">
                  {m.stem}
                </span>
              </button>
            ))}
            {!results.length && (
              <p className="col-span-5 text-xs text-zinc-400 px-1 py-3 text-center">No textures match “{query}”.</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ItemLibrary() {
  const [models, setModels] = useState([])
  const [items, setItems] = useState([])
  const [draft, setDraft] = useState(blankDraft)
  const [status, setStatus] = useState('idle') // idle | saving | error
  const [error, setError] = useState('')

  useEffect(() => {
    fetchModels().then(setModels).catch((e) => setError(e.message))
    fetchItems().then(setItems).catch((e) => setError(e.message))
  }, [])

  const setName = (custom_name) => setDraft((d) => ({ ...d, custom_name }))
  const setLoreLine = (i, line) =>
    setDraft((d) => ({ ...d, lore: d.lore.map((l, j) => (j === i ? line : l)) }))
  const addLore = () => setDraft((d) => ({ ...d, lore: [...d.lore, blankFmt('')] }))
  const removeLore = (i) => setDraft((d) => ({ ...d, lore: d.lore.filter((_, j) => j !== i) }))

  const editItem = (item) => { setDraft(itemToDraft(item)); setError('') }
  const resetDraft = () => { setDraft(blankDraft()); setError('') }

  const canSave = draft.model_stem && (status !== 'saving')

  const save = async () => {
    setStatus('saving'); setError('')
    try {
      const payload = draftToItem(draft)
      const saved = draft.id ? await updateItem(draft.id, payload) : await createItem(payload)
      setItems((cur) => {
        const without = cur.filter((it) => it.id !== saved.id)
        return [saved, ...without]
      })
      resetDraft()
      setStatus('idle')
    } catch (e) {
      setError(e.message); setStatus('error')
    }
  }

  const remove = async (id) => {
    try {
      await deleteItem(id)
      setItems((cur) => cur.filter((it) => it.id !== id))
      if (draft.id === id) resetDraft()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h2 className="text-5xl leading-none">Item Library</h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-2">
          Create custom items with a texture, name, and lore. Drag them onto NPC choices to give them in dialogue.
        </p>
      </div>

      {error && (
        <div className="border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 text-sm rounded-xl px-4 py-3 font-mono">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ---- Editor ---- */}
        <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 space-y-4">
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">{draft.id ? 'Edit item' : 'New item'}</p>
            {draft.id && (
              <button onClick={resetDraft} className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200">
                + New item
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="space-y-1">
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Texture</span>
              <TexturePicker
                models={models}
                value={draft.model_stem}
                onPick={(m) => setDraft((d) => ({ ...d, model_stem: m.stem, base_item: m.base_item }))}
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Base item {draft.base_item && <span className="text-zinc-400">(auto)</span>}
              </span>
              <input
                value={draft.base_item}
                onChange={(e) => setDraft((d) => ({ ...d, base_item: e.target.value.trim() }))}
                placeholder="auto from texture"
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
              />
            </label>
          </div>

          {/* Name + format */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Item name</span>
            <div className="flex items-center gap-2">
              <input
                value={draft.custom_name.text}
                onChange={(e) => setName({ ...draft.custom_name, text: e.target.value })}
                placeholder="Excalibur"
                className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
              />
              <FormatToggles fmt={draft.custom_name} onChange={setName} />
            </div>
            <div className="w-40"><ColorPicker value={draft.custom_name.color} onChange={(c) => setName({ ...draft.custom_name, color: c })} /></div>
          </div>

          {/* Lore */}
          <div className="space-y-2">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Lore</span>
            {draft.lore.map((line, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  value={line.text}
                  onChange={(e) => setLoreLine(i, { ...line, text: e.target.value })}
                  placeholder={`Lore line ${i + 1}`}
                  className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
                />
                <div className="w-28"><ColorPicker value={line.color} onChange={(c) => setLoreLine(i, { ...line, color: c })} /></div>
                <FormatToggles fmt={line} onChange={(nf) => setLoreLine(i, nf)} />
                <button onClick={() => removeLore(i)} className="p-1.5 rounded-md text-zinc-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950">
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            <button onClick={addLore} className="flex items-center gap-1.5 text-xs font-medium text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200">
              <Plus size={14} /> Add lore line
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="space-y-1">
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Count</span>
              <input
                type="number" min={1} max={64}
                value={draft.count}
                onChange={(e) => setDraft((d) => ({ ...d, count: e.target.value }))}
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Custom-data flags <span className="text-zinc-400">(optional, comma-sep)</span></span>
              <input
                value={draft.flags}
                onChange={(e) => setDraft((d) => ({ ...d, flags: e.target.value }))}
                placeholder="rune1, boot1"
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
              />
            </label>
          </div>

          {/* Live preview slot */}
          <div className="flex items-center gap-3 pt-1">
            <span className="text-xs text-zinc-500 dark:text-zinc-400">Preview (hover):</span>
            <ItemSlot
              texture={draft.model_stem ? textureUrl(draft.model_stem) : null}
              name={draft.custom_name}
              lore={draft.lore}
            />
          </div>

          <button
            onClick={save}
            disabled={!canSave}
            className="flex items-center gap-2 px-5 py-2 border border-transparent bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <Save size={15} /> {status === 'saving' ? 'Saving…' : draft.id ? 'Update item' : 'Save item'}
          </button>
        </div>

        {/* ---- Library grid ---- */}
        <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4">
          <p className="text-sm font-semibold mb-3 flex items-center gap-1.5">
            <Package size={15} /> Saved items <span className="text-zinc-400 font-normal">({items.length})</span>
          </p>
          {items.length === 0 ? (
            <p className="text-xs text-zinc-400 py-8 text-center">No saved items yet. Create one on the left.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {items.map((item) => (
                <ItemSlot
                  key={item.id}
                  texture={textureUrl(item.model_stem)}
                  name={item.custom_name}
                  lore={item.lore}
                  title={item.name}
                >
                  <div className="absolute -top-1.5 -right-1.5 flex gap-0.5">
                    <button onClick={() => editItem(item)} title="Edit"
                      className="p-0.5 rounded bg-zinc-700 text-white hover:bg-zinc-600 shadow">
                      <Pencil size={11} />
                    </button>
                    <button onClick={() => remove(item.id)} title="Delete"
                      className="p-0.5 rounded bg-red-600 text-white hover:bg-red-500 shadow">
                      <X size={11} />
                    </button>
                  </div>
                </ItemSlot>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
