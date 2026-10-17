/* Tier List Studio — Cyberpunk TCG tier list & deck slide maker.
 * Plain JS, no build step. State lives in localStorage and can be saved/loaded as JSON. */
'use strict';

const STORE_KEY = 'cp-tierlist-studio-v1';
const STAGE_W = 1920, STAGE_H = 1080;
const CARD_ASPECT = 0.72;            // width / height of a TCG card
// Crop = the card's art window (top/bottom, % of card height) + focus point + extra zoom.
// Every layout scales the card so only the art window is visible, so rules text never shows.
const DEFAULT_CROP = { top: 6, bottom: 56, x: 50, y: 30, zoom: 1 };
const COLORS = {
  R: { name: 'Red', hex: '#e5383b' },
  Y: { name: 'Yellow', hex: '#f5c518' },
  G: { name: 'Green', hex: '#2fbf71' },
  B: { name: 'Blue', hex: '#3a86ff' },
};
const DISPLAY_MODES = {
  'key-full': 'Key card (full)',
  'key-art': 'Key card (art only)',
  legends: 'Legends (art strips)',
  'legends-rows': 'Legends (art bands)',
  split: 'Key art + legends',
};
// Tier-list stage geometry (keep in sync with .tier-table in styles.css)
const TABLE = { left: 340, top: 170, right: 450, bottom: 170, labelW: 300, gap: 6 };

