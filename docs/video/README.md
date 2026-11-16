# Demo video

`octoman-lite-demo.mp4` is the submission video: 1:26, 1920×1080, 30 fps.
The footage is the deployed dashboard, driven by a scripted browser; the title
cards, camera moves and captions are added afterwards.

| File | What it does |
|---|---|
| `capture.js` | Opens the live dashboard, warms it up, restocks, then records the race, a sale in Germany, the low-stock sale and the How it works tab. Writes `take/` (frames, timings, mouse path). Restocks the demo again at the end. |
| `edit.js` | The edit: which part of the take plays when, where the camera looks, and the caption text. |
| `comp.html` | Draws one frame of the video for a given time: title cards, footage, cursor, captions. |
| `render.js` | Steps `comp.html` through every frame and encodes the MP4 with ffmpeg. |

## Re-create it

Needs Node.js, Playwright with Chromium, and ffmpeg. `capture.js` places real
orders on the deployed demo (the URL is at the top of the file).

```bash
node docs/video/capture.js
```

```bash
node docs/video/render.js --out docs/video/silent.mp4
```

`node docs/video/render.js --at 5,20,60` writes still frames to `stills/` instead.

The recording hides the page footer (the credits line), as the video checklist
in `docs/submission_article.md` asks. Each take differs slightly: the two stores
in the race are picked at random.

## Music

"Bubbles (Lofi, Bright, Relaxed)" by HoliznaCC0, from the album *Public Domain
Lofi*, CC0 1.0 Universal (public domain):
https://freemusicarchive.org/music/holiznacc0/public-domain-lofi/bubbles-lofi-bright-relaxed/

Mixed in with ffmpeg (2.5 dB quieter, 0.8 s fade in, 3.7 s fade out):

```bash
ffmpeg -i docs/video/silent.mp4 -i bubbles.mp3 -filter_complex "[1:a]atrim=0:86.1667,volume=-2.5dB,afade=t=in:st=0:d=0.8,afade=t=out:st=82.4:d=3.7[a]" -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 192k -movflags +faststart docs/video/octoman-lite-demo.mp4
```
