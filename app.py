from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import zipfile
import io
import re

app = Flask(__name__)
CORS(app)

BASE = "https://www.podnapisi.net"

# -------------------------------------
# Chrome-like headers (BREZ fejk Cloudflare cookie)
# -------------------------------------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.6261.112 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "sl,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "DNT": "1",
})


# -------------------------------------
# IMDb → Title
# -------------------------------------
def imdb_to_title(imdb_id: str) -> str | None:
    url = f"https://www.imdb.com/title/{imdb_id}/"
    print("🎬 IMDb URL:", url)
    r = SESSION.get(url, timeout=10)

    if r.status_code != 200:
        print("❌ IMDb status:", r.status_code)
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    tag = soup.find("meta", {"property": "og:title"})
    if not tag or "content" not in tag.attrs:
        print("❌ IMDb meta og:title not found")
        return None

    full = tag["content"]
    clean = re.sub(r"\(\d{4}\).*", "", full).strip()
    print("✅ IMDb title:", clean)
    return clean


# -------------------------------------
# Search subtitles (movies + series)
# -------------------------------------
def search_subtitles(title: str):
    url = f"{BASE}/sl/subtitles/search"
    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads",
    }

    print("🔍 Searching Podnapisi:", url, params)
    r = SESSION.get(url, params=params, timeout=15)

    print("🔍 Search status:", r.status_code)
    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    # DEBUG: pokaži prvih par znakov HTML (za loge na Renderju)
    print("🔍 HTML preview:", r.text[:400].replace("\n", " ")[:400])

    rows = soup.select("table tbody tr")
    results = []

    for row in rows:
        a = row.select_one("a[href*='/sl/subtitles/']")
        if not a:
            continue

        name = a.get_text(strip=True)
        href = a.get("href")
        if not href:
            continue

        dl_url = BASE + href + "/download"

        results.append({
            "name": name,
            "url": dl_url,
        })

    print(f"✅ Found {len(results)} subtitle entries")
    return results


# -------------------------------------
# Download ZIP → extract SRT
# -------------------------------------
def download_srt(url: str) -> str | None:
    print("⬇ Downloading subtitle ZIP:", url)
    r = SESSION.get(url, timeout=20)

    if r.status_code != 200:
        print("❌ ZIP status:", r.status_code)
        return None

    try:
        z = zipfile.ZipFile(io.BytesIO(r.content))
        for fname in z.namelist():
            if fname.lower().endswith(".srt"):
                print("📦 Extracting SRT:", fname)
                try:
                    return z.read(fname).decode("utf-8", errors="ignore")
                except UnicodeDecodeError:
                    return z.read(fname).decode("iso-8859-1", errors="ignore")
    except Exception as e:
        print("❌ ZIP error:", e)

    print("❌ No .srt file found in ZIP")
    return None


# -------------------------------------
# Manifest
# -------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "6.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (no browser)",
        "description": "Slovenski podnapisi (filmi + serije) preko Podnapisi.NET, brez browserja.",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"],
    })


# -------------------------------------
# Subtitles endpoint
# -------------------------------------
@app.route("/subtitles/<video_type>/<imdb_id>.json")
def subtitles(video_type: str, imdb_id: str):
    print("==================================================")
    print("🎬 Request for:", video_type, imdb_id)

    title = imdb_to_title(imdb_id)
    if not title:
        print("❌ No title from IMDb")
        return jsonify({"subtitles": []})

    results = search_subtitles(title)
    if not results:
        print("❌ No results from Podnapisi search")
        return jsonify({"subtitles": []})

    out = []
    for r in results:
        srt = download_srt(r["url"])
        if not srt:
            continue

        out.append({
            "id": r["name"],
            "lang": "sl",
            "title": r["name"],
            "subtitles": srt,
        })

    print("✅ Returning", len(out), "subtitles")
    return jsonify({"subtitles": out})


# -------------------------------------
# Run server (Render)
# -------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
