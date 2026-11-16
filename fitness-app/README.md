# Ironfuel

A workout logger and macro tracker in one installable web app. No account, no server:
all data stays on your device (with a copy-paste backup/restore).

## Features

- **Food**: daily calorie ring and protein/carb/fat bars, four meals, a built-in food list
  (~40 common foods), custom foods, serving steppers, and "copy yesterday".
- **Train**: start an empty workout or a saved routine (Push/Pull/Legs included), log
  weight × reps with your previous numbers shown beside each set, an automatic rest timer
  with a beep, custom exercises, and a history you can repeat or save as a routine.
- **Progress**: body-weight trend, weekly training volume, 7-day nutrition averages
  against your goal, and personal bests (estimated 1RM).
- **You**: macro targets, a target calculator (Mifflin-St Jeor), lb/kg, rest length,
  backup/restore.

## Run it

```bash
cd fitness-app
python3 build.py                 # src/app.html -> public/index.html
python3 -m http.server -d public 8000
```

Open http://localhost:8000. To put it on your phone, host the `public/` folder on any
static host (GitHub Pages, Netlify, Cloudflare Pages), open it in Safari, then
**Share → Add to Home Screen**. It runs full-screen and works offline.

## Layout

- `src/app.html`: the whole app (HTML, CSS, JS in one file). Edit this.
- `build.py`: wraps it with the PWA head tags into `public/index.html`.
- `public/`: deployable folder (`index.html`, `manifest.webmanifest`, `sw.js`, `icon.svg`).
