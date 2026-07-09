import { useState, useEffect, useMemo, useRef } from "react";
import {
  Trash2,
  X,
  Search,
  Save,
  Package,
  Pencil,
  Upload,
  Lock,
  Copy,
  Terminal,
} from "lucide-react";
import {
  ItemSlot,
  RichTextEditor,
  lineToComponent,
  plainText,
  textureUrl,
  resolveColor,
  manifestStem,
  manifestName,
  manifestLore,
  manifestTags,
  manifestExtraKeys,
  manifestLabel,
  manifestTextures,
  fetchModels,
  fetchItems,
  createItem,
  updateItem,
  deleteItem,
  importItems,
  giveCommand,
} from "./mc";

// The editor works on a structured manifest { base_item, components } plus a few
// surfaced fields. Name/lore/tags are editable; any other component rides along
// untouched in the manifest and is shown as locked "additional data".
const blankDraft = () => ({
  id: null,
  manifest: { base_item: "", components: {} },
  model_stem: "",
  base_item: "",
  name: [[]],
  lore: [[]],
  flags: "",
});

// Saved item row (with structured manifest) → editor draft.
function itemToDraft(item) {
  const m = item.manifest || { base_item: "", components: {} };
  const lore = manifestLore(m);
  return {
    id: item.id,
    manifest: m,
    model_stem: manifestStem(m) || "",
    base_item: m.base_item || "",
    name: [manifestName(m) || []],
    lore: lore.length ? lore.map((c) => [c]) : [[]],
    flags: manifestTags(m).join(", "),
  };
}

// Editor draft → structured manifest. Preserves every non-editable component
// from the original manifest, overwriting only name / lore / tags / item_model.
function draftToManifest(d) {
  const components = { ...(d.manifest.components || {}) };

  if (d.model_stem)
    components["minecraft:item_model"] = `minecraft:custom/${d.model_stem}`;

  const nameComp = lineToComponent(d.name[0] || []);
  if (plainText(nameComp)) components["minecraft:custom_name"] = nameComp;
  else delete components["minecraft:custom_name"];

  const lore = d.lore.map(lineToComponent).filter((c) => plainText(c));
  if (lore.length) components["minecraft:lore"] = lore;
  else delete components["minecraft:lore"];

  // Rebuild boolean flags, keeping any non-boolean custom_data entries intact.
  const flags = d.flags
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  const cd = { ...(components["minecraft:custom_data"] || {}) };
  for (const k of Object.keys(cd)) if (cd[k] === true) delete cd[k];
  for (const f of flags) cd[f] = true;
  if (Object.keys(cd).length) components["minecraft:custom_data"] = cd;
  else delete components["minecraft:custom_data"];

  return { base_item: d.base_item || "paper", components };
}

// Renders a texture image, cycling through frames if height is a multiple of width.
function AnimatedTexture({ src, size = 44 }) {
  const [nFrames, setNFrames] = useState(1);
  const [frame, setFrame] = useState(0);

  const onLoad = (e) => {
    const img = e.currentTarget;
    const n = img.naturalHeight / img.naturalWidth;
    if (Number.isInteger(n) && n > 1) setNFrames(n);
  };

  useEffect(() => {
    if (nFrames <= 1) return;
    const id = setInterval(() => setFrame((f) => (f + 1) % nFrames), 250);
    return () => clearInterval(id);
  }, [nFrames]);

  return (
    <div
      style={{
        width: size,
        height: size,
        overflow: "hidden",
        position: "relative",
        flexShrink: 0,
      }}
    >
      <img
        src={src}
        alt=""
        loading="lazy"
        onLoad={onLoad}
        style={{
          width: size,
          height: size * nFrames,
          position: "absolute",
          top: -frame * size,
          imageRendering: "pixelated",
        }}
      />
    </div>
  );
}

