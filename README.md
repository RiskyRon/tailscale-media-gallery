# tailscale-media-gallery

Dark-mode Flask media gallery with automatic thumbnail generation. Designed to be served over [Tailscale Serve](https://tailscale.com/kb/1312/serve/) for private access across your tailnet.

Displays images, SVGs, PDFs, HTML files, videos, and Markdown in a responsive tile grid with lazy-loaded thumbnails. Markdown files are rendered as styled dark-mode pages.

## Install

```bash
pip install tailscale-media-gallery
```

Or install from source:

```bash
git clone https://github.com/RiskyRon/tailscale-media-gallery.git
cd tailscale-media-gallery
pip install -e .
```

## Quick start

```bash
# Serve a directory
media-gallery --media-dir ~/my-media --port 8766

# With a custom title
media-gallery --media-dir ~/my-media --title "My Gallery"

# Or via env vars
GALLERY_MEDIA_DIR=~/my-media GALLERY_PORT=8766 media-gallery
```

Then expose via Tailscale Serve:

```bash
tailscale serve --https=8766 http://127.0.0.1:8766
```

## Configuration

All options can be set via CLI flags or environment variables:

| CLI flag | Env var | Default | Description |
|---|---|---|---|
| `--media-dir` | `GALLERY_MEDIA_DIR` | *(required)* | Path to the media directory |
| `--cache-dir` | `GALLERY_CACHE_DIR` | `<media-dir>/.thumbs` | Thumbnail cache directory |
| `--port` | `GALLERY_PORT` | `8766` | Port to listen on |
| `--host` | `GALLERY_HOST` | `127.0.0.1` | Bind address |
| `--title` | `GALLERY_TITLE` | `Media Gallery` | Page title |
| | `CHROME_PATH` | macOS Chrome path | Path to Chrome/Chromium for HTML/SVG screenshots |

## Features

- **Thumbnail generation** for images (Pillow), PDFs (pdftoppm), videos (ffmpeg), HTML/SVG (headless Chrome), and Markdown (rendered to HTML then screenshotted)
- **Thumbnail caching** — keyed on source file mtime, only regenerated when the source changes
- **Pair deduplication** — if both `diagram.excalidraw` and `diagram.svg` exist, only the thumbnailable version shows
- **Type filtering** — filter bar for images, SVGs, PDFs, HTML, video, Markdown, and other files
- **Markdown rendering** — `.md` files render as styled dark-mode HTML pages with a "view source" toggle
- **Mobile-first** — responsive grid, safe-area insets, tap-friendly tiles
- **Date-slug filenames** — files named `YYYY-MM-DD-slug.ext` display with parsed date and human-readable title
- **Path traversal protection** — all file access is resolved and checked against the media directory

## Optional dependencies

- **pdftoppm** (from poppler) — PDF thumbnail generation
- **ffmpeg** — video poster frame extraction
- **Google Chrome / Chromium** — HTML and SVG screenshot thumbnails

Without these, the respective file types will show a generic file icon instead of a thumbnail.

## License

MIT