/* ---------------- utils ---------------- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const uid = () => Math.random().toString(36).slice(2, 10);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const clone = (o) => JSON.parse(JSON.stringify(o));
const getPath = (obj, path) => (path ? String(path).split('.').reduce((o, k) => (o == null ? o : o[k]), obj) : obj);

function toast(msg, ms = 3000) {
  const t = $('#toast');
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), ms);
}

function normColor(v) {
  if (v == null) return '';
  if (Array.isArray(v)) v = v[0];
  const s = String(v).trim().toLowerCase();
  if (!s) return '';
  if (s.startsWith('r')) return 'R';
  if (s.startsWith('y')) return 'Y';
  if (s.startsWith('g')) return 'G';
  if (s.startsWith('b') && s !== 'black') return 'B';
  return '';
}

/* ---------------- placeholder art (demo only) ---------------- */
function placeholderArt(name, color, kind) {
  const hex = COLORS[color]?.hex || '#777';
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="630" height="880" viewBox="0 0 630 880">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${hex}"/><stop offset="1" stop-color="#111"/></linearGradient>
  <pattern id="p" width="24" height="24" patternUnits="userSpaceOnUse" patternTransform="rotate(35)"><rect width="12" height="24" fill="#ffffff10"/></pattern></defs>
  <rect width="630" height="880" rx="28" fill="#0c0c0c"/>
  <rect x="24" y="24" width="582" height="520" rx="12" fill="url(#g)"/><rect x="24" y="24" width="582" height="520" rx="12" fill="url(#p)"/>
  <circle cx="315" cy="250" r="${kind === 'legend' ? 130 : 95}" fill="#ffffff22" stroke="#fff6" stroke-width="6"/>
  <text x="315" y="275" font-family="Arial Black,Arial" font-size="80" text-anchor="middle" fill="#fff">${esc(name.split(' ').map((w) => w[0]).join('').slice(0, 3))}</text>
  <rect x="24" y="560" width="582" height="296" rx="12" fill="#1b1b1b"/>
  <text x="44" y="610" font-family="Arial" font-weight="bold" font-size="34" fill="#fff">${esc(name)}</text>
  <text x="44" y="650" font-family="Arial" font-size="22" fill="#aaa">${kind === 'legend' ? 'LEGEND' : 'KEY CARD'} · PLACEHOLDER</text>
  ${[0, 1, 2, 3].map((i) => `<rect x="44" y="${690 + i * 36}" width="${480 - i * 70}" height="14" rx="7" fill="#333"/>`).join('')}
</svg>`;
  return 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
}

/* ---------------- demo project ---------------- */
function makeDemo() {
  const cards = [];
  const legendsBy = {};
  const keyBy = {};
  for (const c of Object.keys(COLORS)) {
    legendsBy[c] = ['A', 'B', 'C'].map((s) => {
      const name = `${COLORS[c].name} Legend ${s}`;
      const card = { id: uid(), name, kind: 'legend', color: c, img: placeholderArt(name, c, 'legend'), crop: { ...DEFAULT_CROP }, placeholder: true };
      cards.push(card);
      return card.id;
    });
    const name = `${COLORS[c].name} Key Card`;
    const card = { id: uid(), name, kind: 'card', color: c, img: placeholderArt(name, c, 'card'), crop: { ...DEFAULT_CROP }, placeholder: true };
    cards.push(card);
    keyBy[c] = card.id;
  }
  const mkDeck = (name, extra = {}) => {
    const letters = name.toUpperCase().split('').filter((l) => COLORS[l]);
    const used = {};
    const legends = letters.length === 3
      ? letters.map((l) => { used[l] = (used[l] || 0) + 1; return legendsBy[l][used[l] - 1]; })
      : [null, null, null];
    return { id: uid(), name, subtitle: '', legends, keyCard: letters[0] ? keyBy[letters[0]] : null, display: 'inherit', notes: '', ...extra };
  };
  const decks = ['RRG', 'YYR', 'BBG', 'RRB', 'RRY', 'YYB', 'YYG', 'GGY', 'BBY', 'YYY', 'GGB'].map((n) => mkDeck(n));
  decks.push(mkDeck('Slop', { subtitle: 'Rainbow pile' }));
  const id = (n) => decks.find((d) => d.name === n).id;

  const tierSlide = {
    id: uid(), type: 'tier', name: 'Weekly Tier List',
    title: 'Plus Two | Weekly Tier List',
    logo: '',
    badge: 'Beta\nFormat',
    badgeSub: '(Oct 2026)',
    footnote: 'Ozob Bozo Tier: It Exists.',
    display: 'key-full',
    showArrow: true,
    tiers: [
      { id: uid(), name: 'Tier 1', lines: 'Most Relevant Threats\nGreat Picks\nLikely to Win Events', color: '#f5e663', deckIds: ['RRG', 'YYR', 'BBG', 'RRB'].map(id) },
      { id: uid(), name: 'Tier 2', lines: 'Threats to Consider\nGood Picks\nCan Win Events', color: '#9ee6d9', deckIds: ['RRY', 'YYB', 'YYG', 'GGY', 'BBY'].map(id) },
      { id: uid(), name: 'Rogue', lines: 'Outside of Usual Prep\nSpicy Picks\nCompetitive Strategies', color: '#ffffff', deckIds: ['YYY', 'GGB', 'Slop'].map(id) },
    ],
  };
  const spot = { id: uid(), type: 'deck', name: 'Spotlight: RRG', deckId: id('RRG') };
  decks[0].notes = 'Top threat this week.\nFast clock, resilient to removal.';
  return {
    version: 1, cards, decks, slides: [tierSlide, spot],
    source: { url: '', listPath: '', idKey: 'id', nameKey: 'name', imageKey: 'image', imageTemplate: '', colorKey: 'color', typeKey: 'type', legendValue: 'legend' },
  };
}

/* ---------------- state ---------------- */
let state = load() || makeDemo();
const ui = { view: 'slides', slideId: state.slides[0]?.id, deckId: state.decks[0]?.id, selectedDeck: null, selectedTier: null };

function load() {
  try { const raw = localStorage.getItem(STORE_KEY); return raw ? JSON.parse(raw) : null; } catch { return null; }
}
function save() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
  catch { toast('Browser storage is full — save the project as .json, and prefer image URLs over uploads.', 6000); }
}
const card = (id) => state.cards.find((c) => c.id === id) || null;
const deck = (id) => state.decks.find((d) => d.id === id) || null;
const slide = (id = ui.slideId) => state.slides.find((s) => s.id === id) || null;

function deckColors(d) {
  const fromLegends = d.legends.map((id) => card(id)?.color).filter(Boolean);
  if (fromLegends.length) return fromLegends;
  return d.name.toUpperCase().split('').filter((l) => COLORS[l]);
}
function deckBorder(d) {
  const cols = [...new Set(deckColors(d))].map((c) => COLORS[c].hex);
  if (!cols.length) return 'linear-gradient(135deg, #e5383b, #f5c518, #2fbf71, #3a86ff)';
  if (cols.length === 1) return cols[0];
  return `linear-gradient(135deg, ${cols.join(', ')})`;
}

/* ---------------- rendering: art + tiles ---------------- */
function artHTML(c, { full = false, cls = '' } = {}) {
  if (!c || !c.img) return `<div class="art empty ${cls}"></div>`;
  const style = full ? '' : cropStyle({ ...DEFAULT_CROP, ...c.crop });
  return `<div class="art ${full ? 'full' : ''} ${cls}"><img src="${esc(c.img)}" alt="${esc(c.name)}" draggable="false" referrerpolicy="no-referrer" style="${style}"></div>`;
}

const hexOf = (c) => COLORS[c?.color]?.hex || '#6b7280';
/** Inline style for the colored plinth + underline (tint uses hex alpha so PNG export can parse it). */
const plinth = (hex) => `--c:${hex};--ct:${hex}55`;
const chips = (cols, cls = 'chip') => cols.map((c) => `<span class="${cls}" style="background:${COLORS[c].hex}"></span>`).join('');

function deckTileHTML(d, mode, { style = '', selectable = true } = {}) {
  if (d.display && d.display !== 'inherit') mode = d.display;
  const key = card(d.keyCard);
  const legends = d.legends.map(card);
  const cells = legends.map((c) => `<div class="lg" style="${plinth(hexOf(c))}">${artHTML(c)}</div>`).join('');
  const strips = `<div class="legend-strips">${cells}</div>`;
  let inner;
  if (mode === 'legends') inner = strips;
  else if (mode === 'legends-rows') inner = `<div class="legend-strips rows">${cells}</div>`;
  else if (mode === 'split') inner = `<div class="split">${artHTML(key)}${strips}</div>`;
  else {
    // key-card modes: segmented underline in the Legends' colors
    const cols = deckColors(d);
    inner = artHTML(key, { full: mode === 'key-full' }) +
      (cols.length ? `<div class="underline">${cols.map((c) => `<span style="background:${COLORS[c].hex}"></span>`).join('')}</div>` : '');
  }
  const len = d.name.length;
  const lcls = len > 5 ? 'xlong' : len > 3 ? 'long' : '';
  const sel = selectable && ui.selectedDeck === d.id ? 'selected' : '';
  return `<div class="deck-tile ${sel}" draggable="true" data-deck="${d.id}" title="${esc(d.name)}" style="--deck-border:${deckBorder(d)};${style}">
    <div class="inner">${inner}</div>
    <div class="label ${lcls}">${esc(d.name)}</div>
    ${d.subtitle ? `<div class="subtitle">${esc(d.subtitle)}</div>` : ''}
  </div>`;
}

/** CSS that sizes/positions the card image so the .art box (a size container) only shows the art window. */
function cropStyle(k) {
  const y0 = k.top / 100, y1 = Math.max(k.bottom, k.top + 5) / 100;
  const fx = k.x / 100, fy = Math.min(Math.max(k.y / 100, y0), y1);
  const A = CARD_ASPECT;
  const H = `(max(100cqh / ${y1 - y0}, 100cqw / ${A}) * ${k.zoom})`;
  return [
    `height:calc${H}`,
    `width:calc(${H} * ${A})`,
    `left:clamp(calc(100cqw - ${H} * ${A}), calc(50cqw - ${H} * ${A * fx}), 0px)`,
    `top:clamp(calc(100cqh - ${H} * ${y1}), calc(50cqh - ${H} * ${fy}), calc(${H} * ${-y0}))`,
  ].join(';');
}

/** Best tile width for n tiles in a w×h box, allowing up to 3 wrapped lines. */
function fitTiles(n, w, h, gap = TABLE.gap) {
  if (!n) return h * CARD_ASPECT;
  let best = 0;
  for (let lines = 1; lines <= 3; lines++) {
    const per = Math.ceil(n / lines);
    const byH = ((h - (lines - 1) * gap) / lines) * CARD_ASPECT;
    const byW = (w - (per - 1) * gap) / per;
    best = Math.max(best, Math.min(byH, byW));
  }
  return Math.floor(best);
}

function tierSlideHTML(s, editing) {
  const tableH = STAGE_H - TABLE.top - TABLE.bottom;
  const rowH = (tableH - (s.tiers.length - 1) * TABLE.gap) / Math.max(1, s.tiers.length);
  const areaW = STAGE_W - TABLE.left - TABLE.right - TABLE.labelW - TABLE.gap;
  const rows = s.tiers.map((t) => {
    const ds = t.deckIds.map(deck).filter(Boolean);
    const w = fitTiles(ds.length, areaW, rowH);
    const tiles = ds.map((d) => deckTileHTML(d, s.display, { style: `width:${w}px;height:${Math.floor(w / CARD_ASPECT)}px`, selectable: editing })).join('');
    return `<div class="tier-row ${editing && ui.selectedTier === t.id ? 'selected' : ''}" data-tier="${t.id}">
      <div class="tier-label" style="background:${esc(t.color)}"><div class="tier-name">${esc(t.name)}</div><div class="tier-lines">${esc(t.lines)}</div></div>
      <div class="tier-decks" data-drop="${t.id}">${tiles}</div>
    </div>`;
  }).join('');
  return `<div class="stage ${editing ? 'editing' : ''}">
    <h1 class="s-title">${esc(s.title)}</h1>
    ${s.logo ? `<img class="s-logo" src="${esc(s.logo)}" alt="">` : ''}
    ${s.showArrow ? '<div class="tier-arrow"></div>' : ''}
    <div class="tier-table">${rows}</div>
    <div class="s-badge">${esc(s.badge)}${s.badgeSub ? `<span class="sub">${esc(s.badgeSub)}</span>` : ''}</div>
    ${s.footnote ? `<div class="s-foot">${esc(s.footnote)}</div>` : ''}
  </div>`;
}

function deckSlideHTML(s) {
  const d = deck(s.deckId);
  if (!d) return `<div class="stage"><div class="spot"><div class="spot-name">Pick a deck →</div></div></div>`;
  const tierSlide = state.slides.find((x) => x.type === 'tier' && x.tiers.some((t) => t.deckIds.includes(d.id)));
  const tier = tierSlide?.tiers.find((t) => t.deckIds.includes(d.id));
  const key = card(d.keyCard);
  const legends = d.legends.map((id) => {
    const c = card(id);
    return `<div class="spot-legend plate" style="${plinth(hexOf(c))}">${artHTML(c)}<div class="cap">${esc(c?.name || '—')}</div></div>`;
  }).join('');
  return `<div class="stage">
    <div class="spot">
      <div class="spot-info">
        ${tier ? `<div class="spot-tier" style="background:${esc(tier.color)}">${esc(tier.name)}</div>` : ''}
        <div class="spot-name">${esc(d.name)}</div>
        <div class="spot-pips">${chips(deckColors(d), 'pip')}</div>
        ${d.subtitle ? `<div class="spot-sub">${esc(d.subtitle)}</div>` : ''}
        <div class="spot-notes">${esc(d.notes)}</div>
      </div>
      <div class="spot-legends">${legends}</div>
      <div class="spot-key"><div class="spot-heading">Key card</div><div class="plate" style="${plinth(hexOf(key))}">${artHTML(key, { full: true })}<div class="cap">${esc(key?.name || '')}</div></div></div>
    </div>
  </div>`;
}

function slideHTML(s, editing = false) {
  if (!s) return '<div class="stage"></div>';
  const body = s.type === 'deck' ? deckSlideHTML(s) : tierSlideHTML(s, editing);
  return body;
}

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
  const s = slide();
  $('#slide-list').innerHTML = state.slides.map((x, i) => `
    <li data-slide="${x.id}" class="${x.id === ui.slideId ? 'active' : ''}">
      <span class="t">${i + 1}. ${esc(x.name || (x.type === 'deck' ? 'Deck spotlight' : 'Tier list'))}<br><span class="k">${x.type === 'deck' ? 'Deck spotlight' : 'Tier list'}</span></span>
      <button data-move="-1" title="Move up">↑</button><button data-move="1" title="Move down">↓</button><button data-del-slide title="Delete">×</button>
    </li>`).join('');
  renderPool();
  renderStage();
  renderSlideInspector();
}

function renderStage() {
  const wrap = $('#stage-wrap');
  const r = wrap.getBoundingClientRect();
  mountScaled($('#stage-host'), slideHTML(slide(), true), Math.max(200, r.width - 28), Math.max(120, r.height - 28));
}

function renderPool() {
  const s = slide();
  const pw = $('.pool-wrap');
  if (!s || s.type !== 'tier') { pw.hidden = true; return; }
  pw.hidden = false;
  const ranked = new Set(s.tiers.flatMap((t) => t.deckIds));
  const pool = state.decks.filter((d) => !ranked.has(d.id));
  $('#pool').innerHTML = pool.length ? pool.map((d) => deckTileHTML(d, s.display)).join('') : '<span class="hint">All decks are ranked. Drag one here to unrank it.</span>';
}

function renderSlideInspector() {
  const s = slide();
  const el = $('#slide-inspector');
  if (!s) { el.innerHTML = '<p class="hint">Add a slide to get started.</p>'; return; }
  if (s.type === 'deck') {
    el.innerHTML = `<h3>Deck spotlight</h3>
      <label>Slide name</label><input data-s="name" value="${esc(s.name)}">
      <label>Deck</label><select data-s="deckId">${state.decks.map((d) => `<option value="${d.id}" ${d.id === s.deckId ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</select>
      <p class="hint">The spotlight shows the deck's three Legends (art crops) and its key card. Edit those, plus notes, in the Decks tab.</p>
      <button data-edit-deck="${s.deckId}" class="block">Edit this deck</button>`;
    return;
  }
  el.innerHTML = `<h3>Tier list slide</h3>
    <label>Slide name</label><input data-s="name" value="${esc(s.name)}">
    <label>Title</label><input data-s="title" value="${esc(s.title)}">
    <label>Deck display</label>
    <select data-s="display">${Object.entries(DISPLAY_MODES).map(([k, v]) => `<option value="${k}" ${k === s.display ? 'selected' : ''}>${v}</option>`).join('')}</select>
    <div class="grid2">
      <div><label>Side badge</label><textarea data-s="badge" rows="2">${esc(s.badge)}</textarea></div>
      <div><label>Badge accent line</label><input data-s="badgeSub" value="${esc(s.badgeSub)}"></div>
    </div>
    <label>Footnote</label><input data-s="footnote" value="${esc(s.footnote)}">
    <label>Logo (URL or upload)</label>
    <div class="row gap"><input data-s="logo" value="${esc(s.logo?.startsWith('data:') ? '(uploaded image)' : s.logo)}" placeholder="https://…">
      <label class="filebtn" style="margin:0;text-transform:none;letter-spacing:0;font-size:13px;color:var(--text)">Upload<input type="file" accept="image/*" data-upload-logo hidden></label></div>
    <label><input type="checkbox" data-s="showArrow" ${s.showArrow ? 'checked' : ''} style="width:auto"> Show tier arrow</label>
    <h3 style="margin-top:18px">Tiers</h3>
    ${s.tiers.map((t, i) => `<div class="tier-edit ${ui.selectedTier === t.id ? 'selected' : ''}" data-tier-edit="${t.id}">
      <div class="row gap"><input data-t="name" value="${esc(t.name)}" style="flex:1"><input type="color" data-t="color" value="${esc(t.color)}">
      <button class="small" data-tmove="-1">↑</button><button class="small" data-tmove="1">↓</button><button class="small danger" data-tdel>×</button></div>
      <textarea data-t="lines" rows="3" style="margin-top:6px">${esc(t.lines)}</textarea>
    </div>`).join('')}
    <button data-tadd class="block">+ Add tier</button>`;
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
  renderStage();
  renderPool();
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
    } else {
      ui.slideId = li.dataset.slide;
      ui.selectedTier = null;
    }
    save(); renderSlides();
  });
  $('#add-tier-slide').onclick = () => {
    const base = state.slides.find((x) => x.type === 'tier');
    const s = base ? clone(base) : makeDemo().slides[0];
    s.id = uid(); s.name = 'Tier list ' + (state.slides.length + 1);
    s.tiers.forEach((t) => { t.id = uid(); t.deckIds = []; });
    state.slides.push(s); ui.slideId = s.id; save(); renderSlides();
  };
  $('#add-deck-slide').onclick = () => {
    const d = state.decks[0];
    const s = { id: uid(), type: 'deck', name: 'Spotlight: ' + (d?.name || ''), deckId: d?.id || null };
    state.slides.push(s); ui.slideId = s.id; save(); renderSlides();
  };

  // inspector edits
  const insp = $('#slide-inspector');
  insp.addEventListener('input', (e) => {
    const s = slide();
    const k = e.target.dataset.s;
    const tk = e.target.dataset.t;
    if (k) {
      if (k === 'logo' && e.target.value === '(uploaded image)') return;
      s[k] = e.target.type === 'checkbox' ? e.target.checked : e.target.value;
      if (k === 'deckId') { const d = deck(s.deckId); s.name = 'Spotlight: ' + (d?.name || ''); }
    } else if (tk) {
      const t = s.tiers.find((x) => x.id === e.target.closest('[data-tier-edit]').dataset.tierEdit);
      t[tk] = e.target.value;
    } else return;
    save(); renderStage();
    if (k === 'name' || k === 'deckId') $$('#slide-list li.active .t')[0] && renderSlidesListOnly();
  });
  insp.addEventListener('change', async (e) => {
    if (e.target.matches('[data-upload-logo]') && e.target.files[0]) {
      slide().logo = await fileToDataURL(e.target.files[0], 400);
      save(); renderStage(); renderSlideInspector();
    } else if (e.target.dataset.s === 'display' || e.target.dataset.s === 'deckId') {
      renderSlides();
    }
  });
  insp.addEventListener('click', (e) => {
    const s = slide();
    if (e.target.dataset.editDeck) { ui.deckId = e.target.dataset.editDeck; setView('decks'); return; }
    if ('tadd' in e.target.dataset) {
      s.tiers.push({ id: uid(), name: 'Tier ' + (s.tiers.length + 1), lines: '', color: '#cccccc', deckIds: [] });
    } else {
      const box = e.target.closest('[data-tier-edit]');
      if (!box) return;
      const i = s.tiers.findIndex((t) => t.id === box.dataset.tierEdit);
      if (e.target.dataset.tmove) {
        const j = i + Number(e.target.dataset.tmove);
        if (j < 0 || j >= s.tiers.length) return;
        [s.tiers[i], s.tiers[j]] = [s.tiers[j], s.tiers[i]];
      } else if ('tdel' in e.target.dataset) {
        if (!confirm('Delete this tier? Its decks go back to Unranked.')) return;
        s.tiers.splice(i, 1);
      } else return;
    }
    save(); renderSlides();
  });

  // drag & drop + tap-to-move on stage and pool
  const zones = [$('#stage-host'), $('#pool')];
  let dragId = null;
  for (const z of zones) {
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
      const dz = e.target.closest('[data-drop]');
      const label = e.target.closest('.tier-label');
      if (label) {
        const tid = label.closest('[data-tier]').dataset.tier;
        if (ui.selectedDeck) return moveDeck(ui.selectedDeck, tid);
        ui.selectedTier = ui.selectedTier === tid ? null : tid;
        renderStage(); renderSlideInspector();
        return;
      }
      if (tile && (!ui.selectedDeck || ui.selectedDeck === tile.dataset.deck)) {
        ui.selectedDeck = ui.selectedDeck === tile.dataset.deck ? null : tile.dataset.deck;
        renderStage(); renderPool();
      } else if (ui.selectedDeck && dz) {
        moveDeck(ui.selectedDeck, dz.dataset.drop, tile?.dataset.deck);
      }
    });
    z.addEventListener('dblclick', (e) => {
      const tile = e.target.closest('.deck-tile');
      if (tile) { ui.deckId = tile.dataset.deck; ui.selectedDeck = null; setView('decks'); }
    });
  }
}
function renderSlidesListOnly() {
  const active = $('#slide-list li.active .t');
  const s = slide();
  if (active) active.firstChild.textContent = `${state.slides.indexOf(s) + 1}. ${s.name}`;
}

