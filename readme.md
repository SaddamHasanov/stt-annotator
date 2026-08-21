# 🎧 STT Annotator

A high-performance, lightweight, local web-based Speech-to-Text (STT) transcription annotation and correction tool. Designed specifically for reviewing and refining conversational Azerbaijani audio-to-text transcripts with manual editing controls and rule-based AI assistance.

---

## ✨ Features & Functions

- **Manual Annotation & Correction**:
  - Edit speaker segment text inline with real-time change tracking.
  - Interactive speaker toggle: click speaker labels to switch between `Operator` and `Müştəri`.
  - **Millisecond timestamps** (`MM:SS.mmm → MM:SS.mmm`) everywhere in the UI, with format validation.
    Legacy `MM:SS` files load fine, and any segment you do not touch is written back byte-for-byte.
  - Add and delete segments on the fly.
- **Waveform Segment Cropper (phone-style trim)**:
  - Full-width **Studio** panel with a real waveform decoded in the browser
    (WAV PCM 8/16/24/32-bit, float, A-law and **μ-law** — the format Verint call recordings use).
  - Two-channel recordings render as **two lanes**, and the app works out which lane is the
    Operator and which is the Müştəri by correlating channel energy with the transcript.
  - **Overview strip** (whole file) + **zoom view** that you can zoom to ≈0.2 ms per pixel.
  - Drag the **orange handles** to trim the selected segment's start/end; drag inside the region to
    slide the whole window. The segment's timestamps update live as you drag, in milliseconds.
  - `▶ Play segment` plays **only** the cropped region; `↻ Loop` repeats it while you fine-tune.
  - `−100 / −10 / +10 / +100` nudge buttons and typed `MM:SS.mmm` fields for exact values.
  - Neighbouring segments are drawn as coloured ticks so you can see the boundaries you are cutting against.
- **Autosave**:
  - Every edit — text, speaker, crop, add/delete — is written to `working/` as a draft ~0.7 s later.
    The badge in the header shows `● unsaved → ↻ saving… → ✓ auto-saved`.
  - Pending edits are flushed when you switch files and on page unload.
  - Finished files are *not* autosaved — press **Update Finished** to commit those.
