"""
STT Annotator — local version
------------------------------
Folder structure expected:
  anywhere/
    audio/        ← dump Verint Zənglər contents here
    transcripts/  ← dump your Shahin E JSON files here
    finished/     ← corrected files go here (auto-created)

Run:
    pip install flask
    python app.py
Then open http://localhost:5000
"""

from flask import Flask, jsonify, request, send_file, render_template
import os, json, shutil, glob, re

app = Flask(__name__)
# Pick up edits to templates/index.html without needing a server restart
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.jinja_env.auto_reload = True

BASE     = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR       = os.path.join(BASE, "audio")
TRANSCRIPT_DIR  = os.path.join(BASE, "transcripts")
FINISHED_DIR    = os.path.join(BASE, "finished")
WORKING_DIR     = os.path.join(BASE, "working")

os.makedirs(AUDIO_DIR, exist_ok=True)
os.makedirs(TRANSCRIPT_DIR, exist_ok=True)
os.makedirs(FINISHED_DIR, exist_ok=True)
os.makedirs(WORKING_DIR, exist_ok=True)

# ── Pages ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

def load_jsonl_segments(file_path):
    try:
        segments = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    segments.append(json.loads(line))
        return segments
    except Exception:
        return None

def is_different(f1_path, f2_path):
    s1 = load_jsonl_segments(f1_path)
    s2 = load_jsonl_segments(f2_path)
    if s1 is None or s2 is None:
        return True
    if len(s1) != len(s2):
        return True
    for seg1, seg2 in zip(s1, s2):
        for key in ["start_time", "end_time", "speaker", "text"]:
            if seg1.get(key) != seg2.get(key):
                return True
    return False

def to_seconds(t_str):
    """Parse "SS", "MM:SS", "MM:SS.mmm" or "HH:MM:SS.mmm" into float seconds."""
    if t_str is None or t_str == "":
        return 0.0
    if isinstance(t_str, (int, float)):
        return float(t_str)
    total = 0.0
    for part in str(t_str).strip().split(":"):
        try:
            value = float(part.replace(",", "."))
        except ValueError:
            value = 0.0
        total = total * 60 + value
    return total

def to_time_str(secs, millis=True):
    """Format float seconds as "MM:SS.mmm" (or "MM:SS" when millis=False)."""
    if secs is None or secs < 0:
        secs = 0
    total_ms = int(round(float(secs) * 1000))
    ms = total_ms % 1000
    whole = total_ms // 1000
    m, s = divmod(whole, 60)
    if millis:
        return f"{m:02d}:{s:02d}.{ms:03d}"
    return f"{m:02d}:{s:02d}"

def normalize_speaker(speaker_name):
    s = speaker_name.strip().lower()
    if "operator" in s or "agent" in s or "bank" in s:
        return "Operator"
    else:
        return "Müştəri"

def parse_txt_to_jsonl_segments(file_path):
    segments = []
    current_time = 0
    last_speaker = "Operator"
    after_hold = False
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return []
        
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        is_parenthetical = (line.startswith("*(") and line.endswith(")*")) or (line.startswith("(") and line.endswith(")"))
        
        if is_parenthetical:
            text = line
            speaker = last_speaker
            line_lower = line.lower()
            if any(term in line_lower for term in ["musiqi", "sükut", "silence", "gözləmə"]):
                after_hold = True
        elif line.startswith("–") or line.startswith("-") or line.startswith("—"):
            text = line.lstrip("–-— ").strip()
            
            if not segments:
                speaker = "Operator"
            elif after_hold:
                speaker = "Operator"
                after_hold = False
            else:
                speaker = "Müştəri" if last_speaker == "Operator" else "Operator"
                
            text_lower = text.lower()
            if any(term in text_lower for term in ["hörmətli müştəri", "təşəkkür edirəm", "müraciət etdiyiniz üçün", "xətdə gözlədiyiniz", "xəttə gözlədiyiniz"]):
                speaker = "Operator"
            elif any(term in text_lower for term in ["xanım", "qardaş"]):
                speaker = "Müştəri"
                
            last_speaker = speaker
            after_hold = False
        elif ":" in line:
            parts = line.split(":", 1)
            speaker_candidate = parts[0].replace("*", "").strip()
            text_candidate = parts[1].strip().strip("*").strip()
            
            speaker_lower = speaker_candidate.lower()
            valid_keywords = ["operator", "müştəri", "musteri", "bank", "agent", "mərzuəçi", "məruzəçi"]
            is_valid_speaker = any(kw in speaker_lower for kw in valid_keywords) or (len(speaker_candidate) < 15 and len(speaker_candidate) > 0)
            
            if is_valid_speaker:
                speaker = normalize_speaker(speaker_candidate)
                text = text_candidate
                last_speaker = speaker
                after_hold = False
            else:
                if not segments:
                    continue
                segments[-1]["text"] += " " + line
                continue
        else:
            if not segments:
                continue
            segments[-1]["text"] += " " + line
            continue
            
        words = text.split()
        duration = max(2, min(30, int(len(words) * 0.4)))
        
        start_str = to_time_str(current_time)
        end_str = to_time_str(current_time + duration)
        
        segments.append({
            "start_time": start_str,
            "end_time": end_str,
            "speaker": speaker,
            "text": text
        })
        current_time += duration
        
    return segments