/* ---------------- Decks view ---------------- */
function renderDecks() {
  if (!deck(ui.deckId)) ui.deckId = state.decks[0]?.id;
  $('#deck-list').innerHTML = state.decks.map((d) => `<li data-deck-item="${d.id}" class="${d.id === ui.deckId ? 'active' : ''}">
    <span class="fan">${d.legends.map((id) => { const c = card(id); return `<span class="mini" style="${plinth(hexOf(c))}">${artHTML(c, { full: true })}</span>`; }).join('')}</span>
    <span class="dl-text"><strong>${esc(d.name)}</strong><span class="hint">${esc(d.subtitle)}</span>
    <span class="chips">${chips(deckColors(d))}</span></span></li>`).join('');
  const d = deck(ui.deckId);
  const ed = $('#deck-editor');
  if (!d) { ed.innerHTML = '<div class="empty-msg">No decks yet. Create one on the left.</div>'; return; }
  const slot = (id, role, i) => {
    const c = card(id);
    return `<div class="slot" data-slot="${role}" data-i="${i ?? ''}">${artHTML(c)}<div class="n">${esc(c?.name || (role === 'key' ? 'Pick key card' : 'Pick legend'))}</div></div>`;
  };
  ed.innerHTML = `<div class="deck-edit">
    <div>
      <h3>Deck</h3>
      <div class="grid2">
        <div><label>Name / color code</label><input data-d="name" value="${esc(d.name)}" placeholder="RRG"></div>
        <div><label>Subtitle (optional)</label><input data-d="subtitle" value="${esc(d.subtitle)}" placeholder="e.g. Control"></div>
      </div>
      <label>Legends</label>
      <div class="slots">${d.legends.map((id, i) => slot(id, 'legend', i)).join('')}</div>
      <label>Key card</label>
      <div class="slots"><div></div>${slot(d.keyCard, 'key')}<div></div></div>
      <label>Display override</label>
      <div class="seg">${[['inherit', 'Use slide setting'], ...Object.entries(DISPLAY_MODES)].map(([k, v]) => `<button data-display="${k}" class="${(d.display || 'inherit') === k ? 'on' : ''}">${v}</button>`).join('')}</div>
      <label>Notes (shown on spotlight slide)</label>
      <textarea data-d="notes" rows="4">${esc(d.notes)}</textarea>
      <div class="row gap" style="margin-top:14px">
        <button data-spotlight>+ Spotlight slide for this deck</button>
        <button data-dup>Duplicate</button>
        <button data-del-deck class="danger">Delete deck</button>
      </div>
    </div>
    <div>
      <h3>Preview</h3>
      <div class="previews" id="deck-previews"></div>
      <p class="hint" style="margin-top:14px">Art crops are set per card. Open the Card Library and use <b>Crop art</b> to frame each Legend's art so the card text is hidden.</p>
    </div>
  </div>`;
  renderDeckPreviews();
}
function renderDeckPreviews() {
  const d = deck(ui.deckId);
  const box = $('#deck-previews');
  if (!d || !box) return;
  box.innerHTML = Object.entries(DISPLAY_MODES).map(([k, v]) =>
    `<figure>${deckTileHTML({ ...d, display: k }, k, { selectable: false })}<figcaption>${v}</figcaption></figure>`).join('');
}