- **Numbers → Azerbaijani words (`🔢 Rəqəm → söz`)**:
  - One click converts every digit in the open transcript to its spoken word form
    (`29-u` → `iyirmi doqquzu`, `1-ci` → `birinci`, `0.5%` → `sıfır tam beş faiz`).
  - Same engine is available as a batch CLI — see [Number normalisation](#-number-normalisation-rəqəm--söz).
- **AI-Powered Corrections (Gemini)**:
  - Supports the latest Gemini models: **Gemini 3.5 Flash** (recommended flagship), **Gemini 3.1 Pro Preview**, **Gemini 2.5 Pro**, and **Gemini 2.5 Flash**.
  - Dynamic rules ingestion: reads transcription guidelines directly from `ai/rules.md` (e.g., standardizing spelling, filtering filler words, background noise tags like `[fon_küyü]`).
  - High-precision minimal edit constraints: only updates rule violations without changing core dialect/phrasing.
  - Visual change comparison: displays the original text alongside corrected segments.
  - **Reconstruction Overlay**: Displays a backdrop-blur loading state with the message `Transcripts is under reconstruction…` while the AI processes corrections.
- **Custom Audio Player**:
  - Auto-mapped audio streams synced with segment clicks.
  - Keyboard shortcuts for hands-free playback controls.
  - Playback speed controls (`0.5x` to `2x`) and volume sliders.
  - The audio file is fetched once and shared between the `<audio>` element and the waveform.
- **Workflow & Queue Management**:
  - Real-time batch progress bar tracks completion.
  - Separate, collapsible **Finished** panel containing reviewed files.
  - Quick **Re-queue (↩)** action to move files back into the active queue.
  - **Draft Save (Save Draft)**: Save partial edits to a separate drafts folder. Shows a `working` badge next to the file in the queue.
  - **Semantic Comparison**: Checks if a draft has actual differences compared to the original before assigning the `working` badge. Reverting edits clears the badge and cleans up the draft automatically.
- **Privacy Mode (👁️ Blur Text)**:
  - Toggles a visual CSS blur filter over all text area content, blocking screen visibility for privacy while editing or showing screens.

---

## 📁 Directory Structure

Organize your workspace as follows:

```text
stt-local/
├── audio/          ← Put .wav / .mp3 files here
├── transcripts/    ← Put .jsonl transcript files here
├── working/        ← Partial draft edits are saved here (auto-created)
├── finished/       ← Completed files are saved here (auto-created)
├── normalized/     ← output of the number-normalisation CLI (auto-created)
├── ai/
│   ├── rules.md    ← Markdown file containing spelling & formatting rules
│   └── correct.py  ← Gemini API integration wrapper
├── tools/
│   └── az_num2words.py  ← digits → Azerbaijani words normaliser (CLI + module)
├── templates/
│   └── index.html  ← Frontend UI (Vanilla CSS/JS)
├── app.py          ← Flask Backend
├── .env            ← Environment file for your API keys (ignored by git)
└── readme.md       ← This instruction file
```

### Transcript File Format (`.jsonl`)
Transcripts must be in Newline-Delimited JSON (JSONL) format:
```json
{"start_time": "00:02.480", "end_time": "00:05.120", "speaker": "Operator", "text": "Alo, hər vaxtınız xeyir."}
{"start_time": "00:05", "end_time": "00:08", "speaker": "Müştəri", "text": "Salam, hər vaxtınız xeyir."}
```
Timestamps accept `MM:SS`, `MM:SS.mmm` and `HH:MM:SS.mmm`. The UI always *displays* milliseconds;
on save, a segment whose timing you never touched keeps its original string, and one you cropped is
written as `MM:SS.mmm`. That keeps diffs against the raw files minimal.

*Note: Audio and transcript files are matched by their base filename (e.g., `202501091637.jsonl` matches `202501091637.wav`).*

---

## 🛠️ Backend API Endpoints

The Flask backend (`app.py`) exposes the following endpoints:

| Method | Route | Description |
| :--- | :--- | :--- |
| `GET` | `/` | Serves the HTML frontend interface. |
| `GET` | `/api/samples` | Lists active transcripts in `transcripts/` (excluding those already in `finished/`). Includes a `status` field (`working` if a draft exists and has edits, otherwise `raw`). |
| `GET` | `/api/finished` | Lists all finalized transcript filenames in `finished/`. |
| `GET` | `/api/transcript/<name>` | Retrieves the transcript JSONL content. Fallback check order: `finished/` → `working/` (drafts) → `transcripts/` (original). |
| `GET` | `/api/audio/<name>` | Serves the matching audio file for playback. |
| `GET` | `/api/rules` | Reads and returns the Azerbaijani transcription guidelines from `ai/rules.md`. |
| `POST` | `/api/save` | Finalizes a transcript. Writes content to `finished/` and deletes any matching draft from `working/`. |
| `POST` | `/api/save_draft` | Saves partial edits to `working/` as a draft. |
| `POST` | `/api/requeue` | Removes a completed file from `finished/`, returning it back to the active queue. |
| `POST` | `/api/ai/correct` | Triggers LLM-based correction using the selected Gemini model and rules configuration. |
| `POST` | `/api/ai/adjust_timestamps` | Pushes overlapping segments apart (the **🕒 Fix Overlaps** button), millisecond-aware. |
| `POST` | `/api/normalize_numbers` | Converts digits in the posted segments to Azerbaijani words (the **🔢 Rəqəm → söz** button). |

---

## 🔢 Number normalisation (Rəqəm → söz)

`tools/az_num2words.py` rewrites every digit in a transcript as the Azerbaijani word that was
actually spoken, attaching the case/ordinal suffix correctly (vowel harmony, buffer consonants,
`i → İ` capitalisation at sentence start).

| Input | Output |
| :--- | :--- |
| `6 rəqəmli kod` | `altı rəqəmli kod` |
| `29-u`, `28-i`, `6-sı`, `10-na` | `iyirmi doqquzu`, `iyirmi səkkizi`, `altısı`, `ona` |
| `1-ci`, `13-cü`, `12-ci` | `birinci`, `on üçüncü`, `on ikinci` |
| `10-dir` | `ondur` *(suffix harmony is recomputed, not copied)* |
| `3000 AZN-ə`, `3000₼-dən` | `üç min AZN-ə`, `üç min manatdan` |
| `24%`, `0.5%`, `131,68-dir` | `iyirmi dörd faiz`, `sıfır tam beş faiz`, `yüz otuz bir tam altmış səkkizdir` |
| `20 000`, `50000-lik` | `iyirmi min`, `əlli minlik` |
| `1-10 aralığı`, `3-4` | `bir-on aralığı`, `üç-dörd` |
| `055 223 13 70` | `sıfır əlli beş iki yüz iyirmi üç on üç yetmiş` |
| `27.07.1995`, `15:00-da` | `iyirmi yeddi iyul min doqquz yüz doxsan beş`, `on beşdə` |
| `2L4SBRX`, `3D Secure`, `2x` | *left untouched and reported* |

### Running it

```bash
# 1) Dry run over transcripts/ — prints what would change, writes nothing
python tools/az_num2words.py

# 2) Write the converted copies into normalized/
python tools/az_num2words.py --apply

# 3) Overwrite the originals (a .bak copy is kept next to each file)
python tools/az_num2words.py --apply --in-place

# 4) Full change log for review
python tools/az_num2words.py --report num_report.txt
```

| Flag | Meaning |
| :--- | :--- |
| `--dir NAME` | Folder to process (default `transcripts`) — e.g. `--dir finished` |
| `--file PATH` | Process only this file; repeatable |
| `--out NAME` | Destination folder (default `normalized`) |
| `--apply` | Actually write; without it the run is a dry run |
| `--in-place` | Overwrite the source files, keeping a `.bak` |
| `--skip A,B` | Disable passes: `codes,thousands,dates,times,plus,ranges,fractions,decimals,plain` |
| `--report FILE` | Write every before/after pair plus warnings |
| `--selftest` | Run the built-in conversion tests |

Anything the converter is unsure about is left alone and listed in the report — mixed
letter/digit codes (`2L4SBRX`, `014D`), unknown suffixes (`2x`), dates, times, fractions,
dot-decimals and space-separated thousands. Skim those before shipping a batch.

The same engine backs the **🔢 Rəqəm → söz** button, which converts only the transcript currently
open in the browser and shows the usual word-level diff so you can review each change.

> ⚠️ **This is the opposite direction of rule `R4` in `ai/rules.md`**, which tells the Gemini
> correction pass to turn words *into* digits (`iyirmi üç` → `23`). If you standardise on spelled-out
> numbers, update `R4` as well — otherwise **✨ AI Correct** will convert them straight back.

---

## 🚀 Setup & Installation

### 1. Clone the repository
```bash
git clone git@github.com:shahin1717/stt-annotator.git
cd stt-annotator
```

### 2. Install dependencies
Only Flask is required. All AI requests use native Python standard libraries (zero third-party SDK dependencies).
```bash
pip install flask
```

### 3. Add API Keys
Create a `.env` file in the root directory and add your Google Gemini API key:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```

---

## 💻 Running the App

### 🪟 Windows (One-Click / Auto Setup)
You can run the automatic setup and launcher script which checks Python, creates `.venv`, installs dependencies, and starts the server:
- **PowerShell**:
  ```powershell
  .\run.ps1
  ```
  *(Or execute `powershell -ExecutionPolicy Bypass -File .\run.ps1` if execution policies are restricted)*
- **Or double-click** `run.bat` directly in File Explorer.

### 🐧 Linux / macOS / Manual
1. Place your raw audio files into the `audio/` directory.
2. Place your corresponding transcript `.jsonl` files into the `transcripts/` directory.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the Flask application:
   ```bash
   python app.py
   ```
5. Open your browser and navigate to:
   ```text
   http://localhost:5000
   ```

---

## ⌨️ Keyboard Shortcuts

These shortcuts are active only when you are **not** typing inside input fields or textareas:

| Key | Action |
| :--- | :--- |
| `Space` | Play / Pause the whole file |
| `P` | Play **only** the selected (cropped) segment |
| `L` | Toggle looping of the cropped region |
| `←` / `→` | Seek ∓5 seconds |
| `Shift` + `←` / `→` | Move the segment **start** by ∓10 ms (hold `Ctrl` for 100 ms) |
| `Alt` + `←` / `→` | Move the segment **end** by ∓10 ms (hold `Ctrl` for 100 ms) |
| `,` / `.` | Select the previous / next segment |
| `+` / `−` | Zoom the waveform in / out |

Mouse, over the zoom waveform: **wheel** zooms around the cursor, **Shift + wheel** pans,
**drag a handle** trims one edge, **drag inside the region** slides the whole window, and a
**click outside** it moves the playhead.

---

## 🔄 Recommended Workflow

1. **Upload Batch**: Drop raw `.jsonl` transcripts into `transcripts/` and `.wav` audios into `audio/`.
2. **Launch & Correct**: Open the web application. You can review segments manually or press **✨ AI Correct** to run the selected Gemini model over the rules.
3. **Fix the timing**: Click a segment — it loads into the Studio cropper above. Drag the orange
   handles until they hug the speech, hit **▶ Play segment** (or `P`) to check, and `↻ Loop` while
   fine-tuning. Use `Shift`/`Alt` + `←`/`→` for 10 ms nudges. Move on with `.` — nothing to save,
   the draft is written automatically.
4. **Normalise numbers** *(optional)*: **🔢 Rəqəm → söz** rewrites digits as spoken words, or run
   `python tools/az_num2words.py --apply` over the whole batch.
5. **Save Progress**: Edits autosave to `working/` and the item shows a `working` badge in the queue.
   **Save Draft** forces an immediate write if you want one.
6. **Verify & Save**: Listen once more, then click **Save to Finished** to move the file into `finished/`.
7. **Final Export**: Once the queue is empty, grab your finalized transcript files from the `finished/` folder and upload them back to your storage system.