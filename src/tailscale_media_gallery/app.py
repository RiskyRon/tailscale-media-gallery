#!/usr/bin/env python3
"""Flask gallery for a media directory.

Serves a tile-grid index at /, individual files at /<filename>, and
lazy-generated thumbnails at /thumb/<filename>. Thumbnails are cached
to disk keyed on source mtime.

Env vars:
  GALLERY_TITLE       — page title (default: "Media Gallery")
  GALLERY_MEDIA_DIR   — path to the media directory (required)
  GALLERY_CACHE_DIR   — thumbnail cache directory (default: <media_dir>/.thumbs)
  GALLERY_PORT        — port to listen on (default: 8766)
  GALLERY_HOST        — bind address (default: 127.0.0.1)
  CHROME_PATH         — path to Chrome/Chromium for HTML/SVG screenshots
                        (default: /Applications/Google Chrome.app/Contents/MacOS/Google Chrome)
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path
from flask import Flask, render_template, send_from_directory, abort, request
import markdown as md_lib

TITLE = os.environ.get("GALLERY_TITLE", "Media Gallery")
MEDIA_DIR = Path(os.environ.get("GALLERY_MEDIA_DIR", "")).resolve() if os.environ.get("GALLERY_MEDIA_DIR") else None
CACHE_DIR = Path(os.environ.get("GALLERY_CACHE_DIR", "")).resolve() if os.environ.get("GALLERY_CACHE_DIR") else None
PORT = int(os.environ.get("GALLERY_PORT", 8766))
HOST = os.environ.get("GALLERY_HOST", "127.0.0.1")

THUMB_MAX = (512, 512)
CHROME = os.environ.get("CHROME_PATH", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
SVG_EXTS = {".svg"}
PDF_EXTS = {".pdf"}
HTML_EXTS = {".html", ".htm"}
VIDEO_EXTS = {".mp4", ".mov", ".webm"}
MD_EXTS = {".md", ".markdown"}
THUMBABLE = IMAGE_EXTS | SVG_EXTS | PDF_EXTS | HTML_EXTS | VIDEO_EXTS | MD_EXTS

app = Flask(__name__, template_folder=str(Path(__file__).parent / "templates"))

FILENAME_RE = re.compile(r"^(?P<date>\d{4}-\d{2}-\d{2})-(?P<slug>.+?)\.(?P<ext>[^.]+)$")


def parse_filename(name: str) -> dict:
    m = FILENAME_RE.match(name)
    if m:
        return {
            "date": m.group("date"),
            "slug": m.group("slug").replace("-", " ").replace("_", " "),
            "ext": m.group("ext").lower(),
            "raw": name,
        }
    return {"date": "", "slug": Path(name).stem, "ext": Path(name).suffix.lstrip(".").lower(), "raw": name}


def _dot_ext(ext: str) -> str:
    e = ext.lower()
    return e if e.startswith(".") else "." + e


def file_type(ext: str) -> str:
    e = _dot_ext(ext)
    if e in IMAGE_EXTS: return "image"
    if e in SVG_EXTS: return "svg"
    if e in PDF_EXTS: return "pdf"
    if e in HTML_EXTS: return "html"
    if e in VIDEO_EXTS: return "video"
    if e in MD_EXTS: return "md"
    return "other"


def has_thumb(ext: str) -> bool:
    return _dot_ext(ext) in THUMBABLE


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def list_media() -> list[dict]:
    """List media/ contents, deduping source+rendered pairs, newest first."""
    if MEDIA_DIR is None or not MEDIA_DIR.exists():
        return []
    items = []
    for p in MEDIA_DIR.iterdir():
        if not p.is_file() or p.name.startswith("."):
            continue
        st = p.stat()
        info = parse_filename(p.name)
        info["type"] = file_type(info["ext"])
        info["size"] = human_size(st.st_size)
        info["has_thumb"] = has_thumb(info["ext"])
        info["stem"] = Path(p.name).stem
        info["mtime"] = st.st_mtime
        items.append(info)

    from collections import defaultdict
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        groups[item["stem"]].append(item)

    deduped = []
    for group in groups.values():
        if len(group) == 1:
            deduped.extend(group)
            continue
        thumbable = [i for i in group if i["has_thumb"]]
        deduped.extend(thumbable if thumbable else group)

    deduped.sort(key=lambda i: i["mtime"], reverse=True)
    return deduped


def ensure_thumb(filename: str) -> Path | None:
    """Return path to cached thumbnail, generating on miss."""
    if MEDIA_DIR is None or CACHE_DIR is None:
        return None
    src = MEDIA_DIR / filename
    try:
        src = src.resolve(strict=True)
    except (FileNotFoundError, OSError):
        return None
    if not src.is_relative_to(MEDIA_DIR):
        return None
    if not has_thumb(src.suffix):
        return None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    thumb = CACHE_DIR / f"{filename}.png"

    if thumb.exists() and thumb.stat().st_mtime >= src.stat().st_mtime:
        return thumb

    ext = src.suffix.lower()
    try:
        if ext in IMAGE_EXTS:
            from PIL import Image
            img = Image.open(src)
            img.thumbnail(THUMB_MAX)
            if img.mode not in ("RGB", "RGBA", "L"):
                img = img.convert("RGB")
            img.save(thumb, "PNG")
        elif ext in SVG_EXTS:
            _chrome_screenshot(src, thumb, 512, 512)
        elif ext in PDF_EXTS:
            _pdf_first_page(src, thumb)
        elif ext in HTML_EXTS:
            _chrome_screenshot(src, thumb, 1280, 800, resize=True)
        elif ext in MD_EXTS:
            _md_thumbnail(src, thumb)
        elif ext in VIDEO_EXTS:
            _video_poster(src, thumb)
        else:
            return None
    except Exception as e:
        app.logger.warning("thumb failed for %s: %s", filename, e)
        return None

    return thumb if thumb.exists() else None


def _chrome_screenshot(src: Path, dest: Path, w: int, h: int, resize: bool = False) -> None:
    subprocess.run(
        [
            CHROME, "--headless", "--disable-gpu", "--no-sandbox",
            f"--screenshot={dest}",
            f"--window-size={w},{h}",
            f"file://{src}",
        ],
        check=True, capture_output=True, timeout=30,
    )
    if resize and dest.exists():
        from PIL import Image
        img = Image.open(dest)
        img.thumbnail(THUMB_MAX)
        img.save(dest, "PNG")


def _pdf_first_page(src: Path, dest: Path) -> None:
    prefix = dest.parent / (dest.stem + "_raw")
    subprocess.run(
        ["pdftoppm", "-png", "-r", "100", "-f", "1", "-l", "1", str(src), str(prefix)],
        check=True, capture_output=True, timeout=30,
    )
    raw = None
    for candidate in dest.parent.glob(f"{prefix.name}-*.png"):
        raw = candidate
        break
    if raw is None:
        return
    from PIL import Image
    img = Image.open(raw)
    img.thumbnail(THUMB_MAX)
    img.save(dest, "PNG")
    raw.unlink(missing_ok=True)


def _video_poster(src: Path, dest: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-ss", "1", "-i", str(src), "-vframes", "1", str(dest)],
        check=True, capture_output=True, timeout=30,
    )
    from PIL import Image
    img = Image.open(dest)
    img.thumbnail(THUMB_MAX)
    img.save(dest, "PNG")


MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists", "toc", "nl2br", "footnotes"]


def render_md_html(md_text: str, title: str) -> str:
    """Render Markdown to a full dark-mode HTML page for mobile reading."""
    md_parser = md_lib.Markdown(extensions=MD_EXTENSIONS)
    body = md_parser.convert(md_text)
    return render_template("md_view.html", body=body, title=title)


def _md_thumbnail(src: Path, dest: Path) -> None:
    html = render_md_html(src.read_text(encoding="utf-8"), title=src.stem)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", dir=CACHE_DIR, delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(html)
        tmp_path = Path(tmp.name)
    try:
        _chrome_screenshot(tmp_path, dest, 800, 800, resize=True)
    finally:
        tmp_path.unlink(missing_ok=True)


# ---- Routes ----

@app.route("/")
def index():
    items = list_media()
    types_present = sorted({i["type"] for i in items})
    return render_template("gallery.html", agent=TITLE, items=items, total=len(items), types_present=types_present)


@app.route("/thumb/<path:filename>")
def route_thumb(filename):
    thumb_path = ensure_thumb(filename)
    if thumb_path is None:
        abort(404)
    return send_from_directory(str(thumb_path.parent), thumb_path.name, mimetype="image/png")


@app.route("/<path:filename>")
def route_file(filename):
    if MEDIA_DIR is None:
        abort(404)
    target = (MEDIA_DIR / filename)
    try:
        target = target.resolve(strict=True)
    except (FileNotFoundError, OSError):
        abort(404)
    if not target.is_relative_to(MEDIA_DIR) or not target.is_file():
        abort(404)
    if target.suffix.lower() in MD_EXTS and request.args.get("raw") != "1":
        return render_md_html(target.read_text(encoding="utf-8"), title=target.stem)
    return send_from_directory(str(MEDIA_DIR), filename)


def main():
    global MEDIA_DIR, CACHE_DIR, TITLE

    parser = argparse.ArgumentParser(description="Tailscale Media Gallery")
    parser.add_argument("--media-dir", default=os.environ.get("GALLERY_MEDIA_DIR"),
                        help="Path to the media directory (or set GALLERY_MEDIA_DIR)")
    parser.add_argument("--cache-dir", default=os.environ.get("GALLERY_CACHE_DIR"),
                        help="Thumbnail cache directory (or set GALLERY_CACHE_DIR)")
    parser.add_argument("--port", type=int, default=PORT,
                        help=f"Port to listen on (default: {PORT})")
    parser.add_argument("--host", default=HOST,
                        help=f"Bind address (default: {HOST})")
    parser.add_argument("--title", default=TITLE,
                        help=f"Gallery title (default: {TITLE})")
    args = parser.parse_args()

    if args.media_dir:
        MEDIA_DIR = Path(args.media_dir).resolve()
    if MEDIA_DIR is None:
        parser.error("--media-dir or GALLERY_MEDIA_DIR is required")
    if args.cache_dir:
        CACHE_DIR = Path(args.cache_dir).resolve()
    if CACHE_DIR is None:
        CACHE_DIR = MEDIA_DIR / ".thumbs"
    TITLE = args.title

    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