function bindDecks() {
  $('#deck-list').addEventListener('click', (e) => {
    const li = e.target.closest('[data-deck-item]');
    if (li) { ui.deckId = li.dataset.deckItem; renderDecks(); }
  });
  $('#add-deck').onclick = () => {
    const d = { id: uid(), name: 'NEW', subtitle: '', legends: [null, null, null], keyCard: null, display: 'inherit', notes: '' };
    state.decks.push(d); ui.deckId = d.id; save(); renderDecks();
  };
  const ed = $('#deck-editor');
  ed.addEventListener('input', (e) => {
    const k = e.target.dataset.d;
    if (!k) return;
    deck(ui.deckId)[k] = e.target.value;
    save(); renderDeckPreviews();
    const li = $(`[data-deck-item="${ui.deckId}"] strong`);
    if (li && k === 'name') li.textContent = e.target.value;
  });
  ed.addEventListener('click', (e) => {
    const d = deck(ui.deckId);
    const slotEl = e.target.closest('[data-slot]');
    if (slotEl) {
      const role = slotEl.dataset.slot;
      openPicker(role === 'key' ? 'all' : 'legend', (id) => {
        if (role === 'key') d.keyCard = id; else d.legends[Number(slotEl.dataset.i)] = id;
        save(); renderDecks();
      });
      return;
    }
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.display) { d.display = b.dataset.display; }
    else if ('spotlight' in b.dataset) {
      const s = { id: uid(), type: 'deck', name: 'Spotlight: ' + d.name, deckId: d.id };
      state.slides.push(s); ui.slideId = s.id; save(); setView('slides'); return;
    } else if ('dup' in b.dataset) {
      const c = { ...clone(d), id: uid(), name: d.name + ' (copy)' };
      state.decks.push(c); ui.deckId = c.id;
    } else if ('delDeck' in b.dataset) {
      if (!confirm(`Delete deck "${d.name}"?`)) return;
      state.decks = state.decks.filter((x) => x.id !== d.id);
      state.slides.forEach((s) => s.tiers?.forEach((t) => (t.deckIds = t.deckIds.filter((x) => x !== d.id))));
    } else return;
    save(); renderDecks();
  });
}

