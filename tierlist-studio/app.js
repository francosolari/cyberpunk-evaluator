/* Tier List Studio — Cyberpunk TCG tier list & deck page slide maker.
 * Plain JS, no build step. Card data comes from the Cyberpunk TCG Sim public catalog
 * (the same /api/cards/catalog the cyberpunk-tcg-tracker uses). Decks come from deck exports. */
'use strict';

const STORE_KEY = 'cp-tierlist-studio-v2';
const SIM_ORIGIN = 'https://cyberpunk-tcg-sim.online';
const CATALOG_URL = `${SIM_ORIGIN}/api/cards/catalog`;
const LEADERBOARD_URL = `${SIM_ORIGIN}/api/ranked/leaderboard`;
const STAGE_W = 1920, STAGE_H = 1080;
const CATALOG_SCHEMA = 2; // 2 added rules text; older saved catalogs are refreshed once
const CARD_ASPECT = 0.716;          // card width / height
const TILE_ASPECT = 0.74;           // deck tile width / height (art + caption)
// Crop = the card's art window (top/bottom, % of card height) + focus point + extra zoom.
// Layouts scale the card so only the art window is visible, so the rules text never shows.
// Card frame: the name and subtitle end around 17% of the image height and rules text starts
// near 62%; faces usually sit at 22–30%, so the focus aims there.
const DEFAULT_CROP = { top: 18, bottom: 62, x: 50, y: 28, zoom: 1 };
const OLD_DEFAULT_CROPS = ['15/61', '22/62', '29/62', '23/62'];
const COLORS = {
  R: { name: 'Red', hex: '#ff4655' },
  Y: { name: 'Yellow', hex: '#f7d046' },
  G: { name: 'Green', hex: '#3ddc97' },
  B: { name: 'Blue', hex: '#3fa7ff' },
};
const COLOR_ORDER = ['R', 'Y', 'G', 'B'];
const TIER_PALETTE = ['#ff4d6d', '#ff9f1c', '#f7d046', '#3ddc97', '#3fa7ff', '#a78bfa', '#94a3b8'];
const TIER_PRESETS = {
  'Tier 1 / 2 / Rogue': [['Tier 1', 'Most relevant threats\nGreat picks\nLikely to win events'], ['Tier 2', 'Threats to consider\nGood picks\nCan win events'], ['Rogue', 'Outside usual prep\nSpicy picks']],
  'S / A / B / C': [['S', 'Format-defining'], ['A', 'Top contenders'], ['B', 'Solid choices'], ['C', 'Niche or fringe']],
  'Tier 0 – 3': [['Tier 0', 'Best deck'], ['Tier 1', 'Top threats'], ['Tier 2', 'Contenders'], ['Tier 3', 'Playable']],
};
const DISPLAY_MODES = {
  legends: 'Legends (strips)',
  'legends-bands': 'Legends (bands)',
  'key-art': 'Key card (art)',
  split: 'Key card + Legends',
  'key-full': 'Key card (full card)',
};

