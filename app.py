from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import zipfile
import io
import re

app = Flask(__name__)
CORS(app)

SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search"
DETAIL_URL = "https://www.podnapisi.net"


# -----------------------------
# IMDb → Title
# -----------------------------
def imdb_to_title(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/"
    print("📡 IMDb:", url)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ IMDb fetch failed")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    meta = soup.find("meta", property="og:title")

    if not meta:
        return None

    clean = re.sub(r"\(\d{4}\).*", "", meta["content"]).strip()
    print("🎬 Parsed title:", clean)
    return clean


# -----------------------------
# Search Podnapisi.net (NEW PARSER)
# -----------------------------
def find_subtitles(title):
    print("🔍 Searching for:", title)

    params = {
        "keywords": title,
        "language": "sl",
        "sort": "downloads"
    }

    r = requests.get(SEARCH_URL, params=params, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(r.text, "html.parser")

    results = []

    # NEW STRUCTURE 1 — table row format
    rows = soup.select("tr.subtitle-row a[href]")
    for a in rows:
        href = a.get("href")
        if href.startswith("/sl/subtitles/"):
            results.append({
                "id": href.split("/")[-1],
                "url": DETAIL_URL + href,
                "title": a.get_text(strip=True),
                "lang": "sl"
            })

    # NEW STRUCTURE 2 — div-based table rows
    links = soup.select("div.table-row a[href]")
    for a in links:
        href = a.get("href")
        if href.startswith("/sl/subtitles/"):
            results.append({
                "id": href.split("/")[-1],
                "url": DETAIL_URL + href,
                "title": a.get_text(strip=True),
                "lang": "sl"
            })

    print(f"✅ Found {len(results)} subtitles")
    return results


# -----------------------------
# Download ZIP → extract SRT
# -----------------------------
def download_subtitle(url):
    print("⬇ Downloading:", url)

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("❌ ZIP download failed")
        return None

    z = zipfile.ZipFile(io.BytesIO(r.content))

    for f in z.namelist():
        if f.lower().endswith(".srt"):
            print("📦 Extracted:", f)
            try:
                return z.read(f).decode("utf-8", errors="ignore")
            except:
                return z.read(f).decode("iso-8859-1", errors="ignore")

    print("❌ No SRT found")
    return None


# -----------------------------
# Manifest
# -----------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "name": "Podnapisi.NET 🇸🇮 (no-login)",
        "version": "1.2.0",
        "description": "Slovenski podnapisi iz Podnapisi.NET brez prijave.",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# -----------------------------
# Main Subtitles Endpoint
# -----------------------------
@app.route("/subtitles/<type>/<imdb_id>.json")
def subtitles(type, imdb_id):

    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    search_results = find_subtitles(title)
    out = []

    for s in search_results:
        dl_url = s["url"] + "/download"
        srt = download_subtitle(dl_url)
        if not srt:
            continue

        out.append({
            "id": s["id"],
            "lang": "sl",
            "title": s["title"],
            "subtitles": srt
        })

    return jsonify({"subtitles": out})


# -----------------------------
# Diagnostic Test
# -----------------------------
@app.route("/test/<imdb>")
def test(imdb):
    title = imdb_to_title(imdb)
    results = find_subtitles(title) if title else []

    return jsonify({
        "imdb": imdb,
        "title": title,
        "results_found": len(results)
    })


# -----------------------------
# Run server
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
