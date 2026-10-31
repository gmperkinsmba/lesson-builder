#!/usr/bin/env python3
"""Local lesson builder with source-linked claims and checked arithmetic exercises."""
import hashlib
import html
import ipaddress
import json
import math
import os
import re
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
HOST = "127.0.0.1"
PORT = int(os.environ.get("LESSONS_PORT", "8325"))
RUNTIME = Path(os.environ.get("LESSONS_RUNTIME_DIR", str(Path.home() / ".research-to-lessons")))
RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
os.chmod(RUNTIME, 0o700)
DB = RUNTIME / "lessons.sqlite3"
TOKEN = secrets.token_urlsafe(24)
MAX_BODY = 128_000
LOCK = threading.RLock()
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

LICENSE_URL = "https://docs.python.org/3/license.html"
SOURCES = [
    {
        "id": "src-mean", "title": "Python statistics: arithmetic mean",
        "url": "https://docs.python.org/3/library/statistics.html#statistics.mean",
        "section": "statistics.mean", "notes": "Checked the definition: sum the values and divide by the count.",
        "attribution": "Python Software Foundation, Python documentation",
        "license_url": LICENSE_URL, "version": 1, "source_reviewed": True,
        "checked_at": "2026-10-31"
    },
    {
        "id": "src-median", "title": "Python statistics: median",
        "url": "https://docs.python.org/3/library/statistics.html#statistics.median",
        "section": "statistics.median", "notes": "Checked the odd and even count rules for numeric data.",
        "attribution": "Python Software Foundation, Python documentation",
        "license_url": LICENSE_URL, "version": 1, "source_reviewed": True,
        "checked_at": "2026-10-31"
    }
]
CLAIMS = [
    {
        "id": "claim-mean", "text": "The arithmetic mean is the sum of all values divided by the number of values.",
        "source_ids": ["src-mean"], "is_inference": False, "inference_note": "",
        "claim_reviewed": True, "review_note": "Paraphrase checked against the linked definition.",
        "reviewed_source_versions": {"src-mean": 1}
    },
    {
        "id": "claim-median", "text": "For numeric data, the median is the middle value after sorting; for an even count, it is the mean of the two middle values.",
        "source_ids": ["src-median"], "is_inference": False, "inference_note": "",
        "claim_reviewed": True, "review_note": "Paraphrase checked against the linked definition.",
        "reviewed_source_versions": {"src-median": 1}
    },
    {
        "id": "claim-example", "text": "In this example, the high value makes the mean larger than the median.",
        "source_ids": [], "is_inference": True,
        "inference_note": "This follows from the five values shown in the worked example.",
        "claim_reviewed": True, "review_note": "Checked by calculating both results from the example values.",
        "reviewed_source_versions": {}
    }
]
LESSON = {
    "id": "lesson-mean-median", "title": "Mean and median tell different stories",
    "question": "How can two measures summarize the same set of numbers differently?",
    "audience": "New analysts learning to summarize a small data set",
    "learning_goal": "Compare the arithmetic mean and median for one list of values.",
    "worked_example": "Use the values below to compare both measures.",
    "data": [2, 4, 6, 8, 30], "learner_prompt": "Calculate the mean and median for the values shown.",
    "revision": 1, "updated_at": NOW
}
DEFAULT_SETTINGS = {
    "instructor_name": "Instructor", "reading_target": 8,
    "learner_instruction": "Show your steps. Check the order of the values before finding the median."
}


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def source_fingerprint(source):
    fields = [source.get(k, "") for k in ("title", "url", "section", "notes", "attribution", "license_url")]
    return digest(json.dumps(fields, ensure_ascii=False, separators=(",", ":")))


def claim_fingerprint(claim):
    fields = [claim.get("text", ""), claim.get("is_inference", False), claim.get("inference_note", ""), claim.get("source_ids", [])]
    return digest(json.dumps(fields, ensure_ascii=False, separators=(",", ":")))


@contextmanager
def db():
    c = sqlite3.connect(DB, timeout=5)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=5000")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def settings_default():
    return dict(DEFAULT_SETTINGS)