/* ---------------- utils ---------------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const uid = () => Math.random().toString(36).slice(2, 10);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clone = (o) => JSON.parse(JSON.stringify(o));
const norm = (s) => String(s ?? '').toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '');

function toast(msg, ms = 3200) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), ms);
}

function colorCode(v) {
  const s = String(Array.isArray(v) ? v[0] : v ?? '').trim().toLowerCase();
  return { red: 'R', yellow: 'Y', green: 'G', blue: 'B', r: 'R', y: 'Y', g: 'G', b: 'B' }[s] || '';
}

/* ---------------- placeholder art (demo only) ---------------- */
function placeholderArt(name, color, kind) {
  const hex = COLORS[color]?.hex || '#777';
  const initials = name.split(' ').map((w) => w[0]).join('').slice(0, 3);
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="630" height="880" viewBox="0 0 630 880">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${hex}"/><stop offset="1" stop-color="#0b0d12"/></linearGradient>
  <pattern id="p" width="22" height="22" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><rect width="11" height="22" fill="#ffffff0d"/></pattern></defs>
  <rect width="630" height="880" rx="26" fill="#0c0c0c"/>
  <rect x="18" y="18" width="594" height="540" rx="14" fill="url(#g)"/><rect x="18" y="18" width="594" height="540" rx="14" fill="url(#p)"/>
  <circle cx="315" cy="300" r="${kind === 'legend' ? 120 : 90}" fill="#ffffff1c" stroke="#ffffff55" stroke-width="5"/>
  <text x="315" y="325" font-family="Arial Black,Arial" font-size="74" text-anchor="middle" fill="#fff">${esc(initials)}</text>
  <rect x="18" y="18" width="594" height="110" rx="14" fill="#00000066"/>
  <text x="315" y="84" font-family="Arial" font-weight="bold" font-size="34" text-anchor="middle" fill="#fff">${esc(name.toUpperCase())}</text>
  <rect x="18" y="566" width="594" height="296" rx="14" fill="#16181d"/>
  <text x="44" y="618" font-family="Arial" font-size="22" fill="#9aa">${kind === 'legend' ? 'LEGEND' : 'CARD'} · DEMO PLACEHOLDER</text>
  ${[0, 1, 2, 3].map((i) => `<rect x="44" y="${650 + i * 40}" width="${500 - i * 80}" height="14" rx="7" fill="#2a2d33"/>`).join('')}
</svg>`;
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

/* ---------------- sample decks ---------------- */
// Real decks used to populate a fresh project once card data loads. The two starters are the
// sim's public starter lists (as used by cyberpunk-tcg-tracker); entries may be card ids or names.
const SAMPLE_DECKS = [
  `# Name: Heist Tempo
#L
1x v_corporate_exile
1x viktor_vektor_sit_down_and_relax
1x jackie_welles_pour_one_out_for_me
#D
2x dexter_deshawn_one_last_chance
2x heywood_ripperdoc
2x offduty_malfini
2x secondhand_bombus
2x t_bug_amateur_philosopher
3x kiroshi_optics
3x mandibular_upgrade
3x zetatech_faceplate
2x afterparty_at_lizzie_s
3x delamain_cab
3x evelyn_parker_scheming_siren
2x mt0d12_flathead
2x psycho_squad
2x dying_night_v_s_pistol
2x tetratronic_rippler
3x floor_it
2x reboot_optics`,
  `# Name: Arasaka Steel
#L
1x goro_takemura_hands_unclean
1x yorinobu_arasaka_embracing_destruction
1x saburo_arasaka_stubborn_patriarch
#D
2x chrome_fang
2x minotaur
3x ruthless_lowlife
2x swordwise_huscle
2x emergency_atlus
2x field_operator
2x goro_takemura_losing_his_way
2x maxtac_av
2x arasaka_emergency_radioport
3x mantis_blades
3x satori_sword_of_saburo
2x industrial_assembly
2x over_the_edge
2x shattered_memories
3x corpo_security
3x sandevistan
3x corporate_surveillance`,
  `# Name: Geary Noble Safety
#L
1x Panam Palmer
1x River Ward
1x Muamar Reyes`,
];
const SAMPLE_NOTES = {
  'Heist Tempo': 'Sample: the sim\'s public starter list.\nReplace with your own export any time.',
  'Arasaka Steel': 'Sample: the sim\'s public starter list.',
};

/** Replaces the placeholder demo with real sample decks (and ranked meta trios, if reachable). */
async function applySamples() {
  if (!state.catalog || !state.decks.some(isDemoDeck)) return false;
  const decks = SAMPLE_DECKS.map(parseDeckExport).filter((d) => d.legends.filter(Boolean).length === 3);
  decks.forEach((d) => { d.notes = SAMPLE_NOTES[d.name] || ''; d.sample = true; });
  try {
    const r = await fetch(LEADERBOARD_URL, { credentials: 'omit' });
    if (r.ok) {
      for (const t of topTrios(await r.json(), 14)) {
        if (decks.some((d) => d.legends.slice().sort().join('+') === t.key)) continue;
        const d = newDeck({ legends: t.key.split('+'), notes: `${t.games} ranked games on the sim leaderboard`, sample: true });
        if (d.legends.every(card)) { d.name = d.legends.map((id) => card(id).name.split(',')[0].split(' ')[0]).join(' · '); decks.push(d); }
      }
    }
  } catch { /* leaderboard is optional */ }
  if (!decks.length) return false;
  const gone = new Set(state.decks.filter(isDemoDeck).map((d) => d.id));
  state.decks = [...state.decks.filter((d) => !gone.has(d.id)), ...decks];
  state.custom = state.custom.filter((c) => !c.demo);
  rebuildIndex(); nameIndex = null;
  // Spread the samples over the demo tier list so it opens fully populated.
  const tierSlide = state.slides.find((x) => x.type === 'tier');
  if (tierSlide) {
    tierSlide.showNames = true;
    const order = [...decks.slice(3), ...decks.slice(0, 3)]; // ranked trios first, starters lower
    const sizes = [4, 5, 4];
    let i = 0;
    tierSlide.tiers.forEach((t, k) => { t.deckIds = order.slice(i, i + (sizes[k] ?? 4)).map((d) => d.id); i += sizes[k] ?? 4; });
  }
  state.slides = state.slides.filter((x) => x.type !== 'deck' || !gone.has(x.deckId));
  const heist = decks.find((d) => d.name === 'Heist Tempo') || decks[0];
  state.slides.push({ id: uid(), type: 'deck', name: 'Deck: ' + heist.name, deckId: heist.id });
  save();
  return true;
}
function topTrios(json, n) {
  const trios = {};
  for (const row of Array.isArray(json?.standings) ? json.standings : []) {
    const ids = (row?.mostPlayedArchetype?.legends || []).map((l) => l?.id).filter((id) => typeof id === 'string');
    if (ids.length !== 3) continue;
    const key = [...new Set(ids)].sort().join('+');
    trios[key] = (trios[key] || 0) + Math.max(1, row.mostPlayedArchetype.games || 1);
  }
  return Object.entries(trios).sort((a, b) => b[1] - a[1]).slice(0, n).map(([key, games]) => ({ key, games }));
}

/* ---------------- demo project ---------------- */
function makeDemo() {
  const custom = [];
  const legendsBy = {};
  const keyBy = {};
  for (const c of COLOR_ORDER) {
    legendsBy[c] = ['A', 'B', 'C'].map((s) => {
      const name = `${COLORS[c].name} Legend ${s}`;
      const card = { id: 'demo_' + norm(name), name, type: 'Legend', color: c, img: placeholderArt(name, c, 'legend'), demo: true };
      custom.push(card);
      return card.id;
    });
    const name = `${COLORS[c].name} Key Card`;
    custom.push({ id: 'demo_' + norm(name), name, type: 'Unit', color: c, img: placeholderArt(name, c, 'card'), demo: true });
    keyBy[c] = 'demo_' + norm(name);
  }
  const mkDeck = (code) => {
    const used = {};
    const legends = code.split('').map((l) => { used[l] = (used[l] || 0) + 1; return legendsBy[l][used[l] - 1]; });
    return newDeck({ name: code, legends, keyCard: keyBy[code[0]], main: [[keyBy[code[0]], 3]] });
  };
  const decks = ['RRG', 'YYR', 'BBG', 'RRB', 'RRY', 'YYB', 'YYG', 'GGY', 'BBY', 'YYY', 'GGB'].map(mkDeck);
  const id = (n) => decks.find((d) => d.name === n).id;
  const tiers = TIER_PRESETS['Tier 1 / 2 / Rogue'].map(([name, desc], i) => ({ id: uid(), name, desc, color: [TIER_PALETTE[2], TIER_PALETTE[4], TIER_PALETTE[5]][i], deckIds: [] }));
  tiers[0].deckIds = ['RRG', 'YYR', 'BBG', 'RRB'].map(id);
  tiers[1].deckIds = ['RRY', 'YYB', 'YYG', 'GGY', 'BBY'].map(id);
  tiers[2].deckIds = ['YYY', 'GGB'].map(id);
  return {
    version: 2,
    catalog: null,
    custom,
    crops: {},
    legendCrop: {},
    decks,
    slides: [
      { id: uid(), type: 'tier', name: 'Weekly Tier List', title: 'Weekly Tier List', eyebrow: 'Plus Two', pill: 'Beta Format · Oct 2026', footnote: '', logo: '', display: 'legends', showNames: false, tiers },
      { id: uid(), type: 'deck', name: 'Deck: RRG', deckId: id('RRG') },
    ],
  };
}
function newDeck(p = {}) {
  return { id: uid(), name: '', label: '', subtitle: '', legends: [null, null, null], keyCard: null, main: [], side: [], notes: '', display: 'inherit', ...p };
}

/* ---------------- state ---------------- */
let state = load() || makeDemo();
const ui = { view: 'slides', slideId: state.slides[0]?.id, deckId: state.decks[0]?.id, selectedDeck: null };
let cardIndex = new Map();
// Projects saved with an earlier default crop pick up the current one.
if (state.legendCrop && OLD_DEFAULT_CROPS.includes(`${state.legendCrop.top}/${state.legendCrop.bottom}`)) state.legendCrop = {};
rebuildIndex();

function load() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}
function save() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
  catch { toast('Browser storage is full. Save the project as .json and use image URLs instead of uploads.', 6000); }
}

/* ---------------- cards & catalog ---------------- */
function rebuildIndex() {
  cardIndex = new Map();
  for (const c of state.catalog?.cards || []) cardIndex.set(c.id, c);
  for (const c of state.custom || []) cardIndex.set(c.id, c);
}
const card = (id) => (id ? cardIndex.get(id) || null : null);
const allCards = () => [...cardIndex.values()];
const isLegend = (c) => /legend/i.test(c?.type || '');
const cropOf = (c) => ({ ...DEFAULT_CROP, ...(isLegend(c) ? state.legendCrop : {}), ...(state.crops[c?.id] || {}) });
const deck = (id) => state.decks.find((d) => d.id === id) || null;
const slide = (id = ui.slideId) => state.slides.find((s) => s.id === id) || null;

/** Parses the sim catalog ({cards:[…]}) into compact records. Image paths are relative to the sim. */
function parseCatalog(json, origin = SIM_ORIGIN) {
  const list = Array.isArray(json?.cards) ? json.cards : Array.isArray(json) ? json : [];
  const seen = new Set();
  const out = [];
  for (const c of list) {
    const id = c?.id;
    const name = c?.display_name || c?.name;
    if (typeof id !== 'string' || typeof name !== 'string' || seen.has(id)) continue;
    seen.add(id);
    const path = c.assets?.image_url || c.image_url || c.image || '';
    const codes = Object.entries(c).filter(([k, v]) => typeof v === 'string' && /number|code|collector/i.test(k) && /^[a-z]{0,4}-?\d{1,4}[a-z]?$/i.test(v)).map(([, v]) => v);
    out.push({
      id, name,
      type: typeof c.card_type === 'string' ? c.card_type : '',
      color: colorCode(c.color),
      cost: Number.isFinite(c.cost) ? c.cost : null,
      ram: Number.isFinite(c.ram) ? c.ram : null,
      img: !path ? '' : /^(https?:|data:)/.test(path) ? path : path.startsWith('/') ? origin + path : path,
      page: c.source?.card_page_url || '',
      text: typeof c.rules_text === 'string' ? c.rules_text.slice(0, 800) : '',
      codes,
    });
  }
  return out;
}

async function loadCatalogFromSim() {
  const r = await fetch(CATALOG_URL, { headers: { Accept: 'application/json' }, credentials: 'omit' });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return applyCatalog(await r.json(), 'Cyberpunk TCG Sim');
}
function applyCatalog(json, from) {
  const cards = parseCatalog(json);
  if (!cards.length) throw new Error('No cards found in that JSON.');
  state.catalog = { schema: CATALOG_SCHEMA, from, at: new Date().toISOString(), revision: String(json?.cardPoolRevision ?? ''), cards };
  rebuildIndex();
  nameIndex = null;
  relinkDecks();
  save();
  return cards.length;
}
/** After a catalog loads, resolve deck lines that didn't match a card before. */
function relinkDecks() {
  for (const d of state.decks) {
    d.unmatched = (d.unmatched || []).filter((u) => {
      const id = resolveCard(u.name);
      if (!id) return true;
      if (u.section === 'legend' || isLegend(card(id))) {
        const free = d.legends.indexOf(null);
        if (free >= 0 && !d.legends.includes(id)) d.legends[free] = id;
      } else (u.section === 'side' ? d.side : d.main).push([id, u.qty]);
      return false;
    });
    if (!d.keyCard) d.keyCard = suggestKeyCard(d);
  }
}

/* ---------------- deck export parsing ---------------- */
let nameIndex = null;
function buildNameIndex() {
  nameIndex = { exact: new Map(), list: [] };
  for (const c of allCards()) {
    for (const k of [c.name, c.id, ...(c.codes || [])]) if (k) nameIndex.exact.set(norm(k), c.id);
    nameIndex.list.push([norm(c.name), c.id]);
  }
}
function resolveCard(name) {
  if (!nameIndex) buildNameIndex();
  const n = norm(name);
  if (!n) return null;
  if (nameIndex.exact.has(n)) return nameIndex.exact.get(n);
  // "Panam Palmer" vs "Panam Palmer, Nomad Cavalry": accept a unique prefix match either way
  const hits = nameIndex.list.filter(([k]) => k.startsWith(n) || n.startsWith(k));
  return hits.length === 1 ? hits[0][1] : null;
}

function decodeB64Deck(text) {
  const m = text.match(/[?&#]b64deck=([A-Za-z0-9_\-+/=%]+)/);
  if (!m) return null;
  let b = decodeURIComponent(m[1]).replace(/-/g, '+').replace(/_/g, '/');
  while (b.length % 4) b += '=';
  const bin = atob(b);
  return new TextDecoder().decode(Uint8Array.from(bin, (ch) => ch.charCodeAt(0)));
}

/** Accepts sim text exports (# Name / #L / #D / #S), official "Text List" style lists, import links, or JSON. */
function parseDeckExport(raw) {
  let text = String(raw || '').trim();
  const fromLink = decodeB64Deck(text);
  if (fromLink) text = fromLink.trim();
  const entries = [];
  let name = '';
  if (/^[[{]/.test(text)) {
    try {
      const j = JSON.parse(text);
      name = j.name || j.title || j.deckName || '';
      const walk = (v, section) => {
        if (Array.isArray(v)) v.forEach((x) => walk(x, section));
        else if (v && typeof v === 'object') {
          const nm = v.name || v.title || v.card || v.id || v.cardId || v.card_id;
          const qty = v.count ?? v.quantity ?? v.qty ?? v.copies;
          if (typeof nm === 'string' && (qty != null || section)) entries.push({ section: section || 'main', qty: Number(qty) || 1, name: nm });
          else for (const [k, x] of Object.entries(v)) walk(x, /legend/i.test(k) ? 'legend' : /side/i.test(k) ? 'side' : /main|deck|cards/i.test(k) ? 'main' : section);
        }
      };
      walk(j, null);
    } catch { /* not JSON: fall through to text */ }
  }
  if (!entries.length) {
    let section = 'main';
    for (let line of text.split(/\r?\n/)) {
      line = line.trim();
      if (!line) continue;
      const nm = line.match(/^(?:#|\/\/)\s*(?:deck\s*)?name\s*[:=]\s*(.+)$/i) || line.match(/^name\s*[:=]\s*(.+)$/i);
      if (nm) { name = nm[1].trim(); continue; }
      const head = line.replace(/^(#+|\/\/)\s*/, '').replace(/[:\s]*(\(\d+\))?\s*$/, '').toLowerCase();
      if (/^(l|legends?)$/.test(head)) { section = 'legend'; continue; }
      if (/^(d|deck|main|main ?deck|cards|units|gear|programs?)$/.test(head)) { section = 'main'; continue; }
      if (/^(s|side|sideboard)$/.test(head)) { section = 'side'; continue; }
      if (/^(#|\/\/)/.test(line)) continue;
      const m = line.match(/^(\d+)\s*[x×]?\s+(.+)$/i) || line.match(/^(.+?)\s+[x×]\s*(\d+)$/i) || line.match(/^(.+?)\s+(\d+)$/);
      let qty = 1, nmText = line;
      if (m) { if (/^\d+$/.test(m[1])) { qty = +m[1]; nmText = m[2]; } else { nmText = m[1]; qty = +m[2]; } }
      entries.push({ section, qty, name: nmText.replace(/\s*\[[^\]]*\]\s*$/, '').trim() });
    }
  }
  buildNameIndex();
  const d = newDeck({ name: name || '' });
  const add = (list, id, qty) => { const row = list.find((r) => r[0] === id); if (row) row[1] += qty; else list.push([id, qty]); };
  const legends = [];
  d.unmatched = [];
  for (const e of entries) {
    const id = resolveCard(e.name);
    if (!id) { d.unmatched.push(e); continue; }
    if (e.section === 'legend' || isLegend(card(id))) { if (!legends.includes(id)) legends.push(id); continue; }
    add(e.section === 'side' ? d.side : d.main, id, e.qty);
  }
  d.legends = [0, 1, 2].map((i) => legends[i] || null);
  d.keyCard = suggestKeyCard(d);
  if (!d.name) d.name = autoCode(d) || 'Imported deck';
  return d;
}
function suggestKeyCard(d) {
  const rows = [...d.main].filter(([id]) => card(id)).sort((a, b) => b[1] - a[1] || (card(b[0]).cost ?? 0) - (card(a[0]).cost ?? 0));
  return rows[0]?.[0] || null;
}

/* ---------------- deck derived data ---------------- */
function deckColors(d) {
  const cols = d.legends.map((id) => card(id)?.color).filter(Boolean);
  if (cols.length) return cols;
  return (d.label || d.name || '').toUpperCase().split('').filter((l) => COLORS[l]);
}
/** Color code like the community uses: majority color first, e.g. 2 Red + 1 Green Legends → RRG. */
function autoCode(d) {
  const cols = d.legends.map((id) => card(id)?.color).filter(Boolean);
  if (cols.length < 3) return '';
  const count = {};
  cols.forEach((c) => (count[c] = (count[c] || 0) + 1));
  return cols.slice().sort((a, b) => count[b] - count[a] || COLOR_ORDER.indexOf(a) - COLOR_ORDER.indexOf(b)).join('');
}
const isDemoDeck = (d) => d.legends.some((id) => id?.startsWith('demo_'));
/** A deck's key cards (up to 3). `keyCard` stays the first one, which tiles use. */
const keysOf = (d) => (d.keyCards?.length ? d.keyCards : d.keyCard ? [d.keyCard] : []).filter(Boolean);
const isKey = (d, id) => keysOf(d).includes(id);
function setKeys(d, ids) {
  d.keyCards = [...new Set(ids.filter(Boolean))].slice(0, 3);
  d.keyCard = d.keyCards[0] || null;
}
const deckLabel = (d) => d.label || autoCode(d) || d.name || 'Deck';
const deckCount = (d) => d.main.reduce((n, r) => n + r[1], 0);

/* ---------------- rendering: art ---------------- */
function cropStyle(k) {
  const y0 = k.top / 100, y1 = Math.max(k.bottom, k.top + 5) / 100;
  const fx = k.x / 100, fy = Math.min(Math.max(k.y / 100, y0), y1);
  const A = CARD_ASPECT;
  const H = `(max(100cqh / ${(y1 - y0).toFixed(4)}, 100cqw / ${A}) * ${k.zoom})`;
  return [
    `height:calc${H}`,
    `width:calc(${H} * ${A})`,
    `left:clamp(calc(100cqw - ${H} * ${A}), calc(50cqw - ${H} * ${(A * fx).toFixed(4)}), 0px)`,
    `top:clamp(calc(100cqh - ${H} * ${y1}), calc(50cqh - ${H} * ${fy.toFixed(4)}), calc(${H} * ${-y0}))`,
  ].join(';');
}
function artHTML(c, { full = false, cls = '', crop = null } = {}) {
  if (!c || !c.img) return `<div class="art empty ${cls}"></div>`;
  const style = full ? '' : cropStyle(crop || cropOf(c));
  return `<div class="art ${full ? 'full' : ''} ${cls}"><img src="${esc(c.img)}" alt="" draggable="false" loading="lazy" referrerpolicy="no-referrer" style="${style}"></div>`;
}
const hexOf = (c) => COLORS[c?.color]?.hex || '#8b93a3';
const chips = (cols, cls = 'chip') => cols.map((c) => `<span class="${cls}" style="background:${COLORS[c].hex}"></span>`).join('');

/* ---------------- rendering: deck tile ---------------- */
function deckTileHTML(d, mode, { style = '', selectable = true, showName = false } = {}) {
  if (d.display && d.display !== 'inherit') mode = d.display;
  const key = card(d.keyCard);
  const legends = d.legends.map(card);
  const strips = `<div class="strips">${legends.map((c) => `<div class="strip" style="--c:${hexOf(c)}">${artHTML(c)}</div>`).join('')}</div>`;
  let art;
  if (mode === 'legends') art = strips;
  else if (mode === 'legends-bands') art = strips.replace('class="strips"', 'class="strips bands"');
  else if (mode === 'split') art = `<div class="split">${artHTML(key)}${strips}</div>`;
  else art = artHTML(key, { full: mode === 'key-full' });
  const cols = deckColors(d);
  const label = deckLabel(d);
  const sel = selectable && ui.selectedDeck === d.id ? 'selected' : '';
  const sub = showName && d.name && d.name !== label ? d.name : d.subtitle;
  return `<div class="deck-tile ${sel}" draggable="true" data-deck="${d.id}" title="${esc(d.name || label)}" style="${style}">
    <div class="tile-art">${art}</div>
    <div class="tile-cap">
      <div class="segs">${cols.map((c) => `<span style="background:${COLORS[c].hex}"></span>`).join('') || '<span style="background:#8b93a3"></span>'}</div>
      <div class="code ${label.length > 5 ? 'long' : ''}">${esc(label)}</div>
      ${sub ? `<div class="sub">${esc(sub)}</div>` : ''}
    </div>
  </div>`;
}

/** Largest tile width for n tiles in a w×h box, wrapping onto up to 3 lines. */
function fitTiles(n, w, h, gap) {
  if (!n) return Math.floor(h * TILE_ASPECT);
  let best = 0;
  for (let lines = 1; lines <= 3; lines++) {
    const per = Math.ceil(n / lines);
    const byH = ((h - (lines - 1) * gap) / lines) * TILE_ASPECT;
    const byW = (w - (per - 1) * gap) / per;
    best = Math.max(best, Math.min(byH, byW));
  }
  return Math.floor(best);
}

/* ---------------- rendering: slides ---------------- */
const TL = { x: 80, top: 236, bottom: 76, head: 290, rowGap: 14, pad: 14, tileGap: 14 };

function tierSlideHTML(s, editing) {
  const tiers = s.tiers;
  const tableH = STAGE_H - TL.top - (s.footnote ? TL.bottom + 20 : TL.bottom - 20);
  const rowH = (tableH - (tiers.length - 1) * TL.rowGap) / Math.max(1, tiers.length);
  const areaW = STAGE_W - TL.x * 2 - TL.head - TL.pad * 2;
  const areaH = rowH - TL.pad * 2;
  const rows = tiers.map((t) => {
    const ds = t.deckIds.map(deck).filter(Boolean);
    const w = Math.min(fitTiles(ds.length, areaW, areaH, TL.tileGap), 250);
    const tiles = ds.map((d) => deckTileHTML(d, s.display, { style: `width:${w}px;height:${Math.floor(w / TILE_ASPECT)}px`, selectable: editing, showName: s.showNames })).join('');
    const nameSize = Math.min(64, Math.max(30, rowH * 0.3));
    return `<div class="tier-row" data-tier="${t.id}" style="--t:${esc(t.color)};--tt:${esc(t.color)}40;height:${rowH}px">
      <div class="tier-head">
        <div class="tier-name" style="font-size:${nameSize}px">${esc(t.name)}</div>
        ${t.desc && rowH > 120 ? `<div class="tier-desc">${esc(t.desc)}</div>` : ''}
      </div>
      <div class="tier-decks" data-drop="${t.id}">${tiles || (editing ? '<span class="drop-hint">Drop decks here</span>' : '')}</div>
    </div>`;
  }).join('');
  return `<div class="stage tier-slide">
    <div class="glow g1"></div><div class="glow g2"></div>
    <header class="s-head">
      ${s.eyebrow || s.pill ? `<div class="s-eyebrow">${s.eyebrow ? `<span class="brandmark">${esc(s.eyebrow)}</span>` : ''}${s.pill ? `<span class="pill">${esc(s.pill)}</span>` : ''}</div>` : ''}
      <h1 class="s-title">${esc(s.title)}</h1>
      ${s.logo ? `<img class="s-logo" src="${esc(s.logo)}" alt="">` : ''}
    </header>
    <div class="tiers" style="top:${TL.top}px;height:${tableH}px">${rows}</div>
    ${s.footnote ? `<div class="s-foot">${esc(s.footnote)}</div>` : ''}
  </div>`;
}

function tierOf(d) {
  for (const s of state.slides) if (s.type === 'tier') for (const t of s.tiers) if (t.deckIds.includes(d.id)) return t;
  return null;
}

function deckSlideHTML(s) {
  const d = deck(s.deckId);
  if (!d) return `<div class="stage deck-slide"><div class="ds-empty">Pick a deck in the panel →</div></div>`;
  if (s.listStyle === 'cards') return deckStacksSlideHTML(s, d); // any other value shows names
  const tier = tierOf(d);
  const keys = keysOf(d).map(card).filter(Boolean);
  const cols = deckColors(d);
  const legends = d.legends.map((id) => {
    const c = card(id);
    const [main, ...rest] = (c?.name || '—').split(/,\s*|\s+[—–-]\s+/);
    return `<figure class="ds-legend" style="--c:${hexOf(c)};--ca:${hexOf(c)}66">${artHTML(c)}<figcaption><b>${esc(main)}</b><span>${esc(rest.join(', '))}</span></figcaption></figure>`;
  }).join('');
  const rows = d.main.map(([id, n]) => [card(id), n]).filter(([c]) => c);
  const groups = typeGroups(rows);
  const total = rows.reduce((t, [, n]) => t + n, 0);
  // Compact rows when the grouped list wouldn't fit under the notes and breakdown.
  const lines = groups.reduce((t, g) => t + Math.ceil(g.rows.length / 2), 0);
  const many = lines * 66 + groups.length * 48 > (d.notes ? 640 : 770);
  const rowHTML = ([c, n]) => `<div class="ds-row ${isKey(d, c.id) ? 'is-key' : ''}" style="--c:${hexOf(c)};--ca:${hexOf(c)}40">
      ${artHTML(c, { cls: 'ds-row-art' })}
      <span class="ds-cost">${c.cost ?? '·'}</span><span class="ds-name">${esc(c.name)}</span>${roleTag(s, d, c.id)}<span class="ds-n">${n}×</span>
    </div>`;
  const list = groups.map((g) => `<div class="ds-group"><span>${esc(g.label)}</span><b>${g.count}</b></div>${g.rows.map(rowHTML).join('')}`).join('');
  const breakdown = total ? breakdownHTML(groups) : '';
  return `<div class="stage deck-slide">
    <div class="glow g1" style="background:radial-gradient(closest-side, ${hexOf(card(d.legends[0]))}38, transparent)"></div><div class="glow g2"></div>
    <header class="ds-head">
      <div class="ds-eyebrow">${tier ? `<span class="pill tier-pill" style="--t:${esc(tier.color)}">${esc(tier.name)}</span>` : ''}<span class="chips">${chips(cols, 'chip-lg')}</span>${d.main.length ? `<span class="ds-meta">${deckCount(d)} cards</span>` : ''}</div>
      <h1 class="ds-code">${esc(deckLabel(d))}</h1>
      ${d.name && d.name !== deckLabel(d) ? `<div class="ds-name-big">${esc(d.name)}</div>` : ''}
    </header>
    <div class="ds-legends">${legends}</div>
    ${keys.length ? `<div class="ds-keys">${keys.map((k, i) => `<div class="ds-key" style="--c:${hexOf(k)}">${artHTML(k, { cls: 'ds-key-art' })}<div class="ds-key-cap"><span>${i ? '&nbsp;' : keys.length > 1 ? 'Key cards' : 'Key card'}</span><b>${esc(k.name)}</b></div></div>`).join('')}</div>` : ''}
    <div class="ds-right">
      ${d.notes ? `<div class="ds-notes">${esc(d.notes)}</div>` : ''}
      ${breakdown}
      <div class="ds-list ${many ? 'dense' : ''}">${list || '<div class="ds-nolist">Import a deck export to show the decklist.</div>'}</div>
    </div>
  </div>`;
}

const ROLES = ['', 'core', 'flex'];
const roleTag = (s, d, id) => (s.showRoles !== false && d.roles?.[id] ? `<span class="role ${d.roles[id]}">${d.roles[id]}</span>` : '');
const breakdownHTML = (groups, cls = '') => `<div class="ds-breakdown ${cls}">${groups.map((g) => `<div class="ds-type" style="flex-grow:${g.count};--k:${g.color}">
  <div class="ds-type-n">${g.count}</div><div class="ds-type-l">${esc(g.label)}</div></div>`).join('')}</div>`;
const deckEyebrow = (d) => {
  const tier = tierOf(d);
  return `${tier ? `<span class="pill tier-pill" style="--t:${esc(tier.color)}">${esc(tier.name)}</span>` : ''}<span class="chips">${chips(deckColors(d), 'chip-lg')}</span>${d.main.length ? `<span class="ds-meta">${deckCount(d)} cards</span>` : ''}`;
};

/** Full decklist as cards: a Legends column, then a column per card type, cards overlapped so every
 * name bar shows and the last card of each column is fully visible (like a visual deck builder). */
function deckStacksSlideHTML(s, d) {
  const groups = typeGroups(d.main.map(([id, n]) => [card(id), n]).filter(([c]) => c));
  const legends = d.legends.map(card).filter(Boolean).map((c) => [c, 0]);
  const PEEK = 0.15; // visible share of each covered card: its name bar and cost
  const W = 1780, H = 800, gap = 30;
  // Try different maximum column lengths; keep the one that gives the largest cards.
  let best = null;
  for (let maxPer = 3; maxPer <= 12; maxPer++) {
    const cols = [];
    const push = (label, color, rows, count) => {
      for (let i = 0; i < rows.length; i += maxPer) cols.push({ label: i ? '' : label, count: i ? '' : count, color, rows: rows.slice(i, i + maxPer) });
    };
    if (legends.length) push('Legends', '#eef1f6', legends, legends.length);
    for (const g of groups) {
      // Key card last so it shows in full; otherwise by cost.
      const rows = g.rows.slice().sort((a, b) => isKey(d, a[0].id) - isKey(d, b[0].id));
      push(g.label, g.color, rows, g.count);
    }
    const tallest = Math.max(...cols.map((c) => c.rows.length));
    const h = Math.min((H - 40) / (1 + (tallest - 1) * PEEK), ((W - (cols.length - 1) * gap) / cols.length) / CARD_ASPECT);
    if (!best || h > best.h) best = { h, cols };
  }
  const h = Math.floor(best.h), w = Math.floor(h * CARD_ASPECT), step = Math.round(h * PEEK);
  const colHTML = (col) => `<div class="dk-col" style="width:${w}px">
      <div class="dk-label" style="--k:${col.color}">${esc(col.label)}${col.count !== '' ? ` <b>${col.count}</b>` : ''}</div>
      <div class="dk-stack" style="height:${h + step * (col.rows.length - 1)}px">${col.rows.map(([c, n], i) => `
        <div class="dk-card ${isKey(d, c.id) ? 'is-key' : ''}" style="top:${i * step}px;width:${w}px;height:${h}px;z-index:${i + 1}">
          ${artHTML(c, { full: true })}
          ${roleTag(s, d, c.id)}${n ? `<span class="dk-n">${n}×</span>` : ''}
        </div>`).join('')}</div>
    </div>`;
  return `<div class="stage deck-slide deck-stacks">
    <div class="glow g1" style="background:radial-gradient(closest-side, ${hexOf(card(d.legends[0]))}38, transparent)"></div><div class="glow g2"></div>
    <header class="dk-head">
      <div><div class="ds-eyebrow">${deckEyebrow(d)}</div>
      <h1 class="dk-code">${esc(deckLabel(d))}${d.name && d.name !== deckLabel(d) ? ` <span>${esc(d.name)}</span>` : ''}</h1></div>
      ${groups.length ? breakdownHTML(groups, 'compact') : ''}
    </header>
    <div class="dk-cols">${best.cols.length ? best.cols.map(colHTML).join('') : '<div class="ds-nolist">Import a deck export to show the decklist.</div>'}</div>
  </div>`;
}

// Main-deck cards by type (Units, Gear, Programs, then anything else), each sorted by cost.
const TYPE_GROUPS = [['unit', 'Units', '#ff6b6b'], ['gear', 'Gear', '#5ce1e6'], ['program', 'Programs', '#c08bff']];
function typeGroups(rows) {
  const out = TYPE_GROUPS.map(([key, label, color]) => ({ key, label, color, rows: [], count: 0 }));
  for (const [c, n] of rows) {
    let g = out.find((x) => (c.type || '').toLowerCase().includes(x.key));
    if (!g) {
      const label = c.type ? c.type.replace(/^./, (ch) => ch.toUpperCase()) + 's' : 'Other';
      g = out.find((x) => x.label === label) || out[out.push({ key: label, label, color: '#8b93a3', rows: [], count: 0 }) - 1];
    }
    g.rows.push([c, n]);
    g.count += n;
  }
  out.forEach((g) => g.rows.sort((a, b) => (a[0].cost ?? 99) - (b[0].cost ?? 99) || a[0].name.localeCompare(b[0].name)));
  return out.filter((g) => g.count);
}

const slideHTML = (s, editing = false) => (!s ? '<div class="stage"></div>' : s.type === 'deck' ? deckSlideHTML(s) : tierSlideHTML(s, editing));

function mountScaled(host, html, boxW, boxH) {
  const scale = Math.min(boxW / STAGE_W, boxH / STAGE_H);
  host.style.width = STAGE_W * scale + 'px';
  host.style.height = STAGE_H * scale + 'px';
  host.innerHTML = html;
  const st = host.firstElementChild;
  if (st) st.style.transform = `scale(${scale})`;
}

/* ---------------- Slides view ---------------- */
function renderSlides() {
  if (!slide()) ui.slideId = state.slides[0]?.id;
  renderSlideList();
  renderPool();
  renderStage();
  renderSlideInspector();
}
function renderSlideList() {
  $('#slide-list').innerHTML = state.slides.map((x, i) => `
    <li data-slide="${x.id}" class="${x.id === ui.slideId ? 'active' : ''}">
      <span class="t"><span class="nm">${i + 1}. ${esc(x.name || 'Slide')}</span><span class="k">${x.type === 'deck' ? 'Deck page' : 'Tier list'}</span></span>
      <button data-move="-1" title="Move up">↑</button><button data-move="1" title="Move down">↓</button><button data-del-slide title="Delete">×</button>
    </li>`).join('');
}
function renderStage() {
  const wrap = $('#stage-wrap');
  const narrow = window.innerWidth <= 900; // stacked layout: fit to width, let the page scroll
  const w = Math.max(200, wrap.clientWidth - 28);
  mountScaled($('#stage-host'), slideHTML(slide(), true), w, narrow ? Infinity : Math.max(120, wrap.clientHeight - 28));
}
function renderPool() {
  const s = slide();
  const pw = $('.pool-wrap');
  if (!s || s.type !== 'tier') { pw.hidden = true; return; }
  pw.hidden = false;
  const ranked = new Set(s.tiers.flatMap((t) => t.deckIds));
  const pool = state.decks.filter((d) => !ranked.has(d.id));
  $('#pool').innerHTML = pool.length ? pool.map((d) => deckTileHTML(d, s.display, { showName: true })).join('')
    : '<span class="hint">Every deck is ranked. Drag one here to unrank it, or import more decks in the Decks tab.</span>';
}

function renderSlideInspector() {
  const s = slide();
  const el = $('#slide-inspector');
  if (!s) { el.innerHTML = '<p class="hint">Add a slide to get started.</p>'; return; }
  if (s.type === 'deck') {
    el.innerHTML = `<h3>Deck page</h3>
      <label>Deck</label><select data-s="deckId">${state.decks.map((d) => `<option value="${d.id}" ${d.id === s.deckId ? 'selected' : ''}>${esc(deckLabel(d))}${d.name && d.name !== deckLabel(d) ? ' — ' + esc(d.name) : ''}</option>`).join('')}</select>
      <label>Decklist shows</label>
      <select data-s="listStyle">${[['list', 'Names'], ['cards', 'Full decklist (cards)']].map(([k, v]) => `<option value="${k}" ${(s.listStyle === 'cards' ? 'cards' : 'list') === k ? 'selected' : ''}>${v}</option>`).join('')}</select>
      <label class="check"><input type="checkbox" data-s="showRoles" ${s.showRoles !== false ? 'checked' : ''}> Show Core / Flex tags</label>
      <p class="hint">Mark cards as Core or Flex, and pick up to 3 key cards, in the deck editor.</p>
      <button data-edit-deck="${s.deckId}" class="block">Edit this deck</button>`;
    return;
  }
  el.innerHTML = `<h3>Tier list</h3>
    <label>Title</label><input data-s="title" value="${esc(s.title)}">
    <div class="grid2">
      <div><label>Brand</label><input data-s="eyebrow" value="${esc(s.eyebrow)}" placeholder="Plus Two"></div>
      <div><label>Format pill</label><input data-s="pill" value="${esc(s.pill)}" placeholder="Beta · Oct 2026"></div>
    </div>
    <label>Footnote</label><input data-s="footnote" value="${esc(s.footnote)}" placeholder="optional">
    <label>Deck tiles show</label>
    <select data-s="display">${Object.entries(DISPLAY_MODES).map(([k, v]) => `<option value="${k}" ${k === s.display ? 'selected' : ''}>${v}</option>`).join('')}</select>
    <label class="check"><input type="checkbox" data-s="showNames" ${s.showNames ? 'checked' : ''}> Show deck names under codes</label>
    <label>Logo</label>
    <div class="row gap"><input data-s="logo" value="${esc(s.logo?.startsWith('data:') ? '(uploaded)' : s.logo)}" placeholder="https://…" style="flex:1">
      <label class="filebtn">Upload<input type="file" accept="image/*" data-upload-logo hidden></label></div>
    <h3 style="margin-top:20px">Tiers <span class="hint">(${s.tiers.length})</span></h3>
    <div id="tier-edits">${s.tiers.map((t) => `<div class="tier-edit" data-tier-edit="${t.id}" style="--t:${esc(t.color)}">
      <div class="row gap"><input type="color" data-t="color" value="${esc(t.color)}"><input data-t="name" value="${esc(t.name)}" style="flex:1">
      <button class="small" data-tmove="-1" title="Move up">↑</button><button class="small" data-tmove="1" title="Move down">↓</button><button class="small danger" data-tdel title="Remove tier">×</button></div>
      <textarea data-t="desc" rows="2" placeholder="Description (optional)">${esc(t.desc)}</textarea>
    </div>`).join('')}</div>
    <button data-tadd class="block">+ Add tier</button>
    <label>Start from a preset</label>
    <div class="row gap">${Object.keys(TIER_PRESETS).map((k) => `<button class="small" data-preset="${esc(k)}">${esc(k)}</button>`).join('')}</div>
    <p class="hint">Presets keep your rankings in order and only rename or recolor the tiers. Decks in removed tiers go back to Unranked.</p>`;
}

function moveDeck(deckId, toTierId, beforeDeckId = null) {
  const s = slide();
  if (!s || s.type !== 'tier') return;
  s.tiers.forEach((t) => (t.deckIds = t.deckIds.filter((x) => x !== deckId)));
  if (toTierId && toTierId !== 'pool') {
    const t = s.tiers.find((x) => x.id === toTierId);
    if (!t) return;
    const idx = beforeDeckId ? t.deckIds.indexOf(beforeDeckId) : -1;
    if (idx >= 0) t.deckIds.splice(idx, 0, deckId); else t.deckIds.push(deckId);
  }
  ui.selectedDeck = null;
  save();
  renderPool();
  renderStage();
}

function applyPreset(s, key) {
  const preset = TIER_PRESETS[key];
  const n = preset.length;
  s.tiers = preset.map(([name, desc], i) => ({
    id: s.tiers[i]?.id || uid(), name, desc,
    color: TIER_PALETTE[Math.round((i * (TIER_PALETTE.length - 2)) / Math.max(1, n - 1))],
    deckIds: s.tiers[i]?.deckIds || [],
  }));
}

function bindSlides() {
  $('#slide-list').addEventListener('click', (e) => {
    const li = e.target.closest('li[data-slide]');
    if (!li) return;
    const i = state.slides.findIndex((x) => x.id === li.dataset.slide);
    if (e.target.dataset.move) {
      const j = i + Number(e.target.dataset.move);
      if (j < 0 || j >= state.slides.length) return;
      [state.slides[i], state.slides[j]] = [state.slides[j], state.slides[i]];
    } else if ('delSlide' in e.target.dataset) {
      if (!confirm('Delete this slide?')) return;
      state.slides.splice(i, 1);
    } else ui.slideId = li.dataset.slide;
    save(); renderSlides();
  });
  $('#add-tier-slide').onclick = () => {
    const base = state.slides.find((x) => x.type === 'tier');
    const s = base ? clone(base) : makeDemo().slides[0];
    s.id = uid(); s.name = 'Tier list ' + (state.slides.filter((x) => x.type === 'tier').length + 1);
    s.tiers.forEach((t) => { t.id = uid(); t.deckIds = []; });
    state.slides.push(s); ui.slideId = s.id; save(); renderSlides();
  };
  $('#add-deck-slide').onclick = () => addDeckSlide(state.decks[0]);

  const insp = $('#slide-inspector');
  insp.addEventListener('input', (e) => {
    const s = slide();
    const k = e.target.dataset.s, tk = e.target.dataset.t;
    if (k) {
      if (k === 'logo' && e.target.value === '(uploaded)') return;
      s[k] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
      if (k === 'title') s.name = s.title;
      if (k === 'deckId') s.name = 'Deck: ' + deckLabel(deck(s.deckId));
      if (k === 'showNames' || k === 'display') renderPool();
    } else if (tk) {
      const t = s.tiers.find((x) => x.id === e.target.closest('[data-tier-edit]').dataset.tierEdit);
      t[tk] = e.target.value;
      if (tk === 'color') e.target.closest('[data-tier-edit]').style.setProperty('--t', t.color);
    } else return;
    save(); renderStage();
    if (k === 'title' || k === 'deckId') renderSlideList();
  });
  insp.addEventListener('change', async (e) => {
    if (e.target.matches('[data-upload-logo]') && e.target.files[0]) {
      slide().logo = await fileToDataURL(e.target.files[0], 400);
      save(); renderSlides();
    }
  });
  insp.addEventListener('click', (e) => {
    const s = slide();
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.editDeck) { ui.deckId = b.dataset.editDeck; setView('decks'); return; }
    if (b.dataset.preset) applyPreset(s, b.dataset.preset);
    else if ('tadd' in b.dataset) s.tiers.push({ id: uid(), name: 'Tier ' + (s.tiers.length + 1), desc: '', color: TIER_PALETTE[s.tiers.length % TIER_PALETTE.length], deckIds: [] });
    else {
      const box = b.closest('[data-tier-edit]');
      if (!box) return;
      const i = s.tiers.findIndex((t) => t.id === box.dataset.tierEdit);
      if (b.dataset.tmove) {
        const j = i + Number(b.dataset.tmove);
        if (j < 0 || j >= s.tiers.length) return;
        [s.tiers[i], s.tiers[j]] = [s.tiers[j], s.tiers[i]];
      } else if ('tdel' in b.dataset) {
        if (s.tiers[i].deckIds.length && !confirm(`Remove "${s.tiers[i].name}"? Its decks go back to Unranked.`)) return;
        s.tiers.splice(i, 1);
      } else return;
    }
    save(); renderSlides();
  });

  // drag & drop, plus tap-to-move for touch screens
  let dragId = null;
  for (const z of [$('#stage-host'), $('#pool')]) {
    z.addEventListener('dragstart', (e) => {
      const t = e.target.closest('.deck-tile');
      if (!t) return;
      dragId = t.dataset.deck;
      e.dataTransfer.setData('text/plain', dragId);
      e.dataTransfer.effectAllowed = 'move';
      t.classList.add('dragging');
    });
    z.addEventListener('dragend', () => { dragId = null; $$('.dragging, .drop-hover').forEach((x) => x.classList.remove('dragging', 'drop-hover')); });
    z.addEventListener('dragover', (e) => {
      const dz = e.target.closest('[data-drop]');
      if (!dz || !dragId) return;
      e.preventDefault();
      $$('.drop-hover').forEach((x) => x !== dz && x.classList.remove('drop-hover'));
      dz.classList.add('drop-hover');
    });
    z.addEventListener('drop', (e) => {
      const dz = e.target.closest('[data-drop]');
      if (!dz) return;
      e.preventDefault();
      const id = e.dataTransfer.getData('text/plain') || dragId;
      const before = e.target.closest('.deck-tile')?.dataset.deck;
      moveDeck(id, dz.dataset.drop, before !== id ? before : null);
    });
    z.addEventListener('click', (e) => {
      const tile = e.target.closest('.deck-tile');
      const dz = e.target.closest('[data-drop]') || e.target.closest('[data-tier]')?.querySelector('[data-drop]');
      if (tile && (!ui.selectedDeck || ui.selectedDeck === tile.dataset.deck)) {
        ui.selectedDeck = ui.selectedDeck === tile.dataset.deck ? null : tile.dataset.deck;
        renderPool(); renderStage();
      } else if (ui.selectedDeck && dz) moveDeck(ui.selectedDeck, dz.dataset.drop, tile?.dataset.deck);
    });
    z.addEventListener('dblclick', (e) => {
      const tile = e.target.closest('.deck-tile');
      if (tile) { ui.deckId = tile.dataset.deck; ui.selectedDeck = null; setView('decks'); }
    });
  }
}
function addDeckSlide(d) {
  const s = { id: uid(), type: 'deck', name: 'Deck: ' + (d ? deckLabel(d) : ''), deckId: d?.id || null };
  state.slides.push(s); ui.slideId = s.id; save(); setView('slides');
}

/* ---------------- Decks view ---------------- */
function renderDecks() {
  if (!deck(ui.deckId)) ui.deckId = state.decks[0]?.id;
  $('#deck-list').innerHTML = state.decks.map((d) => `<li data-deck-item="${d.id}" class="${d.id === ui.deckId ? 'active' : ''}">
    <span class="fan">${d.legends.map((id) => `<span class="mini" style="--c:${hexOf(card(id))}">${artHTML(card(id))}</span>`).join('')}</span>
    <span class="dl-text"><strong>${esc(deckLabel(d))}</strong><span class="hint">${esc(d.name && d.name !== deckLabel(d) ? d.name : d.main.length ? deckCount(d) + ' cards' : '')}</span></span>
    <span class="chips">${chips(deckColors(d))}</span></li>`).join('') || '<li class="hint">No decks yet.</li>';
  const demos = state.decks.filter(isDemoDeck).length;
  $('#deck-list').insertAdjacentHTML('beforeend', demos && state.catalog ? `<li class="demo-note"><button id="clear-demo" class="small block">Remove ${demos} demo decks</button></li>` : '');
  const d = deck(ui.deckId);
  const ed = $('#deck-editor');
  if (!d) { ed.innerHTML = '<div class="empty-msg">No decks yet. Import a deck export or create a blank deck.</div>'; return; }
  const slot = (id, role, i) => {
    const c = card(id);
    return `<button class="slot" data-slot="${role}" data-i="${i ?? ''}" style="--c:${hexOf(c)}">${artHTML(c)}<span class="n">${esc(c?.name || (role === 'key' ? 'Pick key card' : 'Pick Legend'))}</span></button>`;
  };
  const listRows = (rows, side) => rows.map(([id, n]) => {
    const c = card(id);
    return `<div class="dl-row" style="--c:${hexOf(c)}"><span class="ds-cost">${c?.cost ?? '·'}</span><span class="nm">${esc(c?.name || id)}</span>
      <span class="qty"><button class="small" data-q="${id}" data-side="${side}" data-dq="-1">−</button>${n}<button class="small" data-q="${id}" data-side="${side}" data-dq="1">+</button></span>
      <button class="small role-btn ${d.roles?.[id] || ''}" data-role="${id}" title="Mark as Core or Flex">${d.roles?.[id] || 'core/flex'}</button>
      <button class="small ${isKey(d, id) ? 'on' : ''}" data-setkey="${id}" title="Key card (up to 3)">★</button></div>`;
  }).join('');
  ed.innerHTML = `<div class="deck-edit">
    <div>
      <div class="grid2">
        <div><label>Tile code</label><input data-d="label" value="${esc(d.label)}" placeholder="${esc(autoCode(d) || 'auto')}"></div>
        <div><label>Deck name</label><input data-d="name" value="${esc(d.name)}" placeholder="e.g. Geary Noble Safety"></div>
      </div>
      <label>Legends</label>
      <div class="slots">${d.legends.map((id, i) => slot(id, 'legend', i)).join('')}</div>
      <label>Key cards (up to 3)</label>
      <div class="slots">${[...keysOf(d), null].slice(0, 3).map((id, i) => slot(id, 'key', i)).join('')}</div>
      <p class="hint">Up to 3 cards that define the deck. Pick them here, or press ★ on cards in the decklist. The first one is used on tier list tiles.</p>
      <label>Tile display</label>
      <div class="seg">${[['inherit', 'Slide default'], ...Object.entries(DISPLAY_MODES)].map(([k, v]) => `<button data-display="${k}" class="${(d.display || 'inherit') === k ? 'on' : ''}">${v}</button>`).join('')}</div>
      <label>Notes (shown on the deck page)</label>
      <textarea data-d="notes" rows="3">${esc(d.notes)}</textarea>
      <div class="row gap" style="margin-top:14px">
        <button data-deckpage class="primary">+ Deck page slide</button>
        <button data-reimport>Replace from export…</button>
        <button data-copy-export>Copy sim export</button>
        <button data-del-deck class="danger">Delete</button>
      </div>
    </div>
    <div>
      <h3>Preview</h3>
      <div class="previews">${Object.entries(DISPLAY_MODES).map(([k, v]) => `<figure>${deckTileHTML({ ...d, display: k }, k, { selectable: false, showName: true })}<figcaption>${v}</figcaption></figure>`).join('')}</div>
      <h3 style="margin-top:20px">Decklist <span class="hint">${deckCount(d)} main${d.side.length ? ` · ${d.side.reduce((n, r) => n + r[1], 0)} side` : ''}</span></h3>
      ${d.unmatched?.length ? `<div class="callout warn">${d.unmatched.length} line(s) didn't match a card${state.catalog ? '' : ' (load the card data first)'}: ${d.unmatched.map((u) => esc(u.name)).join(', ')}</div>` : ''}
      <div class="dl">${listRows(d.main, 0) || '<p class="hint">No decklist yet. Use “Replace from export…” to import one.</p>'}</div>
      ${d.side.length ? `<h3 style="margin-top:14px">Sideboard</h3><div class="dl">${listRows(d.side, 1)}</div>` : ''}
    </div>
  </div>`;
}

function exportSimText(d) {
  const nm = (id) => card(id)?.name || id;
  const lines = (rows) => rows.map(([id, n]) => `${n}x ${nm(id)}`).sort();
  const out = [`# Name: ${d.name || deckLabel(d)}`, '#L', ...d.legends.filter(Boolean).map((id) => `1x ${nm(id)}`), '', '#D', ...lines(d.main)];
  if (d.side.length) out.push('', '#S', ...lines(d.side));
  return out.join('\n');
}

