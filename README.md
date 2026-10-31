# Lesson Builder

**Mac app install**

Build on macOS with Python 3.12, then install the owned app:

```sh
python3.12 -m venv .desktop-venv
.desktop-venv/bin/python -m pip install -r requirements-desktop.lock.txt
.desktop-venv/bin/python build_desktop.py
.desktop-venv/bin/python install_desktop.py
```

Build creates `dist/Lesson Builder.app`.

Open `~/Applications/Lesson Builder.app` in Finder. Close its window or press Command-Q to quit. The app includes Python. It has an ad-hoc signature. It has no Developer ID signature or notarization. Lesson data stays in `~/.research-to-lessons/lessons.sqlite3`. To remove the app, move it from Applications to Trash. The runtime data stays until you remove that folder yourself.

For optional browser development, run `python3 server.py` and open `http://127.0.0.1:8325`. The desktop app starts and stops its own local server.

**First principle:** Turn reviewed sources into a lesson others can teach and practice.

Build a lesson around a question, a short source list, and clear statements. Check each statement against a source or mark it as an inference. Then export a teacher copy and a learner exercise.

## Run

Requires Python 3.10 or later. The app uses the Python standard library. It also uses browser JavaScript. No package install is needed.

```sh
python3 server.py
```

Open http://127.0.0.1:8325. Set `LESSONS_PORT` to use another port. Set `LESSONS_RUNTIME_DIR` to choose the local data folder. By default, SQLite lives in `~/.research-to-lessons/lessons.sqlite3`. The folder uses owner-only access.

## Use the lesson desk

Start with the question and audience. Add a source link and notes that say what you checked. Source pages do not load into the app. It keeps your link and review note.

Write one factual sentence on each statement card. Link it to a source, or mark it as an inference and explain why. Mark the source reviewed first. Then check each statement yourself and write a review note. The app does not scan words to decide if a claim is true.

Changing a source adds a new version and clears reviews on only the claims linked to it. Changing a statement clears its review. Changing the worked values clears reviews on inference claims. The revision list shows saved edits.

The sample uses the Python `statistics` documentation. Its lesson text is an original paraphrase. It does not copy the source page. Read the [mean and median definitions](https://docs.python.org/3/library/statistics.html). Read the [Python documentation license](https://docs.python.org/3/license.html).

Arithmetic checks the exercise mean and median. The app does not run learner input as code. Teacher exports include answers and source links. Learner exports leave out the answers. Both exports include source credit. Both mark the worked-example note as unchecked teacher text.

## Readability

The reading panel shows a grade estimate, reading ease, and word count. It is a rough signal from sentence length and word syllables. It does not test whether a learner understands the lesson.

## Settings and reset

Settings save the teacher name and target grade. They also save learner instructions in the local database. Use **Reset to sample lesson** to restore the demo lesson. It also restores the sources, review notes, and settings.

## Test

```sh
python3 -m unittest discover -s tests -v
```

Tests cover claim reviews and source reviews. They check selective invalidation and revision history. They check export rules and answer checks. They check escaping, local data permissions, and request guards. Tests use synthetic local data. They do not fetch live sources.

## Limits

This app does not fetch web pages, make claims for you, or prove that a statement is correct. A teacher must read the source and check each statement. The reading score is only a diagnostic. The arithmetic checker checks the mean and median for the values shown.

All original code is under the MIT License. See `LICENSE`. No external packages or fonts are bundled.
