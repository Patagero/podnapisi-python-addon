import os
import json
import requests
import zipfile
import tempfile
from flask import Flask, jsonify, send_file
from bs4 import BeautifulSoup

# --------------------------
# CONFIG
# --------------------------

USERNAME = os.getenv("PODNAPISI_USER", "")
PASSWORD = os.getenv("PODNAPISI_PASS", "")

LOGIN_URL = "https://www.podnapisi.net/sl/login"
SEARCH_URL = "https://www.podnapisi.net/sl/subtitles/search/?keywords={}&language=sl"

session = requests.Session()
cookies_loaded = False

app = Flask(__name__)


# --------------------------
# LOGIN HANDLER
# --------------------------

def login_if_needed():
    """Ensures we are logged in at Podnapisi.NET"""
    global cookies_loaded
    if cookies_loaded:
        return

    print("🔐 Logging into Podnapisi.NET...")

    resp = session.get(LOGIN_URL)
    soup = BeautifulSoup(resp.text, "lxml")

    token = soup.find("input", {"name": "_token"})
    if not token:
        print("⚠️ Token missing — login may fail.")
        return

    payload = {
        "_token": token["value"],
        "username": USERNAME,
        "password": PASSWORD
    }

    session.post(LOGIN_URL, data=payload)
    cookies_loaded = True
    print("✅ Login done.")


# --------------------------
# SCRAPING SUBTITLES
# --------------------------

def find_subtitles(title: str):
    login_if_needed()

    url = SEARCH_URL.format(title)
    print("🔍 Searching:", url)

    r = session.get(url)
    soup = BeautifulSoup(r.text, "lxml")

    results = []
    rows = soup.select("table.table tbody tr")

    for row in rows:
        a = row.find("a", href=True)
        if not a:
            continue

        if "/download" not in a["href"]:
            continue

        full_link = "https://www.podnapisi.net" + a["href"]
        name = a.text.strip()

        results.append({
            "title": name,
            "link": full_link
        })

    print(f"✅ Found {len(results)} subtitles")
    return results


# --------------------------
# ZIP → SRT extraction
# --------------------------

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
    except:
        print("⚠️ Failed to extract ZIP")

    for f in os.listdir(extract_dir):
        if f.endswith(".srt"):
            srt_path = os.path.join(extract_dir, f)
            print("📜 Extracted SRT:", srt_path)
            return srt_path

    return None


# --------------------------
# STREMIO ROUTES
# --------------------------

@app.route("/manifest.json")
def manifest():
    with open("manifest.json", "r", encoding="utf8") as f:
        return jsonify(json.load(f))


@app.route("/subtitles/<type>/<imdb>.json")
def subtitles(type, imdb):
    print("🎬 Request:", imdb)

    title = imdb  # direct match, no OMDB needed
    results = find_subtitles(title)

    subtitles = []
    idx = 1

    base_url = os.getenv("RENDER_EXTERNAL_URL", "http://localhost:7000")

    for r in results:
        srt = extract_srt_from_zip(r["link"])
        if not srt:
            continue

        filename = os.path.basename(srt)
        serve_url = f"{base_url}/file/{filename}"

        subtitles.append({
            "id": f"srt-{idx}",
            "lang": "sl",
            "url": serve_url,
            "title": f"🇸🇮 {r['title']}"
        })
        idx += 1

    return jsonify({"subtitles": subtitles})


@app.route("/file/<filename>")
def serve_file(filename):
    tmp_match = []
    for root, dirs, files in os.walk(tempfile.gettempdir()):
        if filename in files:
            return send_file(os.path.join(root, filename), as_attachment=False)

    return "Not Found", 404


# --------------------------
# RUN
# --------------------------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7000))
    app.run(host="0.0.0.0", port=port)