function bindDecks() {
  $('#deck-list').addEventListener('click', (e) => {
    if (e.target.id === 'clear-demo') {
      const gone = new Set(state.decks.filter(isDemoDeck).map((d) => d.id));
      state.decks = state.decks.filter((d) => !gone.has(d.id));
      state.slides.forEach((s) => s.tiers?.forEach((t) => (t.deckIds = t.deckIds.filter((x) => !gone.has(x)))));
      state.slides = state.slides.filter((s) => s.type !== 'deck' || !gone.has(s.deckId));
      state.custom = state.custom.filter((c) => !c.demo);
      rebuildIndex(); nameIndex = null; save(); renderDecks();
      return;
    }
    const li = e.target.closest('[data-deck-item]');
    if (li) { ui.deckId = li.dataset.deckItem; renderDecks(); }
  });
  $('#add-deck').onclick = () => { const d = newDeck({ name: 'New deck' }); state.decks.push(d); ui.deckId = d.id; save(); renderDecks(); };
  $('#import-deck').onclick = () => openImport();
  const ed = $('#deck-editor');
  ed.addEventListener('input', (e) => {
    const k = e.target.dataset.d;
    if (!k) return;
    deck(ui.deckId)[k] = e.target.value;
    save();
    clearTimeout(ed._t);
    ed._t = setTimeout(() => { const f = document.activeElement?.dataset.d; renderDecks(); if (f) { const i = $(`[data-d="${f}"]`); i?.focus(); i?.setSelectionRange(i.value.length, i.value.length); } }, 400);
  });
  ed.addEventListener('click', (e) => {
    const d = deck(ui.deckId);
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.slot) {
      const role = b.dataset.slot;
      const onlyDeck = role === 'key' && d.main.length ? d.main.map((r) => r[0]) : null;
      openPicker(role === 'key' ? 'all' : 'legend', (id) => {
        if (role === 'key') { const ks = keysOf(d).slice(); ks[Number(b.dataset.i)] = id; setKeys(d, ks); } else d.legends[Number(b.dataset.i)] = id;
        save(); renderDecks();
      }, onlyDeck);
      return;
    }
    if (b.dataset.display) d.display = b.dataset.display;
    else if (b.dataset.setkey) {
      const id = b.dataset.setkey, ks = keysOf(d);
      if (ks.includes(id)) setKeys(d, ks.filter((x) => x !== id));
      else if (ks.length >= 3) return toast('A deck can have up to 3 key cards. Unstar one first.');
      else setKeys(d, [...ks, id]);
    }
    else if (b.dataset.role) {
      d.roles = d.roles || {};
      const next = ROLES[(ROLES.indexOf(d.roles[b.dataset.role] || '') + 1) % ROLES.length];
      if (next) d.roles[b.dataset.role] = next; else delete d.roles[b.dataset.role];
    }
    else if (b.dataset.dq) {
      const list = b.dataset.side === '1' ? d.side : d.main;
      const row = list.find((r) => r[0] === b.dataset.q);
      row[1] += Number(b.dataset.dq);
      if (row[1] <= 0) list.splice(list.indexOf(row), 1);
    } else if ('deckpage' in b.dataset) return addDeckSlide(d);
    else if ('reimport' in b.dataset) return openImport(d);
    else if ('copyExport' in b.dataset) {
      navigator.clipboard?.writeText(exportSimText(d)).then(() => toast('Copied in Cyberpunk TCG Sim text format.'), () => toast('Copy failed.'));
      return;
    } else if ('delDeck' in b.dataset) {
      if (!confirm(`Delete deck "${deckLabel(d)}"?`)) return;
      state.decks = state.decks.filter((x) => x.id !== d.id);
      state.slides.forEach((s) => s.tiers?.forEach((t) => (t.deckIds = t.deckIds.filter((x) => x !== d.id))));
    } else return;
    save(); renderDecks();
  });
}

