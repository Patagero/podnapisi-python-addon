from flask import Flask, jsonify
from flask_cors import CORS
import requests
import urllib.parse

app = Flask(__name__)
CORS(app)

API_URL = "https://www.podnapisi.net/subtitles/search/"


# ---------------------------------------------
# IMDb → Title
# ---------------------------------------------
def imdb_to_title(imdb_id):
    url = f"https://www.imdb.com/title/{imdb_id}/"
    headers = {"User-Agent": "Mozilla/5.0"}

    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        return None

    import re
    import bs4

    soup = bs4.BeautifulSoup(r.text, "html.parser")
    tag = soup.find("meta", property="og:title")
    if not tag:
        return None

    full = tag["content"]
    title = re.sub(r"\(\d{4}\).*", "", full).strip()

    return title


# ---------------------------------------------
# Get subtitles via JSON API (never CF blocked!)
# ---------------------------------------------
def fetch_subtitles(title):
    params = {
        "keywords": title,
        "language": "sl",
        "format": "json",
        "page": 1
    }

    r = requests.get(API_URL, params=params, headers={"User-Agent": "Mozilla/5.0"})

    if r.status_code != 200:
        return []

    data = r.json()

    out = []

    for sub in data.get("subtitles", []):
        out.append({
            "id": sub.get("id"),
            "title": sub.get("title"),
            "lang": sub.get("language"),
            "url": f"https://www.podnapisi.net{sub.get('url')}",
            "downloads": sub.get("downloads"),
            "rating": sub.get("rating")
        })

    return out


# ---------------------------------------------
# Manifest
# ---------------------------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "3.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "description": "Stabilna verzija z uradnim JSON API (brez browserja, brez CF blockov).",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# ---------------------------------------------
# Subtitles endpoint
# ---------------------------------------------
@app.route("/subtitles/<type>/<imdb_id>.json")
def subtitles_simple(type, imdb_id):
    title = imdb_to_title(imdb_id)
    if not title:
        return jsonify({"subtitles": []})

    results = fetch_subtitles(title)

    return jsonify({"subtitles": results})


@app.route("/subtitles/<type>/<imdb_id>/<extra>.json")
def subtitles_extra(type, imdb_id, extra):
    return subtitles_simple(type, imdb_id)


# ---------------------------------------------
# Run server
# ---------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
