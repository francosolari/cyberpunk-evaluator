# Tier List Studio

A browser tool for building Cyberpunk TCG tier list slides and deck spotlight slides. It's plain HTML, CSS and JS, so there's no build step.

## Run it

Open `index.html` in a browser. To serve it locally instead, run this from this folder:

```sh
python3 -m http.server 8000   # then visit http://localhost:8000
```

Your work saves to the browser automatically. Use **Project → Save project (.json)** to back it up, share it or move it to another machine.

## How it fits together

| Tab | What it's for |
| --- | --- |
| **Slides** | A 1920×1080 slide editor. Drag decks between tiers, or tap a deck and then tap a tier. Edit the title, side badge, footnote, logo, tier names, colors and description lines. Add **Deck spotlight** slides. |
| **Decks** | Each deck has a name/color code (e.g. `RRG`), an optional subtitle, **3 Legends**, a **key card** and notes. You can also set a per-deck display override. |
| **Card Library** | All the cards (Legends and others), each with an image. **Crop art** sets which part of the card is shown. |
| **Card Source** | Imports cards in bulk from the card database's JSON. |

### Deck display modes (per slide, or overridden per deck)

- **Key card (full)**: the whole key card with the color code over it, like the current slides.
- **Key card (art only)**: only the key card's illustration.
- **Legends (art strips)**: the three Legends' art side by side in one tile.
- **Legends (art bands)**: the three Legends' art stacked as horizontal bands.
- **Key art + legends**: key card art on top and a strip of Legend art below.

Deck borders take their colors from the Legends' colors. If no Legends are set, they come from the letters of the deck name.

### Art cropping (showing the art, not the text)

Each card stores an **art window**: the top and bottom of its illustration, as a % of card height. It also stores a focus point and an optional extra zoom. Every layout scales the image so that only the art window is visible. The rules text box never shows, whatever the tile shape is (a tall strip, a tile, a wide band or a spotlight).

All cards share a frame layout, so you can set the window once on one Legend and click **Use window for all Legends**. After that, only fine-tune the focus point per card.

### Presenting / exporting

- **▶ Present** opens a fullscreen slideshow. Use ← → or Space to move between slides, and Esc to exit.
- **Export PNG** renders the current slide at 1920×1080 using html2canvas, which is loaded from cdnjs. Card images hosted on another domain only export if that host sends CORS headers. If an export fails, use Present mode and take a screenshot.

## Connecting the official card database

Out of the box the project has **placeholder** cards (marked `demo`). To use real card art:

1. Find the JSON the official card database loads. Open the database site, open DevTools → Network, filter by `Fetch/XHR`, and look for the request that returns the card list. You can also note the image URLs it loads (the CDN host and naming pattern).
2. In **Card Source**, fetch that URL. If the site blocks cross-origin requests, open the JSON in a tab, save it as a file and use **Load .json file**, or paste it in.
3. Check the field mapping: the list path, name, image, color, type, and the type value that means "Legend". Fields are guessed automatically, and dotted paths like `images.large` work.
4. If the JSON has only an id or filename, fill in the **image URL template**, e.g. `https://<cdn-host>/cards/{id}.webp`. Any `{field}` is filled in from each card.
5. Click **Preview**, then **Import into library**. Re-importing updates existing cards by id or name and keeps your crops.

You can also add single cards by hand (**Card Library → + Add card**) with an image URL or an uploaded image. Uploads are downscaled and stored in the browser. Image URLs keep the project small.

Card art and names belong to their owners. This tool only shows images from wherever you point it.
