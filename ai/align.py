"""
ElevenLabs Forced Alignment — millisaniyə dəqiqliyi ilə timestamp.

Verint yazıları 8 kHz G.711 mu-law STEREO-dur və iki kanal iki danışanı ayrı-ayrı
saxlayır. Ona görə yenidən transkripsiya etmək (və əl ilə edilmiş düzəlişləri itirmək)
əvəzinə hər kanal öz mətni ilə ayrıca hizalanır. Bu, Forced Alignment API-nin
diarizasiya dəstəkləməməsi problemini də həll edir.
"""

import os
import re
import json
import struct
import hashlib
import urllib.request
import urllib.error

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FA_URL = "https://api.elevenlabs.io/v1/forced-alignment"
CACHE_DIR = os.path.join(BASE, ".align_cache")

# etiketlər danışılan söz deyil — hizalayıcıya göndərilmir
TAG_RE = re.compile(r"\[[^\]]*\]")


# ── mu-law / WAV (audioop Python 3.13-də silinir, ona görə öz dekoder) ──────

def _ulaw_table():
    """G.711 mu-law -> signed 16-bit PCM (Sun reference implementation)."""
    table = []
    for i in range(256):
        u = ~i & 0xFF
        t = ((u & 0x0F) << 3) + 0x84
        t <<= (u & 0x70) >> 4
        table.append(0x84 - t if (u & 0x80) else t - 0x84)
    return table

ULAW = _ulaw_table()


def read_wav(path):
    """(fmt_tag, channels, sample_rate, bits, payload) qaytarır."""
    with open(path, "rb") as f:
        data = f.read()
    i = data.find(b"fmt ")
    if i < 0:
        raise ValueError("RIFF/WAVE deyil: %s" % path)
    tag, ch, rate, byterate, align, bits = struct.unpack_from("<HHIIHH", data, i + 8)
    j = data.find(b"data", i)
    size = struct.unpack_from("<I", data, j + 4)[0]
    payload = data[j + 8: j + 8 + size] if size else data[j + 8:]
    return tag, ch, rate, bits, payload


def _pcm16_wav(samples, rate):
    raw = struct.pack("<%dh" % len(samples), *samples)
    hdr = (b"RIFF" + struct.pack("<I", 36 + len(raw)) + b"WAVEfmt "
           + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
           + b"data" + struct.pack("<I", len(raw)))
    return hdr + raw


def split_channels(path):
    """Stereo yazını iki mono 16-bit PCM WAV-a ayırır.

    (wav0, wav1, sample_rate, [samples0, samples1]) qaytarır.
    Mono girişdə wav1 = None olur.
    """
    tag, ch, rate, bits, payload = read_wav(path)

    if tag == 7:                                     # mu-law, 1 bayt/sample
        if ch == 1:
            s0 = [ULAW[b] for b in payload]
            return _pcm16_wav(s0, rate), None, rate, [s0]
        s0 = [ULAW[b] for b in payload[0::2]]
        s1 = [ULAW[b] for b in payload[1::2]]
    elif tag == 1 and bits == 16:                    # linear PCM
        n = len(payload) // 2
        allsamples = struct.unpack("<%dh" % n, payload[:n * 2])
        if ch == 1:
            return _pcm16_wav(list(allsamples), rate), None, rate, [list(allsamples)]
        s0 = list(allsamples[0::2])
        s1 = list(allsamples[1::2])
    else:
        raise ValueError("dəstəklənməyən WAV kodlaşması: tag=%s, %s-bit" % (tag, bits))

    return _pcm16_wav(s0, rate), _pcm16_wav(s1, rate), rate, [s0, s1]


# ── hansı kanal hansı danışana aiddir ──────────────────────────────────────

