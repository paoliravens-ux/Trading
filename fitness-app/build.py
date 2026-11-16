"""Wrap src/app.html into a standalone, installable public/index.html."""
from pathlib import Path

root = Path(__file__).parent
body = (root / "src" / "app.html").read_text()
head = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#0d1016">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Ironfuel">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" href="icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="icon.svg">
<style>:root{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}body{margin:0}[hidden]{display:none!important}</style>
"""
# Split the fragment: everything up to the first <div id="app"> belongs in <head>.
idx = body.index('<div id="app">')
tail = """
<script>if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});</script>
</body>
</html>
"""
out = head + body[:idx] + "</head>\n<body>\n" + body[idx:] + tail
(root / "public" / "index.html").write_text(out)
print("wrote", root / "public" / "index.html", len(out), "bytes")