/* ---------------- Import modal ---------------- */
function openImport(target = null) {
  openModal(`<h3>${target ? 'Replace decklist from export' : 'Import deck export'}</h3>
    <p class="hint">Paste a deck from the <b>Cyberpunk TCG Sim</b> (Export → Text, or an import link containing <code>b64deck=</code>),
      or the <b>official deck builder's</b> text list. Paste several decks at once by separating them with a line of <code>---</code>.</p>
    ${state.catalog ? '' : '<div class="callout warn">Card data isn\'t loaded yet, so card names can\'t be matched to art. Load it in the <b>Card Data</b> tab first.</div>'}
    <textarea id="imp-text" rows="12" placeholder="# Name: Geary Noble Safety&#10;#L&#10;1x Panam Palmer&#10;1x River Ward&#10;1x Muamar Reyes&#10;&#10;#D&#10;3x …"></textarea>
    <div class="row gap" style="margin-top:8px"><label class="filebtn">Load .txt file<input type="file" id="imp-file" accept=".txt,.json,text/plain" hidden></label></div>
    <div id="imp-preview" style="margin-top:12px"></div>
    <div class="row gap" style="margin-top:14px"><button class="primary" id="imp-go" disabled>Import</button><button data-close>Cancel</button></div>`);
  let parsed = [];
  const preview = () => {
    const raw = $('#imp-text').value;
    parsed = raw.trim() ? raw.split(/^\s*-{3,}\s*$/m).map((t) => t.trim()).filter(Boolean).map(parseDeckExport) : [];
    $('#imp-go').disabled = !parsed.length;
    $('#imp-preview').innerHTML = parsed.map((d) => `<div class="imp-row">
      ${deckTileHTML(d, 'legends', { selectable: false, style: 'width:96px;height:130px', showName: true })}
      <div><b>${esc(d.name)}</b> <span class="hint">· ${d.legends.filter(Boolean).length}/3 Legends · ${deckCount(d)} cards${d.side.length ? ' + side' : ''}</span>
      ${d.unmatched.length ? `<div class="warn-text">Not matched: ${d.unmatched.slice(0, 8).map((u) => esc(u.name)).join(', ')}${d.unmatched.length > 8 ? '…' : ''}</div>` : '<div class="ok-text">All cards matched.</div>'}</div></div>`).join('');
  };
  $('#imp-text').oninput = preview;
  $('#imp-file').onchange = async (e) => { if (e.target.files[0]) { $('#imp-text').value = await e.target.files[0].text(); preview(); } };
  $('#imp-go').onclick = () => {
    if (target && parsed[0]) {
      const p = parsed[0];
      Object.assign(target, { legends: p.legends, main: p.main, side: p.side, unmatched: p.unmatched, keyCards: keysOf(target).filter((k) => p.main.some((r) => r[0] === k)) });
      if (!keysOf(target).length) setKeys(target, [p.keyCard]); else setKeys(target, keysOf(target));
      if (!target.name || target.name === 'New deck') target.name = p.name;
    } else {
      for (const d of parsed) state.decks.push(d);
      ui.deckId = parsed[0].id;
    }
    save(); closeModal(); renderDecks();
    toast(target ? 'Decklist replaced.' : `Imported ${parsed.length} deck(s). They're in Unranked on your tier list.`);
  };
  $('#imp-text').focus();
}

