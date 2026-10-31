import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


class LessonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        server.RUNTIME = Path(cls.tmp.name)
        os.chmod(server.RUNTIME, 0o700)
        server.DB = server.RUNTIME / "lessons.sqlite3"
        server.init_db()
        cls.http = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        server.PORT = cls.http.server_address[1]
        cls.base = f"http://127.0.0.1:{server.PORT}"
        cls.thread = threading.Thread(target=cls.http.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        if server.DB.exists():
            server.DB.unlink()
        Path(str(server.DB) + "-wal").unlink(missing_ok=True)
        Path(str(server.DB) + "-shm").unlink(missing_ok=True)
        server.init_db()

    def request(self, path, body=None, headers=None):
        raw = None
        hdrs = dict(headers or {})
        if body is not None:
            raw = json.dumps(body).encode()
            hdrs.update({"Content-Type": "application/json", "X-Request-Token": server.TOKEN})
        req = urllib.request.Request(self.base + path, data=raw, headers=hdrs)
        try:
            with urllib.request.urlopen(req) as res:
                return res.status, res.headers, res.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.headers, exc.read()

    def source_payload(self, source):
        return {key: source[key] for key in ("id", "title", "url", "section", "notes", "attribution", "license_url")}

    def test_fixture_has_two_cited_claims_and_explicit_inference(self):
        s = server.state()
        self.assertEqual(len(s["sources"]), 2)
        self.assertEqual(len(s["claims"]), 3)
        self.assertTrue(s["export_ready"])
        self.assertEqual([c["is_inference"] for c in s["claims"]].count(True), 1)
        self.assertEqual(s["worked_results"]["mean"], 10)
        self.assertEqual(s["worked_results"]["median"], 6)

    def test_source_change_invalidates_only_linked_claim_and_needs_rereview(self):
        mean = next(x for x in server.state()["sources"] if x["id"] == "src-mean")
        payload = self.source_payload(mean)
        payload["notes"] = "Re-read the definition and record the checked section."
        status, _, body = self.request("/api/source/save", payload)
        self.assertEqual(status, 200, body)
        s = json.loads(body)
        claims = {x["id"]: x for x in s["claims"]}
        self.assertFalse(claims["claim-mean"]["review_current"])
        self.assertTrue(claims["claim-median"]["review_current"])
        self.assertTrue(claims["claim-example"]["review_current"])
        source = next(x for x in s["sources"] if x["id"] == "src-mean")
        self.assertEqual(source["version"], 2)
        self.assertFalse(source["source_reviewed"])
        self.assertEqual(self.request("/api/claim/review", {"id": "claim-mean", "review_note": "Checked"})[0], 400)
        self.assertEqual(self.request("/api/source/review", {"id": "src-mean"})[0], 200)
        status, _, body = self.request("/api/claim/review", {"id": "claim-mean", "review_note": "Compared with the updated source."})
        self.assertEqual(status, 200, body)
        s = json.loads(body)
        self.assertTrue(next(x for x in s["claims"] if x["id"] == "claim-mean")["review_current"])

    def test_claim_edit_invalidates_that_claim_review(self):
        claim = next(x for x in server.state()["claims"] if x["id"] == "claim-mean")
        body = {key: claim[key] for key in ("id", "text", "source_ids", "is_inference", "inference_note")}
        body["text"] = "The mean is the total divided by the count of values."
        status, _, response = self.request("/api/claim/save", body)
        self.assertEqual(status, 200, response)
        s = json.loads(response)
        claims = {x["id"]: x for x in s["claims"]}
        self.assertFalse(claims["claim-mean"]["review_current"])
        self.assertTrue(claims["claim-median"]["review_current"])

    def test_unlinked_fact_cannot_be_saved_or_exported_as_checked(self):
        payload = {"id": "claim-new", "text": "The result is always useful.", "source_ids": [], "is_inference": False, "inference_note": ""}
        status, _, response = self.request("/api/claim/save", payload)
        self.assertEqual(status, 400)
        self.assertIn(b"Link a source or label", response)
        self.assertEqual(self.request("/api/export", {"mode": "instructor"})[0], 200)

    def test_unreviewed_linked_claim_blocks_export(self):
        source = next(x for x in server.state()["sources"] if x["id"] == "src-mean")
        payload = self.source_payload(source)
        payload["notes"] = "The wording changed after source review."
        self.assertEqual(self.request("/api/source/save", payload)[0], 200)
        status, _, body = self.request("/api/export", {"mode": "instructor"})
        self.assertEqual(status, 400)
        self.assertIn(b"Review every claim", body)

    def test_changed_example_invalidates_only_inference_review(self):
        lesson = server.state()["lesson"]
        lesson["data"] = [1, 2, 3]
        status, _, body = self.request("/api/lesson", lesson)
        self.assertEqual(status, 200, body)
        claims = {x["id"]: x for x in json.loads(body)["claims"]}
        self.assertTrue(claims["claim-mean"]["review_current"])
        self.assertTrue(claims["claim-median"]["review_current"])
        self.assertFalse(claims["claim-example"]["review_current"])
        self.assertIn("cleared inference reviews", json.loads(body)["revisions"][0]["summary"])

    def test_inference_requires_label_reason_and_manual_review(self):
        payload = {"id": "inference-test", "text": "This example suggests a pattern.", "source_ids": [], "is_inference": True, "inference_note": "This is a conclusion drawn from the shown values."}
        status, _, response = self.request("/api/claim/save", payload)
        self.assertEqual(status, 200, response)
        self.assertFalse(next(c for c in json.loads(response)["claims"] if c["id"] == "inference-test")["review_current"])
        status, _, response = self.request("/api/claim/review", {"id": "inference-test", "review_note": "Compared the conclusion to the example values."})
        self.assertEqual(status, 200, response)
        self.assertTrue(next(c for c in json.loads(response)["claims"] if c["id"] == "inference-test")["review_current"])

    def test_numeric_exercise_checks_right_and_wrong_answers_without_leaking_key(self):
        status, _, correct = self.request("/api/check", {"answer": {"mean": 10, "median": 6}})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(correct)["correct"])
        status, _, wrong = self.request("/api/check", {"answer": {"mean": 9, "median": 7}})
        self.assertEqual(status, 200, wrong)
        self.assertFalse(json.loads(wrong)["correct"])
        self.assertNotIn(b"expected", wrong.lower())
        self.assertNotIn(b'"mean"', wrong)

    def test_learner_export_has_no_answers_and_instructor_has_key(self):
        status, headers, learner = self.request("/api/export", {"mode": "learner"})
        self.assertEqual((status, headers.get_content_type()), (200, "text/html"))
        self.assertNotIn(b"Mean: 10", learner)
        self.assertNotIn(b"Median: 6", learner)
        status, _, instructor = self.request("/api/export", {"mode": "instructor"})
        self.assertEqual(status, 200)
        self.assertIn(b"Mean: 10", instructor)
        self.assertIn(b"median: 6", instructor)
        self.assertIn(b"Teacher note, not source checked", learner)
        self.assertIn(b"Teacher note, not source checked", instructor)
        self.assertIn(server.LICENSE_URL.encode(), instructor)

    def test_readability_is_labeled_diagnostic_not_a_truth_check(self):
        s = server.state()
        self.assertIsInstance(s["readability"]["flesch_kincaid_grade"], float)
        self.assertIn("diagnostic only", server.export_html("instructor"))

    def test_revision_history_tracks_teacher_edits(self):
        before = server.state()["lesson"]["revision"]
        payload = server.state()["lesson"]
        payload["title"] = "A teacher-edited lesson title"
        status, _, body = self.request("/api/lesson", payload)
        self.assertEqual(status, 200, body)
        s = json.loads(body)
        self.assertEqual(s["lesson"]["revision"], before + 1)
        self.assertIn("Edited lesson text", s["revisions"][0]["summary"])

    def test_settings_persist_and_reset_restores_fixture(self):
        settings = {"instructor_name": "A. Teacher", "reading_target": 7, "learner_instruction": "Show your arithmetic."}
        status, _, body = self.request("/api/settings", {"settings": settings})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["settings"], settings)
        status, _, body = self.request("/api/reset", {})
        self.assertEqual(status, 200, body)
        self.assertEqual(json.loads(body)["settings"], server.settings_default())
        self.assertEqual(json.loads(body)["lesson"]["revision"], 1)

    def test_security_guards_and_string_ids(self):
        self.assertEqual(self.request("/api/state", headers={"Host": "attacker.example"})[0], 403)
        self.assertEqual(self.request("/api/state", headers={"Origin": "https://bad.example"})[0], 403)
        req = urllib.request.Request(self.base + "/api/reset", data=b"{}", headers={"Content-Type": "application/json"})
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        self.assertEqual(err.exception.code, 403)
        err.exception.close()
        req = urllib.request.Request(self.base + "/api/reset", data=b"x" * 128001, headers={"X-Request-Token": server.TOKEN})
        with self.assertRaises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req)
        self.assertEqual(err.exception.code, 413)
        err.exception.close()
        self.assertEqual(self.request("/api/claim/review", {"id": 1, "review_note": "Reviewed"})[0], 400)
        self.assertEqual(self.request("/api/source/save", {"id": "bad", "title": "Local", "url": "https://127.0.0.1/private", "attribution": "x", "license_url": "https://example.com/license"})[0], 400)
        self.assertEqual(os.stat(server.RUNTIME).st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(server.DB).st_mode & 0o777, 0o600)

    def test_exports_escape_user_text(self):
        s = server.state()
        lesson = s["lesson"]
        lesson["title"] = "<script>alert(1)</script>"
        status, _, response = self.request("/api/lesson", lesson)
        self.assertEqual(status, 200, response)
        status, _, export = self.request("/api/export", {"mode": "learner"})
        self.assertEqual(status, 200)
        self.assertNotIn(b"<script>", export)
        self.assertIn(b"&lt;script&gt;", export)


if __name__ == "__main__":
    unittest.main()