// Live-search popover for picking a texture/model from the resource pack.
function TexturePicker({ models, value, onPick, disabled }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const ref = useRef(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    return q ? models.filter((m) => m.stem.toLowerCase().includes(q)) : models;
  }, [models, query]);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-2 px-3 py-1.5 text-sm border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {value ? (
          <>
            <img
              src={textureUrl(value)}
              alt=""
              style={{ width: 20, height: 20, imageRendering: "pixelated" }}
            />
            <span className="truncate">{value}</span>
          </>
        ) : (
          <span className="text-zinc-400">Choose texture…</span>
        )}
        <Search size={14} className="ml-auto text-zinc-400 shrink-0" />
      </button>

      {open && !disabled && (
        <div className="absolute z-40 mt-1 w-[min(34rem,92vw)] bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg shadow-2xl p-3">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search textures…"
            className="w-full px-2 py-1.5 text-sm rounded-md border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
          />
          <div className="mt-2 grid grid-cols-6 gap-2 max-h-96 overflow-auto">
            {results.map((m) => (
              <button
                key={m.stem}
                type="button"
                title={`${m.stem} (${m.base_item})`}
                onClick={() => {
                  onPick(m);
                  setOpen(false);
                }}
                className={`flex flex-col items-center gap-0.5 p-1 rounded-md hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors ${
                  value === m.stem ? "bg-zinc-100 dark:bg-zinc-700" : ""
                }`}
              >
                <AnimatedTexture src={textureUrl(m.stem)} size={44} />
                <span className="text-[10px] leading-none truncate w-full text-center text-zinc-500 dark:text-zinc-400">
                  {m.stem}
                </span>
              </button>
            ))}
            {!results.length && (
              <p className="col-span-6 text-xs text-zinc-400 px-1 py-3 text-center">
                No textures match “{query}”.
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Modal for importing items from /give commands and/or a .schem file.
function ImportModal({ onClose, onImported }) {
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef(null);

  const run = async () => {
    setBusy(true);
    setError("");
    try {
      const items = await importItems({
        text: text.trim() || undefined,
        file: file || undefined,
      });
      onImported(items);
      onClose();
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl shadow-2xl p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-semibold">Import items</p>
          <button
            onClick={onClose}
            className="p-1 rounded-md text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-700"
          >
            <X size={16} />
          </button>
        </div>
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Paste one or more <code>/give</code> commands (one per line) and/or
          upload a <code>.schem</code> — every custom item found is parsed and
          saved to the library.
        </p>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={6}
          spellCheck={false}
          placeholder={
            '/give @p minecraft:diamond_sword[minecraft:custom_name=\'{"text":"Excalibur"}\'] 1'
          }
          className="w-full px-3 py-2 text-xs font-mono rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600 resize-y"
        />
        <div className="flex items-center gap-2">
          <button
            onClick={() => fileRef.current?.click()}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800"
          >
            <Upload size={14} /> {file ? file.name : "Choose .schem…"}
          </button>
          {file && (
            <button
              onClick={() => setFile(null)}
              className="text-xs text-zinc-400 hover:text-red-600"
            >
              clear
            </button>
          )}
          <input
            ref={fileRef}
            type="file"
            accept=".schem"
            className="hidden"
            onChange={(e) => setFile(e.target.files[0] || null)}
          />
        </div>
        {error && (
          <p className="text-xs text-red-600 dark:text-red-400 font-mono">
            {error}
          </p>
        )}
        <div className="flex items-center justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700"
          >
            Cancel
          </button>
          <button
            onClick={run}
            disabled={busy || (!text.trim() && !file)}
            className="px-4 py-1.5 border border-transparent bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 transition-colors"
          >
            {busy ? "Importing…" : "Import"}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function ItemLibrary() {
  const [models, setModels] = useState([]);
  const [items, setItems] = useState([]);
  const [draft, setDraft] = useState(blankDraft);
  const [status, setStatus] = useState("idle"); // idle | saving | error
  const [error, setError] = useState("");
  const [showImport, setShowImport] = useState(false);
  const [copiedId, setCopiedId] = useState(null);
  const [query, setQuery] = useState("");
  const editorRef = useRef(null);

  useEffect(() => {
    fetchModels()
      .then(setModels)
      .catch((e) => setError(e.message));
    fetchItems()
      .then(setItems)
      .catch((e) => setError(e.message));
  }, []);

  const setName = (lines) => setDraft((d) => ({ ...d, name: lines }));
  const setLore = (lines) => setDraft((d) => ({ ...d, lore: lines }));

  const editItem = (item) => {
    setDraft(itemToDraft(item));
    setError("");
    // The scroll container is <main>, not window — scroll the editor into view.
    editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  const resetDraft = () => {
    setDraft(blankDraft());
    setError("");
  };

  const canSave = (draft.model_stem || draft.base_item) && status !== "saving";

  // Components beyond name/lore/tags/texture — locked, shown as a chip.
  const extraKeys = manifestExtraKeys(draft.manifest);
  const hasAdditional = extraKeys.length > 0;
  const previewLore = draft.lore.filter((l) => plainText(l).length > 0);

  const filteredItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter(
      (it) =>
        manifestLabel(it.manifest).toLowerCase().includes(q) ||
        (it.manifest.base_item || "").toLowerCase().includes(q),
    );
  }, [items, query]);

  const save = async () => {
    setStatus("saving");
    setError("");
    try {
      const manifest = draftToManifest(draft);
      const saved = draft.id
        ? await updateItem(draft.id, manifest)
        : await createItem(manifest);
      setItems((cur) => [saved, ...cur.filter((it) => it.id !== saved.id)]);
      resetDraft();
      setStatus("idle");
    } catch (e) {
      setError(e.message);
      setStatus("error");
    }
  };

  const remove = async (id) => {
    try {
      await deleteItem(id);
      setItems((cur) => cur.filter((it) => it.id !== id));
      if (draft.id === id) resetDraft();
    } catch (e) {
      setError(e.message);
    }
  };

  const onImported = (newItems) => setItems((cur) => [...newItems, ...cur]);

  const copyGive = async (item) => {
    try {
      const cmd = await giveCommand(item.manifest);
      await navigator.clipboard.writeText(cmd);
      setCopiedId(item.id);
      setTimeout(() => setCopiedId((c) => (c === item.id ? null : c)), 1600);
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">
      {showImport && (
        <ImportModal
          onClose={() => setShowImport(false)}
          onImported={onImported}
        />
      )}

      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-5xl leading-none">Item Library</h2>
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mt-2">
            Create custom items with a texture, name, and lore. Highlight text
            to make it bold, italic, or colored. Drag items onto NPC choices to
            give them in dialogue.
          </p>
        </div>
        <button
          onClick={() => setShowImport(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-800 transition-colors shrink-0"
        >
          <Upload size={14} /> Import
        </button>
      </div>

      {error && (
        <div className="border border-red-200 dark:border-red-900 bg-red-50 dark:bg-red-950 text-red-700 dark:text-red-400 text-sm rounded-xl px-4 py-3 font-mono">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ---- Editor ---- */}
        <div
          ref={editorRef}
          className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 space-y-4 scroll-mt-4"
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold">
              {draft.id ? "Edit item" : "New item"}
            </p>
            {draft.id && (
              <button
                onClick={resetDraft}
                className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
              >
                + New item
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <label className="space-y-1">
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Texture
              </span>
              <TexturePicker
                models={models}
                value={draft.model_stem}
                disabled={hasAdditional}
                onPick={(m) =>
                  setDraft((d) => ({
                    ...d,
                    model_stem: m.stem,
                    base_item: m.base_item,
                  }))
                }
              />
            </label>
            <label className="space-y-1">
              <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
                Base item{" "}
                {draft.base_item && (
                  <span className="text-zinc-400">(auto)</span>
                )}
              </span>
              <input
                value={draft.base_item}
                disabled={hasAdditional}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, base_item: e.target.value.trim() }))
                }
                placeholder="auto from texture"
                className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600 disabled:opacity-50"
              />
            </label>
          </div>

          {/* Name — rich text, single line */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Item name
            </span>
            <RichTextEditor
              value={draft.name}
              onChange={setName}
              singleLine
              placeholder=""
              defaultItalic={true}
              defaultColor={resolveColor("white")}
            />
          </div>

          {/* Lore — rich text, one line per lore entry */}
          <div className="space-y-1">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Lore{" "}
              <span className="text-zinc-400">
                (press Enter for a new line)
              </span>
            </span>
            <RichTextEditor
              value={draft.lore}
              onChange={setLore}
              placeholder=""
              defaultItalic={true}
              defaultColor={resolveColor("light_purple")}
            />
          </div>

          <label className="space-y-1 block">
            <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
              Custom-data flags{" "}
              <span className="text-zinc-400">(optional, comma-sep)</span>
            </span>
            <input
              value={draft.flags}
              onChange={(e) =>
                setDraft((d) => ({ ...d, flags: e.target.value }))
              }
              placeholder="rune1, boot1"
              className="w-full px-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
            />
          </label>

          {/* Locked additional-data chip */}
          {hasAdditional && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-lg border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/40 text-xs text-amber-800 dark:text-amber-300">
              <Lock size={13} className="mt-0.5 shrink-0" />
              <span>
                Contains additional data ({extraKeys.length} component
                {extraKeys.length > 1 ? "s" : ""}) — preserved on save:
                <span className="font-mono">
                  {" "}
                  {extraKeys.map((k) => k.replace("minecraft:", "")).join(", ")}
                </span>
              </span>
            </div>
          )}

          {/* Live preview slot */}
          <div className="flex items-center gap-3 pt-1">
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              Preview (hover):
            </span>
            <ItemSlot
              texture={draft.model_stem ? textureUrl(draft.model_stem) : null}
              name={draft.name[0] || []}
              lore={previewLore}
            />
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <button
              onClick={save}
              disabled={!canSave}
              className="flex items-center gap-2 px-5 py-2 border border-transparent bg-zinc-900 dark:bg-zinc-100 text-white dark:text-zinc-900 text-sm font-medium rounded-lg hover:bg-zinc-700 dark:hover:bg-zinc-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Save size={15} />{" "}
              {status === "saving"
                ? "Saving…"
                : draft.id
                  ? "Update item"
                  : "Save item"}
            </button>
            {/* Copy /give for the current draft — works before the item is saved. */}
            <button
              onClick={() =>
                copyGive({
                  id: draft.id ?? "__draft__",
                  manifest: draftToManifest(draft),
                })
              }
              disabled={!canSave}
              title={
                copiedId === (draft.id ?? "__draft__")
                  ? "Copied!"
                  : "Copy /give command"
              }
              className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 text-zinc-600 dark:text-zinc-300 hover:bg-zinc-100 dark:hover:bg-zinc-700 transition-colors"
            >
              {copiedId === (draft.id ?? "__draft__") ? (
                <Copy size={14} />
              ) : (
                <Terminal size={14} />
              )}
              {copiedId === (draft.id ?? "__draft__") ? "Copied!" : "/give"}
            </button>
            {draft.id && (
              <button
                onClick={() => remove(draft.id)}
                className="flex items-center gap-1.5 px-3 py-2 text-sm rounded-lg border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950 transition-colors"
              >
                <Trash2 size={14} /> Delete
              </button>
            )}
          </div>
        </div>

        {/* ---- Library grid ---- */}
        <div className="bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-xl p-4 flex flex-col">
          <p className="text-sm font-semibold mb-3 flex items-center gap-1.5">
            <Package size={15} /> Saved items{" "}
            <span className="text-zinc-400 font-normal">({items.length})</span>
          </p>
          <div className="relative mb-3">
            <Search
              size={14}
              className="absolute left-2.5 top-1/2 -translate-y-1/2 text-zinc-400"
            />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search saved items…"
              className="w-full pl-8 pr-3 py-1.5 text-sm rounded-lg border border-zinc-200 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900 focus:outline-none focus:ring-2 focus:ring-zinc-300 dark:focus:ring-zinc-600"
            />
          </div>
          {items.length === 0 ? (
            <p className="text-xs text-zinc-400 py-8 text-center">
              No saved items yet. Create one on the left or import.
            </p>
          ) : filteredItems.length === 0 ? (
            <p className="text-xs text-zinc-400 py-8 text-center">
              No items match “{query}”.
            </p>
          ) : (
            <div className="grid grid-cols-5 gap-2 max-h-[28rem] overflow-y-auto pr-1">
              {filteredItems.map((item) => {
                const { texture, fallbackTexture } = manifestTextures(
                  item.manifest,
                );
                return (
                  <ItemSlot
                    key={item.id}
                    texture={texture}
                    fallbackTexture={fallbackTexture}
                    name={manifestName(item.manifest)}
                    lore={manifestLore(item.manifest)}
                    title={manifestLabel(item.manifest)}
                    onClick={() => editItem(item)}
                  />
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