def _energy(samples, rate, ranges):
    total, count = 0.0, 0
    n = len(samples)
    for a, b in ranges:
        i, j = max(0, int(a * rate)), min(n, int(b * rate))
        step = max(1, (j - i) // 4000)               # yalnız nisbət testi, subsample kifayətdir
        for k in range(i, j, step):
            v = samples[k]
            total += v * v
            count += 1
    return (total / count) if count else 0.0


def detect_channel_map(segments, chans, rate, to_seconds):
    """Mövcud təxmini timestamp-lara görə Operator kanalını tapır."""
    if len(chans) < 2:
        return None

    ranges = {"Operator": [], "Müştəri": []}
    for s in segments:
        spk = "Operator" if "operator" in str(s.get("speaker", "")).lower() else "Müştəri"
        a, b = to_seconds(s.get("start_time")), to_seconds(s.get("end_time"))
        if b > a:
            ranges[spk].append((a, b))
    if not ranges["Operator"] or not ranges["Müştəri"]:
        return None

    def ratio(samples):
        op = _energy(samples, rate, ranges["Operator"])
        mu = _energy(samples, rate, ranges["Müştəri"])
        return op / mu if mu else float("inf")

    r0, r1 = ratio(chans[0]), ratio(chans[1])
    if r0 >= r1:
        return {"Operator": 0, "Müştəri": 1, "confidence": r0 / r1 if r1 else float("inf")}
    return {"Operator": 1, "Müştəri": 0, "confidence": r1 / r0 if r0 else float("inf")}


# ── ElevenLabs çağırışı ────────────────────────────────────────────────────

def _multipart(fields, files):
    boundary = "----sttannotator7f3a9b2c"
    out = b""
    for k, v in fields.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                % (boundary, k, v)).encode("utf-8")
    for k, (fname, content, ctype) in files.items():
        out += ("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                "Content-Type: %s\r\n\r\n" % (boundary, k, fname, ctype)).encode("utf-8")
        out += content + b"\r\n"
    out += ("--%s--\r\n" % boundary).encode("utf-8")
    return out, "multipart/form-data; boundary=%s" % boundary


def _cache_path(wav_bytes, text):
    h = hashlib.sha1()
    h.update(str(len(wav_bytes)).encode())
    h.update(wav_bytes[:4096])
    h.update(wav_bytes[-4096:])
    h.update(text.encode("utf-8"))
    return os.path.join(CACHE_DIR, h.hexdigest() + ".json")


def forced_align(wav_bytes, text, api_key, timeout=600, use_cache=True):
    """Audio + mətn göndərir, hizalama JSON-unu qaytarır.

    Cavablar diskə keşlənir: hər çağırış kreditlə ödənilir, ona görə eyni faylı
    təkrar emal etmək ikinci dəfə pul yeməməlidir.
    """
    cp = _cache_path(wav_bytes, text)
    if use_cache and os.path.exists(cp):
        with open(cp, encoding="utf-8") as f:
            return json.load(f)

    body, ctype = _multipart({"text": text},
                             {"file": ("audio.wav", wav_bytes, "audio/wav")})
    req = urllib.request.Request(FA_URL, data=body, method="POST",
                                 headers={"xi-api-key": api_key, "Content-Type": ctype})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            res = json.loads(r.read().decode("utf-8"))
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(cp, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False)
        except OSError:
            pass
        return res
    except urllib.error.HTTPError as e:
        raise RuntimeError("ElevenLabs %s: %s"
                           % (e.code, e.read().decode("utf-8", "replace")[:600]))


# ── nəticələri seqmentlərə xəritələmək ─────────────────────────────────────

def _clean(text):
    """Yalnız danışılan sözlər — etiketlər marker-dir, nitq deyil."""
    return TAG_RE.sub(" ", text or "").strip()


def _assign(tokens_per_seg, fa_words):
    """FA sözlərini seqment-seqment paylayır; [(start, end) | None] qaytarır."""
    total = sum(tokens_per_seg)
    out, i = [], 0
    if total and len(fa_words) != total:
        scale = len(fa_words) / float(total)
        cum = 0
        for c in tokens_per_seg:
            if c == 0:
                out.append(None); continue
            a = min(len(fa_words) - 1, int(round(cum * scale)))
            b = max(a, min(len(fa_words) - 1, int(round((cum + c) * scale)) - 1))
            out.append((fa_words[a]["start"], fa_words[b]["end"]))
            cum += c
        return out

    for c in tokens_per_seg:
        if c == 0:
            out.append(None); continue
        a, b = i, i + c - 1
        if b >= len(fa_words):
            out.append(None); continue
        out.append((fa_words[a]["start"], fa_words[b]["end"]))
        i += c
    return out


def align_segments(segments, audio_path, api_key, to_seconds, to_time_str, log=print):
    """Seqmentləri audio ilə millisaniyə dəqiqliyində yenidən vaxtlandırır.

    (segments, report) qaytarır. Mətn HEÇ VAXT dəyişmir — yalnız start_time/end_time.
    """
    report = {"channels": 1, "calls": 0, "aligned": 0, "interpolated": 0,
              "kept": 0, "loss": {}, "warnings": [], "suspect": []}

    w0, w1, rate, chans = split_channels(audio_path)
    report["channels"] = len(chans)

    chmap = detect_channel_map(segments, chans, rate, to_seconds) if len(chans) > 1 else None
    if chmap:
        log("  kanallar: Operator=ch%d, Müştəri=ch%d (əminlik %.1fx)"
            % (chmap["Operator"], chmap["Müştəri"], chmap["confidence"]))
        groups = {"Operator": [], "Müştəri": []}
        wavs = {"Operator": (w0, w1)[chmap["Operator"]], "Müştəri": (w0, w1)[chmap["Müştəri"]]}
    else:
        log("  mono / kanallar ayırd edilmədi — bütün qarışıq bir dəfəyə hizalanır")
        report["warnings"].append("Danışanlar kanala görə ayrılmadı; dəqiqlik aşağıdır.")
        groups = {"ALL": []}
        wavs = {"ALL": w0}

    for idx, s in enumerate(segments):
        key = "ALL"
        if chmap:
            key = "Operator" if "operator" in str(s.get("speaker", "")).lower() else "Müştəri"
        groups[key].append(idx)

    new_times = [None] * len(segments)
    for key, idxs in groups.items():
        if not idxs:
            continue
        counts, parts = [], []
        for i in idxs:
            words = _clean(segments[i].get("text", "")).split()
            counts.append(len(words))
            if words:
                parts.append(" ".join(words))
        text = " ".join(parts).strip()
        if not text:
            continue

        res = forced_align(wavs[key], text, api_key)
        report["calls"] += 1
        report["loss"][key] = res.get("loss")

        # API boşluqları da ayrıca element kimi qaytarır (n söz -> 2n-1 element),
        # ona görə boş olanlar atılır
        fa_words = [w for w in (res.get("words") or []) if (w.get("text") or "").strip()]
        log("  %-9s %d söz göndərildi, %d hizalandı, loss=%s"
            % (key + ":", sum(counts), len(fa_words), res.get("loss")))
        if len(fa_words) != sum(counts):
            report["warnings"].append(
                "%s: %d söz göndərildi, %d qayıtdı — vaxtlar interpolyasiya edildi."
                % (key, sum(counts), len(fa_words)))

        for i, span in zip(idxs, _assign(counts, fa_words)):
            new_times[i] = span

    # yalnız etiketdən ibarət seqmentlərdə söz yoxdur: qonşular arasındakı boşluğu tutur
    for i, span in enumerate(new_times):
        if span is not None:
            continue
        prev_end = next((new_times[j][1] for j in range(i - 1, -1, -1) if new_times[j]), None)
        next_start = next((new_times[j][0] for j in range(i + 1, len(new_times)) if new_times[j]), None)
        if prev_end is not None and next_start is not None and next_start > prev_end:
            new_times[i] = (prev_end, next_start)
            report["interpolated"] += 1

    out = []
    for s, span in zip(segments, new_times):
        seg = dict(s)
        if span:
            seg["start_time"] = to_time_str(span[0])
            seg["end_time"] = to_time_str(span[1])
            report["aligned"] += 1
        else:
            # hizalanacaq söz yoxdur: köhnə vaxt saxlanılır, amma format eyniləşdirilir
            seg["start_time"] = to_time_str(to_seconds(s.get("start_time")))
            seg["end_time"] = to_time_str(to_seconds(s.get("end_time")))
            report["kept"] += 1
        out.append(seg)
    report["aligned"] -= report["interpolated"]

    # QC: açıq-aşkar səhv hizalamaları işarələ ki, 150 fayl boyu gözdən qaçmasın
    prev_start = None
    for i, seg in enumerate(out):
        a, b = to_seconds(seg["start_time"]), to_seconds(seg["end_time"])
        why = []
        if b - a < 0.05:
            why.append("sıfır uzunluq")
        if b < a:
            why.append("end < start")
        if prev_start is not None and a < prev_start - 0.001:
            why.append("ardıcıllıq pozulub")
        if b - a > 30:
            why.append("30s-dən uzun")
        if why:
            report["suspect"].append({
                "index": i,
                "time": "%s-%s" % (seg["start_time"], seg["end_time"]),
                "text": (seg.get("text") or "")[:40],
                "why": ", ".join(why),
            })
        prev_start = a
    if report["suspect"]:
        log("  %d seqment əl ilə yoxlanmalıdır:" % len(report["suspect"]))
        for s in report["suspect"]:
            log("    #%d %s  %s  (%s)" % (s["index"], s["time"], s["text"], s["why"]))

    return out, report