def serialize_segment(s):
    ordered = {
        "start_time": s.get("start_time", ""),
        "end_time": s.get("end_time", ""),
        "speaker": s.get("speaker", ""),
        "text": s.get("text", "")
    }
    for k, v in s.items():
        if k not in ordered:
            ordered[k] = v
    return json.dumps(ordered, ensure_ascii=False)


def get_original_segments(name):
    base = os.path.splitext(name)[0]
    for ext in [".json", ".jsonl", ".txt"]:
        path = os.path.join(TRANSCRIPT_DIR, f"{base}{ext}")
        if os.path.exists(path):
            if ext == ".txt":
                return parse_txt_to_jsonl_segments(path)
            else:
                return load_jsonl_segments(path)
    return None

def check_and_propagate_shifts(draft_segments, original_segments):
    if not original_segments:
        return draft_segments

    import re
    def get_words(text):
        if not text:
            return set()
        cleaned = re.sub(r"[.,!?;:()\[\]\{\}'\"\-]", "", text.lower())
        return set(cleaned.split())

    n_d = len(draft_segments)
    n_o = len(original_segments)
    
    if n_d == n_o:
        mapping = {i: i for i in range(n_d)}
    else:
        dp = [[0.0] * (n_o + 1) for _ in range(n_d + 1)]
        parent = [[(0, 0)] * (n_o + 1) for _ in range(n_d + 1)]
        
        def get_match_score(d_idx, o_idx):
            d_seg = draft_segments[d_idx]
            o_seg = original_segments[o_idx]
            score = 0.0
            
            d_text = d_seg.get("text", "")
            o_text = o_seg.get("text", "")
            w1 = get_words(d_text)
            w2 = get_words(o_text)
            
            has_word_overlap = bool(w1 and w2 and w1.intersection(w2))
            has_time_match = (
                d_seg.get("start_time") == o_seg.get("start_time") or 
                d_seg.get("end_time") == o_seg.get("end_time")
            )
            has_exact_text = (d_text == o_text)
            
            if not (has_word_overlap or has_time_match or has_exact_text):
                return 0.0
                
            if d_seg.get("text") == o_seg.get("text") and d_seg.get("speaker") == o_seg.get("speaker") and d_seg.get("start_time") == o_seg.get("start_time") and d_seg.get("end_time") == o_seg.get("end_time"):
                score += 100.0
            elif d_seg.get("text") == o_seg.get("text"):
                score += 80.0
                
            if d_seg.get("start_time") == o_seg.get("start_time") and d_seg.get("end_time") == o_seg.get("end_time"):
                score += 40.0
                
            if d_seg.get("speaker") == o_seg.get("speaker"):
                score += 10.0
                
            if w1 and w2:
                intersection = w1.intersection(w2)
                score += (len(intersection) / max(len(w1), len(w2))) * 20.0
                
            score += 5.0 / (1.0 + abs(d_idx - o_idx))
            return score

        for i in range(1, n_d + 1):
            for j in range(1, n_o + 1):
                score = get_match_score(i-1, j-1)
                op1 = dp[i-1][j-1] + score
                op2 = dp[i-1][j]
                op3 = dp[i][j-1]
                
                best = max(op1, op2, op3)
                dp[i][j] = best
                
                if best == op1:
                    parent[i][j] = (i-1, j-1)
                elif best == op2:
                    parent[i][j] = (i-1, j)
                else:
                    parent[i][j] = (i, j-1)
                    
        mapping = {}
        i, j = n_d, n_o
        while i > 0 and j > 0:
            pi, pj = parent[i][j]
            if pi == i-1 and pj == j-1:
                if get_match_score(i-1, j-1) > 2.0:
                    mapping[i-1] = j-1
                i, j = pi, pj
            elif pi == i-1:
                i = pi
            else:
                j = pj

    changed_or_propagated = [False] * n_d
    for d_idx in range(n_d):
        o_idx = mapping.get(d_idx)
        if o_idx is None:
            changed_or_propagated[d_idx] = True
        else:
            d_seg = draft_segments[d_idx]
            o_seg = original_segments[o_idx]
            if d_seg.get("start_time") != o_seg.get("start_time") or d_seg.get("end_time") != o_seg.get("end_time"):
                changed_or_propagated[d_idx] = True

    for idx in range(n_d - 1):
        if changed_or_propagated[idx]:
            prev_seg = draft_segments[idx]
            next_seg = draft_segments[idx + 1]
            
            prev_end = to_seconds(prev_seg.get("end_time", "00:00"))
            next_start = to_seconds(next_seg.get("start_time", "00:00"))
            
            orig_gap = 0
            o_idx_prev = mapping.get(idx)
            o_idx_next = mapping.get(idx + 1)
            if o_idx_prev is not None and o_idx_next is not None:
                o_prev = original_segments[o_idx_prev]
                o_next = original_segments[o_idx_next]
                orig_prev_end = to_seconds(o_prev.get("end_time", "00:00"))
                orig_next_start = to_seconds(o_next.get("start_time", "00:00"))
                orig_gap = orig_next_start - orig_prev_end
            
            min_allowed_gap = min(0, orig_gap)
            
            if next_start < prev_end + min_allowed_gap:
                next_end = to_seconds(next_seg.get("end_time", "00:00"))
                duration = max(0, next_end - next_start)
                
                new_start_str = to_time_str(prev_end + min_allowed_gap)
                new_end_str = to_time_str(prev_end + min_allowed_gap + duration)
                
                next_seg["start_time"] = new_start_str
                next_seg["end_time"] = new_end_str
                
                changed_or_propagated[idx + 1] = True

    return draft_segments