/* ---------------- Card picker ---------------- */
function openPicker(kind, onPick, onlyIds = null) {
  let q = '', filter = kind, limit = !!onlyIds;
  const draw = () => {
    const list = allCards().filter((c) => (!limit || onlyIds.includes(c.id)) && (filter === 'all' || (filter === 'legend') === isLegend(c)) && norm(c.name).includes(norm(q)))
      .sort((a, b) => a.name.localeCompare(b.name)).slice(0, 300);
    $('#picker-grid').innerHTML = `<div class="pick" data-pick=""><div class="art empty"></div><div class="n">(none)</div></div>` +
      list.map((c) => `<div class="pick" data-pick="${c.id}">${artHTML(c, { full: true })}<div class="n">${esc(c.name)}</div></div>`).join('');
  };
  openModal(`<h3>Choose ${kind === 'legend' ? 'a Legend' : 'a card'}</h3>
    <div class="toolbar"><input type="search" id="picker-q" placeholder="Search…">
    <select id="picker-f"><option value="legend" ${kind === 'legend' ? 'selected' : ''}>Legends</option><option value="card">Non-Legends</option><option value="all" ${kind === 'all' ? 'selected' : ''}>All</option></select>
    ${onlyIds ? '<label class="check"><input type="checkbox" id="picker-limit" checked> Only cards in this deck</label>' : ''}</div>
    <div class="picker-grid" id="picker-grid"></div>
    ${state.catalog ? '' : '<p class="hint">Only demo cards are available. Load the real card data in the Card Data tab.</p>'}`);
  draw();
  $('#picker-q').oninput = (e) => { q = e.target.value; draw(); };
  $('#picker-f').onchange = (e) => { filter = e.target.value; draw(); };
  if ($('#picker-limit')) $('#picker-limit').onchange = (e) => { limit = e.target.checked; draw(); };
  $('#picker-q').focus();
  $('#picker-grid').onclick = (e) => {
    const p = e.target.closest('[data-pick]');
    if (!p) return;
    closeModal();
    onPick(p.dataset.pick || null);
  };
}

