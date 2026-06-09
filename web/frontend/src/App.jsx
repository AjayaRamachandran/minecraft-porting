import { useState, useRef, useCallback, useEffect } from 'react'

const API_BASE = ''

function SunIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="5" />
      <line x1="12" y1="1" x2="12" y2="3" /><line x1="12" y1="21" x2="12" y2="23" />
      <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" /><line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
      <line x1="1" y1="12" x2="3" y2="12" /><line x1="21" y1="12" x2="23" y2="12" />
      <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" /><line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
    </svg>
  )
}

function MoonIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  )
}

function CopyIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function FileIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-zinc-400 dark:text-zinc-500">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  )
}

export default function App() {
  const [dark, setDark] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
  )
  const [mode, setMode] = useState('text')
  const [text, setText] = useState('')
  const [schemFile, setSchemFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const fileInputRef = useRef(null)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f?.name.endsWith('.schem')) setSchemFile(f)
  }, [])

  const handleDragOver = useCallback((e) => {
    e.preventDefault()
    setDragging(true)
  }, [])

  const handleDragLeave = useCallback((e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setDragging(false)
  }, [])

  const canConvert = mode === 'text' ? text.trim().length > 0 : schemFile !== null

  const handleConvert = async () => {
    setStatus('loading')
    setResult(null)
    setError('')
    setCopied(false)

    const body = new FormData()
    if (mode === 'text') {
      body.append('text', text)
    } else {
      body.append('file', schemFile)
    }

    try {
      const res = await fetch(`${API_BASE}/api/convert`, { method: 'POST', body })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || 'Conversion failed')
      setResult(data)
      setStatus('done')
    } catch (err) {
      setError(err.message)
      setStatus('error')
    }
  }

  const handleDownload = () => {
    if (!result?.is_binary) return
    const bytes = atob(result.content)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i)
    const blob = new Blob([arr], { type: 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = result.filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleCopy = async () => {
    await navigator.clipboard.writeText(result?.content || '')
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const switchMode = (m) => {
    setMode(m)
    setStatus('idle')
    setResult(null)
    setError('')
  }

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 antialiased transition-colors">
      {/* Header */}
      <header className="border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-base font-semibold tracking-tight">MC Command Converter</h1>
            <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-0.5">
              Converts 1.20.1 commands and schematics to 1.21.11 format
            </p>
          </div>
          <button
            onClick={() => setDark(d => !d)}
            className="p-2 rounded-lg text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors"
            aria-label="Toggle dark mode"
          >
            {dark ? <SunIcon /> : <MoonIcon />}
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-5">

        {/* Mode tabs */}
        <div className="flex gap-1 bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 p-1 rounded-lg w-fit">
          {[
            { key: 'text', label: 'Command Script' },
            { key: 'schem', label: 'Schematic File' },
          ].map(({ key, label }) => (
            <button
              key={key}
              onClick={() => switchMode(key)}
              className={`px-4 py-1.5 text-sm rounded-md transition-all ${
                mode === key
                  ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 font-medium shadow-sm border border-zinc-200 dark:border-zinc-600'
                  : 'text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Input panel */}
        <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl overflow-hidden">
          {mode === 'text' ? (
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste your .mcfunction commands here…"
              rows={14}
              spellCheck={false}
              className="w-full px-4 py-3 text-sm font-mono bg-white dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 focus:outline-none resize-y block placeholder-zinc-300 dark:placeholder-zinc-600"
            />
          ) : (
            <div
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className={`flex flex-col items-center justify-center gap-3 px-8 py-20 cursor-pointer select-none transition-colors ${
                dragging
                  ? 'bg-zinc-100 dark:bg-zinc-700'
                  : schemFile
                  ? 'bg-zinc-50 dark:bg-zinc-800'
                  : 'hover:bg-zinc-50 dark:hover:bg-zinc-750'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".schem"
                className="hidden"
                onChange={(e) => setSchemFile(e.target.files[0] || null)}
              />
              <FileIcon />
              {schemFile ? (
                <div className="text-center">
                  <p className="text-sm font-medium text-zinc-800 dark:text-zinc-200">{schemFile.name}</p>
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">
                    {(schemFile.size / 1024).toFixed(1)} KB · click to change
                  </p>
                </div>
              ) : (
                <div className="text-center">
                  <p className="text-sm text-zinc-600 dark:text-zinc-400">
                    Drop a <code className="font-mono bg-zinc-100 dark:bg-zinc-700 px-1 py-0.5 rounded text-xs">.schem</code> file here
                  </p>
                  <p className="text-xs text-zinc-400 dark:text-zinc-500 mt-1">or click to browse</p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Convert button */}
        <button
          onClick={handleConvert}
          disabled={!canConvert || status === 'loading'}
          className="px-5 py-2 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {status === 'loading' ? (
            <span className="flex items-center gap-2">
              <span className="inline-block w-3.5 h-3.5 border-2 border-white/30 dark:border-zinc-900/30 border-t-white dark:border-t-zinc-900 rounded-full animate-spin" />
              Converting…
            </span>
          ) : 'Convert'}
        </button>

        {/* Error */}
        {status === 'error' && (
          <div className="border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 text-sm rounded-xl px-4 py-3 font-mono">
            {error}
          </div>
        )}

        {/* Result */}
        {status === 'done' && result && (
          <div className="space-y-3">
            <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl overflow-hidden">
              <div className="flex items-center justify-between px-4 py-2.5 border-b border-zinc-100 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900">
                <span className="text-xs font-mono text-zinc-500 dark:text-zinc-400">{result.filename}</span>
                {result.is_binary ? (
                  <button
                    onClick={handleDownload}
                    className="flex items-center gap-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
                  >
                    <DownloadIcon />
                    Download
                  </button>
                ) : (
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-1.5 text-xs font-medium text-zinc-700 dark:text-zinc-300 hover:text-zinc-900 dark:hover:text-zinc-100 transition-colors"
                  >
                    <CopyIcon />
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                )}
              </div>

              {result.is_binary ? (
                <div className="px-4 py-10 flex flex-col items-center gap-3">
                  <p className="text-sm text-zinc-500 dark:text-zinc-400">Schematic converted successfully.</p>
                  <button
                    onClick={handleDownload}
                    className="flex items-center gap-2 px-4 py-2 bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 transition-colors"
                  >
                    <DownloadIcon />
                    Download {result.filename}
                  </button>
                </div>
              ) : (
                <pre className="px-4 py-3 text-xs font-mono text-zinc-800 dark:text-zinc-200 overflow-auto max-h-96 leading-relaxed whitespace-pre-wrap break-all">
                  {result.content}
                </pre>
              )}
            </div>

            {result.warnings?.length > 0 && (
              <div className="border border-amber-200 dark:border-amber-900 bg-amber-50 dark:bg-amber-950 rounded-xl px-4 py-3 space-y-1.5">
                <p className="text-xs font-semibold text-amber-800 dark:text-amber-400">
                  {result.warnings.length} warning{result.warnings.length !== 1 ? 's' : ''}
                </p>
                <ul className="space-y-1">
                  {result.warnings.map((w, i) => (
                    <li key={i} className="text-xs text-amber-700 dark:text-amber-500 font-mono leading-relaxed">{w}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  )
}
