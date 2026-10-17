# Tier List Studio: promo shots

What the tool is, what to show, and how to capture it with real card art.

## What it is

Tier List Studio builds Cyberpunk TCG presentation slides: meta tier lists and deck pages, with real Legend and card art, ready to present full screen or export as 1920×1080 images. It runs in the browser. Your decks and tier lists save on your device, and a tier list can be shared as a read-only link.

## Features to show

**Tier lists**
- Any number of tiers, named and colored freely (Tier 1 / Tier 2 / Rogue, S/A/B/C, …), with short descriptions.
- Deck tiles in five views: key card + Legends, Legends as strips, Legends as bands, key card art, full key card.
- Four slide styles: Ledger (default), Band, Frame, Rail.
- Legend art is cropped to the illustration, without names or rules text. A doubled color always comes first (YYB, never YBY).
- Optional: alternate Legends on tiles (the flexible Legend's strip splits).

**Deck pages**
- Names view: deck code and name, tier, Legends, key card, notes, and a grouped list (Units / Gear / Programs) with copy counts.
- Full decklist view, modelled on the official deck builder: Legends column, every card at full size by type, copy counts, sellable % and cost curve in the header.
- **Key cards** (up to 3): cyan corner brackets and a ★ Key tag.
- **Core** (solid yellow tag) and **Flex** (white outline tag) cards. A key card doesn't repeat "Core".
- **Sideboard / Options**: cards around the deck, whether the registered sideboard or fringe cards you're discussing.
- **Alternate (flex) Legends**: one deck, several Legends for a slot. Chips on the names view, a panel with small cards on the full decklist.

**Editing**
- Drag decks between tiers; tiles slide out of the way as you drag. On phones, press and hold, then drag.
- Core / Deck / Flex / Sideboard·Options board under each slide: drag cards between columns, or tap a card and then a column. Use −/+ for counts and ★ for key cards.
- Quick add: find any card by name and drop it into a column.
- Import decks by scanning a deck image's QR code (read on your device; the image is never uploaded), or by pasting a text export or deck link.
- Present full screen, export PNG, share a tier list as a link, and save or load a project file.

## What you get

1. **`promo/story/`: the feature story to share.** Ten 1600×1000 panels. Each one has a headline, a line of context and the screenshots that show the feature:
   01 cover · 02 drag and drop tiers · 03 tile views · 04 full decklist · 05 Key / Core / Flex · 06 flexible Legends · 07 editing on the slide · 08 import by scanning · 09 on your phone · 10 present and share.
   Open `promo/story.html` in a browser to see them all in a row. Edit its headlines and captions there, then rerun the script, or reload the page and screenshot it yourself.
2. **`promo/shots/`: the raw screenshots** the story is built from, plus a short drag video. Use them for anything the story doesn't cover.

## Shot list

The script names each file with its number. Slides are 1920×1080; interface shots are a 1600×1000 window or an iPhone 13.

| # | File | Shows |
|---|------|-------|
| 01 | `01-tier-key-and-legends.png` | Tier list, tiles with key card + Legends (hero shot) |
| 02 | `02-tier-legends.png` | Tiles as Legend strips |
| 03 | `03-tier-legend-bands.png` | Tiles as Legend bands |
| 04 | `04-tier-key-art.png` | Tiles as key card art |
| 05 | `05-tier-key-full-card.png` | Tiles as full key cards |
| 06 | `06-tier-style-band/frame/rail.png` | The other three slide styles |
| 07 | `07-tier-alternate-legends.png` | Alternate Legends shown on tiles (optional setting) |
| 08 | `08-deck-page-names.png` | Deck page, names view: key card, Core / Flex tags, alternate Legend chips, sideboard / options |
| 09 | `09-deck-page-full-decklist.png` | Full decklist: key brackets, Core / Flex tags, flex Legend panel, sellable % and curve |
| 10 | `10-ui-tier-list-editor.png` | The studio with a tier list open |
| 11 | `11-ui-drag-deck-between-tiers.png` | A deck mid-drag between tiers |
| 12 | `12-ui-deck-page-editor.png` | The studio with a deck page open and its board below |
| 13 | `13-ui-core-flex-board.png` | Core / Deck / Flex / Sideboard·Options board with a card picked up |
| 14 | `14-ui-deck-editor-alternate-legends.png` | Deck editor: Legends with alternates, the make-main / remove menu, key cards |
| 14b | `14b-legend-alternates.png` | Close-up of the Legends with their alternates (used in the story) |
| 15 | `15-ui-import-scan-or-paste.png` | Import: scan a deck image or paste an export |
| 16 | `16-ui-card-browser.png` | Card browser with art |
| 17 | `17-ui-share-tier-list.png` | Share a tier list as a link |
| 18–20 | `18-phone-*.png` … | The tier list, a deck page and the deck list on a phone |
| 21 | `21-drag-demo.webm` | Two decks dragged up a tier (convert to GIF/MP4 for posts) |

## Capturing them

Needs Node 18+ and network access to the site and its card images.

```sh
npm i playwright
npx playwright install chromium
node promo/capture.mjs                                   # live site → promo/shots/ and promo/story/
node promo/capture.mjs https://…/ ./my-shots             # another URL or folder
```

The script starts with an empty browser, so it sees the same seeded decks and tier list a new visitor does. It then sets up one **featured deck** to show every deck feature: Core / Flex roles, two key cards, a few sideboard / options cards, and two alternate Legends on one slot. It makes three slides (the tier list, a names deck page and a full decklist deck page) and captures everything above.

**Featuring a specific deck:** save its export (text, import link or deck-builder link) as `promo/hero-deck.txt`. It's added to Tier 1 and used for the deck pages. Without it, the seeded deck with the fullest list is used.

**Checking the results:** in the console output, `Featured deck` names the deck used and `Page errors` should be empty. Look over 09 and 14 in particular. The automatic Core / Flex roles, key cards and alternate Legends are picks for demo purposes, so swap in a real list with `hero-deck.txt` if they don't make sense for the deck.

## Captions (draft)

Plain descriptions of what each image shows. These match the story panels.

- Tier lists and deck pages for Cyberpunk TCG, made from real card data.
- Drag decks between tiers. Tiers can be renamed, recolored, reordered, added or removed.
- Five ways to show a deck on a tier list: Legends, Legends as bands, key card art, full key card, or key card with Legends.
- Full decklists laid out like the deck builder, with the cost curve and sellable share worked out from the list.
- Key cards get corner brackets, core and flex cards get a tag, and options sit under the deck with the sideboard.
- When a deck plays different Legends in one slot, list them as alternates instead of making two decks.
- Import a deck by scanning the QR code on its image. The image stays on your device.
- Present full screen, export 1920×1080 PNGs, or share a read-only link to a tier list.

Fan-made, not affiliated with CD PROJEKT or WeirdCo. Cyberpunk and card images © CD PROJEKT S.A.
