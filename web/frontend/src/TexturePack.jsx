import { useState, useEffect, useRef, useCallback } from 'react'
import { Upload, RefreshCw, Copy, Check, Search, X, Image as ImageIcon } from 'lucide-react'
import { fetchTextures, uploadTextures, syncTexturePack, textureThumbUrl } from './mc'

// Mirror the server's name derivation so the preview matches what gets written:
// lowercase, spaces -> _, drop the extension, strip anything but [a-z0-9_.-].
function deriveName(filename) {
  const stem = filename.replace(/\.[^.]+$/, '').trim().toLowerCase().replace(/ /g, '_')
  return stem.replace(/[^a-z0-9_.-]/g, '')
}

const PARENTS = [
  { key: 'generated', label: 'Flat (generated)', hint: 'Ingots, gems, most items' },
  { key: 'handheld', label: 'Handheld', hint: 'Swords, tools — held at an angle' },
]

export default function TexturePack() {
  const [parent, setParent] = useState('generated')
  const [overwrite, setOverwrite] = useState(true)
  const [staged, setStaged] = useState([]) // { file, url, name }
  const [uploading, setUploading] = useState(false)
  const [results, setResults] = useState(null)
  const [dragging, setDragging] = useState(false)

  const [existing, setExisting] = useState(null) // { textures, count } | null
  const [query, setQuery] = useState('')
  const [listErr, setListErr] = useState('')

  const [syncing, setSyncing] = useState(false)
  const [syncLink, setSyncLink] = useState('')
  const [syncErr, setSyncErr] = useState('')
  const [copied, setCopied] = useState(false)

  const inputRef = useRef(null)

  const loadList = useCallback(() => {
    setListErr('')
    fetchTextures()
      .then(setExisting)
      .catch((e) => setListErr(e.message || 'Failed to load textures'))
  }, [])

  useEffect(() => { loadList() }, [loadList])

  // Revoke object URLs on unmount / restage to avoid leaks.
  useEffect(() => () => staged.forEach((s) => URL.revokeObjectURL(s.url)), [staged])

  const addFiles = (fileList) => {
    const pngs = Array.from(fileList).filter(
      (f) => f.type === 'image/png' || f.name.toLowerCase().endsWith('.png')
    )
    const next = pngs.map((file) => ({ file, url: URL.createObjectURL(file), name: deriveName(file.name) }))
    setStaged((prev) => [...prev, ...next])
    setResults(null)
  }

  const removeStaged = (idx) => {
    setStaged((prev) => {
      URL.revokeObjectURL(prev[idx].url)
      return prev.filter((_, i) => i !== idx)
    })
  }

  const onDrop = (e) => {
    e.preventDefault()
    setDragging(false)
    if (e.dataTransfer.files?.length) addFiles(e.dataTransfer.files)
  }

  const doUpload = async () => {
    if (!staged.length) return
    setUploading(true)
    setResults(null)
    try {
      const res = await uploadTextures({ files: staged.map((s) => s.file), parent, overwrite })
      setResults(res)
      // Clear the ones that succeeded; keep failures staged for another go.
      const failed = new Set(res.results.filter((r) => r.status === 'error').map((r) => r.filename))
      setStaged((prev) => {
        prev.filter((s) => !failed.has(s.file.name)).forEach((s) => URL.revokeObjectURL(s.url))
        return prev.filter((s) => failed.has(s.file.name))
      })
      loadList()
    } catch (e) {
      setResults({ error: e.message || 'Upload failed', results: [] })
    } finally {
      setUploading(false)
    }
  }

  const doSync = async () => {
    setSyncing(true)
    setSyncErr('')
    setSyncLink('')
    try {
      const res = await syncTexturePack()
      setSyncLink(res.link)
    } catch (e) {
      setSyncErr(e.message || 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const copyLink = () => {
    navigator.clipboard.writeText(syncLink)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const filtered = existing?.textures.filter((n) => n.includes(query.toLowerCase())) ?? []

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-6">
      <header>
        <h1 className="text-5xl">Texture Pack</h1>
        <p className="text-sm text-zinc-400 mt-1">
          Upload custom item PNGs to the server pack, then sync to publish a new
          pack.zip for Apex to pull.
        </p>
      </header>

      {/* ---- Upload ------------------------------------------------------- */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-950 p-5 space-y-4">
        <div className="flex items-center justify-between gap-4 flex-wrap">
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500">Model type</span>
            <div className="flex rounded-lg border border-zinc-800 overflow-hidden">
              {PARENTS.map((p) => (
                <button
                  key={p.key}
                  title={p.hint}
                  onClick={() => setParent(p.key)}
                  className={`px-3 py-1.5 text-xs transition-colors ${
                    parent === p.key
                      ? 'bg-zinc-800 text-zinc-100'
                      : 'text-zinc-500 hover:text-zinc-300'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
          <label className="flex items-center gap-2 text-xs text-zinc-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
              className="accent-zinc-500"
            />
            Overwrite if name exists
          </label>
        </div>

        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => inputRef.current?.click()}
          className={`rounded-lg border-2 border-dashed p-8 text-center cursor-pointer transition-colors ${
            dragging ? 'border-zinc-500 bg-zinc-900' : 'border-zinc-800 hover:border-zinc-700'
          }`}
        >
          <Upload size={22} className="mx-auto text-zinc-500 mb-2" />
          <p className="text-sm text-zinc-400">Drop PNGs here, or click to choose</p>
          <p className="text-xs text-zinc-600 mt-1">
            The file name becomes the item name (e.g. <code>valhallasword.png</code> → <code>valhallasword</code>)
          </p>
          <input
            ref={inputRef}
            type="file"
            accept="image/png,.png"
            multiple
            hidden
            onChange={(e) => { addFiles(e.target.files); e.target.value = '' }}
          />
        </div>

        {staged.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
            {staged.map((s, i) => (
              <div key={i} className="relative rounded-lg border border-zinc-800 bg-zinc-900 p-2">
                <button
                  onClick={() => removeStaged(i)}
                  className="absolute top-1 right-1 p-0.5 rounded bg-zinc-800/80 text-zinc-400 hover:text-zinc-100"
                >
                  <X size={12} />
                </button>
                <img
                  src={s.url}
                  alt={s.name}
                  className="w-full aspect-square object-contain image-render-pixel bg-zinc-950 rounded"
                  style={{ imageRendering: 'pixelated' }}
                />
                <p className="mt-1 text-xs text-zinc-300 truncate" title={s.name}>{s.name || '—'}</p>
                {!s.name && <p className="text-[10px] text-red-400">invalid name</p>}
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={doUpload}
            disabled={uploading || !staged.length || staged.some((s) => !s.name)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-zinc-100 text-zinc-900 text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white transition-colors"
          >
            {uploading ? <RefreshCw size={15} className="animate-spin" /> : <Upload size={15} />}
            Upload {staged.length ? `(${staged.length})` : ''}
          </button>
          {results && !results.error && (
            <span className="text-xs text-zinc-400">
              {results.ok}/{results.total} uploaded
            </span>
          )}
        </div>

        {results?.error && <p className="text-xs text-red-400">{results.error}</p>}
        {results?.results?.some((r) => r.status === 'error') && (
          <ul className="text-xs text-red-400 space-y-0.5">
            {results.results.filter((r) => r.status === 'error').map((r, i) => (
              <li key={i}>{r.filename}: {r.error}</li>
            ))}
          </ul>
        )}
      </section>

      {/* ---- Sync --------------------------------------------------------- */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-950 p-5 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium">Sync</p>
            <p className="text-xs text-zinc-500 mt-0.5">
              Repack the pack into pack.zip and get the direct-download link for Apex.
            </p>
          </div>
          <button
            onClick={doSync}
            disabled={syncing}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-zinc-700 text-sm text-zinc-200 disabled:opacity-40 hover:bg-zinc-900 transition-colors"
          >
            <RefreshCw size={15} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Syncing…' : 'Sync now'}
          </button>
        </div>
        {syncErr && <p className="text-xs text-red-400">{syncErr}</p>}
        {syncLink && (
          <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900 p-2">
            <input
              readOnly
              value={syncLink}
              className="flex-1 bg-transparent text-xs text-zinc-300 outline-none px-1"
            />
            <button
              onClick={copyLink}
              className="inline-flex items-center gap-1 px-2 py-1 rounded bg-zinc-800 text-xs text-zinc-200 hover:bg-zinc-700"
            >
              {copied ? <Check size={13} /> : <Copy size={13} />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        )}
      </section>

      {/* ---- Existing textures ------------------------------------------- */}
      <section className="rounded-xl border border-zinc-800 bg-zinc-950 p-5 space-y-3">
        <div className="flex items-center justify-between gap-3">
          <p className="text-sm font-medium flex items-center gap-2">
            <ImageIcon size={15} className="text-zinc-500" />
            Current custom textures
            {existing && <span className="text-zinc-500 font-normal">({existing.count})</span>}
          </p>
          <div className="relative">
            <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-600" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter…"
              className="pl-7 pr-2 py-1 text-xs rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-200 outline-none focus:border-zinc-700 w-40"
            />
          </div>
        </div>
        {listErr && <p className="text-xs text-red-400">{listErr}</p>}
        {!existing && !listErr && <p className="text-xs text-zinc-600">Loading…</p>}
        {existing && (
          <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-6 gap-3 max-h-[30rem] overflow-auto pr-1">
            {filtered.length === 0 && <p className="text-xs text-zinc-600 col-span-full">No matches.</p>}
            {filtered.map((n) => (
              <div
                key={n}
                className="flex flex-col items-center rounded-lg border border-zinc-800 bg-zinc-900 p-2"
              >
                <img
                  src={textureThumbUrl(n)}
                  alt={n}
                  loading="lazy"
                  onError={(e) => { e.currentTarget.style.visibility = 'hidden' }}
                  className="w-full aspect-square object-contain bg-zinc-950 rounded"
                  style={{ imageRendering: 'pixelated' }}
                />
                <p className="mt-1.5 text-[11px] text-zinc-400 truncate w-full text-center" title={n}>
                  {n}
                </p>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
