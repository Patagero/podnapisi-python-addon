from flask import Flask, jsonify, request
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app)

API_URL = "https://www.podnapisi.net/subtitles/search/"


# -----------------------------
# Extract TITLE from Stremio filename
# -----------------------------
def extract_title(extra):
    # Stremio pošlje: filename=Titanic.1997.4K.mkv&videoHash=....
    match = re.search(r"filename=([^&]+)", extra)
    if not match:
        return None

    filename = match.group(1)

    # odstrani končnice (.mkv, .mp4, .avi, itd.)
    filename = re.sub(r"\.(mkv|mp4|avi|mov|wmv|flv)$", "", filename, flags=re.IGNORECASE)

    # odstrani letnico (1997), UHD oznake, resolucije, HDR, ipd.
    filename = re.sub(r"\b(19\d{2}|20\d{2})\b", "", filename)
    filename = re.sub(r"\b(720p|1080p|2160p|4K|HDR|HDR10|HDR10\+|DV|DoVi|Remux|BDRip|UHD)\b", "", filename, flags=re.IGNORECASE)

    # zamenjaj pike/spaces z normalnimi presledki
    title = re.sub(r"[._]+", " ", filename).strip()

    return title


# -----------------------------
# Fetch subtitles from Podnapisi JSON API
# -----------------------------
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


# -----------------------------
# Manifest
# -----------------------------
@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "5.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon (No IMDb, No API Key)",
        "description": "Direct filename → Podnapisi.NET JSON API (fast, stable, simple).",
        "idPrefixes": ["tt"],
        "types": ["movie", "series"],
        "resources": ["subtitles"]
    })


# -----------------------------
# Subtitles endpoint
# -----------------------------
@app.route("/subtitles/<type>/<imdb_id>/<extra>.json")
def subtitles_with_extra(type, imdb_id, extra):

    title = extract_title(extra)

    if not title:
        return jsonify({"subtitles": []})

    results = fetch_subtitles(title)
    return jsonify({"subtitles": results})


# fallback, če Stremio ne pošlje extra
@app.route("/subtitles/<type>/<imdb_id>.json")
def subtitles_basic(type, imdb_id):
    return jsonify({"subtitles": []})


# -----------------------------
# Run
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