/* ---------------- Cards view ---------------- */
function renderCards() {
  const q = norm($('#card-search').value);
  const f = $('#card-filter').value;
  const list = allCards().filter((c) => (f === 'all' || (f === 'legend') === isLegend(c)) && norm(c.name).includes(q)).sort((a, b) => a.name.localeCompare(b.name));
  $('#card-grid').innerHTML = (state.catalog ? '' : '<div class="callout warn" style="grid-column:1/-1">Showing demo placeholders. Load the real cards in the <b>Card Data</b> tab.</div>') +
    (list.map((c) => `<div class="card-cell" style="--c:${hexOf(c)}">
      <div class="thumbs">${artHTML(c, { full: true })}${artHTML(c)}</div>
      <div class="nm" title="${esc(c.name)}">${esc(c.name)}</div>
      <div class="meta">${c.color ? `<span class="chip" style="background:${hexOf(c)}"></span>` : ''}<span class="tag">${esc(c.type || 'Card')}</span>${state.crops[c.id] ? '<span class="tag">custom crop</span>' : ''}</div>
      <div class="btns"><button class="small" data-crop="${c.id}">Crop art</button>${c.custom || c.demo ? `<button class="small danger" data-del-card="${c.id}">×</button>` : ''}</div>
    </div>`).join('') || '<div class="empty-msg">No cards match.</div>');
}