@app.route("/api/samples")
def samples():
    """List all files in transcripts/ that aren't already in finished/ with draft status."""
    done = {os.path.basename(f) for f in glob.glob(os.path.join(FINISHED_DIR, "*.json*"))}
    working = {os.path.basename(f) for f in glob.glob(os.path.join(WORKING_DIR, "*.json*"))}
    
    files = []
    for f in sorted(os.listdir(TRANSCRIPT_DIR)):
        if f.startswith("."):
            continue
        base, ext = os.path.splitext(f)
        if ext.lower() not in [".json", ".jsonl", ".txt"]:
            continue
            
        jsonl_name = f"{base}.jsonl"
        
        # Check if already finished
        if jsonl_name in done:
            continue
            
        is_working = False
        if jsonl_name in working:
            w_path = os.path.join(WORKING_DIR, jsonl_name)
            t_path = os.path.join(TRANSCRIPT_DIR, f)
            if os.path.exists(w_path) and os.path.exists(t_path):
                if ext.lower() == ".txt":
                    raw_segments = parse_txt_to_jsonl_segments(t_path)
                    draft_segments = load_jsonl_segments(w_path)
                    different = False
                    if raw_segments is None or draft_segments is None or len(raw_segments) != len(draft_segments):
                        different = True
                    else:
                        for seg1, seg2 in zip(raw_segments, draft_segments):
                            for key in ["start_time", "end_time", "speaker", "text"]:
                                if seg1.get(key) != seg2.get(key):
                                    different = True
                                    break
                            if different:
                                break
                    if different:
                        is_working = True
                    else:
                        try:
                            os.remove(w_path)
                        except Exception:
                            pass
                else:
                    if is_different(w_path, t_path):
                        is_working = True
                    else:
                        try:
                            os.remove(w_path)
                        except Exception:
                            pass
            
        files.append({
            "name": jsonl_name,
            "status": "working" if is_working else "raw"
        })
    return jsonify(files)

@app.route("/api/transcript/<name>")
def get_transcript(name):
    # try exact name first, then with .jsonl extension
    for fname in [name, name.replace(".json", ".jsonl")]:
        f_path = os.path.join(FINISHED_DIR, fname)
        if os.path.exists(f_path):
            return open(f_path, encoding="utf-8").read(), 200, {"Content-Type": "application/json"}
        w_path = os.path.join(WORKING_DIR, fname)
        if os.path.exists(w_path):
            return open(w_path, encoding="utf-8").read(), 200, {"Content-Type": "application/json"}
        path = os.path.join(TRANSCRIPT_DIR, fname)
        if os.path.exists(path):
            return open(path, encoding="utf-8").read(), 200, {"Content-Type": "application/json"}
        
        # Check .txt fallback
        base = os.path.splitext(fname)[0]
        txt_path = os.path.join(TRANSCRIPT_DIR, f"{base}.txt")
        if os.path.exists(txt_path):
            segments = parse_txt_to_jsonl_segments(txt_path)
            content = "\n".join(serialize_segment(s) for s in segments)
            return content, 200, {"Content-Type": "application/json"}
            
    return "Not found", 404

@app.route("/api/finished")
def get_finished():
    """List all JSON/JSONL files in finished/."""
    files = sorted([
        f for f in os.listdir(FINISHED_DIR)
        if (f.endswith(".json") or f.endswith(".jsonl"))
    ])
    return jsonify(files)