/* ---------------- Card picker ---------------- */
function openPicker(kind, onPick) {
  let q = '';
  let filter = kind;
  const draw = () => {
    const list = state.cards.filter((c) => (filter === 'all' || c.kind === filter) && c.name.toLowerCase().includes(q.toLowerCase()));
    $('#picker-grid').innerHTML = `<div class="pick" data-pick=""><div class="art empty"></div><div class="n">(none)</div></div>` +
      list.map((c) => `<div class="pick" data-pick="${c.id}">${artHTML(c)}<div class="n">${esc(c.name)}</div></div>`).join('');
  };
  openModal(`<h3>Choose ${kind === 'legend' ? 'a Legend' : 'a card'}</h3>
    <div class="toolbar"><input type="search" id="picker-q" placeholder="Search…">
    <select id="picker-f"><option value="legend" ${kind === 'legend' ? 'selected' : ''}>Legends</option><option value="card">Other cards</option><option value="all" ${kind === 'all' ? 'selected' : ''}>All</option></select></div>
    <div class="picker-grid" id="picker-grid"></div>
    <p class="hint">Missing a card? Add it in the Card Library or import from your card source.</p>`);
  draw();
  $('#picker-q').oninput = (e) => { q = e.target.value; draw(); };
  $('#picker-f').onchange = (e) => { filter = e.target.value; draw(); };
  $('#picker-q').focus();
  $('#picker-grid').onclick = (e) => {
    const p = e.target.closest('[data-pick]');
    if (!p) return;
    closeModal();
    onPick(p.dataset.pick || null);
  };
}

