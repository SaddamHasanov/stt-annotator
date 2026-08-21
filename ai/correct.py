import os
import json
import urllib.request
import urllib.error
import re
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_env():
    env_path = os.path.join(BASE, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

def get_audio_mime_type(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".wav":
        return "audio/wav"
    elif ext == ".mp3":
        return "audio/mp3"
    elif ext in [".ogg", ".oga"]:
        return "audio/ogg"
    elif ext == ".aac":
        return "audio/aac"
    elif ext == ".flac":
        return "audio/flac"
    elif ext == ".webm":
        return "audio/webm"
    return "audio/wav"

def call_gemini(system_instruction, user_content, audio_path=None, model="gemini-3.5-flash"):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return {"error": "GEMINI_API_KEY not found in environment or .env file"}
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    
    parts = []
    if audio_path and os.path.exists(audio_path):
        try:
            import base64
            with open(audio_path, "rb") as f:
                audio_data = base64.b64encode(f.read()).decode("utf-8")
            mime = get_audio_mime_type(audio_path)
            parts.append({
                "inlineData": {
                    "mimeType": mime,
                    "data": audio_data
                }
            })
            print(f"[AI Info] Multimodal mode enabled. Sending audio file: {audio_path}")
        except Exception as e:
            print(f"[AI Warning] Failed to load audio file for Gemini: {str(e)}")
            
    parts.append({"text": user_content})
    
    payload = {
        "systemInstruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": [
            {"parts": parts}
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=req_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as response:
                res_data = json.loads(response.read().decode("utf-8"))
                
                if not res_data.get("candidates"):
                    return {"error": f"No candidates returned by Gemini: {json.dumps(res_data)}"}
                
                candidate = res_data["candidates"][0]
                if "content" not in candidate:
                    finish_reason = candidate.get("finishReason", "UNKNOWN")
                    return {"error": f"Gemini generation blocked. Reason/Status: {finish_reason}. Response: {json.dumps(res_data)}"}
                
                try:
                    text_out = candidate["content"]["parts"][0]["text"].strip()
                except (KeyError, IndexError):
                    return {"error": f"Invalid content structure in candidate response: {json.dumps(res_data)}"}
                
                # Semantic JSON parsing
                try:
                    parsed_data = json.loads(text_out)
                    return {"success": True, "data": parsed_data}
                except json.JSONDecodeError:
                    cleaned_text = text_out
                    if cleaned_text.startswith("```"):
                        lines = cleaned_text.splitlines()
                        if len(lines) > 2:
                            if lines[-1].strip() == "```":
                                cleaned_text = "\n".join(lines[1:-1])
                            else:
                                cleaned_text = "\n".join(lines[1:])
                        cleaned_text = cleaned_text.strip()
                    
                    try:
                        parsed_data = json.loads(cleaned_text)
                        return {"success": True, "data": parsed_data}
                    except json.JSONDecodeError:
                        # Fallback: extract JSON array or object using regex
                        match = re.search(r'(\[[\s\S]*\]|\{[\s\S]*\})', text_out)
                        if match:
                            try:
                                parsed_data = json.loads(match.group(1))
                                return {"success": True, "data": parsed_data}
                            except json.JSONDecodeError:
                                pass
                        return {"error": f"Failed to parse Gemini response as JSON. Raw response content: {text_out}"}
        except urllib.error.HTTPError as e:
            # Retry transient rate limits (429) or server errors (503/504)
            if e.code in [429, 503, 504] and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            
            try:
                err_msg = e.read().decode("utf-8")
                # Parse error response to check for resource exhaustion
                try:
                    err_json = json.loads(err_msg)
                    msg_detail = err_json.get("error", {}).get("message", "")
                    status_str = err_json.get("error", {}).get("status", "")
                    if "prepayment" in msg_detail.lower() or "credits" in msg_detail.lower():
                        return {
                            "error": f"Prepayment Credits Depleted (429). Your Google AI Studio PRO account has depleted its prepaid balance. Please go to AI Studio billing settings to add credits, or switch back to a Free Tier API Key in your .env.\n\nDetails: {msg_detail}"
                        }
                    elif status_str == "RESOURCE_EXHAUSTED" or "Quota exceeded" in msg_detail:
                        return {
                            "error": f"Quota Exceeded / Model Restricted (429). If using a Free Tier API Key, please switch the model dropdown to a Flash model (like 'Gemini 3.5 Flash' or 'Gemini 2.5 Flash') instead of 'Pro'.\n\nDetails: {msg_detail}"
                        }
                except Exception:
                    pass
            except Exception:
                err_msg = str(e)
            return {"error": f"API error: {e.code} - {err_msg}"}
        except Exception as e:
            if attempt < 2:
                time.sleep(1)
                continue
            return {"error": f"Connection error: {str(e)}"}

def run_ai_correction(segments, model="gemini-3.5-flash", audio_path=None):
    load_env()
    
    rules_path = os.path.join(BASE, "ai", "rules.md")
    rules_content = ""
    if os.path.exists(rules_path):
        with open(rules_path, encoding="utf-8") as f:
            rules_content = f.read()
            
    if audio_path and os.path.exists(audio_path):
        # Multimodal Audio Mode: AI listens to audio, writes audio-accurate timestamps, and normalizes text per rules
        system_instruction = f"""You are an expert Azerbaijani speech-to-text audio aligner and transcriber.
You are provided with:
1. The raw audio recording.
2. A draft transcript text of the conversation.

YOUR CORE TASKS:
1. LISTEN TO THE AUDIO: Listen to the audio recording from beginning to end.
2. AUDIO-ACCURATE TIMESTAMPS: For every spoken dialogue segment, determine its EXACT start_time and end_time (format MM:SS, e.g. "00:15", "03:42") based on when the words are actually spoken in the audio.
   - Do NOT retain arbitrary or dummy input timestamps. Every timestamp MUST correspond precisely to the real audio playback timing.
   - Wrap timestamps tightly around the actual spoken speech. Exclude long silent pauses or hold music.
   - Mark hold music or waiting periods as dedicated segments with text "[musiqi]" and their exact timestamps.
3. AZERBAIJANI TRANSCRIPTION RULES:
   Apply all transcription rules below to standardize, correct spelling/numbers, and filter hesitations:
{rules_content}
4. SPEAKERS: Use strictly "Operator" or "Müştəri".
5. SEGMENT LENGTH (Rule R13): Maximum segment duration is 30 seconds. Split any dialogue exceeding 30 seconds into sequential segments (each <= 30s).

OUTPUT FORMAT:
Return ONLY a valid JSON array of segment objects:
[
  {{"start_time": "MM:SS", "end_time": "MM:SS", "speaker": "Operator|Müştəri", "text": "..."}}
]
No explanations, no markdown wrapping, just the JSON array.
"""
        draft_dialogue = []
        for s in segments:
            draft_dialogue.append({
                "speaker": s.get("speaker", "Operator"),
                "text": s.get("text", "")
            })
        user_content = "Draft transcript to align and correct against the provided audio file:\n" + json.dumps(draft_dialogue, ensure_ascii=False)
    else:
        # Text-Only Mode: strictly apply rules without changing timestamps
        system_instruction = f"""You are an expert Azerbaijani speech-to-text transcript corrector.
Your task is to apply the transcription rules below to a JSON array of transcript segments.

Rules:
{rules_content}

CRITICAL INSTRUCTIONS (Strictness & Minimal Changes):
1. Do NOT edit a segment unless it CLEARLY and UNAMBIGUOUSLY violates one of the numbered rules above. When in doubt, leave it unchanged.
2. Do NOT perform stylistic editing, paraphrasing, rewording, or "improving" grammatically correct or standard Azerbaijani speech.
3. Do NOT add, remove, or change punctuation/capitalization/words unless a specific rule explicitly requires it for that exact case.
4. By default, do NOT change start_time or end_time, and do NOT add, merge, or omit segments — preserve the original segment structure and chronological ordering.
5. The ONLY exceptions for changing structure:
   - A segment duration > 30 seconds: split into consecutive segments <= 30s.
   - Splitting out "[unclear]" or "[another_language]".
   - Entirely unintelligible segment: may be omitted if no usable content.

OUTPUT FORMAT:
Return ONLY a valid JSON array containing the corrected segments:
[
  {{"start_time": "MM:SS", "end_time": "MM:SS", "speaker": "Operator|Müştəri", "text": "..."}}
]
No explanations, no markdown, no extra text.
"""
        user_content = json.dumps(segments, ensure_ascii=False)
        
    res = call_gemini(system_instruction, user_content, audio_path if (audio_path and os.path.exists(audio_path)) else None, model)
    
    if "error" in res:
        print(f"\n[AI Error] Gemini call failed for model '{model}':")
        print(f"Details: {res['error']}\n")
        return False, res["error"]
        
    return True, res["data"]