@app.route("/api/requeue", methods=["POST"])
def requeue():
    data = request.json
    name = data.get("name")
    if not name:
        return jsonify({"ok": False, "error": "Missing name parameter"}), 400
    path = os.path.join(FINISHED_DIR, name)
    if os.path.exists(path):
        os.remove(path)
        return jsonify({"ok": True})
    return jsonify({"ok": False, "error": "File not found in finished"}), 404

@app.route("/api/audio/<name>")
def get_audio(name):
    """Find audio file matching the base name (any extension)."""
    base = name.replace(".jsonl", "").replace(".json", "")
    for f in os.listdir(AUDIO_DIR):
        if os.path.splitext(f)[0] == base:
            return send_file(os.path.join(AUDIO_DIR, f))
    return "Audio not found", 404

@app.route("/api/rules")
def get_rules():
    rules_path = os.path.join(BASE, "ai", "rules.md")
    if os.path.exists(rules_path):
        with open(rules_path, encoding="utf-8") as f:
            return jsonify({"ok": True, "rules": f.read()})
    return jsonify({"ok": False, "error": "Rules file not found"}), 404

@app.route("/api/save", methods=["POST"])
def save():
    data = request.json
    name    = data["name"]
    content = data["content"]
    
    try:
        segments = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if line:
                segments.append(json.loads(line))
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to parse content: {str(e)}"}), 400

    content = "\n".join(serialize_segment(s) for s in segments)
    
    out = os.path.join(FINISHED_DIR, name)
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
        
    # Delete from working folder if it exists since it's now finalized
    w_path = os.path.join(WORKING_DIR, name)
    if os.path.exists(w_path):
        os.remove(w_path)
        
    return jsonify({"ok": True, "segments": segments})

@app.route("/api/save_draft", methods=["POST"])
def save_draft():
    data = request.json
    name    = data["name"]
    content = data["content"]
    
    try:
        segments = []
        for line in content.strip().split("\n"):
            line = line.strip()
            if line:
                segments.append(json.loads(line))
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to parse content: {str(e)}"}), 400

    content = "\n".join(serialize_segment(s) for s in segments)
    
    out = os.path.join(WORKING_DIR, name)
    with open(out, "w", encoding="utf-8") as f:
        f.write(content)
    return jsonify({"ok": True, "segments": segments})

@app.route("/api/ai/correct", methods=["POST"])
def ai_correct():
    data = request.json
    segments = data.get("segments", [])
    model = data.get("model", "gemini-3.5-flash")
    name = data.get("name")
    use_audio = data.get("use_audio", False)
    
    # No automatic shift propagation before AI correction
    pass
        
    audio_path = None
    if use_audio and name:
        base = name.replace(".jsonl", "").replace(".json", "")
        for f in os.listdir(AUDIO_DIR):
            if os.path.splitext(f)[0] == base:
                audio_path = os.path.join(AUDIO_DIR, f)
                break
    
    from ai.correct import run_ai_correction
    ok, result = run_ai_correction(segments, model, audio_path=audio_path)
    
    if not ok:
        print(f"\n❌ [AI Error] correction failed for file '{name or 'unknown'}': {result}\n")
        return jsonify({"ok": False, "error": result})
        
    return jsonify({"ok": True, "segments": result})

@app.route("/api/normalize_numbers", methods=["POST"])
def normalize_numbers():
    """Rəqəmləri Azərbaycan dilində söz formasına çevirir (tools/az_num2words.py)."""
    data = request.json or {}
    segments = data.get("segments", [])
    skip = set(data.get("skip", []))

    try:
        from tools.az_num2words import convert_segments
    except Exception as e:
        return jsonify({"ok": False, "error": f"Number converter unavailable: {e}"}), 500

    segments = [{k: v for k, v in s.items() if not k.startswith("_")} for s in segments]
    converted, changes = convert_segments(segments, skip)
    notes = []
    for change in changes:
        notes.extend(change.get("notes", []))
    return jsonify({
        "ok": True,
        "segments": converted,
        "changed": len(changes),
        "notes": notes[:40],
    })

@app.route("/api/ai/adjust_timestamps", methods=["POST"])
def adjust_timestamps():
    data = request.json
    segments = data.get("segments", [])
    name = data.get("name")
    
    if not name:
        return jsonify({"ok": False, "error": "Missing name"}), 400
        
    original_segments = get_original_segments(name)
    adjusted_segments = check_and_propagate_shifts(segments, original_segments)
    
    return jsonify({"ok": True, "segments": adjusted_segments})



if __name__ == "__main__":
    # Windows consoles default to cp1252 when the output is redirected to a file
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("\n✓ STT Annotator running → http://localhost:5000\n")
    print(f"  audio/       → {AUDIO_DIR}")
    print(f"  transcripts/ → {TRANSCRIPT_DIR}")
    print(f"  finished/    → {FINISHED_DIR}\n")
    app.run(debug=False, port=5000)