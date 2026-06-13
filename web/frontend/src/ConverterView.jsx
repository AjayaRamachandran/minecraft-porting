import { useState, useRef, useCallback } from 'react'
import { CopyIcon, DownloadIcon, FileIcon } from './icons'

const API_BASE = ''

// The original command/schematic converter UI, unchanged except for being
// lifted into its own component so the app shell can host multiple tools.
export default function ConverterView() {
  const [mode, setMode] = useState('text')
  const [text, setText] = useState('')
  const [schemFile, setSchemFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [status, setStatus] = useState('idle')
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const fileInputRef = useRef(null)

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
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-5">
      <div>
        <h2 className="text-5xl leading-none">MC Command Converter</h2>
        <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-2">
          Converts 1.20.1 commands and schematics to 1.21.11 format
        </p>
      </div>

      {/* Mode tabs */}
      <div className="flex gap-1 bg-zinc-100 dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 p-1 rounded-lg w-fit">
        {[
          { key: 'text', label: 'Command Script' },
          { key: 'schem', label: 'Schematic File' },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => switchMode(key)}
            className={`px-4 py-1.5 text-sm rounded-md border border-transparent transition-all ${
              mode === key
                ? 'bg-white dark:bg-zinc-700 text-zinc-900 dark:text-zinc-100 font-medium border-zinc-200 dark:border-zinc-600'
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
                ? 'bg-zinc-500/20'
                : schemFile
                ? 'bg-zinc-500/5'
                : 'hover:bg-zinc-500/10'
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
                  Drop a <span className="bg-zinc-100 dark:bg-zinc-700 px-1 py-0.5 font-display">.schem</span> file here
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
        className="px-5 py-2 border border-transparent bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
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
                  className="flex items-center gap-2 px-4 py-2 border border-transparent bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 transition-colors"
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
    </div>
  )
}
