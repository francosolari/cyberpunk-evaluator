// Captures the promo screenshots listed in PROMO_SHOTS.md from the live site, with real card art.
//
//   npm i playwright && npx playwright install chromium
//   node promo/capture.mjs [siteUrl] [outDir]
//
// Optional: put a deck export (text, import link or deck-builder link) in promo/hero-deck.txt to feature
// that deck. Otherwise the seeded deck with the fullest list is used.
import { chromium, devices } from 'playwright';
import { mkdirSync, existsSync, readFileSync, renameSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const SITE = process.argv[2] || 'https://francosolari.github.io/cyberpunk-evaluator/';
const OUT = process.argv[3] || join(here, 'shots');
const HERO = existsSync(join(here, 'hero-deck.txt')) ? readFileSync(join(here, 'hero-deck.txt'), 'utf8') : '';
mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch();
const shotsTaken = [];
const errors = [];

async function openStudio(ctx) {
  const page = await ctx.newPage();
  page.on('pageerror', (e) => errors.push(e.message));
  await page.goto(SITE);
  // First run loads the card data and the seeded decks.
  await page.waitForFunction(() => typeof state !== 'undefined' && state.catalog && state.decks.length >= 4 && !state.decks.some(isDemoDeck), null, { timeout: 90_000 });
  await page.addStyleTag({ content: '.present-hud, .toast { display: none !important; } * { caret-color: transparent !important; }' });
  return page;
}
const settle = (page, root = 'body') => page.waitForFunction((r) => [...document.querySelectorAll(`${r} img`)].every((i) => i.complete), root, { timeout: 30_000 })
  .catch(() => {}).then(() => page.waitForTimeout(600));
async function shot(page, name, opts = {}) {
  await settle(page);
  await page.screenshot({ path: join(OUT, name + '.png'), ...opts });
  shotsTaken.push(name);
}
/** A slide at full 1920×1080 through Present mode. */
async function slideShot(page, index, name) {
  await page.evaluate((i) => present(i), index);
  await settle(page, '#present-host');
  await page.screenshot({ path: join(OUT, name + '.png') });
  shotsTaken.push(name);
  await page.evaluate(() => { $('#present').hidden = true; document.exitFullscreen?.().catch(() => {}); });
}
const selectSlide = (page, i) => page.evaluate((i) => { ui.slideId = state.slides[i].id; renderSlides(); }, i).then(() => page.waitForTimeout(500));
const setSlide = (page, i, patch) => page.evaluate(([i, patch]) => { Object.assign(state.slides[i], patch); save(); renderSlides(); }, [i, patch]);

/* ---------- Desktop: set up the featured deck ---------- */
const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
const page = await openStudio(ctx);
const hero = await page.evaluate((heroText) => {
  state.prefs = { ...state.prefs, guide: { dismissed: true } };
  const tierSlide = state.slides.find((s) => s.type === 'tier');
  let d;
  if (heroText.trim()) {
    d = [].concat(parseDeckExport(heroText))[0];
    state.decks.unshift(d);
  } else {
    d = state.decks.slice().sort((a, b) => deckCount(b) - deckCount(a))[0];
  }
  // Featured deck leads Tier 1.
  tierSlide.tiers.forEach((t) => (t.deckIds = t.deckIds.filter((x) => x !== d.id)));
  tierSlide.tiers[0].deckIds.unshift(d.id);
  // Core: the two most-copied cards of each type. Flex: two single/double copies near the end of the curve.
  d.roles = {};
  for (const g of typeGroups(d.main.map(([id, n]) => [card(id), n]).filter(([c]) => c))) {
    g.rows.slice().sort((a, b) => b[1] - a[1]).slice(0, 2).forEach(([c]) => (d.roles[c.id] = 'core'));
  }
  d.main.filter(([id, n]) => !d.roles[id] && n <= 2).slice(-2).forEach(([id]) => (d.roles[id] = 'flex'));
  const coreIds = Object.keys(d.roles).filter((id) => d.roles[id] === 'core');
  setKeys(d, [suggestKeyCard(d), ...coreIds].filter(Boolean).slice(0, 2));
  // Sideboard / options: a few on-color cards that aren't in the deck.
  if (!(d.side || []).length && !(d.options || []).length) {
    const cols = new Set(deckColors(d));
    const inDeck = new Set(d.main.map(([id]) => id));
    d.options = allCards().filter((c) => !isLegend(c) && cols.has(c.color) && !inDeck.has(c.id)).slice(0, 4).map((c) => [c.id, 2]);
  }
  // Alternate Legends: up to two same-color Legends for one slot, preferring ones other decks play.
  const main = legendsOf(d);
  const played = state.decks.flatMap((x) => x.legends);
  const pool = allCards().filter(isLegend).filter((c) => !main.includes(c.id))
    .sort((a, b) => played.filter((x) => x === b.id).length - played.filter((x) => x === a.id).length);
  const slot = main.find((id) => pool.some((c) => c.color === card(id)?.color)) || main[main.length - 1];
  setAlts(d, slot, pool.filter((c) => c.color === card(slot)?.color).slice(0, 2).map((c) => c.id));
  if (!d.notes) d.notes = 'Fast pressure with a flexible third Legend.';
  // Slides: tier list, deck page (names), deck page (full decklist).
  const deckSlide = (listStyle) => ({ id: uid(), type: 'deck', deckId: d.id, listStyle, name: 'Deck: ' + deckLabel(d) });
  state.slides = [tierSlide, deckSlide('list'), deckSlide('cards')];
  ui.slideId = tierSlide.id;
  save();
  return { id: d.id, name: d.name, label: deckLabel(d) };
}, HERO);
await page.reload();
await page.waitForFunction(() => typeof state !== 'undefined' && state.catalog, null, { timeout: 60_000 });
await page.addStyleTag({ content: '.present-hud, .toast { display: none !important; }' });
console.log('Featured deck:', hero.label, '·', hero.name);

/* ---------- Slides at 1920×1080 ---------- */
for (const [mode, name] of [['split', '01-tier-key-and-legends'], ['legends', '02-tier-legends'], ['legends-bands', '03-tier-legend-bands'], ['key-art', '04-tier-key-art'], ['key-full', '05-tier-key-full-card']]) {
  await setSlide(page, 0, { display: mode, look: 'ledger', showAlts: false });
  await slideShot(page, 0, name);
}
for (const look of ['band', 'frame', 'rail']) {
  await setSlide(page, 0, { display: 'split', look });
  await slideShot(page, 0, `06-tier-style-${look}`);
}
await setSlide(page, 0, { display: 'legends', look: 'ledger', showAlts: true });
await slideShot(page, 0, '07-tier-alternate-legends');
await setSlide(page, 0, { display: 'split', showAlts: false });
await slideShot(page, 1, '08-deck-page-names');
await slideShot(page, 2, '09-deck-page-full-decklist');

/* ---------- Desktop interface ---------- */
await page.setViewportSize({ width: 1600, height: 1000 });
await selectSlide(page, 0);
await shot(page, '10-ui-tier-list-editor');
// Mid-drag: a deck tile from a lower tier toward the top tier.
const tiers = await page.evaluate(() => state.slides[0].tiers.map((t) => ({ id: t.id, n: t.deckIds.length })));
const from = tiers.slice(1).find((t) => t.n) || tiers[0];
const tile = await page.$(`#stage-host [data-drop="${from.id}"] .deck-tile`);
const target = await page.$(`#stage-host [data-drop="${tiers[0].id}"]`);
if (tile && target) {
  const a = await tile.boundingBox(), b = await target.boundingBox();
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await page.mouse.down();
  await page.mouse.move(b.x + b.width - 60, b.y + b.height / 2, { steps: 25 });
  await page.waitForTimeout(400);
  await shot(page, '11-ui-drag-deck-between-tiers');
  await page.mouse.move(a.x + a.width / 2, a.y + a.height / 2, { steps: 10 });
  await page.mouse.up();
}
// Deck page with its board: tap a card to pick it up, columns light up as targets.
await selectSlide(page, 2);
await page.waitForTimeout(800);
await shot(page, '12-ui-deck-page-editor');
const board = await page.$('#slide-board');
if (board) {
  const card = await page.$('#slide-board .bcard .nm');
  await card?.click();
  await page.waitForTimeout(300);
  await board.scrollIntoViewIfNeeded();
  await settle(page);
  await board.screenshot({ path: join(OUT, '13-ui-core-flex-board.png') });
  shotsTaken.push('13-ui-core-flex-board');
  await page.evaluate(() => { try { boardPick = null; refreshBoards(); } catch {} });
}
// Decks tab: Legends, alternates (with the menu open), key cards.
await page.click('[data-view=decks]');
await page.evaluate((id) => { ui.deckId = id; renderDecks(); }, hero.id);
await page.click('.alt-face').catch(() => {});
await shot(page, '14-ui-deck-editor-alternate-legends');
await page.click('#import-deck');
await shot(page, '15-ui-import-scan-or-paste');
await page.click('.modal [data-close]');
await page.click('[data-view=cards]');
await shot(page, '16-ui-card-browser');
await page.click('[data-view=slides]');
await page.click('#btn-share');
await page.waitForTimeout(800);
await shot(page, '17-ui-share-tier-list');
await page.click('.modal [data-close]').catch(() => {});

/* ---------- Phone ---------- */
const saved = await page.evaluate(() => localStorage.getItem(STORE_KEY));
const phone = await browser.newContext({ ...devices['iPhone 13'] });
await phone.addInitScript((s) => { if (!sessionStorage.getItem('seeded')) { localStorage.setItem('cp-tierlist-studio-v2', s); sessionStorage.setItem('seeded', '1'); } }, saved);
const mp = await openStudio(phone);
await selectSlide(mp, 0);
await shot(mp, '18-phone-tier-list');
await selectSlide(mp, 2);
await mp.waitForTimeout(600);
await shot(mp, '19-phone-deck-page', { fullPage: true });
await mp.click('[data-view=decks]');
await shot(mp, '20-phone-decks');

/* ---------- Short drag video ---------- */
const vctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, recordVideo: { dir: OUT, size: { width: 1600, height: 1000 } } });
await vctx.addInitScript((s) => { if (!sessionStorage.getItem('seeded')) { localStorage.setItem('cp-tierlist-studio-v2', s); sessionStorage.setItem('seeded', '1'); } }, saved);
const vp = await openStudio(vctx);
await selectSlide(vp, 0);
await settle(vp);
for (const [fromIdx, toIdx] of [[1, 0], [2, 1]]) {
  const t = await vp.$(`#stage-host [data-drop="${tiers[fromIdx]?.id}"] .deck-tile`);
  const dst = await vp.$(`#stage-host [data-drop="${tiers[toIdx]?.id}"]`);
  if (!t || !dst) continue;
  const a = await t.boundingBox(), b = await dst.boundingBox();
  await vp.mouse.move(a.x + a.width / 2, a.y + a.height / 2);
  await vp.mouse.down();
  await vp.mouse.move(b.x + b.width - 80, b.y + b.height / 2, { steps: 40 });
  await vp.waitForTimeout(300);
  await vp.mouse.up();
  await vp.waitForTimeout(900);
}
const video = vp.video();
await vctx.close();
if (video) { renameSync(await video.path(), join(OUT, '21-drag-demo.webm')); console.log('Drag video: 21-drag-demo.webm'); }

await browser.close();
console.log(`Saved ${shotsTaken.length} screenshots to ${OUT}`);
if (errors.length) console.log('Page errors:', errors);
