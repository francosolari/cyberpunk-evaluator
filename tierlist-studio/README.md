# Tier List Studio

Builds Cyberpunk TCG tier list slides and deck page slides from real card data and real deck exports. It's plain HTML, CSS and JS, so there's no build step.

## Run it

Open `index.html` in a browser, or serve this folder (`python3 -m http.server`). Work saves in the browser. Use **Project → Save project** to back it up or move it to another machine.

## Card data

Cards come from the **Cyberpunk TCG Sim public catalog** at `https://cyberpunk-tcg-sim.online/api/cards/catalog`. It's the same endpoint the sim's deck builder and `cyberpunk-tcg-tracker` use. Each card's `id`, `display_name`, `card_type`, `color`, `cost` and `assets.image_url` are read, and images load from the sim's `/media/…` paths.

The app tries to load the catalog on first run. If the browser blocks the request (CORS), open the catalog URL, save it as `catalog.json`, and use **Card Data → Load catalog .json**.

**Card Data → Add top ranked Legend trios** reads the sim's public ranked leaderboard and creates a Legends-only deck for each popular trio, ready to rank.

## Decks from exports

**Decks → Import deck export** accepts:

- **Sim text export**:
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
- **Sim import links**, e.g. `…/import?svc=sim&b64deck=…`. The deck is decoded from the link.
- **Text lists** from the official deck builder and other builders. These look like `3 Card Name`, `3x Card Name` or `Card Name x3`, with `Legends:`, `Main Deck:` and `Sideboard:` headers or `//` comments. Legends are detected from the card type even without a header.
- **JSON decklists** with name/count fields.

To import several decks at once, separate them with a `---` line. Names are matched to the catalog without regard to case or punctuation. A short name like "Panam Palmer" matches "Panam Palmer, Nomad Cavalry" when only one card fits. Lines that match no card are listed so you can fix them.

Each deck gets a **tile code** from its Legends' colors, majority color first (2 Red + 1 Green → `RRG`). You can override the code. The deck also gets a **key card**, suggested from the decklist; change it with ★. **Copy sim export** writes the deck back out in sim text format.

### Editing a decklist

The **Slides** tab has a **Core / Deck / Flex / Sideboard / Options** board under the slide: for a deck page it edits that deck, and on a tier list it edits whichever deck you tap. The Decks tab has the same board. Drag cards between columns, or tap a card and then a column on a phone. Use −/+ to change counts and ★ for key cards (up to 3). The **quick add** box above the board finds a card by name and adds it to whichever column you pick. On a deck page slide, tap any card to move it, star it, change its count or remove it, without leaving the slide. The slide panel has its own quick add box.

On phones, **press and hold** a card or deck, then drag it. A quick swipe still scrolls, and tap-then-tap still works.

The **Decks** list has search (deck code, name or Legend), grouping (by main color or tier, collapsible) and sorting (newest, name, most cards). The **Unranked** area on a tier list has its own filter and groups by main color once it holds more than 8 decks.

**Sideboard vs. Options:** the sideboard is part of the deck you register (up to 7 cards). It imports from `#S` / `Sideboard:` and is included when you copy the deck out. Options are your own "considering" list; they're never exported. A card can be in more than one list, e.g. 3 in the deck and 1 in the sideboard.

Legends and color strips always list the doubled color first, together: Yellow, Yellow, Blue, never Yellow, Blue, Yellow.

## Slides

- **Tier list**: any number of tiers, each with a name, color and description. Add, remove and reorder tiers freely, or start from a preset (Tier 1/2/Rogue, S/A/B/C, Tier 0–3). Drag decks between tiers, or on a touch screen tap a deck and then a tier. Tiles show the Legends' art, the key card's art, both, or the full key card.
- **Deck page**: the deck code and name, its tier, its Legends and key card, notes, and a Units / Gear / Programs breakdown. The decklist can show **names** grouped by type, or the **full decklist as cards** (modelled on the official deck builder's deck view: Legends in a column, the main deck as full cards in Units, Gear and Programs sections with copy counts, and the sideboard under it, all sized to fill the slide). A deck can have up to **3 key cards**, shown as banners under the Legends. In the deck editor, mark cards **Core** or **Flex**, and keep **Options**: cards you're considering that sit outside the deck (add them there, move cards between deck and options with → opt / → deck, or import them under an `Options:` / `#O` header). The full decklist groups cards by type (Core first, Flex last with a dashed outline, options in a strip below) or by **Core / Flex / Options** side by side.
- **▶ Present** opens fullscreen slides (← → to move, Esc to exit). **Export PNG** renders 1920×1080. Card art only appears in the PNG if the image host allows cross-origin reads. Otherwise use Present and take a screenshot.

## Art crops

Each card has an **art window**: the top and bottom of its illustration, as a % of card height. Every layout scales the card so only that window shows, which keeps names and rules text off the slides. Set it once on any Legend with **Cards → Crop art → Save as default for all Legends**, then fine-tune the focus point on individual cards if needed.
