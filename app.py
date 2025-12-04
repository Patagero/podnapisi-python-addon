import os
import json
import requests
import zipfile
import tempfile
from flask import Flask, jsonify, send_file
from bs4 import BeautifulSoup
from flask_cors import CORS

USERNAME = os.getenv("PODNAPISI_USER", "")
PASSWORD = os.getenv("PODNAPISI_PASS", "")

LOGIN_URL = "https://www.podnapisi.net/sl/login"
SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search/?keywords={}&language=sl"

session = requests.Session()
cookies_loaded = False

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})


# -----------------------------------
# LOGIN
# -----------------------------------
def login_if_needed():
    global cookies_loaded
    if cookies_loaded:
        return

    print("🔐 Logging into Podnapisi.NET...")

    resp = session.get(LOGIN_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    token = soup.find("input", {"name": "_token"})
    if not token:
        print("⚠️ Login token not found")
        return

    payload = {
        "_token": token["value"],
        "username": USERNAME,
        "password": PASSWORD
    }

    session.post(LOGIN_URL, data=payload)
    cookies_loaded = True
    print("✅ Login OK")


# -----------------------------------
# FIND SUBTITLES
# -----------------------------------
def find_subtitles(title):
    login_if_needed()

    url = SEARCH_URL.format(title)
    print("🔍 Searching:", url)

    r = session.get(url)
    soup = BeautifulSoup(r.text, "lxml")

    results = []
    rows = soup.select("table.table tbody tr")

    for row in rows:
        a = row.find("a", href=True)
        if not a or "/download" not in a["href"]:
            continue

        full = "https://www.podnapisi.net" + a["href"]
        name = a.text.strip()

        results.append({
            "title": name,
            "link": full
        })

    print(f"✅ Found {len(results)} subtitles")
    return results


# -----------------------------------
# ZIP → SRT
# -----------------------------------
def extract_srt_from_zip(url):
    print("⬇️ Downloading ZIP:", url)

    r = session.get(url)

    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_zip.write(r.content)
    tmp_zip.close()

    extract_dir = tempfile.mkdtemp()

    try:
        with zipfile.ZipFile(tmp_zip.name, "r") as z:
            z.extractall(extract_dir)
    except Exception as e:
        print("⚠️ Zip error:", e)
        return None

    for file in os.listdir(extract_dir):
        if file.endswith(".srt"):
            return os.path.join(extract_dir, file)

    return None


# -----------------------------------
# ROUTES
# -----------------------------------

@app.route("/manifest.json")
def manifest():
    return jsonify({
        "id": "org.formio.podnapisi.python",
        "version": "1.0.0",
        "name": "Podnapisi.NET 🇸🇮 Python Addon",
        "description": "Slovenski podnapisi iz Podnapisi.NET (Python brez Chromium).",
        "types": ["movie", "series"],
        "resources": ["subtitles"],
        "idPrefixes": ["tt"]
    })


# 🔥 Stremio 5 format: /subtitles/movie/tt1234/<filename...>.json
@app.route("/subtitles/<stype>/<imdb_id>/<path:rest>.json")
def subtitles_with_rest(stype, imdb_id, rest):
    return subtitles(stype, imdb_id)


# 🔥 Stremio 4 format: /subtitles/movie/tt1234.json
@app.route("/subtitles/<stype>/<imdb_id>.json")
def subtitles(stype, imdb_id):
    print("🎬 Request for IMDB:", imdb_id)

    results = find_subtitles(imdb_id)

    base = os.getenv("RENDER_EXTERNAL_URL",
                     f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'podnapisi-python-addon.onrender.com')}")

    subtitles = []
    idx = 1

    for r in results:
        srt = extract_srt_from_zip(r["link"])
        if not srt:
            continue

        fname = os.path.basename(srt)
        url = f"{base}/file/{fname}"

        subtitles.append({
            "id": f"srt-{idx}",
            "lang": "sl",
            "url": url,
            "title": f"🇸🇮 {r['title']}"
        })
        idx += 1

    return jsonify({"subtitles": subtitles})


@app.route("/file/<filename>")
def serve_file(filename):
    temp_dir = tempfile.gettempdir()

    for root, dirs, files in os.walk(temp_dir):
        if filename in files:
            return send_file(os.path.join(root, filename), as_attachment=False)

    return "Not Found", 404


# -----------------------------------
# RUN (REQUIRED FOR RENDER)
# -----------------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7000))
    print(f"🚀 Starting Flask on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
