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

## Slides

- **Tier list**: any number of tiers, each with a name, color and description. Add, remove and reorder tiers freely, or start from a preset (Tier 1/2/Rogue, S/A/B/C, Tier 0–3). Drag decks between tiers, or on a touch screen tap a deck and then a tier. Tiles show the Legends' art, the key card's art, both, or the full key card.
- **Deck page**: the deck code and name, its tier, its Legends and key card, notes, and a Units / Gear / Programs breakdown. The decklist can show **names** grouped by type, **card text** in one column per type (rules text from the catalog), or **full cards** in a grid. In the deck editor, mark cards **Core** or **Flex**; the tags show on the deck page, with a toggle to hide them.
- **▶ Present** opens fullscreen slides (← → to move, Esc to exit). **Export PNG** renders 1920×1080. Card art only appears in the PNG if the image host allows cross-origin reads. Otherwise use Present and take a screenshot.

## Art crops

Each card has an **art window**: the top and bottom of its illustration, as a % of card height. Every layout scales the card so only that window shows, which keeps names and rules text off the slides. Set it once on any Legend with **Cards → Crop art → Save as default for all Legends**, then fine-tune the focus point on individual cards if needed.