/* ---------------- Card library ---------------- */
function renderCards() {
  const q = $('#card-search').value.toLowerCase();
  const f = $('#card-filter').value;
  const list = state.cards.filter((c) => (f === 'all' || c.kind === f) && c.name.toLowerCase().includes(q));
  $('#card-grid').innerHTML = list.length ? list.map((c) => `<div class="card-cell">
      <div class="thumbs">${artHTML(c, { full: true })}${artHTML(c)}</div>
      <div class="nm" title="${esc(c.name)}">${esc(c.name)}</div>
      <div class="meta">${c.color ? `<span class="dot" style="background:${COLORS[c.color].hex}"></span>` : ''}<span class="tag">${c.kind === 'legend' ? 'Legend' : 'Card'}</span>${c.placeholder ? '<span class="tag">demo</span>' : ''}</div>
      <div class="btns"><button class="small" data-crop="${c.id}">Crop art</button><button class="small" data-edit-card="${c.id}">Edit</button><button class="small danger" data-del-card="${c.id}">×</button></div>
    </div>`).join('') : '<div class="empty-msg">No cards match. Add one, or import from the Card Source tab.</div>';
}

function cardForm(c, onSave) {
  const isNew = !c;
  c = c ? clone(c) : { id: uid(), name: '', kind: 'legend', color: '', img: '', crop: { ...DEFAULT_CROP } };
  openModal(`<h3>${isNew ? 'Add card' : 'Edit card'}</h3>
    <div class="grid2">
      <div><label>Name</label><input id="cf-name" value="${esc(c.name)}"></div>
      <div><label>Type</label><select id="cf-kind"><option value="legend" ${c.kind === 'legend' ? 'selected' : ''}>Legend</option><option value="card" ${c.kind !== 'legend' ? 'selected' : ''}>Other card (key card, unit, program…)</option></select></div>
      <div><label>Color</label><select id="cf-color"><option value="">None / multi</option>${Object.entries(COLORS).map(([k, v]) => `<option value="${k}" ${c.color === k ? 'selected' : ''}>${v.name}</option>`).join('')}</select></div>
      <div><label>Image URL</label><input id="cf-img" type="url" value="${esc(c.img?.startsWith('data:') ? '' : c.img)}" placeholder="https://… (from the card database)"></div>
    </div>
    <label>…or upload an image</label><input type="file" id="cf-file" accept="image/*">
    <div class="row gap" style="margin-top:16px"><button class="primary" id="cf-save">Save</button><button data-close>Cancel</button></div>`);
  $('#cf-save').onclick = async () => {
    c.name = $('#cf-name').value.trim() || 'Untitled';
    c.kind = $('#cf-kind').value;
    c.color = $('#cf-color').value;
    const f = $('#cf-file').files[0];
    if (f) { c.img = await fileToDataURL(f, 700); c.placeholder = false; }
    else if ($('#cf-img').value.trim()) { c.img = $('#cf-img').value.trim(); c.placeholder = false; }
    closeModal();
    onSave(c);
  };
}

