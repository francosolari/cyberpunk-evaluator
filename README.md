# Tier List Studio

Builds Cyberpunk TCG tier list slides and deck page slides from real card data and real deck exports. It's plain HTML, CSS and JS, so there's no build step.

## Run it

Open `index.html` in a browser, or serve this folder (`python3 -m http.server`). Work saves in the browser. Use **Project → Save project** to back it up or move it to another machine.

## Card data

Card names, types, colors, costs, rules text, collector numbers and art come from a public card catalog (`CATALOG_URL` in `app.js`, the same catalog `cyberpunk-tcg-tracker` reads). The app loads it on first run and keeps a copy in the browser; **Card Data → Refresh** reloads it after a set release.

**Card Data → Add top ranked Legend trios** reads the public ranked ladder and creates a Legends-only deck for each popular trio, ready to rank.

The interface doesn't name the card data source, so slides and screens are fine for official content creation.

## Seed decks

A new visitor's studio starts from `data/seed-decks.txt`: deck exports separated by `---` lines, each with an optional `# Tier: Tier 1` line (where it starts on the tier list) and `# Notes: …` line. A deck with only Legends shows as an archetype. Edit that file to change what everyone starts with; it doesn't touch anyone's saved decks. Popular trios from the ranked ladder are added to Unranked.

## Decks from exports

**Decks → Import deck export** accepts:

- **Deck text export**:
  ```
  # Name: Heist Tempo
  #L
  1x V, Corporate Exile
  …
  #D
  3x Floor It
  #S
  …
  ```
- **Deck import links**, e.g. `…/import?…&b64deck=…`. The deck is decoded from the link.
- **Text lists** from the official deck builder and other builders. These look like `3 Card Name`, `3x Card Name` or `Card Name x3`, with `Legends:`, `Main Deck:` and `Sideboard:` headers or `//` comments. Legends are detected from the card type even without a header.
- **JSON decklists** with name/count fields.
- **Deck images** with a QR code (deck builder image exports): **Scan deck image**, or paste or drop a screenshot. The QR code holds a compact deck code (`?d=l.w2.w5-a…d.3_w6…s.3_w7…`: Legends, deck and sideboard, each card a set letter plus its collector number in base 36). It's read in the browser (the built-in reader where available, otherwise jsQR), only the decoded deck is kept, and the image is never uploaded or saved.

To import several decks at once, separate them with a `---` line. Names are matched to the catalog without regard to case or punctuation. A short name like "Panam Palmer" matches "Panam Palmer, Nomad Cavalry" when only one card fits. Lines that match no card are listed so you can fix them.

Each deck gets a **tile code** from its Legends' colors, majority color first (2 Red + 1 Green → `RRG`). You can override the code. The deck also gets a **key card**, suggested from the decklist; change it with ★. **Copy deck export** writes the deck back out as a text export.

### Editing a decklist

The **Slides** tab has a **Core / Deck / Flex / Sideboard·Options** board under the slide: for a deck page it edits that deck, and on a tier list it edits whichever deck you tap. The Decks tab has the same board. Drag cards between columns, or tap a card and then a column on a phone. Use −/+ to change counts and ★ for key cards (up to 3). The **quick add** box above the board finds a card by name and adds it to whichever column you pick. On a deck page slide, tap any card to move it, star it, change its count or remove it, without leaving the slide. The slide panel has its own quick add box.

On phones, **press and hold** a card or deck, then drag it. A quick swipe still scrolls, and tap-then-tap still works.

The **Decks** list has search (deck code, name or Legend), grouping (by main color or tier, collapsible) and sorting (newest, name, most cards). The **Unranked** area on a tier list has its own filter and groups by main color once it holds more than 8 decks.

**Sideboard / Options** is one section everywhere you look at it (board, deck pages): cards around the deck that aren't in the main list, whether that's the registered sideboard or fringe cards you're discussing for the archetype. Underneath, imports keep `#S` / `Sideboard:` cards as the sideboard and `Options:` / `Considering:` / `#O` cards as options, so **Copy deck export** still contains only the real sideboard. Cards you drag into the section from the deck go to the sideboard.

Legends and color strips always list the doubled color first, together: Yellow, Yellow, Blue, never Yellow, Blue, Yellow.

## Slides

- **Tier list**: any number of tiers, each with a name, color and description. Add, remove and reorder tiers freely, or start from a preset (Tier 1/2/Rogue, S/A/B/C, Tier 0–3). Drag decks between tiers, or on a touch screen tap a deck and then a tier. Tiles show the Legends' art, the key card's art, both, or the full key card.
- **Deck page**: the deck code and name, its tier, its Legends and key card, notes, and a Units / Gear / Programs breakdown. The decklist can show **names** grouped by type, or the **full decklist as cards**; both always split Units / Gear / Programs and show a Sideboard / Options section. Core and Flex are tags on the cards. The full decklist is (modelled on the official deck builder's deck view: Legends in a column, the main deck as full cards in Units, Gear and Programs sections with copy counts, and the sideboard under it, all sized to fill the slide). A deck can have up to **3 key cards**, shown as banners under the Legends. In the deck editor, mark cards **Core** or **Flex**, and keep **Options**: cards you're considering that sit outside the deck (add them there, move cards between deck and options with → opt / → deck, or import them under an `Options:` / `#O` header). The full decklist groups cards by type (Core first, Flex last with a dashed outline, options in a strip below) or by **Core / Flex / Options** side by side.
- **▶ Present** opens fullscreen slides (← → to move, Esc to exit). **Export PNG** renders 1920×1080. Card art only appears in the PNG if the image host allows cross-origin reads. Otherwise use Present and take a screenshot.

## Sharing

**Share** makes a link to a tier list (or all of them). The link holds the tiers and, for each deck, only what its tile shows: code, name, Legends and key card. Decklists aren't shared; plenty of tools already do that. Opening a link shows a read-only viewer; **Copy to my studio** adds the tier list next to your own decks.

## Art crops

Each card has an **art window**: the top and bottom of its illustration, as a % of card height. Every layout scales the card so only that window shows, which keeps names and rules text off the slides. Set it once on any Legend with **Cards → Crop art → Save as default for all Legends**, then fine-tune the focus point on individual cards if needed.

## Design

The studio follows **Kiroshi Scan**, the design system in `cyberpunk-tcg-tracker/DESIGN.md`:
- Flat charcoal with square geometry; cut corners on buttons, chips and badges, which are always filled.
- Yellow only for identity, the active selection and the primary action.
- Sentence-case labels with no tracking, and a cyan tick opening each section.
- Martian Mono for numbers.
- Card colors fill the cost boxes; there are no colored side stripes.
- Key cards get cyan target-lock brackets; cyan means Key and nothing else. Core is a solid yellow tag, Flex a white outlined tag.
- No glow, gradients, dashed boxes or outlined pills.