def init_db():
    seed = False
    with LOCK, db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), settings_json TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS lesson(id TEXT PRIMARY KEY, title TEXT NOT NULL, question TEXT NOT NULL, audience TEXT NOT NULL,
          learning_goal TEXT NOT NULL, worked_example TEXT NOT NULL, data_json TEXT NOT NULL, learner_prompt TEXT NOT NULL,
          revision INTEGER NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL, section TEXT NOT NULL,
          notes TEXT NOT NULL, attribution TEXT NOT NULL, license_url TEXT NOT NULL, version INTEGER NOT NULL,
          content_hash TEXT NOT NULL, source_reviewed INTEGER NOT NULL, checked_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS claims(id TEXT PRIMARY KEY, text TEXT NOT NULL, source_ids_json TEXT NOT NULL,
          is_inference INTEGER NOT NULL, inference_note TEXT NOT NULL, claim_reviewed INTEGER NOT NULL,
          review_note TEXT NOT NULL, content_hash TEXT NOT NULL, reviewed_source_versions_json TEXT NOT NULL,
          updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY AUTOINCREMENT, lesson_revision INTEGER NOT NULL,
          created_at TEXT NOT NULL, summary TEXT NOT NULL, snapshot_json TEXT NOT NULL);
        """)
        if not c.execute("SELECT 1 FROM settings WHERE id=1").fetchone():
            c.execute("INSERT INTO settings VALUES(1,?)", (json.dumps(settings_default()),))
        if not c.execute("SELECT 1 FROM lesson LIMIT 1").fetchone():
            seed = True
        os.chmod(DB, 0o600)
        if seed:
            _seed(c)


def _seed(c):
    c.execute("INSERT INTO lesson VALUES(?,?,?,?,?,?,?,?,?,?)", (
        LESSON["id"], LESSON["title"], LESSON["question"], LESSON["audience"], LESSON["learning_goal"],
        LESSON["worked_example"], json.dumps(LESSON["data"]), LESSON["learner_prompt"], LESSON["revision"], NOW
    ))
    for source in SOURCES:
        c.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?)", (
            source["id"], source["title"], source["url"], source["section"], source["notes"], source["attribution"],
            source["license_url"], source["version"], source_fingerprint(source), int(source["source_reviewed"]), source["checked_at"]
        ))
    for claim in CLAIMS:
        c.execute("INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?)", (
            claim["id"], claim["text"], json.dumps(claim["source_ids"]), int(claim["is_inference"]), claim["inference_note"],
            int(claim["claim_reviewed"]), claim["review_note"], claim_fingerprint(claim),
            json.dumps(claim["reviewed_source_versions"]), NOW
        ))
    record_revision(c, "Loaded the checked example lesson", initial=True)


def lesson_row(c):
    row = c.execute("SELECT * FROM lesson WHERE id=?", (LESSON["id"],)).fetchone()
    d = dict(row)
    d["data"] = json.loads(d.pop("data_json"))
    return d


def source_rows(c):
    return [dict(r) | {"source_reviewed": bool(r["source_reviewed"])} for r in c.execute("SELECT * FROM sources ORDER BY rowid")]


def claim_rows(c):
    sources = {s["id"]: s for s in source_rows(c)}
    out = []
    for row in c.execute("SELECT * FROM claims ORDER BY rowid"):
        d = dict(row)
        d["source_ids"] = json.loads(d.pop("source_ids_json"))
        d["reviewed_source_versions"] = json.loads(d.pop("reviewed_source_versions_json"))
        d["is_inference"] = bool(d["is_inference"])
        current_hash = d["content_hash"] == claim_fingerprint(d)
        sources_ok = all(
            sid in sources and sources[sid]["source_reviewed"] and d["reviewed_source_versions"].get(sid) == sources[sid]["version"]
            for sid in d["source_ids"]
        )
        d["claim_reviewed"] = bool(d["claim_reviewed"] and current_hash and sources_ok)
        d["review_current"] = d["claim_reviewed"] and (bool(d["source_ids"]) or bool(d["is_inference"] and d["inference_note"].strip()))
        d["is_inference"] = bool(d["is_inference"])
        out.append(d)
    return out


def snapshot(c):
    return {"lesson": lesson_row(c), "sources": source_rows(c), "claims": claim_rows(c)}


def record_revision(c, summary, initial=False):
    if not initial:
        c.execute("UPDATE lesson SET revision=revision+1,updated_at=? WHERE id=?", (utcnow(), LESSON["id"]))
    state = snapshot(c)
    c.execute("INSERT INTO revisions(lesson_revision,created_at,summary,snapshot_json) VALUES(?,?,?,?)", (
        state["lesson"]["revision"], utcnow(), summary[:200], json.dumps(state, ensure_ascii=False)
    ))
    c.execute("DELETE FROM revisions WHERE id NOT IN (SELECT id FROM revisions ORDER BY id DESC LIMIT 1000)")


def syllables(word):
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    groups = re.findall(r"[aeiouy]+", word)
    count = len(groups)
    if word.endswith("e") and count > 1 and not word.endswith(("le", "ye")):
        count -= 1
    return max(1, count)


def readability(text):
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    if not words or not sentences:
        return {"words": len(words), "sentences": len(sentences), "flesch_reading_ease": None, "flesch_kincaid_grade": None}
    syllable_count = sum(syllables(w) for w in words)
    wc, sc = len(words), len(sentences)
    ease = 206.835 - 1.015 * (wc / sc) - 84.6 * (syllable_count / wc)
    grade = 0.39 * (wc / sc) + 11.8 * (syllable_count / wc) - 15.59
    return {"words": wc, "sentences": sc, "flesch_reading_ease": round(ease, 1), "flesch_kincaid_grade": round(grade, 1)}


def arithmetic(data):
    if not isinstance(data, list) or not 1 <= len(data) <= 50:
        raise ValueError("Use between 1 and 50 numeric values")
    values = []
    for value in data:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or abs(value) > 1_000_000_000:
            raise ValueError("Values must be finite numbers within the allowed range")
        values.append(float(value))
    ordered = sorted(values)
    middle = len(ordered) // 2
    median = ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
    return {"mean": sum(values) / len(values), "median": median, "count": len(values), "sorted": ordered}


def _state(c):
    lesson = lesson_row(c)
    claims = claim_rows(c)
    readable = " ".join(x["text"] for x in claims)
    settings = json.loads(c.execute("SELECT settings_json FROM settings WHERE id=1").fetchone()[0])
    sources = source_rows(c)
    revisions = [dict(r) for r in c.execute("SELECT id,lesson_revision,created_at,summary FROM revisions ORDER BY id DESC LIMIT 20")]
    checks = arithmetic(lesson["data"])
    return {
        "lesson": lesson, "sources": sources, "claims": claims, "settings": settings,
        "readability": readability(readable), "worked_results": checks,
        "export_ready": bool(claims) and all(x["review_current"] for x in claims), "revisions": revisions
    }


def state(connection=None):
    if connection is not None:
        return _state(connection)
    with LOCK, db() as c:
        return _state(c)


def validate_https_url(value):
    p = urlparse(value)
    if p.scheme != "https" or not p.hostname or p.username or p.password or len(value) > 1000:
        raise ValueError("Source links must be HTTPS URLs without credentials")
    host = p.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".local"):
        raise ValueError("Local network links are not supported")
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError("Local network links are not supported")
    except ValueError as exc:
        if "Local network" in str(exc):
            raise
    return value


def bounded_text(v, name, limit, required=False):
    if not isinstance(v, str):
        raise ValueError(f"{name} must be text")
    value = v.strip()
    if len(value) > limit or (required and not value):
        raise ValueError(f"{name} must be between 1 and {limit} characters" if required else f"{name} must be at most {limit} characters")
    return value


def source_current(s):
    return bool(s["source_reviewed"])


def export_html(mode, connection=None):
    if mode not in ("instructor", "learner"):
        raise ValueError("Choose instructor or learner export")
    s = state(connection)
    if not s["export_ready"]:
        raise ValueError("Review every claim and source or label the claim as an inference before export")
    esc = html.escape
    lesson = s["lesson"]
    claims = s["claims"]
    sources = {x["id"]: x for x in s["sources"]}
    claim_items = []
    for claim in claims:
        if claim["is_inference"]:
            evidence = f"Inference · {esc(claim['inference_note'])}"
        else:
            refs = [f"<a href=\"{esc(sources[sid]['url'], quote=True)}\">{esc(sources[sid]['title'])}</a>" for sid in claim["source_ids"]]
            evidence = "Source reviewed · " + "; ".join(refs)
        claim_items.append(f"<li>{esc(claim['text'])}<br><small>{evidence}</small><br><small>Review note: {esc(claim['review_note'])}</small></li>")
    claim_html = "".join(claim_items)
    source_html = "".join(
        f"<li><a href=\"{esc(x['url'], quote=True)}\">{esc(x['title'])}</a> — {esc(x['attribution'])}; license: <a href=\"{esc(x['license_url'], quote=True)}\">details</a></li>"
        for x in s["sources"] if any(x["id"] in c["source_ids"] for c in claims)
    )
    numbers = ", ".join(str(int(x) if float(x).is_integer() else x) for x in lesson["data"])
    if mode == "instructor":
        example = f"Values: {esc(numbers)}. Mean: {s['worked_results']['mean']:g}. Median: {s['worked_results']['median']:g}."
        worked = f"<h2>Worked example</h2><p><strong>Teacher note, not source checked:</strong> {esc(lesson['worked_example'])}</p><p>{example}</p>"
        exercise = f"<h2>Exercise and answer key</h2><p>{esc(lesson['learner_prompt'])}</p><p>Values: {esc(numbers)}</p><p>Mean: {s['worked_results']['mean']:g}; median: {s['worked_results']['median']:g}.</p>"
        evidence = f"<p><strong>Instructor:</strong> {esc(s['settings']['instructor_name'])}</p><p>Reading estimate: grade {s['readability']['flesch_kincaid_grade']}; diagnostic only.</p>"
    else:
        worked = f"<h2>Worked example</h2><p><strong>Teacher note, not source checked:</strong> {esc(lesson['worked_example'])}</p><p>Values: {esc(numbers)}</p>"
        exercise = f"<h2>Practice</h2><p>{esc(lesson['learner_prompt'])}</p><p>Values: {esc(numbers)}</p><p>Mean: __________</p><p>Median: __________</p><p>{esc(s['settings']['learner_instruction'])}</p>"
        evidence = "<p>Check your work with your instructor.</p>"
    return "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width\"><title>" + esc(lesson["title"]) + "</title><style>body{max-width:760px;margin:3rem auto;padding:0 1.2rem;font:18px/1.6 system-ui;color:#20242a}h1{font:500 2rem/1.15 Georgia}small{color:#405c77}li{margin:0.8rem 0}@media print{body{margin:1cm auto}}</style><main><h1>" + esc(lesson["title"]) + "</h1><p><strong>Question:</strong> " + esc(lesson["question"]) + "</p><p><strong>For:</strong> " + esc(lesson["audience"]) + "</p><p>" + esc(lesson["learning_goal"]) + "</p><h2>Key statements</h2><ul>" + claim_html + "</ul>" + worked + exercise + evidence + "<h2>Sources</h2><ul>" + source_html + "</ul><p>Statements are checked against the sources listed. Readability scores are estimates, not proof of understanding.</p></main></html>"


def create_source(c, payload):
    sid = bounded_text(payload.get("id"), "Source ID", 64, True)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", sid):
        raise ValueError("Source ID may use letters, numbers, underscores, or hyphens")
    title = bounded_text(payload.get("title"), "Source title", 180, True)
    url = validate_https_url(bounded_text(payload.get("url"), "Source URL", 1000, True))
    section = bounded_text(payload.get("section", ""), "Section", 160)
    notes = bounded_text(payload.get("notes", ""), "Review notes", 1000)
    attribution = bounded_text(payload.get("attribution", ""), "Attribution", 200, True)
    license_url = validate_https_url(bounded_text(payload.get("license_url", ""), "License URL", 1000, True))
    old = c.execute("SELECT * FROM sources WHERE id=?", (sid,)).fetchone()
    if old is None and c.execute("SELECT COUNT(*) FROM sources").fetchone()[0] >= 100:
        raise ValueError("Keep up to 100 sources in one lesson")
    current = {"id": sid, "title": title, "url": url, "section": section, "notes": notes, "attribution": attribution, "license_url": license_url}
    fingerprint = source_fingerprint(current)
    changed = old is not None and old["content_hash"] != fingerprint
    version = int(old["version"] + 1) if old and changed else int(old["version"]) if old else 1
    reviewed = 0 if changed or not old else int(old["source_reviewed"])
    checked_at = "" if changed else (old["checked_at"] if old else "")
    c.execute("""INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,url=excluded.url,
      section=excluded.section,notes=excluded.notes,attribution=excluded.attribution,license_url=excluded.license_url,
      version=excluded.version,content_hash=excluded.content_hash,source_reviewed=excluded.source_reviewed,checked_at=excluded.checked_at""",
      (sid, title, url, section, notes, attribution, license_url, version, fingerprint, reviewed, checked_at))
    if changed:
        for row in c.execute("SELECT id,source_ids_json FROM claims").fetchall():
            if sid in json.loads(row["source_ids_json"]):
                c.execute("UPDATE claims SET claim_reviewed=0,updated_at=? WHERE id=?", (utcnow(), row["id"]))
    return changed


def save_claim(c, payload, allow_blank=False):
    cid = bounded_text(payload.get("id"), "Claim ID", 64, True)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", cid):
        raise ValueError("Claim ID may use letters, numbers, underscores, or hyphens")
    text = bounded_text(payload.get("text"), "Claim", 500, not allow_blank)
    source_ids = payload.get("source_ids")
    if not isinstance(source_ids, list) or len(source_ids) > 12 or any(not isinstance(x, str) for x in source_ids) or len(set(source_ids)) != len(source_ids):
        raise ValueError("Choose up to 12 distinct source IDs")
    inference = payload.get("is_inference") is True
    inference_note = bounded_text(payload.get("inference_note", ""), "Inference note", 500)
    if not text and allow_blank:
        inference = False
        source_ids = []
        inference_note = ""
    elif inference and source_ids:
        raise ValueError("An inference must be labeled without source links")
    if text and not inference and not source_ids:
        raise ValueError("Link a source or label this statement as an inference")
    if inference and not inference_note:
        raise ValueError("Explain why this is an inference")
    sources = {s["id"]: s for s in source_rows(c)}
    if any(sid not in sources for sid in source_ids):
        raise ValueError("Choose sources already in this lesson")
    old = c.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
    if old is None and c.execute("SELECT COUNT(*) FROM claims").fetchone()[0] >= 200:
        raise ValueError("Keep up to 200 statements in one lesson")
    item = {"id": cid, "text": text, "source_ids": source_ids, "is_inference": inference, "inference_note": inference_note}
    fingerprint = claim_fingerprint(item)
    changed = old is not None and old["content_hash"] != fingerprint
    reviewed = 0 if changed or not old else int(old["claim_reviewed"])
    note = "" if changed else (old["review_note"] if old else "")
    versions = {} if changed else (json.loads(old["reviewed_source_versions_json"]) if old else {})
    c.execute("""INSERT INTO claims VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET text=excluded.text,
      source_ids_json=excluded.source_ids_json,is_inference=excluded.is_inference,inference_note=excluded.inference_note,
      claim_reviewed=excluded.claim_reviewed,review_note=excluded.review_note,content_hash=excluded.content_hash,
      reviewed_source_versions_json=excluded.reviewed_source_versions_json,updated_at=excluded.updated_at""",
      (cid, text, json.dumps(source_ids), int(inference), inference_note, reviewed, note, fingerprint, json.dumps(versions), utcnow()))
    return changed


class Handler(BaseHTTPRequestHandler):
    server_version = "ResearchLessons/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def send(self, status, body, content_type="application/json; charset=utf-8", raw=False):
        data = body if raw else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def origin_ok(self):
        port = self.server.server_port
        if self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}"):
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")

    def do_GET(self):
        if not self.origin_ok():
            return self.send(403, {"error": "Host or origin rejected"})
        path = urlparse(self.path).path
        if path == "/api/token":
            return self.send(200, {"token": TOKEN})
        if path == "/api/state":
            return self.send(200, state())
        files = {"/": ("index.html", "text/html; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8")}
        if path in files:
            name, content_type = files[path]
            return self.send(200, (ROOT / name).read_bytes(), content_type, raw=True)
        return self.send(404, {"error": "Not found"})

    def do_POST(self):
        if not self.origin_ok():
            return self.send(403, {"error": "Host or origin rejected"})
        if self.headers.get("X-Request-Token") != TOKEN:
            return self.send(403, {"error": "Request token rejected"})
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return self.send(400, {"error": "Invalid content length"})
        if size < 1 or size > MAX_BODY:
            return self.send(413, {"error": "Request must be 1 to 128000 bytes"})
        try:
            payload = json.loads(self.rfile.read(size))
        except (ValueError, OSError):
            return self.send(400, {"error": "Invalid JSON"})
        if not isinstance(payload, dict):
            return self.send(400, {"error": "JSON object required"})
        path = urlparse(self.path).path
        try:
            with LOCK, db() as c:
                if path == "/api/lesson":
                    allowed = ("title", "question", "audience", "learning_goal", "worked_example", "learner_prompt")
                    old = lesson_row(c)
                    values = {key: bounded_text(payload.get(key), key.replace("_", " ").title(), 1000 if key in ("question", "worked_example", "learning_goal", "learner_prompt") else 240, True) for key in allowed}
                    data = payload.get("data")
                    arithmetic(data)
                    example_changed = old["worked_example"] != values["worked_example"] or old["data"] != data
                    changed = any(old[key] != values[key] for key in allowed) or old["data"] != data
                    if changed:
                        c.execute("UPDATE lesson SET title=?,question=?,audience=?,learning_goal=?,worked_example=?,data_json=?,learner_prompt=? WHERE id=?", (values["title"], values["question"], values["audience"], values["learning_goal"], values["worked_example"], json.dumps(data), values["learner_prompt"], LESSON["id"]))
                        if example_changed:
                            c.execute("UPDATE claims SET claim_reviewed=0,updated_at=? WHERE is_inference=1", (utcnow(),))
                        record_revision(c, "Edited worked example and cleared inference reviews" if example_changed else "Edited lesson text")
                    return self.send(200, state(c))
                if path == "/api/source/save":
                    changed = create_source(c, payload)
                    record_revision(c, "Changed a source and cleared reviews on linked claims" if changed else "Added or saved source details")
                    return self.send(200, state(c))
                if path == "/api/source/review":
                    sid = payload.get("id")
                    if not isinstance(sid, str):
                        raise ValueError("Source ID must be a string")
                    row = c.execute("SELECT id FROM sources WHERE id=?", (sid,)).fetchone()
                    if not row:
                        return self.send(404, {"error": "Source not found"})
                    c.execute("UPDATE sources SET source_reviewed=1,checked_at=? WHERE id=?", (utcnow(), sid))
                    record_revision(c, "Marked a source as reviewed")
                    return self.send(200, state(c))
                if path == "/api/claim/save":
                    changed = save_claim(c, payload)
                    record_revision(c, "Edited a claim and cleared its review" if changed else "Added or saved a claim")
                    return self.send(200, state(c))
                if path == "/api/claim/create":
                    save_claim(c, payload, allow_blank=True)
                    record_revision(c, "Added a claim draft")
                    return self.send(200, state(c))
                if path == "/api/claim/delete":
                    cid = payload.get("id")
                    if not isinstance(cid, str):
                        raise ValueError("Claim ID must be a string")
                    if not c.execute("SELECT 1 FROM claims WHERE id=?", (cid,)).fetchone():
                        return self.send(404, {"error": "Claim not found"})
                    c.execute("DELETE FROM claims WHERE id=?", (cid,))
                    record_revision(c, "Removed a claim")
                    return self.send(200, state(c))
                if path == "/api/claim/review":
                    cid = payload.get("id")
                    if not isinstance(cid, str):
                        raise ValueError("Claim ID must be a string")
                    row = c.execute("SELECT * FROM claims WHERE id=?", (cid,)).fetchone()
                    if not row:
                        return self.send(404, {"error": "Claim not found"})
                    note = bounded_text(payload.get("review_note"), "Review note", 500, True)
                    ids = json.loads(row["source_ids_json"])
                    srcs = {x["id"]: x for x in source_rows(c)}
                    if row["is_inference"]:
                        if not row["inference_note"].strip():
                            raise ValueError("Explain the inference before review")
                    elif not ids or any(sid not in srcs or not srcs[sid]["source_reviewed"] for sid in ids):
                        raise ValueError("Review each linked source before reviewing this claim")
                    versions = {sid: srcs[sid]["version"] for sid in ids}
                    c.execute("UPDATE claims SET claim_reviewed=1,review_note=?,reviewed_source_versions_json=?,updated_at=? WHERE id=?", (note, json.dumps(versions), utcnow(), cid))
                    record_revision(c, "Reviewed a claim")
                    return self.send(200, state(c))
                if path == "/api/check":
                    results = arithmetic(lesson_row(c)["data"])
                    answer = payload.get("answer")
                    if not isinstance(answer, dict):
                        raise ValueError("Enter a mean and median")
                    def number(k):
                        value = answer.get(k)
                        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                            raise ValueError("Answers must be finite numbers")
                        return value
                    correct = math.isclose(number("mean"), results["mean"], rel_tol=0, abs_tol=0.01) and math.isclose(number("median"), results["median"], rel_tol=0, abs_tol=0.01)
                    return self.send(200, {"correct": correct, "message": "Both answers are right." if correct else "Check your arithmetic and try again."})
                if path == "/api/export":
                    mode = payload.get("mode")
                    doc = export_html(mode, c)
                    return self.send(200, doc.encode("utf-8"), "text/html; charset=utf-8", raw=True)
                if path == "/api/settings":
                    settings = payload.get("settings")
                    if not isinstance(settings, dict):
                        raise ValueError("Settings must be an object")
                    name = bounded_text(settings.get("instructor_name"), "Instructor name", 100, True)
                    target = settings.get("reading_target")
                    if isinstance(target, bool) or not isinstance(target, int) or not 1 <= target <= 16:
                        raise ValueError("Reading target must be from 1 to 16")
                    instruction = bounded_text(settings.get("learner_instruction"), "Learner instruction", 500, True)
                    safe = {"instructor_name": name, "reading_target": target, "learner_instruction": instruction}
                    c.execute("UPDATE settings SET settings_json=? WHERE id=1", (json.dumps(safe),))
                    return self.send(200, state(c))
                if path == "/api/reset":
                    c.execute("DELETE FROM claims")
                    c.execute("DELETE FROM sources")
                    c.execute("DELETE FROM revisions")
                    c.execute("DELETE FROM lesson")
                    c.execute("UPDATE settings SET settings_json=? WHERE id=1", (json.dumps(settings_default()),))
                    _seed(c)
                    return self.send(200, state(c))
                return self.send(404, {"error": "Not found"})
        except (ValueError, TypeError, sqlite3.Error, KeyError) as exc:
            return self.send(400, {"error": str(exc)[:240]})

    def log_message(self, fmt, *args):
        return


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def server_bind(self):
        TCPServer.server_bind(self)
        self.server_name = HOST
        self.server_port = self.socket.getsockname()[1]


def make_server(host=HOST, port=PORT):
    if host != HOST:
        raise ValueError("The local server must bind to loopback")
    init_db()
    return LocalHTTPServer((HOST, port), Handler)


if __name__ == "__main__":
    server = make_server()
    print(f"Lesson Builder listening at http://{HOST}:{server.server_port}", flush=True)
    server.serve_forever()
