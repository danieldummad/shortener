"""
Tiny URL shortener demo (standard library only, no installs needed).

How it works:
  1. You submit a long URL.
  2. We hash it with SHA-256 and keep the first few hex characters as the short ID.
  3. We store  ID -> URL  in a SQLite database.
  4. When someone visits /<ID>, we look it up and answer with an HTTP 302 redirect.

Run:   python shortener.py
Open:  http://localhost:8000
"""
import hashlib
import html
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

DB_FILE = "links.db"
PORT = int(os.environ.get("PORT", 8000))  # hosting services set PORT for you
MIN_ID_LENGTH = 7  # characters of the hash kept as the short ID


def connect():
    con = sqlite3.connect(DB_FILE)
    con.execute("CREATE TABLE IF NOT EXISTS links (id TEXT PRIMARY KEY, url TEXT NOT NULL)")
    return con


def make_id(con, url):
    """Hash the URL and return a short ID. Lengthens the ID if two URLs collide."""
    digest = hashlib.sha256(url.encode()).hexdigest()
    for length in range(MIN_ID_LENGTH, len(digest) + 1):
        short = digest[:length]
        row = con.execute("SELECT url FROM links WHERE id = ?", (short,)).fetchone()
        if row is None:  # free slot: store it
            con.execute("INSERT INTO links (id, url) VALUES (?, ?)", (short, url))
            con.commit()
            return short
        if row[0] == url:  # same URL submitted before: reuse the ID
            return short
        # otherwise: collision with a different URL, so try a longer prefix
    raise RuntimeError("could not create an ID")


def is_valid(url):
    parts = urlparse(url)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def page(con, message=""):
    rows = con.execute("SELECT id, url FROM links ORDER BY rowid DESC LIMIT 20").fetchall()
    items = "".join(
        f'<li><a href="/{i}">/{i}</a> &rarr; {html.escape(u)}</li>' for i, u in rows
    )
    return f"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>SWIFT Shortener</title>
<body style="font-family:system-ui;max-width:640px;margin:2rem auto;padding:0 1rem">
<h1>SWIFT Shortener </h1>
<form method="post" action="/shorten">
  <input name="url" placeholder="https://example.com/a/very/long/path" style="width:100%;padding:.6rem" required>
  <p><button style="padding:.6rem 1rem">Shorten</button></p>
</form>
<p>{message}</p>
<h2>Recent links</h2><ul>{items or "<li>None yet</li>"}</ul>
</body>"""


class Handler(BaseHTTPRequestHandler):
    def send_html(self, body, status=200):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        con = connect()
        path = urlparse(self.path).path.strip("/")
        if not path:
            return self.send_html(page(con))
        row = con.execute("SELECT url FROM links WHERE id = ?", (path,)).fetchone()
        if row is None:
            return self.send_html("<h1>Not found</h1>", 404)
        self.send_response(302)  # 302 = temporary redirect; 301 would be permanent
        self.send_header("Location", row[0])
        self.end_headers()

    def do_POST(self):
        if self.path != "/shorten":
            return self.send_html("<h1>Not found</h1>", 404)
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode())
        url = form.get("url", [""])[0].strip()
        con = connect()
        if not is_valid(url):
            return self.send_html(page(con, "Enter a full http:// or https:// URL."), 400)
        short = make_id(con, url)
        host = self.headers.get("Host", f"localhost:{PORT}")
        scheme = self.headers.get("X-Forwarded-Proto", "http")
        link = f"{scheme}://{host}/{short}"
        self.send_html(page(con, f'Short link: <a href="/{short}">{link}</a>'))


if __name__ == "__main__":
    print(f"Running on http://localhost:{PORT}  (Ctrl+C to stop)")
    HTTPServer(("", PORT), Handler).serve_forever()