function openCrop(c) {
  const k = cropOf(c);
  const slider = (id, label, min, max, step) =>
    `<div><label>${label} <span id="cv-${id}"></span></label><input type="range" data-k="${id}" min="${min}" max="${max}" step="${step}" value="${k[id]}"></div>`;
  openModal(`<h3>Crop art · ${esc(c.name)}</h3>
    <p class="hint">Fit the dashed box to the illustration: everything outside it (the title and rules text) is hidden on slides. Click the card to set the focus point.</p>
    <div class="crop">
      <div><div class="crop-src" id="crop-src"><img src="${esc(c.img)}" alt="" referrerpolicy="no-referrer">
        <div class="shade" id="sh-top" style="top:0"></div><div class="shade" id="sh-bot" style="bottom:0"></div>
        <div class="win" id="crop-win"></div><div class="focus" id="crop-focus"></div></div></div>
      <div>
        <div class="grid2">${slider('top', 'Art top', 0, 90, 1)}${slider('bottom', 'Art bottom', 10, 100, 1)}
        ${slider('x', 'Focus X', 0, 100, 1)}${slider('y', 'Focus Y', 0, 100, 1)}</div>
        ${slider('zoom', 'Extra zoom', 1, 3, 0.05)}
        <div class="crop-previews" id="crop-previews"></div>
        <div class="row gap" style="margin-top:16px"><button class="primary" id="crop-save">Save for this card</button>
          ${isLegend(c) ? '<button id="crop-all">Save as default for all Legends</button>' : ''}
          <button id="crop-reset">Reset</button><button data-close>Cancel</button></div>
      </div>
    </div>`);
  const draw = () => {
    if (k.bottom < k.top + 5) k.bottom = Math.min(100, k.top + 5);
    $('#sh-top').style.height = k.top + '%';
    $('#sh-bot').style.height = 100 - k.bottom + '%';
    Object.assign($('#crop-win').style, { top: k.top + '%', height: k.bottom - k.top + '%' });
    Object.assign($('#crop-focus').style, { left: k.x + '%', top: k.y + '%' });
    for (const id of Object.keys(DEFAULT_CROP)) {
      $(`[data-k="${id}"]`).value = k[id];
      $('#cv-' + id).textContent = id === 'zoom' ? k.zoom.toFixed(2) + '×' : k[id] + '%';
    }
    $('#crop-previews').innerHTML = [['Strip', 64, 220], ['Tile', 160, 200], ['Band', 300, 90]]
      .map(([n, w, h]) => `<figure>${artHTML(c, { crop: k }).replace('class="art', `style="width:${w}px;height:${h}px;flex:none" class="art`)}<div>${n}</div></figure>`).join('');
  };
  draw();
  $('#crop-src').onclick = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    k.x = Math.round(((e.clientX - r.left) / r.width) * 100);
    k.y = Math.round(((e.clientY - r.top) / r.height) * 100);
    draw();
  };
  $('#modal-body').oninput = (e) => { const id = e.target.dataset.k; if (id) { k[id] = Number(e.target.value); draw(); } };
  $('#crop-reset').onclick = () => { delete state.crops[c.id]; Object.assign(k, cropOf(c)); draw(); };
  $('#crop-save').onclick = () => { state.crops[c.id] = { ...k }; save(); closeModal(); renderCards(); };
  if ($('#crop-all')) $('#crop-all').onclick = () => { state.legendCrop = { ...k }; delete state.crops[c.id]; save(); closeModal(); renderCards(); toast('Saved as the default crop for all Legends.'); };
}

function customCardForm() {
  openModal(`<h3>Custom card</h3>
    <p class="hint">For cards that aren't in the catalog yet (spoilers, promos).</p>
    <div class="grid2">
      <div><label>Name</label><input id="cf-name"></div>
      <div><label>Type</label><select id="cf-type"><option>Legend</option><option>Unit</option><option>Gear</option><option>Program</option></select></div>
      <div><label>Color</label><select id="cf-color"><option value="">None</option>${COLOR_ORDER.map((k) => `<option value="${k}">${COLORS[k].name}</option>`).join('')}</select></div>
      <div><label>Image URL</label><input id="cf-img" type="url" placeholder="https://…"></div>
    </div>
    <label>…or upload an image</label><input type="file" id="cf-file" accept="image/*">
    <div class="row gap" style="margin-top:16px"><button class="primary" id="cf-save">Add</button><button data-close>Cancel</button></div>`);
  $('#cf-save').onclick = async () => {
    const name = $('#cf-name').value.trim() || 'Untitled';
    const f = $('#cf-file').files[0];
    const img = f ? await fileToDataURL(f, 700) : $('#cf-img').value.trim();
    state.custom.push({ id: 'custom_' + uid(), name, type: $('#cf-type').value, color: $('#cf-color').value, img, custom: true });
    rebuildIndex(); nameIndex = null; save(); closeModal(); renderCards();
  };
}

function bindCards() {
  $('#card-search').oninput = renderCards;
  $('#card-filter').onchange = renderCards;
  $('#add-card').onclick = customCardForm;
  $('#card-grid').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.crop) openCrop(card(b.dataset.crop));
    else if (b.dataset.delCard) {
      state.custom = state.custom.filter((c) => c.id !== b.dataset.delCard);
      rebuildIndex(); nameIndex = null; save(); renderCards();
    }
  });
}

/* ---------------- Card Data view ---------------- */
function renderData() {
  const cat = state.catalog;
  const legends = cat ? cat.cards.filter(isLegend) : [];
  $('#data-view').innerHTML = `<h3>Card data</h3>
    ${cat ? `<div class="callout ok"><b>${cat.cards.length} cards</b> (${legends.length} Legends) from ${esc(cat.from)}, loaded ${new Date(cat.at).toLocaleString()}${cat.revision ? ` · pool revision ${esc(cat.revision)}` : ''}.</div>`
      : '<div class="callout warn">No card data yet. The app is showing demo placeholders.</div>'}
    <p>Card names, types, colors and art come from the <b>Cyberpunk TCG Sim</b> public catalog, the same one its deck builder and the Cyberpunk TCG Tracker use. Card images load straight from the simulator.</p>
    <div class="row gap"><button class="primary" id="cat-fetch">${cat ? 'Refresh' : 'Load'} from Cyberpunk TCG Sim</button>
      <label class="filebtn">Load catalog .json<input type="file" id="cat-file" accept=".json,application/json" hidden></label>
      <button id="cat-paste-btn">Paste JSON</button></div>
    <textarea id="cat-paste" rows="5" hidden placeholder='{"cards":[…]}'></textarea>
    <div id="cat-status" class="hint" style="margin-top:8px"></div>
    <div class="callout" style="margin-top:16px">If <i>Load</i> is blocked by the browser (CORS), open
      <a href="${CATALOG_URL}" target="_blank" rel="noopener">${CATALOG_URL}</a>, save the page as <code>catalog.json</code> (Ctrl/⌘+S), and use <b>Load catalog .json</b>.</div>
    <h3 style="margin-top:26px">Ranked meta</h3>
    <p>Create decks from the most-played Legend trios on the sim's public ranked leaderboard. Each one becomes a Legends-only deck you can rank, then fill in with an export later.</p>
    <div class="row gap"><button id="meta-fetch" ${cat ? '' : 'disabled'}>Add top ranked Legend trios</button>
      <label class="filebtn">Load leaderboard .json<input type="file" id="meta-file" accept=".json" hidden></label>
      <a href="${LEADERBOARD_URL}" target="_blank" rel="noopener" class="hint">leaderboard JSON ↗</a></div>
    <div id="meta-status" class="hint" style="margin-top:8px"></div>`;
}

