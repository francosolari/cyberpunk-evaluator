/* Tier List Studio — Cyberpunk TCG tier list & deck page slide maker.
 * Plain JS, no build step. Card data comes from the Cyberpunk TCG Sim public catalog
 * (the same /api/cards/catalog the cyberpunk-tcg-tracker uses). Decks come from deck exports. */
'use strict';

const STORE_KEY = 'cp-tierlist-studio-v2';
const SIM_ORIGIN = 'https://cyberpunk-tcg-sim.online';
const CATALOG_URL = `${SIM_ORIGIN}/api/cards/catalog`;
const LEADERBOARD_URL = `${SIM_ORIGIN}/api/ranked/leaderboard`;
const STAGE_W = 1920, STAGE_H = 1080;
const CATALOG_SCHEMA = 3; // 2 added rules text, 3 collector numbers; older saved catalogs are refreshed once
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

function toast(msg, ms = 3200, action = null) {
  const t = $('#toast');
  t.textContent = msg;
  if (action) {
    const b = document.createElement('button');
    b.className = 'small toast-action';
    b.textContent = action.label;
    b.onclick = () => { t.hidden = true; action.run(); };
    t.append(' ', b);
  }
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
/** Seed decks: data/seed-decks.txt (deck exports separated by ---, with optional "# Tier:" and
 * "# Notes:" lines), falling back to the built-in starters. */
async function loadSeeds() {
  let blocks;
  try {
    const r = await fetch('data/seed-decks.txt', { cache: 'no-cache' });
    if (!r.ok) throw new Error();
    blocks = (await r.text()).split(/^\s*-{3,}\s*$/m);
  } catch { blocks = SAMPLE_DECKS; }
  return blocks.map((text) => {
    const tier = text.match(/^#\s*Tier:\s*(.+)$/im)?.[1].trim();
    const notes = text.match(/^#\s*Notes:\s*(.+)$/im)?.[1].trim();
    const d = parseDeckExport(text.replace(/^#\s*(Tier|Notes):.*$/gim, ''));
    d.notes = notes || SAMPLE_NOTES[d.name] || '';
    d.sample = true;
    d.seedTier = tier;
    return d;
  }).filter((d) => d.legends.some(Boolean));
}
async function applySamples() {
  if (!state.catalog || !state.decks.some(isDemoDeck)) return false;
  const decks = await loadSeeds();
  try {
    const r = await fetch(LEADERBOARD_URL, { credentials: 'omit' });
    if (r.ok) {
      for (const t of topTrios(await r.json(), 14)) {
        if (decks.some((d) => d.legends.slice().sort().join('+') === t.key)) continue;
        const d = newDeck({ legends: t.key.split('+'), notes: `${t.games} ranked games on the sim leaderboard`, sample: true, fromLeaderboard: true });
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
    tierSlide.tiers.forEach((t) => (t.deckIds = []));
    const byName = (name) => tierSlide.tiers.find((t) => norm(t.name) === norm(name || ''));
    // Seeds with a "# Tier:" line go there; the rest (and leaderboard trios) fill tiers in order.
    const placed = decks.filter((d) => byName(d.seedTier));
    placed.forEach((d) => byName(d.seedTier).deckIds.push(d.id));
    const rest = decks.filter((d) => !placed.includes(d) && !d.fromLeaderboard); // leaderboard trios start unranked
    rest.forEach((d, i) => { const t = tierSlide.tiers[Math.min(tierSlide.tiers.length - 1, Math.floor(i / 4))]; if (t.deckIds.length < 6) t.deckIds.push(d.id); });
  }
  decks.forEach((d) => { delete d.seedTier; delete d.fromLeaderboard; });
  state.slides = state.slides.filter((x) => x.type !== 'deck' || !gone.has(x.deckId));
  const heist = decks.find((d) => d.main.length) || decks[0];
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
  return { id: uid(), createdAt: Date.now(), name: '', label: '', subtitle: '', legends: [null, null, null], keyCard: null, main: [], side: [], options: [], notes: '', display: 'inherit', ...p };
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
// Browsers allow roughly 5 million characters per site. Warn well before that.
const STORAGE_WARN = 3500000;
let storageWarned = false;
function save() {
  if (ui.viewing) return; // a shared link never writes to this browser's own studio
  const json = JSON.stringify(state);
  try { localStorage.setItem(STORE_KEY, json); }
  catch { return toast('Browser storage is full, so this change wasn\'t saved. Save the project as a file (Project → Save project), then remove the logo upload or old decks.', 8000); }
  if (json.length > STORAGE_WARN && !storageWarned) {
    storageWarned = true;
    toast(`Browser storage is ${Math.round((json.length / 5e6) * 100)}% full. Save the project as a file to back it up.`, 7000);
  }
}

/* ---------------- cards & catalog ---------------- */
function rebuildIndex() {
  cardIndex = new Map();
  for (const c of state.catalog?.cards || []) cardIndex.set(c.id, c);
  state.custom = (state.custom || []).filter((c) => c.demo); // custom card images aren't supported
  for (const c of state.custom) cardIndex.set(c.id, c);
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
      // Collector number and set, used to read the sim's compact deck codes (e.g. w32 = #110).
      num: collectorNumber(c),
      set: String(c.set_code || c.set || c.set_name || '').toLowerCase(),
      codes,
    });
  }
  return out;
}

function collectorNumber(c) {
  for (const k of ['collector_number', 'collectorNumber', 'card_number', 'cardNumber', 'number', 'set_number', 'setNumber', 'collector_no', 'code']) {
    const v = c?.[k];
    const m = typeof v === 'number' ? [String(v), String(v)] : typeof v === 'string' && v.match(/(\d{1,4})[a-z]?$/i);
    if (m) return parseInt(m[1], 10);
  }
  return null;
}

/* The sim's deck-image QR code links to its deck builder with a compact code:
 *   …/deck-builder/?d=l.w2.w5-a.w32.d.3_w6.3_wt…s.3_w7.2_wv
 * "l." Legends, "d." deck, "s." sideboard; entries are count_card, and a card is a set letter plus
 * the collector number in base 36 (w32 = Welcome to Night City #110), "-a" marking alternate art.
 * Returns sim text export lines with card ids, or null if the text isn't such a link. */
function decodeSimDeckCode(text) {
  const m = String(text).match(/[?&]d=([a-z0-9._\-]+)/i);
  if (!m || !/(^|\.)l\./.test(m[1])) return null;
  const byCode = new Map();
  for (const c of allCards()) if (c.num != null) {
    const letter = (c.set || '')[0] || '';
    const key = letter + ':' + c.num;
    if (!byCode.has(key)) byCode.set(key, c); // first printing wins; alternate arts share the number
  }
  const lookup = (code) => {
    const mm = code.match(/^([a-z])([0-9a-z]+?)(?:-[a-z0-9]+)?$/i);
    if (!mm) return code;
    const n = parseInt(mm[2], 36);
    const hit = byCode.get(mm[1].toLowerCase() + ':' + n) || [...byCode.entries()].find(([k]) => k.endsWith(':' + n))?.[1];
    return hit ? hit.id : `${code} (#${n})`;
  };
  const out = { l: [], d: [], s: [] };
  let section = null;
  for (const tok of m[1].split('.')) {
    if (tok === 'l' || tok === 'd' || tok === 's') { section = tok; continue; }
    if (!section || !tok) continue;
    const [, n, code] = tok.match(/^(?:(\d+)_)?(.+)$/);
    out[section].push(`${section === 'l' ? 1 : n || 1}x ${lookup(code)}`);
  }
  return ['#L', ...out.l, '', '#D', ...out.d, ...(out.s.length ? ['', '#S', ...out.s] : [])].join('\n');
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
function resolveCard(name, { legend = false } = {}) {
  if (!nameIndex) buildNameIndex();
  const n = norm(name);
  if (!n) return null;
  if (nameIndex.exact.has(n)) return nameIndex.exact.get(n);
  // "Panam Palmer" vs "Panam Palmer, Nomad Cavalry": accept a unique prefix match either way
  let hits = nameIndex.list.filter(([k]) => k.startsWith(n) || n.startsWith(k));
  // Under a Legends header, "Goro Takemura" means the Legend, not a unit with the same name.
  if (legend && hits.length > 1) {
    const legends = hits.filter(([, id]) => isLegend(card(id)));
    if (legends.length) hits = legends.sort((a, b) => a[0].length - b[0].length).slice(0, 1);
  }
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
  const fromLink = decodeB64Deck(text) || decodeSimDeckCode(text);
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
      if (/^(o|options?|considering|maybe(board)?)$/.test(head)) { section = 'options'; continue; }
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
    const id = resolveCard(e.name, { legend: e.section === 'legend' });
    if (!id) { d.unmatched.push(e); continue; }
    if (e.section === 'legend' || isLegend(card(id))) { if (!legends.includes(id)) legends.push(id); continue; }
    add(e.section === 'side' ? d.side : e.section === 'options' ? d.options : d.main, id, e.qty);
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
/** Legends in display order: the most common color first and kept together (Y, Y, B, not Y, B, Y). */
function legendsOf(d) {
  const ids = d.legends.filter(Boolean);
  const count = {};
  ids.forEach((id) => { const c = card(id)?.color || '?'; count[c] = (count[c] || 0) + 1; });
  const rank = (id) => { const c = card(id)?.color || '?'; return [-count[c], COLOR_ORDER.indexOf(c) < 0 ? 9 : COLOR_ORDER.indexOf(c)]; };
  return ids.map((id, i) => [id, i]).sort((a, b) => { const x = rank(a[0]), y = rank(b[0]); return x[0] - y[0] || x[1] - y[1] || a[1] - b[1]; }).map(([id]) => id);
}
function deckColors(d) {
  const cols = legendsOf(d).map((id) => card(id)?.color).filter(Boolean);
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
  const legends = legendsOf(d).map(card);
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
  return `<div class="deck-tile ${sel}" draggable="false" tabindex="0" role="button" aria-label="${esc(label + (d.name && d.name !== label ? ', ' + d.name : ''))}" data-deck="${d.id}" title="${esc(d.name || label)}" style="${style}">
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

function tierGeom(s) {
  const tableH = STAGE_H - TL.top - (s.footnote ? TL.bottom + 20 : TL.bottom - 20);
  const rowH = (tableH - (s.tiers.length - 1) * TL.rowGap) / Math.max(1, s.tiers.length);
  return { tableH, rowH, areaW: STAGE_W - TL.x * 2 - TL.head - TL.pad * 2, areaH: rowH - TL.pad * 2 };
}
const tileSize = (n, g) => { const w = Math.min(fitTiles(n, g.areaW, g.areaH, TL.tileGap), 250); return [w, Math.floor(w / TILE_ASPECT)]; };
function tierSlideHTML(s, editing) {
  const tiers = s.tiers;
  const { tableH, rowH, areaW, areaH } = tierGeom(s);
  const rows = tiers.map((t) => {
    const ds = t.deckIds.map(deck).filter(Boolean);
    const w = Math.min(fitTiles(ds.length, areaW, areaH, TL.tileGap), 250);
    const tiles = ds.map((d) => deckTileHTML(d, s.display, { style: `width:${w}px;height:${Math.floor(w / TILE_ASPECT)}px`, selectable: editing, showName: s.showNames })).join('');
    const nameSize = Math.min(64, Math.max(30, rowH * 0.3));
    return `<div class="tier-row" data-tier="${t.id}" style="--t:${esc(t.color)};--tt:${esc(t.color)}40;height:${rowH}px">
      <div class="tier-head">
        <div class="tier-name" style="font-size:${nameSize}px"><span>${esc(t.name)}</span></div>
        ${t.desc && rowH > 120 ? `<div class="tier-desc">${esc(t.desc)}</div>` : ''}
      </div>
      <div class="tier-decks" data-drop="${t.id}">${tiles || (editing ? '<span class="drop-hint">Drop decks here</span>' : '')}</div>
    </div>`;
  }).join('');
  return `<div class="stage tier-slide look-${esc(s.look || 'ledger')}">
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
  const legends = legendsOf(d).map((id) => {
    const c = card(id);
    const [main, ...rest] = (c?.name || '—').split(/,\s*|\s+[—–-]\s+/);
    return `<figure class="ds-legend" style="--c:${hexOf(c)};--ca:${hexOf(c)}66">${artHTML(c)}<figcaption><b>${esc(main)}</b><span>${esc(rest.join(', '))}</span></figcaption></figure>`;
  }).join('');
  const rows = d.main.map(([id, n]) => [card(id), n]).filter(([c]) => c);
  const groups = typeGroups(rows);
  const total = rows.reduce((t, [, n]) => t + n, 0);
  // Compact rows when the grouped list wouldn't fit under the notes and breakdown.
  const extras = extraRows(d, s);
  const lines = groups.reduce((t, g) => t + Math.ceil(g.rows.length / 2), 0) + Math.ceil(extras.length / 2);
  const many = lines * 66 + (groups.length + (extras.length ? 1 : 0)) * 48 > (d.notes ? 640 : 770);
  const rowHTML = ([c, n]) => `<div data-card="${c.id}" data-zone="${d.roles?.[c.id] || 'deck'}" class="ds-row ${isKey(d, c.id) ? 'is-key' : ''}" style="--c:${hexOf(c)};--ca:${hexOf(c)}40">
      ${artHTML(c, { cls: 'ds-row-art' })}
      <span class="ds-cost">${c.cost ?? '·'}</span><span class="ds-name">${esc(c.name)}</span>${roleTag(s, d, c.id)}<span class="ds-n">${n}×</span>
    </div>`;
  const extraHTML = ([c, n, zone]) => `<div data-card="${c.id}" data-zone="${zone}" class="ds-row is-extra" style="--c:${hexOf(c)};--ca:${hexOf(c)}40">
      ${artHTML(c, { cls: 'ds-row-art' })}
      <span class="ds-cost">${c.cost ?? '·'}</span><span class="ds-name">${esc(c.name)}</span><span class="ds-n">${n}×</span>
    </div>`;
  const list = groups.map((g) => `<div class="ds-group"><span>${esc(g.label)}</span><b>${g.count}</b></div>${g.rows.map(rowHTML).join('')}`).join('') +
    (extras.length ? `<div class="ds-group extra"><span>${EXTRA_LABEL}</span><b>${extras.reduce((t, r) => t + r[1], 0)}</b></div>${extras.map(extraHTML).join('')}` : '');
  const breakdown = total ? breakdownHTML(groups) : '';
  return `<div class="stage deck-slide">
    <div class="glow g1" style="background:radial-gradient(closest-side, ${hexOf(card(legendsOf(d)[0]))}38, transparent)"></div><div class="glow g2"></div>
    <header class="ds-head">
      <div class="ds-eyebrow">${tier ? `<span class="pill tier-pill" style="--t:${esc(tier.color)}">${esc(tier.name)}</span>` : ''}<span class="chips">${chips(cols, 'chip-lg')}</span>${d.main.length ? `<span class="ds-meta">${deckCount(d)} cards</span>` : ''}${missingNote(d)}</div>
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
/** Cards in a deck that the current card data doesn't know (renamed, removed, or data not loaded). */
const missingCount = (d) => [...d.main, ...(d.side || []), ...(d.options || [])].filter(([id]) => !card(id)).length + d.legends.filter((id) => id && !card(id)).length + (d.unmatched || []).length;
const missingNote = (d) => { const n = missingCount(d); return n ? `<span class="missing-note">${n} card${n > 1 ? 's' : ''} not in the current card data</span>` : ''; };
/** Sideboard and options shown together as one "Sideboard / Options" section. Rows: [card, n, zone]. */
function extraRows(d, s = {}) {
  if (s.showOptions === false) return [];
  const rows = [...(d.side || []).map(([id, n]) => [card(id), n, 'side']), ...(d.options || []).map(([id, n]) => [card(id), n, 'options'])].filter(([c]) => c);
  return rows.sort((a, b) => (a[0].cost ?? 99) - (b[0].cost ?? 99) || a[0].name.localeCompare(b[0].name));
}
const EXTRA_LABEL = 'Sideboard / Options';
const roleTag = (s, d, id) => (s.showRoles !== false && d.roles?.[id] ? `<span class="role ${d.roles[id]}">${d.roles[id] === 'core' ? 'Core' : 'Flex'}</span>` : '');
/** Type counts as one plain line: "16 Units · 13 Gear · 7 Programs". */
const breakdownHTML = (groups, cls = '') => `<div class="ds-breakdown-line ${cls}">${groups.map((g) => `<span><b>${g.count}</b> ${esc(g.label)}</span>`).join('<i>·</i>')}</div>`;
const deckEyebrow = (d) => {
  const tier = tierOf(d);
  return `${tier ? `<span class="pill tier-pill" style="--t:${esc(tier.color)}">${esc(tier.name)}</span>` : ''}<span class="chips">${chips(deckColors(d), 'chip-lg')}</span>${d.main.length ? `<span class="ds-meta">${deckCount(d)} cards</span>` : ''}`;
};

/** Full decklist as cards, modelled on the official deck builder's deck view: Legends in a column,
 * the main deck as sections of full cards with copy counts, and options/sideboard along the bottom.
 * Sections are card types (Core cards first, Flex last) or, with groupBy 'role', Core / Flex / Options. */
function deckStacksSlideHTML(s, d) {
  const rowsOf = (list) => (list || []).map(([id, n]) => [card(id), n]).filter(([c]) => c);
  const mainRows = rowsOf(d.main);
  const typeSecs = typeGroups(mainRows);
  const roleOf = (c) => d.roles?.[c.id] || '';
  // Always split by card type; within a type, Core cards first and Flex cards last.
  const byRole = (rows) => rows.slice().sort((a, b) => ({ core: 0, '': 1, flex: 2 }[roleOf(a[0])]) - ({ core: 0, '': 1, flex: 2 }[roleOf(b[0])]));
  const sections = typeSecs.map((g) => ({ ...g, rows: byRole(g.rows) }));
  const extras = extraRows(d, s);
  const strip = extras.length ? [{ label: EXTRA_LABEL, rows: extras }] : [];
  sections.forEach((x) => (x.count = x.rows.reduce((t, r) => t + r[1], 0)));
  const legends = legendsOf(d).map(card).filter(Boolean);
  const X = 70, TOP = 214, BOTTOM = 1080 - 40, gap = 14, label = 44;
  const stripH = strip.length ? 190 : 0;
  const bodyH = BOTTOM - TOP - stripH - label;
  // Legends: stacked in one column running the full height (the bottom strip sits under the deck grid).
  const legH = BOTTOM - TOP - label;
  const lh = legends.length ? Math.floor((legH - (legends.length - 1) * gap) / legends.length) : 0;
  const lw = Math.floor(lh * CARD_ASPECT);
  const deckX = X + (lw ? lw + 56 : 0);
  const deckW = 1920 - X - deckX;
  // Sections side by side. Try every split of columns between them; keep the biggest cards.
  const SG = 40; // gap between sections
  const counts = sections.map((g) => g.rows.length);
  let best = { w: 0, cols: counts.map(() => 1) };
  const tryCols = (cols) => {
    const T = cols.reduce((a, b) => a + b, 0);
    const maxRows = Math.max(...counts.map((n, i) => Math.ceil(n / cols[i])));
    const byW = (deckW - (T - cols.length) * gap - (cols.length - 1) * SG) / T;
    const byH = ((bodyH - (maxRows - 1) * gap) / maxRows) * CARD_ASPECT;
    const w = Math.min(byW, byH);
    if (w > best.w) best = { w, cols: cols.slice() };
  };
  const walk = (i, cols) => {
    if (i === counts.length) return counts.length && tryCols(cols);
    for (let c = 1; c <= counts[i]; c++) { cols[i] = c; walk(i + 1, cols); }
  };
  walk(0, []);
  const w = Math.floor(best.w), h = Math.floor(w / CARD_ASPECT);
  const gridH = Math.max(0, ...counts.map((n, i) => Math.ceil(n / best.cols[i]))) * (h + gap) - gap;
  const stripTop = Math.min(TOP + label + gridH + 28, BOTTOM - stripH + 10); // right under the grid
  const sw = Math.floor((stripH - label - 6) * CARD_ASPECT);
  const cardHTML = (c, n, width, height, extra = '', typeColor = '', option = false, zone = d.roles?.[c.id] || 'deck') => `<div ${n ? `data-card="${c.id}" data-zone="${zone}"` : ''} class="fd-card ${MAIN_ZONES.includes(zone) && isKey(d, c.id) ? 'is-key' : ''} ${MAIN_ZONES.includes(zone) && roleOf(c) === 'flex' ? 'is-flex' : ''} ${extra}" style="width:${width}px;height:${height}px${typeColor ? `;--k:${typeColor}` : ''}">
      ${artHTML(c, { full: true })}${n ? `<span class="fd-n"><small>×</small>${n}</span>` : ''}${n && MAIN_ZONES.includes(zone) ? roleTag(s, d, c.id) : ''}${n && MAIN_ZONES.includes(zone) && isKey(d, c.id) ? '<span class="fd-key">Key</span>' : ''}</div>`;
  const total = deckCount(d);
  return `<div class="stage deck-slide deck-full">
    <div class="glow g1" style="background:radial-gradient(closest-side, ${hexOf(legends[0])}38, transparent)"></div><div class="glow g2"></div>
    <header class="fd-head">
      <div class="fd-title">
        <h1>${esc(d.name && d.name !== deckLabel(d) ? d.name : deckLabel(d))}</h1>
        <div class="fd-meta">${(() => { const t = tierOf(d); return t ? `<span class="pill tier-pill" style="--t:${esc(t.color)}">${esc(t.name)}</span>` : ''; })()}
          <span class="fd-code">${esc(deckLabel(d))}</span><span class="chips">${chips(deckColors(d), 'chip-lg')}</span>
          ${missingNote(d)}<span class="ds-meta">${total} cards · ${legends.length} Legends${extras.length ? ` · ${extras.reduce((t, r) => t + r[1], 0)} sideboard / options` : ''}</span></div>
      </div>
      ${typeSecs.length ? breakdownHTML(typeSecs, 'compact') : ''}
    </header>
    ${legends.length ? `<section class="fd-legends" style="left:${X}px;top:${TOP}px;width:${lw}px">
      <div class="fd-label">Legends <b>${legends.length}</b></div>
      <div class="fd-col">${legends.map((c) => cardHTML(c, 0, lw, lh, 'is-legend', hexOf(c))).join('')}</div></section>
      <div class="fd-rule" style="left:${X + lw + 28}px;top:${TOP}px;height:${legH + label}px"></div>` : ''}
    <div class="fd-deck" style="left:${deckX}px;top:${TOP}px;width:${deckW}px">
      ${sections.map((g, i) => `<section class="fd-section">
        <div class="fd-label" style="--k:${g.color}">${esc(g.label)} <b>${g.count}</b></div>
        <div class="fd-grid" style="grid-template-columns:repeat(${best.cols[i]}, ${w}px)">${g.rows.map(([c, n]) => cardHTML(c, n, w, h)).join('')}</div>
      </section>`).join('') || '<div class="ds-nolist">Import a deck export to show the decklist.</div>'}
    </div>
    ${strip.length ? `<div class="fd-strip" style="left:${deckX}px;top:${stripTop}px">${strip.map((x) => `<section>
      <div class="fd-label">${x.label} <b>${x.rows.reduce((t, r) => t + r[1], 0)}</b></div>
      <div class="fd-row">${x.rows.map(([c, n, zone]) => cardHTML(c, n, sw, Math.floor(sw / CARD_ASPECT), 'is-small', '', false, zone)).join('')}</div></section>`).join('')}</div>` : ''}
  </div>`;
}

// Main-deck cards by type (Units, Gear, Programs, then anything else), each sorted by cost.
// Neutral on purpose: cards already carry their own colors, so types aren't color-coded.
const TYPE_INK = '#4a5263';
const TYPE_GROUPS = [['unit', 'Units', TYPE_INK], ['gear', 'Gear', TYPE_INK], ['program', 'Programs', TYPE_INK]];
function typeGroups(rows) {
  const out = TYPE_GROUPS.map(([key, label, color]) => ({ key, label, color, rows: [], count: 0 }));
  for (const [c, n] of rows) {
    let g = out.find((x) => (c.type || '').toLowerCase().includes(x.key));
    if (!g) {
      const label = c.type ? c.type.replace(/^./, (ch) => ch.toUpperCase()) + 's' : 'Other';
      g = out.find((x) => x.label === label) || out[out.push({ key: label, label, color: TYPE_INK, rows: [], count: 0 }) - 1];
    }
    g.rows.push([c, n]);
    g.count += n;
  }
  out.forEach((g) => g.rows.sort((a, b) => (a[0].cost ?? 99) - (b[0].cost ?? 99) || a[0].name.localeCompare(b[0].name)));
  return out.filter((g) => g.count);
}

const slideHTML = (s, editing = false) => (!s ? '<div class="stage"></div>' : s.type === 'deck' ? deckSlideHTML(s) : tierSlideHTML(s, editing));

function mountScaled(host, html, boxW, boxH) {
  // Only rebuild when the slide actually changed; rebuilding reloads every card image (flicker).
  if (host._html !== html) { host.innerHTML = html; host._html = html; }
  scaleStage(host, boxW, boxH);
}
function scaleStage(host, boxW, boxH) {
  const scale = Math.min(boxW / STAGE_W, boxH / STAGE_H);
  host.style.width = STAGE_W * scale + 'px';
  host.style.height = STAGE_H * scale + 'px';
  const st = host.firstElementChild;
  if (st) st.style.transform = `scale(${scale})`;
}

/* ---------------- Slides view ---------------- */
function renderSlides() {
  if (!slide()) ui.slideId = state.slides[0]?.id;
  renderGuide();
  renderSlideList();
  renderPool();
  renderSlideBoard();
  renderStage();
  renderSlideInspector();
}
function renderSlideList() {
  $('#slide-list').innerHTML = state.slides.map((x, i) => `
    <li data-slide="${x.id}" class="${x.id === ui.slideId ? 'active' : ''}">
      <span class="t"><span class="nm">${i + 1}. ${esc(x.name || 'Slide')}</span><span class="k">${x.type === 'deck' ? 'Deck page' : 'Tier list'}</span></span>
      <button data-move="-1" title="Move up" aria-label="Move slide up">↑</button><button data-move="1" title="Move down" aria-label="Move slide down">↓</button><button data-del-slide title="Delete" aria-label="Delete slide">×</button>
    </li>`).join('');
}
function stageBox() {
  const wrap = $('#stage-wrap');
  const narrow = window.innerWidth <= 900; // stacked layout: fit to width, let the page scroll
  return [Math.max(200, wrap.clientWidth - 28), narrow ? Infinity : Math.max(120, wrap.clientHeight - 28)];
}
function renderStage() {
  mountScaled($('#stage-host'), slideHTML(slide(), true), ...stageBox());
}
function renderPool() {
  const s = slide();
  const pw = $('.pool-wrap');
  if (!s || s.type !== 'tier') { pw.hidden = true; return; }
  pw.hidden = false;
  const ranked = new Set(s.tiers.flatMap((t) => t.deckIds));
  const all = state.decks.filter((d) => !ranked.has(d.id));
  const q = prefs().poolQuery;
  $('#pool-q').value = q;
  $('#pool-count').textContent = all.length ? `(${all.length})` : '';
  const pool = sortDecks(all.filter((d) => deckMatches(d, q)), 'name');
  const groups = pool.length > 8 ? groupDecks(pool, 'color') : [{ label: '', decks: pool }];
  $('#pool').classList.toggle('compact', pool.length > 12);
  $('#pool').innerHTML = pool.length ? groups.map((g) => `<div class="pgroup">${g.label ? `<span class="pg-label" style="--g:${g.color}">${esc(g.label)} <b>${g.decks.length}</b></span>` : ''}
      ${g.decks.map((d) => deckTileHTML(d, s.display, { showName: true })).join('')}</div>`).join('')
    : `<span class="hint">${all.length ? 'No unranked decks match.' : 'Every deck is ranked. Drag one here to unrank it, or import more decks in the Decks tab.'}</span>`;
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
      <p class="hint">Tap a card on the slide to change it, or edit the list below the slide.</p>
      <details class="more" data-more="deckpage" ${prefs().open?.['deckpage'] ? 'open' : ''}><summary>More options</summary>
      <label class="check"><input type="checkbox" data-s="showRoles" ${s.showRoles !== false ? 'checked' : ''}> Show Core / Flex tags</label>
      <label class="check"><input type="checkbox" data-s="showOptions" ${s.showOptions !== false ? 'checked' : ''}> Show sideboard / options</label>
      <button data-edit-deck="${s.deckId}" class="block">Open in the Decks tab</button></details>`;
    return;
  }
  el.innerHTML = `<h3>Tier list</h3>
    <label>Title</label><input data-s="title" value="${esc(s.title)}">
    <label>Subtitle</label><input data-s="pill" value="${esc(s.pill)}" placeholder="e.g. Beta format · Oct 2026">
    <label>Deck tiles show</label>
    <select data-s="display">${Object.entries(DISPLAY_MODES).map(([k, v]) => `<option value="${k}" ${k === s.display ? 'selected' : ''}>${v}</option>`).join('')}</select>
    <details class="more" data-more="tierlist" ${prefs().open?.['tierlist'] ? 'open' : ''}><summary>More options</summary>
    <label>Brand</label><input data-s="eyebrow" value="${esc(s.eyebrow)}" placeholder="Plus Two">
    <label>Footnote</label><input data-s="footnote" value="${esc(s.footnote)}" placeholder="optional">
    <label>Style</label>
    <select data-s="look">${[['ledger', 'Ledger'], ['band', 'Band'], ['frame', 'Frame'], ['rail', 'Rail']].map(([k, v]) => `<option value="${k}" ${(s.look || 'ledger') === k ? 'selected' : ''}>${v}</option>`).join('')}</select>
    <label class="check"><input type="checkbox" data-s="showNames" ${s.showNames ? 'checked' : ''}> Show deck names under codes</label>
    <label>Logo</label>
    <div class="row gap"><input data-s="logo" value="${esc(s.logo?.startsWith('data:') ? '(uploaded)' : s.logo)}" placeholder="https://…" style="flex:1">
      <label class="filebtn">Upload<input type="file" accept="image/*" data-upload-logo hidden></label></div></details>
    <h3 style="margin-top:20px">Tiers <span class="hint">(${s.tiers.length})</span></h3>
    <div id="tier-edits">${s.tiers.map((t) => `<div class="tier-edit" data-tier-edit="${t.id}" style="--t:${esc(t.color)}">
      <div class="row gap"><input type="color" data-t="color" value="${esc(t.color)}" aria-label="Tier color"><input data-t="name" value="${esc(t.name)}" style="flex:1" aria-label="Tier name">
      <button class="small" data-tmove="-1" title="Move up" aria-label="Move tier up">↑</button><button class="small" data-tmove="1" title="Move down" aria-label="Move tier down">↓</button><button class="small danger" data-tdel title="Remove tier" aria-label="Remove tier">×</button></div>
      <textarea data-t="desc" rows="2" placeholder="Description (optional)">${esc(t.desc)}</textarea>
    </div>`).join('')}</div>
    <div class="row gap tier-actions"><button data-tadd>+ Add tier</button><button data-tclear ${s.tiers.some((t) => t.deckIds.length) ? '' : 'disabled'}>Clear tier list</button></div>
    <details class="more" data-more="presets" ${prefs().open?.['presets'] ? 'open' : ''}><summary>Tier presets</summary>
    <label>Start from a preset</label>
    <div class="row gap">${Object.keys(TIER_PRESETS).map((k) => `<button class="small" data-preset="${esc(k)}">${esc(k)}</button>`).join('')}</div>
    <p class="hint">Presets rename and recolor tiers and keep your rankings in order. Decks in removed tiers go back to Unranked.</p></details>`;
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
  renderSlideBoard();
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
  $('#pool-q').oninput = (e) => { prefs().poolQuery = e.target.value; renderPool(); };
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
    else if ('tclear' in b.dataset) {
      // Moves every deck back to Unranked; tiers and decks stay. Undo restores the placement.
      const before = s.tiers.map((t) => t.deckIds.slice());
      s.tiers.forEach((t) => (t.deckIds = []));
      toast('Tier list cleared. All decks are back in Unranked.', 7000, { label: 'Undo', run: () => { s.tiers.forEach((t, i) => (t.deckIds = before[i] || [])); save(); renderSlides(); } });
    }
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

  // Deck tiles: drag with mouse or finger (see enableDeckDrag). Tap selects a deck to edit its list.
  for (const z of [$('#stage-host'), $('#pool')]) {
    z.addEventListener('click', (e) => {
      const cardEl = e.target.closest('[data-card]');
      if (ui.viewing) return;
      if (cardEl && slide()?.type === 'deck') { e.stopPropagation(); openCardMenu(deck(slide().deckId), cardEl.dataset.card, e.clientX, e.clientY, cardEl.dataset.zone); return; }
      const tile = e.target.closest('.deck-tile');
      if (!tile) return;
      selectDeck(ui.selectedDeck === tile.dataset.deck ? null : tile.dataset.deck);
    });
  }
}
/* Keyboard: on a focused deck tile, ↑/↓ move it to the tier above/below (↓ from the last tier, or
 * Delete, unranks it), ←/→ reorder it within its tier, Enter selects it to edit its list. */
function bindDeckKeys() {
  document.addEventListener('keydown', (e) => {
    const tile = e.target.closest?.('#stage-host .deck-tile, #pool .deck-tile');
    const s = slide();
    if (!tile || s?.type !== 'tier' || ui.viewing) return;
    const id = tile.dataset.deck;
    const tierIdx = s.tiers.findIndex((t) => t.deckIds.includes(id)); // -1 = unranked
    let handled = true;
    if (e.key === 'Enter' || e.key === ' ') selectDeck(ui.selectedDeck === id ? null : id);
    else if (e.key === 'ArrowUp') { if (tierIdx !== 0) moveDeck(id, s.tiers[tierIdx < 0 ? s.tiers.length - 1 : tierIdx - 1].id); }
    else if (e.key === 'ArrowDown') moveDeck(id, tierIdx >= 0 && tierIdx < s.tiers.length - 1 ? s.tiers[tierIdx + 1].id : 'pool');
    else if (e.key === 'Delete' || e.key === 'Backspace') moveDeck(id, 'pool');
    else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && tierIdx >= 0) {
      const ids = s.tiers[tierIdx].deckIds, i = ids.indexOf(id), j = i + (e.key === 'ArrowLeft' ? -1 : 1);
      if (j >= 0 && j < ids.length) { [ids[i], ids[j]] = [ids[j], ids[i]]; save(); renderStage(); }
    } else handled = false;
    if (!handled) return;
    e.preventDefault();
    markGuide('ranked');
    $(`#stage-host .deck-tile[data-deck="${id}"], #pool .deck-tile[data-deck="${id}"]`)?.focus();
  });
}

/** Selecting only toggles a class: rebuilding the slide would reload every card image. */
function selectDeck(id) {
  ui.selectedDeck = id;
  $$('#stage-host .deck-tile, #pool .deck-tile').forEach((t) => t.classList.toggle('selected', t.dataset.deck === id));
  syncStageCache();
  renderSlideBoard();
}
/** After changing the slide's DOM in place, record its HTML so the next render doesn't rebuild it. */
function syncStageCache() {
  const s = slide();
  if (s) $('#stage-host')._html = slideHTML(s, true);
}
/** Resize tiles in each tier row to fit their count (same rule as tierSlideHTML). */
function relayoutTiers() {
  const s = slide();
  if (!s || s.type !== 'tier') return;
  const g = tierGeom(s);
  $$('#stage-host .tier-decks').forEach((row) => {
    const tiles = $$('.deck-tile', row);
    const [w, h] = tileSize(tiles.length, g);
    tiles.forEach((t) => { t.style.width = w + 'px'; t.style.height = h + 'px'; });
    row.querySelector('.drop-hint')?.remove();
    if (!tiles.length) row.insertAdjacentHTML('beforeend', '<span class="drop-hint">Drop decks here</span>');
  });
}
/** Writes tier order back from the DOM after a drag. */
function commitTiersFromDom() {
  const s = slide();
  markGuide('ranked');
  for (const t of s.tiers) {
    const row = $(`#stage-host [data-drop="${t.id}"]`);
    if (row) t.deckIds = $$('.deck-tile', row).map((x) => x.dataset.deck);
  }
  save();
  syncStageCache();
  $('#pool-count').textContent = (() => { const r = new Set(s.tiers.flatMap((t) => t.deckIds)); const n = state.decks.filter((d) => !r.has(d.id)).length; return n ? `(${n})` : ''; })();
}

/* Dragging deck tiles on a tier list: the tile follows the pointer and the other tiles slide
 * aside to show where it will land. Mouse starts after a small move; touch after a short hold. */
function enableDeckDrag() {
  let st = null;
  let lastDrop = 0;
  const scale = () => $('#stage-host').getBoundingClientRect().width / STAGE_W;
  // FLIP: record positions, change the DOM, then animate every tile from its old spot.
  const flip = (change) => {
    const tiles = $$('#stage-host .deck-tile, #pool .deck-tile').filter((t) => t !== st?.el);
    const before = new Map(tiles.map((t) => [t, t.getBoundingClientRect()]));
    change();
    const k = scale() || 1;
    for (const t of tiles) {
      const a = before.get(t), b = t.getBoundingClientRect();
      const dx = a.left - b.left, dy = a.top - b.top;
      if (!dx && !dy) continue;
      const inStage = !!t.closest('#stage-host');
      t.style.transition = 'none';
      t.style.transform = `translate(${inStage ? dx / k : dx}px, ${inStage ? dy / k : dy}px)`;
      requestAnimationFrame(() => { t.style.transition = 'transform .18s ease'; t.style.transform = ''; });
    }
  };
  const start = () => {
    st.active = true;
    clearTimeout(st.timer);
    const r = st.el.getBoundingClientRect();
    st.ghost = st.el.cloneNode(true);
    st.ghost.classList.add('drag-ghost');
    st.ghost.classList.remove('selected');
    Object.assign(st.ghost.style, { width: r.width + 'px', height: r.height + 'px', transform: 'none' });
    st.ox = st.x - r.left; st.oy = st.y - r.top;
    document.body.appendChild(st.ghost);
    st.el.classList.add('placeholder');
    document.body.classList.add('dragging-deck');
    navigator.vibrate?.(8);
    move(st.x, st.y);
  };
  const move = (x, y) => {
    st.ghost.style.left = x - st.ox + 'px';
    st.ghost.style.top = y - st.oy + 'px';
    const under = document.elementFromPoint(x, y);
    const row = under?.closest('#stage-host [data-drop]') || under?.closest('#stage-host .tier-row')?.querySelector('[data-drop]');
    const pool = !row && under?.closest('.pool-wrap');
    $$('.drop-hover').forEach((z) => z !== row && z !== $('#pool') && z.classList.remove('drop-hover'));
    if (pool) {
      $('#pool').classList.add('drop-hover');
      if (!st.el.closest('#pool')) flip(() => { st.el.style.width = st.el.style.height = ''; ($('#pool .pgroup') || $('#pool')).prepend(st.el); relayoutTiers(); });
      return;
    }
    $('#pool').classList.remove('drop-hover');
    if (!row) return;
    row.classList.add('drop-hover');
    // Insert before the first tile whose center is past the pointer (reading order).
    const others = $$('.deck-tile', row).filter((t) => t !== st.el);
    const before = others.find((t) => { const b = t.getBoundingClientRect(); return y < b.top + b.height / 2 ? x < b.right || y < b.top : false; })
      || others.find((t) => { const b = t.getBoundingClientRect(); return y < b.bottom && x < b.left + b.width / 2; });
    if (st.el.parentElement === row && (before ? st.el.nextElementSibling === before : st.el === row.lastElementChild)) return;
    flip(() => { row.insertBefore(st.el, before || null); relayoutTiers(); });
  };
  const end = () => {
    if (!st) return;
    clearTimeout(st.timer);
    if (st.active) {
      st.ghost.remove();
      st.el.classList.remove('placeholder');
      document.body.classList.remove('dragging-deck');
      $$('.drop-hover').forEach((z) => z.classList.remove('drop-hover'));
      commitTiersFromDom();
      lastDrop = Date.now();
    }
    st = null;
  };
  document.addEventListener('pointerdown', (e) => {
    if (e.button > 0) return;
    const el = e.target.closest('#stage-host .tier-slide .deck-tile, #pool .deck-tile');
    if (!el || slide()?.type !== 'tier' || ui.viewing) return;
    st = { el, x: e.clientX, y: e.clientY, touch: e.pointerType === 'touch', active: false };
    if (st.touch) st.timer = setTimeout(() => st && start(), 200);
  });
  document.addEventListener('pointermove', (e) => {
    if (!st) return;
    const far = Math.hypot(e.clientX - st.x, e.clientY - st.y) > 6;
    if (!st.active) {
      if (st.touch) { if (far) { clearTimeout(st.timer); st = null; } return; } // swipe = scroll
      if (!far) return;
      start();
    }
    e.preventDefault();
    move(e.clientX, e.clientY);
  });
  document.addEventListener('pointerup', end);
  document.addEventListener('pointercancel', end);
  document.addEventListener('touchmove', (e) => { if (st?.active) e.preventDefault(); }, { passive: false });
  document.addEventListener('contextmenu', (e) => { if (st) e.preventDefault(); });
  document.addEventListener('click', (e) => { if (Date.now() - lastDrop < 350) { e.stopPropagation(); e.preventDefault(); } }, true);
}

/* Tap a card on a deck slide (in the editor) for quick changes. */
function openCardMenu(d, id, x, y, zone = zoneOf(d, id)) {
  closeCardMenu();
  const c = card(id);
  const n = listOf(d, zone).find((r) => r[0] === id)?.[1] || 0;
  const m = document.createElement('div');
  m.className = 'card-menu';
  m.innerHTML = `<div class="cm-title" style="--c:${hexOf(c)}">${esc(c?.name || id)}</div>
    <div class="cm-zones">${ZONES.map(([z, label]) => `<button data-cm-zone="${z}" class="${(zone === 'options' ? 'side' : zone) === z ? 'on' : ''}">${z === 'side' ? 'Side / Opt' : label}</button>`).join('')}</div>
    <div class="cm-row"><button data-cm-bump="-1" aria-label="One fewer">−</button><b>${zone === 'options' ? '+' : '×'}${n}</b><button data-cm-bump="1" aria-label="One more">+</button>
      <button data-cm-key class="${isKey(d, id) ? 'on' : ''}">★ Key</button><button data-cm-remove class="danger">Remove</button></div>`;
  document.body.appendChild(m);
  const r = m.getBoundingClientRect();
  m.style.left = Math.max(8, Math.min(x, innerWidth - r.width - 8)) + 'px';
  m.style.top = Math.max(8, Math.min(y + 8, innerHeight - r.height - 8)) + 'px';
  m.onclick = (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    let now = zone;
    if (b.dataset.cmZone) { moveCard(d, id, b.dataset.cmZone, zone); now = b.dataset.cmZone; }
    else if (b.dataset.cmBump) bumpCard(d, id, Number(b.dataset.cmBump), zone);
    else if ('cmKey' in b.dataset) { toggleKey(d, id); now = zoneOf(d, id); }
    else if ('cmRemove' in b.dataset) removeCard(d, id, zone);
    save(); renderStage(); renderSlideBoard();
    if ('cmRemove' in b.dataset || !listOf(d, now).some((row) => row[0] === id)) closeCardMenu();
    else openCardMenu(d, id, x, y, now);
  };
}
function closeCardMenu() { $$('.card-menu').forEach((m) => m.remove()); }

function addDeckSlide(d) {
  const s = { id: uid(), type: 'deck', name: 'Deck: ' + (d ? deckLabel(d) : ''), deckId: d?.id || null };
  state.slides.push(s); ui.slideId = s.id; save(); setView('slides');
}

/* ---------------- deck search, grouping and sorting ---------------- */
function prefs() {
  state.prefs = { deckGroup: 'color', deckSort: 'new', deckQuery: '', poolQuery: '', collapsed: {}, open: {}, guide: {}, ...state.prefs };
  return state.prefs;
}
const COLOR_GROUPS = [['R', 'Red'], ['Y', 'Yellow'], ['G', 'Green'], ['B', 'Blue'], ['multi', 'Three colors'], ['none', 'No Legends yet']];
/** The deck's main color: its doubled (or tripled) Legend color, or 'multi' when all three differ. */
function mainColor(d) {
  const cols = deckColors(d);
  if (!cols.length) return 'none';
  return cols.length === 3 && new Set(cols).size === 3 ? 'multi' : cols[0];
}
function deckMatches(d, q) {
  q = norm(q);
  return !q || norm([deckLabel(d), d.name, ...legendsOf(d).map((id) => card(id)?.name || '')].join(' ')).includes(q);
}
function sortDecks(list, how) {
  const at = (d) => d.createdAt || state.decks.indexOf(d);
  const by = {
    new: (a, b) => at(b) - at(a),
    name: (a, b) => deckLabel(a).localeCompare(deckLabel(b)) || (a.name || '').localeCompare(b.name || ''),
    cards: (a, b) => deckCount(b) - deckCount(a),
  }[how] || (() => 0);
  return list.slice().sort(by);
}
/** Groups decks for lists: by main color, by tier (first tier list), or one flat group. */
function groupDecks(list, how) {
  if (how === 'color') {
    return COLOR_GROUPS.map(([key, label]) => ({ key: 'c:' + key, label, color: COLORS[key]?.hex || '#8b93a3', decks: list.filter((d) => mainColor(d) === key) })).filter((g) => g.decks.length);
  }
  if (how === 'tier') {
    const ts = state.slides.find((x) => x.type === 'tier');
    const groups = (ts?.tiers || []).map((t) => ({ key: 't:' + t.id, label: t.name, color: t.color, decks: list.filter((d) => t.deckIds.includes(d.id)) }));
    const ranked = new Set((ts?.tiers || []).flatMap((t) => t.deckIds));
    groups.push({ key: 't:none', label: 'Unranked', color: '#8b93a3', decks: list.filter((d) => !ranked.has(d.id)) });
    return groups.filter((g) => g.decks.length);
  }
  return [{ key: 'all', label: '', decks: list }];
}

/* ---------------- Decks view ---------------- */
function renderDecks() {
  if (!deck(ui.deckId)) ui.deckId = state.decks[0]?.id;
  const pf = prefs();
  $('#deck-q').value = pf.deckQuery;
  $('#deck-group').value = pf.deckGroup;
  $('#deck-sort').value = pf.deckSort;
  const shown = sortDecks(state.decks.filter((d) => deckMatches(d, pf.deckQuery)), pf.deckSort);
  const item = (d) => `<li data-deck-item="${d.id}" class="${d.id === ui.deckId ? 'active' : ''}">
    <span class="fan">${legendsOf(d).map((id) => `<span class="mini" style="--c:${hexOf(card(id))}">${artHTML(card(id))}</span>`).join('')}</span>
    <span class="dl-text"><strong>${esc(deckLabel(d))}</strong><span class="hint">${esc(d.name && d.name !== deckLabel(d) ? d.name : d.main.length ? deckCount(d) + ' cards' : '')}</span></span>
    <span class="chips">${chips(deckColors(d))}</span></li>`;
  $('#deck-count').textContent = pf.deckQuery ? `${shown.length} of ${state.decks.length}` : state.decks.length;
  $('#deck-list').innerHTML = groupDecks(shown, pf.deckGroup).map((g) => {
    const closed = !pf.deckQuery && pf.collapsed[g.key];
    return (g.label ? `<li class="dgroup ${closed ? 'closed' : ''}" data-group="${g.key}" style="--g:${g.color}"><span class="caret">▾</span>${esc(g.label)}<b>${g.decks.length}</b></li>` : '') +
      (closed ? '' : g.decks.map(item).join(''));
  }).join('') || `<li class="hint">${state.decks.length ? 'No decks match.' : 'No decks yet.'}</li>`;
  const demos = state.decks.filter(isDemoDeck).length;
  $('#deck-list').insertAdjacentHTML('beforeend', demos && state.catalog ? `<li class="demo-note"><button id="clear-demo" class="small block">Remove ${demos} demo decks</button></li>` : '');
  const d = deck(ui.deckId);
  const ed = $('#deck-editor');
  if (!d) { ed.innerHTML = '<div class="empty-msg">No decks yet. Import a deck export or create a blank deck.</div>'; return; }
  const slot = (id, role, i) => {
    const c = card(id);
    return `<button class="slot" data-slot="${role}" data-i="${i ?? ''}" style="--c:${hexOf(c)}">${artHTML(c)}<span class="n">${esc(c?.name || (role === 'key' ? 'Pick key card' : 'Pick Legend'))}</span></button>`;
  };
  ed.innerHTML = `<div class="deck-edit">
    <div>
      <label>Deck name</label><input data-d="name" value="${esc(d.name)}" placeholder="e.g. Geary Noble Safety">
      <label>Legends</label>
      <div class="slots">${d.legends.map((id, i) => slot(id, 'legend', i)).join('')}</div>
      <label>Key cards (up to 3)</label>
      <div class="slots">${[...keysOf(d), null].slice(0, 3).map((id, i) => slot(id, 'key', i)).join('')}</div>
      <label>Notes (shown on the deck page)</label>
      <textarea data-d="notes" rows="3">${esc(d.notes)}</textarea>
      <div class="row gap" style="margin-top:14px">
        <button data-deckpage class="primary">+ Deck page slide</button>
        <button data-reimport>Replace from export…</button>
      </div>
      <details class="more" data-more="deck" ${prefs().open?.['deck'] ? 'open' : ''}><summary>More options</summary>
      <label>Tile code</label><input data-d="label" value="${esc(d.label)}" placeholder="${esc(autoCode(d) || 'auto')}">
      <p class="hint">Made from the Legends' colors, e.g. RRG. Type to override it.</p>
      <label>Tile display for this deck</label>
      <div class="seg">${[['inherit', 'Slide default'], ...Object.entries(DISPLAY_MODES)].map(([k, v]) => `<button data-display="${k}" class="${(d.display || 'inherit') === k ? 'on' : ''}">${v}</button>`).join('')}</div>
      <div class="row gap" style="margin-top:14px"><button data-copy-export>Copy sim export</button><button data-del-deck class="danger">Delete deck</button></div></details>
    </div>
    <div>
      <h3>On the tier list</h3>
      <div class="previews">${deckTileHTML(d, d.display && d.display !== 'inherit' ? d.display : (state.slides.find((x) => x.type === 'tier')?.display || 'legends'), { selectable: false, showName: true })}</div>
    </div>
    <div class="dl-full">
      <h3>Decklist <span class="hint">${deckCount(d)} in the deck${extraRows(d).length ? ` · ${extraRows(d).reduce((t, r) => t + r[1], 0)} sideboard / options` : ''}</span></h3>
      ${d.unmatched?.length ? `<div class="callout warn">${d.unmatched.length} line(s) didn't match a card${state.catalog ? '' : ' (load the card data first)'}: ${d.unmatched.map((u) => esc(u.name)).join(', ')}</div>` : ''}
      ${quickAddHTML(d)}
      ${boardHTML(d)}

    </div>
  </div>`;
}

/* ---------------- deck card operations (shared by the editor board and the slide menu) ---------------- */
// Zones: 'core' | 'deck' | 'flex' are the main deck with that role; 'options' is outside the deck.
// A card can sit in more than one list (e.g. 2 in the deck and 1 in the sideboard), so the board
// and slide menu always say which zone they mean; zoneOf only guesses for callers that don't.
const MAIN_ZONES = ['core', 'deck', 'flex'];
const listOf = (d, zone) => (zone === 'options' ? (d.options = d.options || []) : zone === 'side' ? (d.side = d.side || []) : d.main);
function zoneOf(d, id) {
  if (d.main.some((r) => r[0] === id)) return d.roles?.[id] || 'deck';
  if ((d.side || []).some((r) => r[0] === id)) return 'side';
  if ((d.options || []).some((r) => r[0] === id)) return 'options';
  return 'deck';
}
function takeRow(list, id) {
  const i = list.findIndex((r) => r[0] === id);
  return i < 0 ? null : list.splice(i, 1)[0];
}
function mergeRow(list, id, n) {
  const row = list.find((r) => r[0] === id);
  if (row) row[1] += n; else list.push([id, n]);
}
function setRole(d, id, zone) {
  d.roles = d.roles || {};
  if (zone === 'core' || zone === 'flex') d.roles[id] = zone; else delete d.roles[id];
}
/** Moves a card (all its copies in `from`) to another zone. */
function moveCard(d, id, to, from = zoneOf(d, id)) {
  if (from === to || (from === 'options' && to === 'side')) return; // same visual section
  if (MAIN_ZONES.includes(from) && MAIN_ZONES.includes(to)) return setRole(d, id, to);
  const row = takeRow(listOf(d, from), id);
  if (!row) return;
  mergeRow(listOf(d, to), id, row[1]);
  if (MAIN_ZONES.includes(to)) setRole(d, id, to);
  else if (MAIN_ZONES.includes(from)) leftMain(d, id);
}
/** Once a card is no longer in the main deck it loses its Core/Flex role and key-card star. */
function leftMain(d, id) {
  if (d.main.some((r) => r[0] === id)) return;
  setRole(d, id, '');
  if (isKey(d, id)) setKeys(d, keysOf(d).filter((k) => k !== id));
}
function addCard(d, id, zone, n = 1) {
  mergeRow(listOf(d, zone), id, n);
  if (MAIN_ZONES.includes(zone)) setRole(d, id, zone);
}
function bumpCard(d, id, delta, zone = zoneOf(d, id)) {
  const list = listOf(d, zone);
  const row = list.find((r) => r[0] === id);
  if (!row) return;
  row[1] += delta;
  if (row[1] <= 0) { takeRow(list, id); leftMain(d, id); }
}
function removeCard(d, id, zone = zoneOf(d, id)) {
  takeRow(listOf(d, zone), id);
  leftMain(d, id);
}
function toggleKey(d, id) {
  const ks = keysOf(d);
  if (ks.includes(id)) return setKeys(d, ks.filter((x) => x !== id)), true;
  if (ks.length >= 3) { toast('A deck can have up to 3 key cards. Unstar one first.'); return false; }
  if (!d.main.some((r) => r[0] === id)) moveCard(d, id, 'deck');
  setKeys(d, [...ks, id]);
  return true;
}

/* Quick add: a search box that adds a card straight into a zone. */
function quickAddHTML(d) {
  return `<div class="qa" data-qa-deck="${d.id}">
    <input class="qa-input" type="search" placeholder="Quick add a card…" autocomplete="off" aria-label="Quick add a card">
    <select class="qa-zone" aria-label="Add to"><option value="deck">to Deck</option><option value="core">to Core</option><option value="flex">to Flex</option><option value="side">to Sideboard / Options</option></select>
    <div class="qa-results" hidden></div>
  </div>`;
}
function bindQuickAdd(onChange) {
  const results = (box) => {
    const q = norm(box.querySelector('.qa-input').value);
    const list = q ? allCards().filter((c) => !isLegend(c) && norm(c.name).includes(q)).sort((a, b) => norm(a.name).indexOf(q) - norm(b.name).indexOf(q) || a.name.localeCompare(b.name)).slice(0, 8) : [];
    const el = box.querySelector('.qa-results');
    el.hidden = !list.length;
    el.innerHTML = list.map((c, i) => `<button class="qa-hit ${i ? '' : 'first'}" data-qa-add="${c.id}" style="--c:${hexOf(c)}"><span class="ds-cost">${c.cost ?? '·'}</span>${esc(c.name)}<span class="hint">${esc(c.type || '')}</span></button>`).join('');
  };
  const add = (box, id) => {
    const d = deck(box.dataset.qaDeck);
    if (!d || !id) return;
    addCard(d, id, box.querySelector('.qa-zone').value);
    save();
    toast(`Added ${card(id).name}.`);
    box.querySelector('.qa-input').value = '';
    onChange();
    document.querySelector(`[data-qa-deck="${d.id}"] .qa-input`)?.focus();
  };
  document.addEventListener('input', (e) => { const box = e.target.closest('.qa'); if (box && e.target.matches('.qa-input')) results(box); });
  document.addEventListener('keydown', (e) => {
    const box = e.target.closest?.('.qa');
    if (box && e.key === 'Enter') { e.preventDefault(); add(box, box.querySelector('.qa-hit')?.dataset.qaAdd); }
  });
  document.addEventListener('click', (e) => {
    const hit = e.target.closest('[data-qa-add]');
    if (hit) add(hit.closest('.qa'), hit.dataset.qaAdd);
  });
}

// Sideboard and options share one column ('side'); each card keeps its own list underneath so
// exports still contain only the real sideboard.
const ZONES = [['core', 'Core', 'always in the list'], ['deck', 'Deck', 'untagged'], ['flex', 'Flex', 'slots that change'], ['side', 'Sideboard / Options', 'outside the main deck']];
let boardPick = null; // tap-to-move on touch screens: the card picked up, then tap a column
function boardHTML(d) {
  const rowsIn = (zone) => (MAIN_ZONES.includes(zone) ? d.main.filter(([id]) => (d.roles?.[id] || 'deck') === zone).map(([id, n]) => [card(id), n, id, zone])
    : [...(d.side || []).map(([id, n]) => [card(id), n, id, 'side']), ...(d.options || []).map(([id, n]) => [card(id), n, id, 'options'])]).sort((a, b) => (a[0]?.cost ?? 99) - (b[0]?.cost ?? 99) || (a[0]?.name || '').localeCompare(b[0]?.name || ''));
  return `<div class="board" data-board-deck="${d.id}">${ZONES.map(([zone, label, hint]) => {
    const rows = rowsIn(zone);
    const n = rows.reduce((t, r) => t + r[1], 0);
    return `<div class="bcol ${zone}" data-zone="${zone}">
      <div class="bhead"><b>${label}</b> <span>${n}</span><small>${hint}</small></div>
      ${rows.map(([c, n, id, cz]) => `<div class="bcard ${boardPick?.card === id && boardPick?.zone === cz ? 'picked' : ''}" draggable="true" data-card="${id}" data-zone="${cz}" style="--c:${hexOf(c)}">
        <span class="ds-cost">${c?.cost ?? '·'}</span><span class="nm">${esc(c?.name || id)}</span>
        <span class="bq"><button class="small" data-bump="-1" aria-label="One fewer">−</button><b>${n}</b><button class="small" data-bump="1" aria-label="One more">+</button></span>
        ${MAIN_ZONES.includes(zone) ? `<button class="small key ${isKey(d, id) ? 'on' : ''}" data-key aria-label="Key card">★</button>` : ''}
      </div>`).join('') || '<div class="bempty">Drop cards here</div>'}
    </div>`;
  }).join('')}</div>
  <p class="hint">Drag cards between columns, or tap a card and then a column. ★ marks a key card (up to 3).</p>`;
}

/** Board interactions work wherever a board is shown: the Decks tab or under a slide on the Slides tab. */
function refreshBoards() {
  if (ui.view === 'decks') renderDecks();
  else if (ui.view === 'slides') { renderStage(); renderSlideBoard(); }
}
function bindBoards() {
  let drag = null; // { deck, card }
  document.addEventListener('dragstart', (e) => {
    const c = e.target.closest?.('.bcard');
    if (!c) return;
    drag = { deck: c.closest('.board').dataset.boardDeck, card: c.dataset.card, zone: c.dataset.zone };
    e.dataTransfer.setData('text/plain', drag.card);
    e.dataTransfer.effectAllowed = 'move';
  });
  document.addEventListener('dragover', (e) => {
    const col = e.target.closest?.('.bcol');
    if (!col || !drag) return;
    e.preventDefault();
    $$('.bcol.over').forEach((x) => x !== col && x.classList.remove('over'));
    col.classList.add('over');
  });
  document.addEventListener('dragend', () => { drag = null; $$('.bcol.over').forEach((x) => x.classList.remove('over')); });
  document.addEventListener('drop', (e) => {
    const col = e.target.closest?.('.bcol');
    if (!col || !drag) return;
    e.preventDefault();
    moveCard(deck(drag.deck), drag.card, col.dataset.zone, drag.zone);
    drag = null; save(); refreshBoards();
  });
  document.addEventListener('click', (e) => {
    const board = e.target.closest?.('.board');
    if (!board) return;
    const d = deck(board.dataset.boardDeck);
    const bc = e.target.closest('.bcard');
    const col = e.target.closest('.bcol');
    if (!bc && !(col && boardPick)) return;
    e.stopPropagation();
    if (bc && e.target.closest('[data-bump]')) bumpCard(d, bc.dataset.card, Number(e.target.closest('[data-bump]').dataset.bump), bc.dataset.zone);
    else if (bc && e.target.closest('[data-key]')) { if (!toggleKey(d, bc.dataset.card)) return; }
    else if (bc) { const same = boardPick?.card === bc.dataset.card && boardPick?.zone === bc.dataset.zone; boardPick = same ? null : { card: bc.dataset.card, zone: bc.dataset.zone }; refreshBoards(); return; }
    else { moveCard(d, boardPick.card, col.dataset.zone, boardPick.zone); boardPick = null; }
    save(); refreshBoards();
  }, true);
}

/** Decklist board under a deck page slide on the Slides tab. */
function renderSlideBoard() {
  const wrap = $('#slide-board');
  const s = slide();
  // Deck page: that deck. Tier list: the deck currently tapped/selected.
  const d = s?.type === 'deck' ? deck(s.deckId) : s?.type === 'tier' && ui.selectedDeck ? deck(ui.selectedDeck) : null;
  wrap.hidden = !d;
  if (!d) return;
  const tip = s.type === 'tier' ? 'Drag the deck to move it, or edit its list here.' : 'Changes show on the slide right away.';
  wrap.innerHTML = `<div class="pool-head"><h3>${esc(deckLabel(d))} decklist</h3><span class="hint">${esc(d.name && d.name !== deckLabel(d) ? d.name + ' · ' : '')}${deckCount(d)} in the deck${extraRows(d).length ? ` · ${extraRows(d).reduce((t, r) => t + r[1], 0)} sideboard / options` : ''}. ${tip}</span></div>
    ${quickAddHTML(d)}${boardHTML(d)}`;
}

function exportSimText(d) {
  const nm = (id) => card(id)?.name || id;
  const lines = (rows) => rows.map(([id, n]) => `${n}x ${nm(id)}`).sort();
  const out = [`# Name: ${d.name || deckLabel(d)}`, '#L', ...d.legends.filter(Boolean).map((id) => `1x ${nm(id)}`), '', '#D', ...lines(d.main)];
  if (d.side.length) out.push('', '#S', ...lines(d.side));
  return out.join('\n');
}

function bindDecks() {
  $('#deck-q').oninput = (e) => { prefs().deckQuery = e.target.value; renderDecks(); };
  $('#deck-group').onchange = (e) => { prefs().deckGroup = e.target.value; save(); renderDecks(); };
  $('#deck-sort').onchange = (e) => { prefs().deckSort = e.target.value; save(); renderDecks(); };
  $('#deck-list').addEventListener('click', (e) => {
    const g = e.target.closest('[data-group]');
    if (g) { const c = prefs().collapsed; c[g.dataset.group] = !c[g.dataset.group]; save(); renderDecks(); return; }
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
    else if ('addOption' in b.dataset) {
      openPicker('card', (id) => {
        if (!id) return;
        d.options = d.options || [];
        const row = d.options.find((r) => r[0] === id);
        if (row) row[1]++; else d.options.push([id, 1]);
        save(); renderDecks();
      });
      return;
    } else if (b.dataset.moveTo) {
      d.options = d.options || [];
      const lists = { 0: d.main, 2: d.options };
      const from = lists[b.dataset.side], to = lists[b.dataset.moveTo];
      const row = from.find((r) => r[0] === b.dataset.q);
      from.splice(from.indexOf(row), 1);
      const dest = to.find((r) => r[0] === row[0]);
      if (dest) dest[1] += row[1]; else to.push(row);
    } else if (b.dataset.dq) {
      d.options = d.options || [];
      const list = { 1: d.side, 2: d.options }[b.dataset.side] || d.main;
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
    <div class="row gap" style="margin-top:8px">
      <label class="filebtn">Scan deck image<input type="file" id="imp-image" accept="image/*" hidden></label>
      <label class="filebtn">Load .txt file<input type="file" id="imp-file" accept=".txt,.json,text/plain" hidden></label>
      <span class="hint" id="imp-scan">Or paste or drop a screenshot of the sim's deck image. It's read on this device and never uploaded or saved.</span>
    </div>
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
  // Deck images: read the QR code locally, add the deck it holds, and let go of the image.
  const scan = async (file) => {
    if (!file || !file.type.startsWith('image/')) return;
    $('#imp-scan').textContent = 'Reading the QR code…';
    try {
      const text = await readQrFromImage(file);
      if (!text) throw new Error('No QR code found in that image. Try a sharper or uncropped export.');
      if (!decodeB64Deck(text) && !decodeSimDeckCode(text) && !/#L|^\s*\d+\s*x?\s+\S/im.test(text)) throw new Error(`The QR code holds "${text.slice(0, 80)}", which isn't a deck export. Open it in the sim and use Export → Text instead.`);
      const box = $('#imp-text');
      box.value = (box.value.trim() ? box.value.trim() + '\n---\n' : '') + text;
      preview();
      $('#imp-scan').textContent = 'Deck read from the image. The image wasn\'t uploaded or kept.';
    } catch (err) { $('#imp-scan').textContent = err.message; }
  };
  $('#imp-image').onchange = (e) => { scan(e.target.files[0]); e.target.value = ''; };
  const card = $('#modal-body');
  card.addEventListener('paste', (e) => { const f = [...(e.clipboardData?.files || [])].find((x) => x.type.startsWith('image/')); if (f) { e.preventDefault(); scan(f); } });
  card.addEventListener('dragover', (e) => e.preventDefault());
  card.addEventListener('drop', (e) => { const f = [...(e.dataTransfer?.files || [])].find((x) => x.type.startsWith('image/')); if (f) { e.preventDefault(); scan(f); } });
  $('#imp-go').onclick = () => {
    if (target && parsed[0]) {
      const p = parsed[0];
      Object.assign(target, { legends: p.legends, main: p.main, side: p.side, unmatched: p.unmatched, keyCards: keysOf(target).filter((k) => p.main.some((r) => r[0] === k)) });
      if (!keysOf(target).length) setKeys(target, [p.keyCard]); else setKeys(target, keysOf(target));
      if (!target.name || target.name === 'New deck') target.name = p.name;
    } else {
      for (const d of parsed) state.decks.push(d);
      markGuide('imported');
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
      <div class="btns"><button class="small" data-crop="${c.id}">Crop art</button></div>
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

function bindCards() {
  $('#card-search').oninput = renderCards;
  $('#card-filter').onchange = renderCards;
  $('#card-grid').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.crop) openCrop(card(b.dataset.crop));
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

/* ---------------- touch dragging ----------------
 * Phones have no HTML drag-and-drop: press and hold a card or deck, then drag it.
 * A quick swipe still scrolls, and tap-then-tap still works. */
function enableTouchDrag() {
  let st = null;
  let lastDrop = 0;
  const cleanup = () => {
    if (!st) return;
    clearTimeout(st.timer);
    st.ghost?.remove();
    st.el.classList.remove('dragging');
    $$('.bcol.over, .drop-hover').forEach((x) => x.classList.remove('over', 'drop-hover'));
    st = null;
  };
  const targetAt = (x, y) => {
    const t = document.elementFromPoint(x, y);
    return st.kind === 'card' ? t?.closest('.bcol') : t?.closest('#stage-host [data-drop], #pool');
  };
  document.addEventListener('pointerdown', (e) => {
    if (e.pointerType !== 'touch' || e.target.closest('button')) return;
    const el = e.target.closest('.bcard');
    if (!el) return;
    const kind = el.matches('.bcard') ? 'card' : 'deck';
    st = { el, kind, x: e.clientX, y: e.clientY, active: false };
    st.timer = setTimeout(() => {
      if (!st) return;
      st.active = true;
      el.classList.add('dragging');
      navigator.vibrate?.(8);
      st.ghost = document.createElement('div');
      st.ghost.className = 'touch-ghost';
      st.ghost.textContent = kind === 'card' ? card(el.dataset.card)?.name || '' : deckLabel(deck(el.dataset.deck));
      document.body.appendChild(st.ghost);
      st.ghost.style.transform = `translate(${st.x}px, ${st.y}px)`;
    }, 220);
  });
  document.addEventListener('pointermove', (e) => {
    if (!st) return;
    if (!st.active) { if (Math.hypot(e.clientX - st.x, e.clientY - st.y) > 10) cleanup(); return; }
    st.x = e.clientX; st.y = e.clientY;
    st.ghost.style.transform = `translate(${st.x}px, ${st.y}px)`;
    const t = targetAt(st.x, st.y);
    $$('.bcol.over, .drop-hover').forEach((x) => x !== t && x.classList.remove('over', 'drop-hover'));
    t?.classList.add(st.kind === 'card' ? 'over' : 'drop-hover');
  });
  // Once a hold has started a drag, stop the page from scrolling under the finger.
  document.addEventListener('touchmove', (e) => { if (st?.active) e.preventDefault(); }, { passive: false });
  document.addEventListener('pointerup', (e) => {
    if (!st) return;
    if (st.active) {
      const t = targetAt(e.clientX, e.clientY);
      if (t && st.kind === 'card') {
        moveCard(deck(st.el.closest('.board').dataset.boardDeck), st.el.dataset.card, t.dataset.zone, st.el.dataset.zone);
        save(); lastDrop = Date.now(); cleanup(); refreshBoards(); return;
      }
      if (t && st.kind === 'deck') {
        const before = document.elementFromPoint(e.clientX, e.clientY)?.closest('.deck-tile')?.dataset.deck;
        const id = st.el.dataset.deck;
        lastDrop = Date.now(); cleanup();
        moveDeck(id, t.dataset.drop || 'pool', before !== id ? before : null); return;
      }
      lastDrop = Date.now();
    }
    cleanup();
  });
  document.addEventListener('pointercancel', cleanup);
  document.addEventListener('contextmenu', (e) => { if (st) e.preventDefault(); });
  // The tap that ends a drag shouldn't also count as a click.
  document.addEventListener('click', (e) => { if (Date.now() - lastDrop < 400) { e.stopPropagation(); e.preventDefault(); } }, true);
}

/* ---------------- share links ----------------
 * Decks live in each person's own browser, so a link can't point at them. Instead the link carries
 * a compressed snapshot of the shared slides and only the decks they use (cards by catalog id).
 * Opening it shows a read-only viewer; "Add to my studio" copies it in with fresh ids. */
const SHARE_PREFIX = '#s=';
// Older links may include deck pages; the viewer only shows tier lists.
const b64url = {
  encRaw: (bytes) => { let bin = ''; for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return btoa(bin); },
  enc: (bytes) => b64url.encRaw(bytes).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''),
  dec: (str) => { let b = str.replace(/-/g, '+').replace(/_/g, '/'); while (b.length % 4) b += '='; return Uint8Array.from(atob(b), (c) => c.charCodeAt(0)); },
};
async function pipe(bytes, Stream) {
  return new Uint8Array(await new Response(new Blob([bytes]).stream().pipeThrough(new Stream('deflate-raw'))).arrayBuffer());
}
function shareSnapshot(slides) {
  // Tier lists only, and for each deck only what its tile shows: no decklists (plenty of tools share those).
  slides = slides.filter((x) => x.type === 'tier');
  const ids = new Set(slides.flatMap((x) => x.tiers.flatMap((t) => t.deckIds)));
  const decks = state.decks.filter((d) => ids.has(d.id)).map((d) => ({ id: d.id, name: d.name, label: d.label, legends: d.legends, keyCards: keysOf(d).slice(0, 1), display: d.display }));
  return { v: 1, slides, decks, legendCrop: state.legendCrop, crops: Object.fromEntries(Object.entries(state.crops).filter(([id]) => decks.some((d) => d.legends.includes(id) || keysOf(d).includes(id)))) };
}
async function shareLink(slides) {
  const bytes = new TextEncoder().encode(JSON.stringify(shareSnapshot(slides)));
  let data;
  try { data = 'z' + b64url.enc(await pipe(bytes, CompressionStream)); } catch { data = 'j' + b64url.enc(bytes); }
  return location.href.split('#')[0] + SHARE_PREFIX + data;
}
async function readShare(hash) {
  const data = hash.slice(SHARE_PREFIX.length);
  const raw = b64url.dec(data.slice(1));
  const bytes = data[0] === 'z' ? await pipe(raw, DecompressionStream) : raw;
  const snap = JSON.parse(new TextDecoder().decode(bytes));
  if (snap.v !== 1 || !Array.isArray(snap.slides)) throw new Error('unknown link format');
  snap.slides = snap.slides.filter((x) => x.type === 'tier');
  snap.decks = snap.decks.map((d) => newDeck({ ...d, main: [], side: [], options: [], keyCard: d.keyCards?.[0] || null }));
  return snap;
}
function openShare() {
  const tierSlides = state.slides.filter((x) => x.type === 'tier');
  if (!tierSlides.length) return toast('Add a tier list slide to share.');
  const s = slide()?.type === 'tier' ? slide() : tierSlides[0];
  openModal(`<h3>Share tier list</h3>
    <p class="hint">Anyone with the link sees the tier list as it is now; decklists aren't included. Share again after changes.</p>
    ${tierSlides.length > 1 ? `<label class="check"><input type="radio" name="share-scope" value="one" checked> ${esc(s.name || 'This tier list')}</label>
    <label class="check"><input type="radio" name="share-scope" value="all"> All ${tierSlides.length} tier lists</label>` : ''}
    <div class="row gap" style="margin-top:12px"><input id="share-url" readonly placeholder="Making link…" style="flex:1"><button class="primary" id="share-copy">Copy link</button></div>
    <p class="hint" id="share-note"></p>`);
  const make = async () => {
    const all = $('input[name=share-scope]:checked')?.value === 'all';
    const url = await shareLink(all ? tierSlides : [s]);
    $('#share-url').value = url;
    $('#share-note').textContent = url.length > 8000 ? `This link is long (${Math.round(url.length / 1000)}k characters). Some chat apps cut long links.` : '';
  };
  $$('input[name=share-scope]').forEach((r) => (r.onchange = make));
  $('#share-copy').onclick = () => {
    const url = $('#share-url').value;
    navigator.clipboard?.writeText(url).then(() => toast('Link copied.'), () => { $('#share-url').select(); toast('Select the link and copy it.'); });
  };
  make();
}
let ownState = null;
async function enterViewer() {
  let snap;
  try { snap = await readShare(location.hash); } catch (err) { toast('This share link is damaged or cut off. Ask for the link again.', 7000); history.replaceState(null, '', location.pathname); return false; }
  ownState = state;
  ui.viewing = true;
  state = { ...makeDemo(), catalog: ownState.catalog, custom: [], decks: snap.decks, slides: snap.slides, legendCrop: snap.legendCrop || {}, crops: snap.crops || {}, prefs: { guide: { dismissed: true } } };
  rebuildIndex(); nameIndex = null;
  ui.slideId = state.slides[0]?.id;
  document.body.classList.add('viewing');
  $('#viewer-bar').hidden = false;
  return true;
}
function addSharedToStudio() {
  const snap = state;
  const mine = ownState;
  const idMap = {};
  for (const d of snap.decks) { idMap[d.id] = uid(); mine.decks.push({ ...clone(d), id: idMap[d.id], createdAt: Date.now() }); }
  for (const sl of snap.slides) {
    const c = clone(sl);
    c.id = uid();
    if (c.type === 'tier') c.tiers.forEach((t) => { t.id = uid(); t.deckIds = t.deckIds.map((x) => idMap[x]).filter(Boolean); });
    else c.deckId = idMap[c.deckId] || null;
    mine.slides.push(c);
  }
  Object.assign(mine.crops, snap.crops);
  if (!mine.catalog && snap.catalog) mine.catalog = snap.catalog;
  ui.viewing = false;
  state = mine;
  save();
  history.replaceState(null, '', location.pathname);
  location.reload();
}
function leaveViewer() {
  history.replaceState(null, '', location.pathname);
  location.reload();
}

/* ---------------- getting started + help ---------------- */
// A short checklist that ticks itself off; hidden once finished or dismissed.
function guideSteps() {
  const g = prefs().guide;
  return [
    ['cards', 'Load the card data', !!state.catalog, () => setView('data')],
    ['import', 'Import a deck export', !!g.imported, () => { setView('decks'); openImport(); }],
    ['rank', 'Drag decks into tiers', !!g.ranked, () => { ui.slideId = state.slides.find((x) => x.type === 'tier')?.id; setView('slides'); }],
    ['present', 'Present your slides', !!g.presented, () => $('#btn-present').click()],
  ];
}
function renderGuide() {
  const box = $('#guide');
  const g = prefs().guide;
  const steps = guideSteps();
  const done = steps.filter((x) => x[2]).length;
  box.hidden = g.dismissed || done === steps.length;
  if (box.hidden) return;
  box.innerHTML = `<div class="guide-head"><b>Getting started</b><span>${done}/${steps.length}</span><button class="small" data-guide-close aria-label="Hide getting started">×</button></div>
    <ol>${steps.map(([key, label, ok]) => `<li class="${ok ? 'ok' : ''}"><button data-guide="${key}" ${ok ? 'disabled' : ''}>${ok ? '✓' : '○'} ${label}</button></li>`).join('')}</ol>
    <button class="linkish" data-help>How it works</button>`;
}
function markGuide(key) {
  const g = prefs().guide;
  if (g[key]) return;
  g[key] = true; save(); renderGuide();
}
function openHelp() {
  openModal(`<div class="help">
    <h3>How Tier List Studio works</h3>
    <ol class="help-steps">
      <li><b>Card data</b> loads by itself. If it doesn't, the Card Data tab shows how to load it from a file.</li>
      <li><b>Decks</b> come from deck exports. In the Decks tab, choose <i>Import deck export</i> and paste a list from the Cyberpunk TCG Sim or the official deck builder.</li>
      <li><b>Tier list:</b> drag decks from Unranked into tiers. Rename, recolor, add or remove tiers in the panel on the right.</li>
      <li><b>Deck pages:</b> add one with <i>+ Deck page</i> to show a deck's Legends, key cards and full list.</li>
      <li><b>Present</b> shows the slides full screen. Use ← → to move, Esc to exit.</li>
    </ol>
    <h3>Gestures</h3>
    <ul class="help-list">
      <li><b>Move a deck or card:</b> drag it. On a phone, press and hold first.</li>
      <li><b>Keyboard:</b> Tab to a deck, then ↑ ↓ to change tier, ← → to reorder, Delete to unrank, Enter to edit its list.</li>
      <li><b>Edit a deck's list:</b> tap the deck; its list opens below the slide.</li>
      <li><b>Change one card:</b> on a deck page, tap the card.</li>
      <li><b>Core, Flex, key cards:</b> drag cards between columns in the list; ★ marks a key card (up to 3).</li>
    </ul>
    <p class="hint">Everything saves in this browser. Use Project → Save project to back up or move to another device.</p>
    <p class="hint">Fan-made, not affiliated with CD PROJEKT or WeirdCo. Cyberpunk and all card images © CD PROJEKT S.A. Card data comes from the Cyberpunk TCG Sim.</p>
    <div class="row gap" style="margin-top:14px"><button class="primary" data-close>Got it</button>${prefs().guide.dismissed ? '<button data-guide-reset>Show getting started again</button>' : ''}</div>
  </div>`);
}

/* ---------------- QR codes in deck images ----------------
 * Everything happens in this browser: the image is decoded into pixels, scanned, and dropped.
 * Uses the built-in BarcodeDetector where it exists (Chrome, Android), otherwise jsQR from a CDN,
 * loaded only the first time a scan is needed. */
let jsQRReady = null;
const loadJsQR = () => (jsQRReady ||= loadScript('https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.min.js'));
async function readQrFromImage(file) {
  const bmp = await createImageBitmap(file);
  try {
    if ('BarcodeDetector' in window) {
      try {
        const hits = await new BarcodeDetector({ formats: ['qr_code'] }).detect(bmp);
        if (hits[0]?.rawValue) return hits[0].rawValue;
      } catch { /* fall through to jsQR */ }
    }
    await loadJsQR();
    // Try the whole image, then each corner enlarged (export QR codes are usually small and in a corner).
    const W = bmp.width, H = bmp.height;
    const regions = [[0, 0, W, H], [W / 2, H / 2, W / 2, H / 2], [0, H / 2, W / 2, H / 2], [W / 2, 0, W / 2, H / 2], [0, 0, W / 2, H / 2]];
    for (const [x, y, w, h] of regions) {
      const scale = Math.min(2, 1600 / Math.max(w, h));
      const cv = document.createElement('canvas');
      cv.width = Math.round(w * scale); cv.height = Math.round(h * scale);
      const ctx = cv.getContext('2d', { willReadFrequently: true });
      ctx.drawImage(bmp, x, y, w, h, 0, 0, cv.width, cv.height);
      const px = ctx.getImageData(0, 0, cv.width, cv.height);
      const hit = window.jsQR(px.data, px.width, px.height, { inversionAttempts: 'attemptBoth' });
      cv.width = cv.height = 0; // release the pixels right away
      if (hit?.data) return hit.data;
    }
    return null;
  } finally {
    bmp.close();
  }
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
  markGuide('presented');
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
    if (e.key === 'Escape') { if (!$('#modal').hidden) closeModal(); else if (ui.selectedDeck) selectDeck(null); }
  });
  document.addEventListener('fullscreenchange', () => { if (!$('#present').hidden) drawPresent(); });
  // Resizing only rescales the slide. On phones, scrolling shows/hides the address bar, which fires
  // height-only resizes; those don't affect the width-fitted slide, so they're ignored.
  let lastW = window.innerWidth, frame = 0;
  window.addEventListener('resize', () => {
    cancelAnimationFrame(frame);
    frame = requestAnimationFrame(() => {
      if (!$('#present').hidden) return scaleStage($('#present-host'), window.innerWidth, window.innerHeight);
      if (window.innerWidth <= 900 && window.innerWidth === lastW) return;
      lastW = window.innerWidth;
      if (ui.view === 'slides') scaleStage($('#stage-host'), ...stageBox());
    });
  });

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
  $('#btn-wipe').onclick = () => {
    if (!confirm('Delete everything saved in this browser (decks, tiers, slides and card data) and start fresh? This can\'t be undone. Save a project file first if you want a backup.')) return;
    try { localStorage.removeItem(STORE_KEY); } catch { /* storage unavailable */ }
    location.hash = '';
    location.reload();
  };
  $('#btn-reset').onclick = () => {
    if (!confirm('Replace your decks and slides with the sample ones? Card data is kept.')) return;
    const catalog = state.catalog;
    state = makeDemo(); state.catalog = catalog;
    rebuildIndex(); nameIndex = null;
    ui.slideId = state.slides[0].id; ui.deckId = state.decks[0].id;
    save(); render();
    applySamples().then((did) => { if (did) { ui.slideId = state.slides[0].id; ui.deckId = state.decks[0].id; render(); } });
  };
}

$('#build').textContent = document.querySelector('meta[name=build]')?.content || '';
document.addEventListener('click', (e) => { if (!e.target.closest('.card-menu')) closeCardMenu(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeCardMenu(); });
bindQuickAdd(refreshBoards);
document.addEventListener('toggle', (e) => {
  const d = e.target.closest?.('details.more');
  if (d) { prefs().open[d.dataset.more] = d.open; save(); }
}, true);
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-guide], [data-guide-close], [data-help], [data-guide-reset], #btn-help');
  if (!b) return;
  if (b.id === 'btn-help' || 'help' in b.dataset) return openHelp();
  if ('guideClose' in b.dataset) { prefs().guide.dismissed = true; save(); return renderGuide(); }
  if ('guideReset' in b.dataset) { prefs().guide.dismissed = false; save(); closeModal(); return renderGuide(); }
  guideSteps().find((x) => x[0] === b.dataset.guide)?.[3]();
});
$('#btn-share').onclick = openShare;
// Pasting a share link into a tab that already has the studio open only changes the hash.
window.addEventListener('hashchange', () => { if (location.hash.startsWith(SHARE_PREFIX)) location.reload(); });
$('#viewer-add').onclick = addSharedToStudio;
$('#viewer-close').onclick = leaveViewer;
$('#viewer-present').onclick = () => present(0);
bindBoards();
enableTouchDrag();
enableDeckDrag();
bindDeckKeys();
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
  const viewing = location.hash.startsWith(SHARE_PREFIX) && (await enterViewer());
  if (viewing) render();
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
  if (viewing) { if (ownState && !ownState.catalog) ownState.catalog = state.catalog; return render(); }
  if (await applySamples()) { ui.slideId = state.slides[0]?.id; ui.deckId = state.decks[0]?.id; toast('Loaded sample decks with real cards.'); }
  render();
})();
