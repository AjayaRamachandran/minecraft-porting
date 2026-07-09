import { useState, useEffect } from 'react'
import { RefreshCw, Bot, Package, Store } from 'lucide-react'
import { SunIcon, MoonIcon } from './icons'
import ConverterView from './ConverterView'
import NpcMaker from './NpcMaker'
import VillagerMaker from './VillagerMaker'
import ItemLibrary from './ItemLibrary'

// Left-rail tools. This is the top hierarchical level — one above the
// page-level horizontal tabs inside the converter (Command vs Schematic).
const TOOLS = [
  { key: 'converter', label: 'Converter', icon: RefreshCw, Component: ConverterView },
  { key: 'npc', label: 'NPC Maker', icon: Bot, Component: NpcMaker },
  { key: 'villager', label: 'Villager Maker', icon: Store, Component: VillagerMaker },
  { key: 'items', label: 'Item Library', icon: Package, Component: ItemLibrary },
]

export default function App() {
  const [dark, setDark] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches
  )
  const [tool, setTool] = useState(() => {
    const seg = window.location.pathname.replace(/^\//, '').split('/')[0]
    return TOOLS.find((t) => t.key === seg) ? seg : 'converter'
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])

  const navigate = (key) => {
    setTool(key)
    window.history.pushState({ tool: key }, '', `/${key}`)
  }

  useEffect(() => {
    // Keep URL in sync on first render (e.g. landing on /)
    window.history.replaceState({ tool }, '', `/${tool}`)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onPopState = (e) => {
      const key = e.state?.tool
      if (key && TOOLS.find((t) => t.key === key)) setTool(key)
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  const Active = TOOLS.find((t) => t.key === tool).Component

  return (
    <div className="h-screen overflow-hidden flex bg-zinc-50 dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100 antialiased transition-colors">
      {/* Left rail (Jira-style vertical tabs) */}
      <aside className="w-52 shrink-0 border-r border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 flex flex-col">
        <div className="px-4 py-4 border-b border-zinc-200 dark:border-zinc-800">
          <h1 className="text-3xl leading-none">MC Toolkit</h1>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">1.21.11 utilities</p>
        </div>
        <nav className="flex-1 p-2 space-y-1">
          {TOOLS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => navigate(key)}
              className={`w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-lg transition-colors ${
                tool === key
                  ? 'bg-zinc-100 dark:bg-zinc-800 text-zinc-900 dark:text-zinc-100 font-medium'
                  : 'text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-900'
              }`}
            >
              <Icon size={16} />
              {label}
            </button>
          ))}
        </nav>
        <div className="p-2 border-t border-zinc-200 dark:border-zinc-800">
          <button
            onClick={() => setDark((d) => !d)}
            className="w-full flex items-center gap-2.5 px-3 py-2 text-sm rounded-lg text-zinc-500 dark:text-zinc-400 hover:text-zinc-800 dark:hover:text-zinc-200 hover:bg-zinc-50 dark:hover:bg-zinc-900 transition-colors"
            aria-label="Toggle dark mode"
          >
            {dark ? <SunIcon /> : <MoonIcon />}
            {dark ? 'Light mode' : 'Dark mode'}
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Active />
      </main>
    </div>
  )
}
