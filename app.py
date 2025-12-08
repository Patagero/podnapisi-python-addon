from flask import Flask, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup

app = Flask(__name__)
CORS(app)

BASE = "https://www.podnapisi.net"


# ---------------------------------------------------
# MOVIE PAGE SCRAPER (DEFINITIVNO DELA BREZ LOGIN)
# ---------------------------------------------------
def get_subtitles_by_moviepage(imdb_id):
    url = f"{BASE}/sl/moviedb/{imdb_id}"
    headers = {"User-Agent": "Mozilla/5.0"}

    print("📡 Fetching movie page:", url)

    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print("❌ Movie page fetch failed", r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    rows = soup.select(".subtitle-entry")
    out = []

    for row in rows:
        link = row.select_one("a")
        if not link:
            continue

        sub_href = link.get("href")
        if not sub_href:
            continue

        lang_flag = row.select_one(".flag")
        lang = lang_flag.get("title", "unknown") if lang_flag else "unknown"

        out.append({
            "id": sub_href.split("/")[-1],
            "url": BASE + sub_href,
            "lang": lang,
            "title": link.text.strip()
        })

    print(f"✅ Found {len(out)} subtitles")
    return out


# ---------------------------------------------------
# MANIFEST (DELUJE)
# ---------------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "5.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (Movie Page Scrape)",
        "description": "Fast, stable, no login, no API, no headless browser.",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# ---------------------------------------------------
# MAIN SUBTITLE ROUTE (TO JE BILO MANJKAJOČE!)
# ---------------------------------------------------
@app.route("/subtitles/<type>/<imdb_id>.json")
def subtitles(type, imdb_id):
    print("📥 Incoming subtitle request:", imdb_id)

    results = get_subtitles_by_moviepage(imdb_id)

    return jsonify({"subtitles": results})


# ---------------------------------------------------
# RUN (Render auto-detects)
# ---------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
