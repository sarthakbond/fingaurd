# Intro videos

Place the two cinematic intro files here, with exactly these names:

| File | Aspect ratio | Used for |
|---|---|---|
| `fingaurd-intro-desktop.mp4` | 16:9 | viewports wider than 768px |
| `fingaurd-intro-mobile.mp4` | 9:16 | viewports 768px and below |

The frontend resolves them at `/static/videos/fingaurd-intro-desktop.mp4` and
`/static/videos/fingaurd-intro-mobile.mp4` (FastAPI already mounts `static/`, so no
backend change is needed).

## Behaviour

- Only one file is ever fetched — the source is chosen from the viewport before the
  `<video>` element is given a `src`, so the mobile file is never downloaded on desktop.
- The video autoplays muted with `playsinline` and fills the viewport.
- `SKIP VIDEO →` (top right) and natural playback end both lead to the same landing page
  and both write `fingaurdIntroSeen` to `sessionStorage`.
- A refresh in the same browser session goes straight to the landing page. Closing the
  browser clears the flag, so the intro plays again next session.
- **If a file is missing** the player does not stall: it waits up to 6 seconds for the
  first frame, then transitions straight to the landing page. So the site stays usable
  before you add these files.
- If the visitor has `prefers-reduced-motion: reduce` set, the intro is skipped entirely.

## Encoding suggestions

H.264 + AAC in an MP4 container, `faststart` enabled so playback can begin before the
whole file arrives:

```bash
ffmpeg -i source-desktop.mov -c:v libx264 -crf 21 -preset slow \
  -vf scale=1920:1080 -c:a aac -b:a 128k -movflags +faststart \
  fingaurd-intro-desktop.mp4

ffmpeg -i source-mobile.mov -c:v libx264 -crf 21 -preset slow \
  -vf scale=1080:1920 -c:a aac -b:a 128k -movflags +faststart \
  fingaurd-intro-mobile.mp4
```

Keep each file under about 8 MB so the first frame appears quickly on a conference
network. The final frame should hold the shield-in-data-network composition, which is
what the landing hero picks up from.