function addTrios(json) {
  const existing = new Set(state.decks.map((d) => d.legends.filter(Boolean).slice().sort().join('+')));
  const top = topTrios(json, 16).map((t) => [t.key, t.games]).filter(([k]) => !existing.has(k));
  for (const [k, games] of top) {
    const d = newDeck({ legends: k.split('+'), notes: `${games} ranked games on the leaderboard` });
    d.name = autoCode(d) || 'Ranked trio';
    state.decks.push(d);
  }
  save();
  return top.length;
}

function bindData() {
  const v = $('#data-view');
  const status = (m) => ($('#cat-status').textContent = m);
  const loaded = (json, from) => {
    try {
      const n = applyCatalog(json, from);
      applySamples().then((did) => did && toast('Loaded sample decks with real cards.'));
      renderData(); updateBadge();
      $('#cat-status').textContent = `Loaded ${n} cards.`;
      toast(`Loaded ${n} cards.`);
    } catch (err) { status(err.message); }
  };
  v.addEventListener('click', async (e) => {
    const id = e.target.id;
    if (id === 'cat-fetch') {
      status('Loading…');
      try { const n = await loadCatalogFromSim(); await applySamples(); renderData(); updateBadge(); status(`Loaded ${n} cards.`); }
      catch (err) { status(`Couldn't load (${err.message}). Use the save-as-file option below.`); }
    } else if (id === 'cat-paste-btn') $('#cat-paste').hidden = !$('#cat-paste').hidden;
    else if (id === 'meta-fetch') {
      $('#meta-status').textContent = 'Loading…';
      try {
        const r = await fetch(LEADERBOARD_URL, { credentials: 'omit' });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        $('#meta-status').textContent = `Added ${addTrios(await r.json())} decks. Find them in Unranked.`;
      } catch (err) { $('#meta-status').textContent = `Couldn't load (${err.message}). Open the leaderboard JSON link, save it, then use Load leaderboard .json.`; }
    }
  });
  v.addEventListener('input', (e) => {
    if (e.target.id === 'cat-paste') { try { loaded(JSON.parse(e.target.value), 'pasted JSON'); } catch { status('Waiting for valid JSON…'); } }
  });
  v.addEventListener('change', async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    try {
      const json = JSON.parse(await f.text());
      if (e.target.id === 'cat-file') loaded(json, f.name);
      if (e.target.id === 'meta-file') $('#meta-status').textContent = `Added ${addTrios(json)} decks. Find them in Unranked.`;
    } catch (err) { status('Could not read file: ' + err.message); }
  });
}
function updateBadge() {
  $('#data-badge').textContent = state.catalog ? state.catalog.cards.length : '!';
  $('#data-badge').classList.toggle('warn', !state.catalog);
}

/* ---------------- images ---------------- */
function fileToDataURL(file, maxW) {
  return new Promise((resolve, reject) => {
    const fr = new FileReader();
    fr.onerror = reject;
    fr.onload = () => {
      const img = new Image();
      img.onload = () => {
        const s = Math.min(1, maxW / img.naturalWidth);
        const cv = document.createElement('canvas');
        cv.width = Math.round(img.naturalWidth * s);
        cv.height = Math.round(img.naturalHeight * s);
        cv.getContext('2d').drawImage(img, 0, 0, cv.width, cv.height);
        resolve(cv.toDataURL(file.type === 'image/png' ? 'image/png' : 'image/jpeg', 0.86));
      };
      img.onerror = () => resolve(fr.result);
      img.src = fr.result;
    };
    fr.readAsDataURL(file);
  });
}

/* ---------------- modal ---------------- */
function openModal(html) { $('#modal-body').innerHTML = html; $('#modal').hidden = false; }
function closeModal() { $('#modal').hidden = true; $('#modal-body').innerHTML = ''; $('#modal-body').oninput = null; }

/* ---------------- present ---------------- */
let presentIdx = 0;
function present(start) {
  if (!state.slides.length) return;
  presentIdx = Math.max(0, start);
  $('#present').hidden = false;
  document.documentElement.requestFullscreen?.().catch(() => {});
  drawPresent();
}
function drawPresent() {
  mountScaled($('#present-host'), slideHTML(state.slides[presentIdx], false), window.innerWidth, window.innerHeight);
  $('#present-count').textContent = `${presentIdx + 1} / ${state.slides.length}`;
}
function stepPresent(dir) { presentIdx = Math.min(state.slides.length - 1, Math.max(0, presentIdx + dir)); drawPresent(); }
function exitPresent() { $('#present').hidden = true; if (document.fullscreenElement) document.exitFullscreen?.(); }

/* ---------------- PNG export ---------------- */
function loadScript(src) {
  return new Promise((res, rej) => { const s = document.createElement('script'); s.src = src; s.onload = res; s.onerror = rej; document.head.appendChild(s); });
}
async function exportPNG() {
  const s = slide();
  if (!s) return;
  toast('Rendering PNG…');
  try {
    if (!window.html2canvas) await loadScript('https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js');
    const host = document.createElement('div');
    host.style.cssText = `position:fixed;left:-99999px;top:0;width:${STAGE_W}px;height:${STAGE_H}px`;
    host.innerHTML = slideHTML(s, false);
    document.body.appendChild(host);
    await document.fonts?.ready;
    $$('img', host).forEach((i) => (i.loading = 'eager'));
    await Promise.all($$('img', host).map((i) => (i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; }))));
    const canvas = await window.html2canvas(host.firstElementChild, { useCORS: true, backgroundColor: '#07080c', scale: 1, width: STAGE_W, height: STAGE_H });
    host.remove();
    const a = document.createElement('a');
    a.download = (s.name || 'slide').replace(/[^\w-]+/g, '_') + '.png';
    a.href = canvas.toDataURL('image/png');
    a.click();
    toast('PNG saved. If card art is missing, the image host blocked export (CORS); use Present and take a screenshot.', 5000);
  } catch (err) {
    toast('PNG export failed: ' + (err.message || err) + '. Use Present mode and take a screenshot instead.', 7000);
  }
}

/* ---------------- views / global ---------------- */
function setView(v) {
  ui.view = v;
  $$('.tabs button').forEach((b) => b.classList.toggle('active', b.dataset.view === v));
  $$('.view').forEach((s) => s.classList.toggle('active', s.id === 'view-' + v));
  render();
}
function render() {
  updateBadge();
  if (ui.view === 'slides') renderSlides();
  else if (ui.view === 'decks') renderDecks();
  else if (ui.view === 'cards') renderCards();
  else if (ui.view === 'data') renderData();
}

function bindGlobal() {
  $$('.tabs button').forEach((b) => (b.onclick = () => setView(b.dataset.view)));
  $('#modal').addEventListener('click', (e) => { if (e.target === e.currentTarget || e.target.closest('[data-close]')) closeModal(); });
  $('#btn-present').onclick = () => present(Math.max(0, state.slides.indexOf(slide())));
  $('#btn-png').onclick = () => { if (ui.view !== 'slides') setView('slides'); exportPNG(); };
  $('#present').onclick = (e) => stepPresent(e.clientX < window.innerWidth / 3 ? -1 : 1);
  document.addEventListener('keydown', (e) => {
    if (!$('#present').hidden) {
      if (e.key === 'Escape') exitPresent();
      else if (['ArrowRight', ' ', 'PageDown'].includes(e.key)) stepPresent(1);
      else if (['ArrowLeft', 'PageUp'].includes(e.key)) stepPresent(-1);
      return;
    }
    if (e.key === 'Escape') { if (!$('#modal').hidden) closeModal(); else if (ui.selectedDeck) { ui.selectedDeck = null; render(); } }
  });
  document.addEventListener('fullscreenchange', () => { if (!$('#present').hidden) drawPresent(); });
  window.addEventListener('resize', () => { if (!$('#present').hidden) drawPresent(); else if (ui.view === 'slides') renderStage(); });

  $('#btn-export').onclick = () => {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(state, null, 2)], { type: 'application/json' }));
    a.download = 'tierlist-project.json';
    a.click();
  };
  $('#file-project').onchange = async (e) => {
    const f = e.target.files[0];
    if (!f) return;
    try {
      const data = JSON.parse(await f.text());
      if (data.version !== 2 || !Array.isArray(data.decks) || !Array.isArray(data.slides)) throw new Error('not a Tier List Studio v2 project');
      state = { ...makeDemo(), ...data };
      rebuildIndex(); nameIndex = null;
      ui.slideId = state.slides[0]?.id; ui.deckId = state.decks[0]?.id;
      save(); render(); toast('Project loaded.');
    } catch (err) { toast('Could not load: ' + err.message); }
    e.target.value = '';
  };
  $('#btn-reset').onclick = () => {
    if (!confirm('Replace everything with the demo project? Card data is kept.')) return;
    const catalog = state.catalog;
    state = makeDemo(); state.catalog = catalog;
    rebuildIndex(); nameIndex = null;
    ui.slideId = state.slides[0].id; ui.deckId = state.decks[0].id;
    save(); render();
    applySamples().then((did) => { if (did) { ui.slideId = state.slides[0].id; ui.deckId = state.decks[0].id; render(); } });
  };
}

$('#build').textContent = document.querySelector('meta[name=build]')?.content || '';
bindGlobal();
bindSlides();
bindDecks();
bindCards();
bindData();
render();
// First run: try to pull real cards straight away (works when the sim allows cross-origin reads).
// First run: load card data (a bundled data/catalog.json when hosted with one, else the sim directly),
// then swap the placeholder demo for real sample decks.
(async () => {
  if (state.catalog && state.catalog.schema !== CATALOG_SCHEMA) {
    try { await loadCatalogFromSim(); } catch { /* keep the older copy */ }
  }
  if (!state.catalog) {
    try {
      const r = await fetch('data/catalog.json');
      if (!r.ok) throw new Error();
      applyCatalog(await r.json(), 'bundled snapshot of the Cyberpunk TCG Sim catalog');
    } catch {
      try { await loadCatalogFromSim(); } catch { return; }
    }
    toast(`Loaded ${state.catalog.cards.length} cards.`);
  }
  if (await applySamples()) { ui.slideId = state.slides[0]?.id; ui.deckId = state.decks[0]?.id; toast('Loaded sample decks with real cards.'); }
  render();
})();