function openCrop(c) {
  const k = { ...DEFAULT_CROP, ...c.crop };
  const slider = (id, label, min, max, step) =>
    `<div><label>${label} <span id="cv-${id}"></span></label><input type="range" data-k="${id}" min="${min}" max="${max}" step="${step}" value="${k[id]}" style="width:100%"></div>`;
  openModal(`<h3>Crop art — ${esc(c.name)}</h3>
    <p class="hint">Set <b>Art top</b> and <b>Art bottom</b> to the edges of the card's illustration (the dashed box). Nothing outside it is ever shown,
      so rules text stays hidden in every layout. Click the card to choose the focus point.</p>
    <div class="crop">
      <div><div class="crop-src" id="crop-src"><img src="${esc(c.img)}" alt="" referrerpolicy="no-referrer">
        <div class="shade" id="sh-top" style="top:0"></div><div class="shade" id="sh-bot" style="bottom:0"></div>
        <div class="win" id="crop-win"></div><div class="focus" id="crop-focus"></div></div></div>
      <div>
        <div class="grid2">${slider('top', 'Art top', 0, 90, 1)}${slider('bottom', 'Art bottom', 10, 100, 1)}
        ${slider('x', 'Focus X', 0, 100, 1)}${slider('y', 'Focus Y', 0, 100, 1)}</div>
        ${slider('zoom', 'Extra zoom', 1, 3, 0.05)}
        <div class="crop-previews" id="crop-previews"></div>
        <div class="row gap" style="margin-top:16px"><button class="primary" id="crop-save">Save crop</button>
          <button id="crop-all" title="Apply this art window (top/bottom) to every card of the same type">Use window for all ${c.kind === 'legend' ? 'Legends' : 'cards'}</button>
          <button id="crop-default">Reset</button><button data-close>Cancel</button></div>
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
    const t = { ...c, crop: k };
    $('#crop-previews').innerHTML = [['Legend strip', 60, 220], ['Tile', 150, 208], ['Band', 200, 70], ['Wide', 260, 146]]
      .map(([n, w, h]) => `<figure>${artHTML(t).replace('class="art', `style="width:${w}px;height:${h}px;flex:none" class="art`)}<div>${n}</div></figure>`).join('');
  };
  draw();
  $('#crop-src').onclick = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    k.x = Math.round(((e.clientX - r.left) / r.width) * 100);
    k.y = Math.round(((e.clientY - r.top) / r.height) * 100);
    draw();
  };
  $('#modal-body').oninput = (e) => { const id = e.target.dataset.k; if (id) { k[id] = Number(e.target.value); draw(); } };
  $('#crop-default').onclick = () => { Object.assign(k, DEFAULT_CROP); draw(); };
  $('#crop-save').onclick = () => { card(c.id).crop = { ...k }; save(); closeModal(); renderCards(); };
  $('#crop-all').onclick = () => {
    state.cards.filter((x) => x.kind === c.kind).forEach((x) => (x.crop = { ...DEFAULT_CROP, ...x.crop, top: k.top, bottom: k.bottom }));
    card(c.id).crop = { ...k };
    save(); closeModal(); renderCards(); toast('Art window applied to all ' + (c.kind === 'legend' ? 'Legends' : 'cards') + '.');
  };
}

function bindCards() {
  $('#card-search').oninput = renderCards;
  $('#card-filter').onchange = renderCards;
  $('#add-card').onclick = () => cardForm(null, (c) => { state.cards.push(c); save(); renderCards(); });
  $('#card-grid').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (!b) return;
    if (b.dataset.crop) openCrop(card(b.dataset.crop));
    else if (b.dataset.editCard) cardForm(card(b.dataset.editCard), (c) => { Object.assign(card(c.id), c); save(); renderCards(); });
    else if (b.dataset.delCard) {
      const id = b.dataset.delCard;
      const used = state.decks.filter((d) => d.keyCard === id || d.legends.includes(id));
      if (!confirm(used.length ? `This card is used in ${used.length} deck(s). Delete anyway?` : 'Delete this card?')) return;
      state.cards = state.cards.filter((c) => c.id !== id);
      used.forEach((d) => { if (d.keyCard === id) d.keyCard = null; d.legends = d.legends.map((x) => (x === id ? null : x)); });
      save(); renderCards();
    }
  });
}

/* ---------------- Card source (import) ---------------- */
function findFirstArray(o, path = '') {
  if (Array.isArray(o)) return path;
  if (o && typeof o === 'object') {
    for (const [k, v] of Object.entries(o)) {
      const p = findFirstArray(v, path ? `${path}.${k}` : k);
      if (p !== null) return p;
    }
  }
  return null;
}
function guessKey(sample, candidates) {
  const keys = Object.keys(sample || {});
  for (const c of candidates) {
    const hit = keys.find((k) => k.toLowerCase() === c);
    if (hit) return hit;
  }
  for (const c of candidates) {
    const hit = keys.find((k) => k.toLowerCase().includes(c));
    if (hit) return hit;
  }
  return '';
}

let sourceData = null;
function renderSource() {
  const src = state.source;
  $('#source-view').innerHTML = `<h3>Card source</h3>
    <div class="callout">Point this at the official Cyberpunk TCG card database export (or any JSON list of cards).
      Load it from a URL, a downloaded <code>.json</code> file, or paste it. Then map the fields and import —
      Legends and key cards land in your Card Library with their official art.<br><br>
      If the JSON only has an image <i>filename</i> or id, use the <b>image URL template</b>, e.g.
      <code>https://&lt;cdn-host&gt;/cards/{id}.webp</code> — any <code>{field}</code> is replaced from each card.</div>
    <label>JSON URL</label>
    <div class="row gap"><input type="url" id="src-url" value="${esc(src.url)}" placeholder="https://…/cards.json"><button id="src-fetch">Fetch</button></div>
    <div class="row gap" style="margin-top:8px"><label class="filebtn" style="margin:0;text-transform:none;letter-spacing:0;font-size:13px;color:var(--text)">Load .json file<input type="file" id="src-file" accept=".json,application/json" hidden></label>
      <button id="src-paste-btn">Paste JSON</button></div>
    <textarea id="src-paste" rows="6" hidden placeholder='[{"id":"...","name":"...","type":"Legend","color":"Red","image":"https://..."}]'></textarea>
    <div id="src-status" class="hint" style="margin-top:8px"></div>
    <h3 style="margin-top:20px">Field mapping</h3>
    <div class="grid2">
      <div><label>Path to card list</label><input id="map-listPath" value="${esc(src.listPath)}" placeholder="(auto) e.g. data.cards"></div>
      <div><label>ID field</label><input id="map-idKey" value="${esc(src.idKey)}"></div>
      <div><label>Name field</label><input id="map-nameKey" value="${esc(src.nameKey)}"></div>
      <div><label>Image field</label><input id="map-imageKey" value="${esc(src.imageKey)}" placeholder="e.g. images.large"></div>
      <div><label>Image URL template (optional)</label><input id="map-imageTemplate" value="${esc(src.imageTemplate)}" placeholder="https://cdn…/{id}.png"></div>
      <div><label>Color field</label><input id="map-colorKey" value="${esc(src.colorKey)}"></div>
      <div><label>Type field</label><input id="map-typeKey" value="${esc(src.typeKey)}"></div>
      <div><label>Type value meaning “Legend”</label><input id="map-legendValue" value="${esc(src.legendValue)}"></div>
    </div>
    <label><input type="checkbox" id="src-legends-only" style="width:auto"> Import Legends only</label>
    <div class="row gap" style="margin-top:12px"><button id="src-preview">Preview</button><button class="primary" id="src-import">Import into library</button></div>
    <div id="src-preview-box" class="picker-grid"></div>`;
}

function mapCards() {
  const src = state.source;
  if (!sourceData) throw new Error('Load some JSON first.');
  let list = getPath(sourceData, src.listPath);
  if (!Array.isArray(list)) {
    const p = findFirstArray(sourceData);
    if (p === null) throw new Error('No array of cards found in that JSON.');
    list = getPath(sourceData, p);
    src.listPath = p;
    $('#map-listPath').value = p;
  }
  return list.filter((o) => o && typeof o === 'object').map((o) => {
    const typeVal = String(getPath(o, src.typeKey) ?? '').toLowerCase();
    let img = src.imageTemplate
      ? src.imageTemplate.replace(/\{([^}]+)\}/g, (_, k) => encodeURIComponent(getPath(o, k) ?? ''))
      : getPath(o, src.imageKey);
    if (img && typeof img === 'object') img = img.url || img.large || img.src || Object.values(img).find((v) => typeof v === 'string');
    return {
      sourceId: String(getPath(o, src.idKey) ?? ''),
      name: String(getPath(o, src.nameKey) ?? 'Unnamed'),
      kind: src.legendValue && typeVal.includes(src.legendValue.toLowerCase()) ? 'legend' : 'card',
      color: normColor(getPath(o, src.colorKey)),
      img: img ? String(img) : '',
    };
  });
}

function bindSource() {
  const view = $('#source-view');
  const status = (m) => ($('#src-status').textContent = m);
  const loaded = (data, from) => {
    sourceData = data;
    const p = findFirstArray(data);
    const list = p === null ? null : getPath(data, p);
    if (!list) return status('Loaded, but no array of cards found.');
    const sample = list[0] || {};
    const s = state.source;
    if (!s.listPath || !Array.isArray(getPath(data, s.listPath))) s.listPath = p;
    if (!(s.nameKey in sample)) s.nameKey = guessKey(sample, ['name', 'title', 'card_name']) || s.nameKey;
    if (!(s.idKey in sample)) s.idKey = guessKey(sample, ['id', 'code', 'card_id', 'number', 'slug']) || s.idKey;
    if (!(s.imageKey in sample)) s.imageKey = guessKey(sample, ['image', 'image_url', 'imageurl', 'img', 'art', 'picture', 'images']) || s.imageKey;
    if (!(s.colorKey in sample)) s.colorKey = guessKey(sample, ['color', 'colour', 'faction', 'colors']) || s.colorKey;
    if (!(s.typeKey in sample)) s.typeKey = guessKey(sample, ['type', 'card_type', 'cardtype', 'category', 'kind']) || s.typeKey;
    save();
    renderSource();
    status(`Loaded ${list.length} records from ${from}. Sample fields: ${Object.keys(sample).join(', ')}`);
  };
  view.addEventListener('input', (e) => {
    const m = e.target.id.match(/^map-(\w+)$/);
    if (m) { state.source[m[1]] = e.target.value; save(); }
    if (e.target.id === 'src-url') { state.source.url = e.target.value; save(); }
    if (e.target.id === 'src-paste') {
      try { loaded(JSON.parse(e.target.value), 'pasted JSON'); } catch { status('Waiting for valid JSON…'); }
    }
  });
  view.addEventListener('change', async (e) => {
    if (e.target.id !== 'src-file' || !e.target.files[0]) return;
    try { loaded(JSON.parse(await e.target.files[0].text()), e.target.files[0].name); }
    catch (err) { status('Could not parse file: ' + err.message); }
  });
  view.addEventListener('click', async (e) => {
    const id = e.target.id;
    if (id === 'src-fetch') {
      const url = $('#src-url').value.trim();
      if (!url) return status('Enter a URL.');
      status('Fetching…');
      try {
        const r = await fetch(url);
        if (!r.ok) throw new Error('HTTP ' + r.status);
        loaded(await r.json(), url);
      } catch (err) {
        status(`Fetch failed (${err.message}). The site may block cross-origin requests — open the URL in a new tab, save it as .json, and use “Load .json file”.`);
      }
    } else if (id === 'src-paste-btn') {
      $('#src-paste').hidden = !$('#src-paste').hidden;
    } else if (id === 'src-preview' || id === 'src-import') {
      let cards;
      try { cards = mapCards(); } catch (err) { return status(err.message); }
      if ($('#src-legends-only').checked) cards = cards.filter((c) => c.kind === 'legend');
      if (id === 'src-preview') {
        $('#src-preview-box').innerHTML = cards.slice(0, 40).map((c) =>
          `<div class="pick">${artHTML(c, { full: true })}<div class="n">${esc(c.name)}</div><div class="n hint">${c.kind}${c.color ? ' · ' + c.color : ''}</div></div>`).join('');
        status(`${cards.length} cards mapped (${cards.filter((c) => c.kind === 'legend').length} Legends). Showing first ${Math.min(40, cards.length)}.`);
      } else {
        let added = 0, updated = 0;
        for (const c of cards) {
          const existing = state.cards.find((x) => (c.sourceId && x.sourceId === c.sourceId) || x.name === c.name);
          if (existing) { Object.assign(existing, { ...c, crop: existing.crop, placeholder: false }); updated++; }
          else { state.cards.push({ id: uid(), ...c, crop: { ...DEFAULT_CROP } }); added++; }
        }
        save();
        status(`Imported: ${added} new, ${updated} updated. Find them in the Card Library.`);
      }
    }
  });
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
        resolve(cv.toDataURL(file.type === 'image/png' ? 'image/png' : 'image/jpeg', 0.85));
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
  presentIdx = Math.max(0, start);
  $('#present').hidden = false;
  document.documentElement.requestFullscreen?.().catch(() => {});
  drawPresent();
}
function drawPresent() {
  const s = state.slides[presentIdx];
  mountScaled($('#present-host'), slideHTML(s, false), window.innerWidth, window.innerHeight);
  $('#present-count').textContent = `${presentIdx + 1} / ${state.slides.length}`;
}
function exitPresent() {
  $('#present').hidden = true;
  if (document.fullscreenElement) document.exitFullscreen?.();
}

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
    const canvas = await window.html2canvas(host.firstElementChild, { useCORS: true, backgroundColor: null, scale: 1, width: STAGE_W, height: STAGE_H });
    host.remove();
    const a = document.createElement('a');
    a.download = (s.name || 'slide').replace(/[^\w-]+/g, '_') + '.png';
    a.href = canvas.toDataURL('image/png');
    a.click();
    toast('PNG saved.');
  } catch (err) {
    toast('PNG export failed: ' + (err.message || err) + '. If card images come from a CDN without CORS, use Present mode + a screenshot instead.', 7000);
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
  if (ui.view === 'slides') renderSlides();
  else if (ui.view === 'decks') renderDecks();
  else if (ui.view === 'cards') renderCards();
  else if (ui.view === 'source') renderSource();
}

function bindGlobal() {
  $$('.tabs button').forEach((b) => (b.onclick = () => setView(b.dataset.view)));
  $('#modal').addEventListener('click', (e) => { if (e.target === e.currentTarget || e.target.closest('[data-close]')) closeModal(); });
  $('#btn-present').onclick = () => present(Math.max(0, state.slides.indexOf(slide())));
  $('#btn-png').onclick = () => { if (ui.view !== 'slides') setView('slides'); exportPNG(); };
  $('#present').onclick = (e) => { presentIdx = Math.min(state.slides.length - 1, presentIdx + (e.clientX < window.innerWidth / 3 ? -1 : 1)); presentIdx = Math.max(0, presentIdx); drawPresent(); };
  document.addEventListener('keydown', (e) => {
    if (!$('#present').hidden) {
      if (e.key === 'Escape') exitPresent();
      else if (['ArrowRight', ' ', 'PageDown'].includes(e.key)) { presentIdx = Math.min(state.slides.length - 1, presentIdx + 1); drawPresent(); }
      else if (['ArrowLeft', 'PageUp'].includes(e.key)) { presentIdx = Math.max(0, presentIdx - 1); drawPresent(); }
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
      if (!Array.isArray(data.cards) || !Array.isArray(data.decks) || !Array.isArray(data.slides)) throw new Error('not a Tier List Studio project');
      state = { ...makeDemo(), ...data };
      ui.slideId = state.slides[0]?.id; ui.deckId = state.decks[0]?.id;
      save(); render(); toast('Project loaded.');
    } catch (err) { toast('Could not load: ' + err.message); }
    e.target.value = '';
  };
  $('#btn-reset').onclick = () => {
    if (!confirm('Replace everything with the demo project? Save your project first if you want to keep it.')) return;
    state = makeDemo(); ui.slideId = state.slides[0].id; ui.deckId = state.decks[0].id;
    save(); render();
  };
}

bindGlobal();
bindSlides();
bindDecks();
bindCards();
bindSource();
render();
