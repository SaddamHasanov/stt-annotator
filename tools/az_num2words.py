"""
az_num2words — Azərbaycan dilində rəqəmləri sözə çevirən regex əsaslı normalizator.
======================================================================================

Transkriptlərdəki bütün rəqəmlə yazılmış ədədləri (və onlara yapışan şəkilçiləri)
söz formasına çevirir:

    "29-u"          → "iyirmi doqquzu"
    "1-ci"          → "birinci"
    "3000 AZN-dən"  → "üç min AZN-dən"
    "3000₼-dən"     → "üç min manatdan"
    "0.5%"          → "sıfır tam beş faiz"
    "20 000"        → "iyirmi min"
    "055 223 13 70" → "sıfır əlli beş iki yüz iyirmi üç on üç yetmiş"
    "27.07.1995"    → "iyirmi yeddi iyul min doqquz yüz doxsan beş"
    "1-10 aralığı"  → "bir-on aralığı"
    "11/26"         → "on bir iyirmi altı"
    "131,68-dir"    → "yüz otuz bir tam altmış səkkiz-dir"  (→ harmoniya ilə "…səkkizdir")

İstifadə (CLI)
--------------
    # Nə dəyişəcəyini göstər, heç nə yazma (default):
    python tools/az_num2words.py

    # transcripts/ → normalized/ qovluğuna yaz:
    python tools/az_num2words.py --apply

    # Faylların üzərinə yaz (.bak nüsxəsi saxlanılır):
    python tools/az_num2words.py --apply --in-place

    # Başqa qovluq / tək fayl:
    python tools/az_num2words.py --dir finished --apply
    python tools/az_num2words.py --file transcripts/2025.jsonl

    # Riskli çevrilmələri söndür:
    python tools/az_num2words.py --skip dates,times,fractions --apply

    # Öz-özünü yoxla:
    python tools/az_num2words.py --selftest

Modul kimi
----------
    from tools.az_num2words import convert_text
    new_text, changes = convert_text("29-u saat 14:00-da")
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# ── Əlifba / sait qrupları ────────────────────────────────────────────────────
AZ_LETTERS = "A-Za-zƏəÇçĞğIıİiÖöŞşÜüÑñ"
VOWELS = set("aıoueəiöü")
BACK = set("aıou")        # qalın saitlər
ROUNDED = set("ouöü")     # dodaqlanan saitlər

# ── Say cədvəlləri ────────────────────────────────────────────────────────────
ONES = ["", "bir", "iki", "üç", "dörd", "beş", "altı", "yeddi", "səkkiz", "doqquz"]
TENS = ["", "on", "iyirmi", "otuz", "qırx", "əlli", "altmış", "yetmiş", "səksən", "doxsan"]
SCALES = [(10 ** 12, "trilyon"), (10 ** 9, "milyard"), (10 ** 6, "milyon"), (1000, "min")]

MONTHS = ["", "yanvar", "fevral", "mart", "aprel", "may", "iyun",
          "iyul", "avqust", "sentyabr", "oktyabr", "noyabr", "dekabr"]

# Rəqəmə yapışan simvollar → söz
SYMBOLS = {"%": "faiz", "₼": "manat", "$": "dollar", "€": "avro", "₽": "rubl"}

# Onluq ayırıcı üçün istifadə olunan söz: "0,5" → "sıfır tam beş"
DECIMAL_WORD = "tam"

# Bu qədər və daha çox rəqəmi olan ədədlər rəqəm-rəqəm oxunur (kart/kod nömrələri)
DIGIT_BY_DIGIT_THRESHOLD = 7


# ── Sait harmoniyası ──────────────────────────────────────────────────────────
def last_vowel(word: str) -> str | None:
    """Sözün son saitini qaytarır."""
    for ch in reversed(word.lower()):
        if ch in VOWELS:
            return ch
    return None


def harmonize(suffix: str, stem: str) -> str:
    """
    `suffix`-in saitlərini `stem`-ə uyğunlaşdırır (irəliləyən sait harmoniyası).

    Şəkilçi transkriptdə rəqəmin oxunuşuna görə yazılıb, amma söz forması
    fərqli sait ilə bitə bilər ("10-dir" → "ondur"). Ona görə saitləri
    yenidən hesablayırıq, samitlərə toxunmuruq.
    """
    prev = last_vowel(stem)
    if prev is None:
        return suffix.lower()

    out = []
    for ch in suffix.lower():
        if ch in VOWELS:
            back = prev in BACK
            if ch in "aə":                                   # 2-li harmoniya
                new = "a" if back else "ə"
            elif ch in "ıiuü":                               # 4-lü harmoniya
                if prev in ROUNDED:
                    new = "u" if back else "ü"
                else:
                    new = "ı" if back else "i"
            else:                                            # o, ö, e — şəkilçidə olmur
                new = ch
            out.append(new)
            prev = new
        else:
            out.append(ch)

    result = "".join(out)
    # -lıq / -lik / -luq / -lük: son samit k/q növbələşməsi
    if re.fullmatch(r"l[ıiuü][kq]", result):
        result = result[:2] + ("q" if result[1] in BACK else "k")
    return result


def ordinal_of(word_form: str) -> str:
    """Say sözünü sıra sayına çevirir: "on iki" → "on ikinci"."""
    head, _, last = word_form.rpartition(" ")
    lv = last_vowel(last) or "i"
    if lv in ROUNDED:
        v = "u" if lv in BACK else "ü"
    else:
        v = "ı" if lv in BACK else "i"
    suffix = ("n" + "c" + v) if last[-1] in VOWELS else (v + "n" + "c" + v)
    return (head + " " if head else "") + last + suffix


# ── Ədəd → söz ────────────────────────────────────────────────────────────────
def _under_thousand(n: int) -> str:
    parts = []
    h, rest = divmod(n, 100)
    if h:
        parts.append("yüz" if h == 1 else ONES[h] + " yüz")
    t, o = divmod(rest, 10)
    if t:
        parts.append(TENS[t])
    if o:
        parts.append(ONES[o])
    return " ".join(parts)


def cardinal(n: int) -> str:
    """Tam ədədi Azərbaycan dilində say sözünə çevirir."""
    if n == 0:
        return "sıfır"
    if n < 0:
        return "mənfi " + cardinal(-n)

    parts = []
    for value, name in SCALES:
        if n >= value:
            count, n = divmod(n, value)
            # "1000" → "min" (not "bir min"); "1 000 000" → "bir milyon"
            if name == "min" and count == 1:
                parts.append("min")
            else:
                parts.append(cardinal(count) + " " + name)
    if n > 0:
        parts.append(_under_thousand(n))
    return " ".join(parts)


def digits_to_words(token: str) -> str:
    """
    Rəqəm sətrini sözə çevirir; baş sıfırları ("055", "01") ayrıca "sıfır" kimi oxuyur,
    çox uzun rəqəm silsilələrini isə rəqəm-rəqəm.
    """
    if not token:
        return ""
    if len(token) >= DIGIT_BY_DIGIT_THRESHOLD:
        return " ".join(cardinal(int(d)) for d in token)

    stripped = token.lstrip("0")
    lead = len(token) - len(stripped)
    if not stripped:                      # "0", "00", "000"
        return " ".join(["sıfır"] * len(token))
    words = cardinal(int(stripped))
    if lead:
        words = " ".join(["sıfır"] * lead) + " " + words
    return words


# ── Şəkilçi emalı ─────────────────────────────────────────────────────────────
ORDINAL_RE = re.compile(r"^(?:[ıiuü]?nc[ıiuü]|c[ıiuü])")

# Bufer samitlə başlayan şəkilçilər (samitlə bitən sözdən sonra bufer düşür):
# "10-na" → "ona", "3-yə" → "üçə". İstisnalar: -nan/-nən (ilə), -sız/-siz.
BUFFER_RE = re.compile(r"^[nsy][aəıiuü]")
BUFFER_KEEP_RE = re.compile(r"^(?:n[aə]n|s[ıiuü]z)")


def _fit_buffer(suffix: str, stem: str) -> str:
    """Bufer samitini sözün son hərfinə uyğunlaşdırır (əlavə edir və ya silir)."""
    if not suffix or not stem:
        return suffix
    stem_ends_with_vowel = stem[-1] in VOWELS

    if not stem_ends_with_vowel:
        if BUFFER_RE.match(suffix) and not BUFFER_KEEP_RE.match(suffix):
            return suffix[1:]
    elif suffix[0] in "aə":
        return "y" + suffix                      # "iyirmi" + "a" → "iyirmiya"
    return suffix


def _suffix_is_plausible(suffix: str) -> bool:
    """
    Yapışan hərf qrupunun həqiqətən şəkilçi olub-olmadığını qiymətləndirir.
    Azərbaycan şəkilçiləri qısadır, saitlə başlayır və ya bir samitdən sonra sait gəlir.
    """
    if not suffix or len(suffix) > 10:
        return False
    lowered = suffix.lower()
    vowel_count = sum(1 for ch in lowered if ch in VOWELS)
    if vowel_count == 0 or vowel_count >= 4:
        return False
    first_vowel = next((i for i, ch in enumerate(lowered) if ch in VOWELS), None)
    return first_vowel is not None and first_vowel <= 1


def attach_suffix(words: str, suffix: str) -> str | None:
    """
    Say sözünə şəkilçi əlavə edir; şəkilçini tanımasa `None` qaytarır.

    * sıra sayı şəkilçisi (-cı/-ci/-cu/-cü, -ıncı…) → tam sıra sayı forması
    * tanınan şəkilçi → sait harmoniyası ilə birbaşa yapışdırılır
    """
    if not suffix:
        return words

    lowered = suffix.lower()

    m = ORDINAL_RE.match(lowered)
    if m:
        base = ordinal_of(words)
        rest = lowered[m.end():]
        if rest:
            base += harmonize(rest, base)
        return base

    if _suffix_is_plausible(lowered):
        return words + harmonize(_fit_buffer(lowered, words), words)

    return None


_SENTENCE_END_RE = re.compile(r'(?:[.!?…]["»)\]]?\s+|\n\s*)$')


def _at_sentence_start(text: str, pos: int) -> bool:
    """Uyğunluğun cümlə başında olub-olmadığını yoxlayır."""
    head = text[:pos]
    return not head.strip() or bool(_SENTENCE_END_RE.search(head))


def az_upper(ch: str) -> str:
    """Azərbaycan əlifbasına uyğun böyük hərf: 'i' → 'İ' (Python default-u 'I' verir)."""
    return "İ" if ch == "i" else ch.upper()


def _cap(replacement: str, m, enabled: bool = True) -> str:
    """Cümlə başındakı rəqəm sözə çevriləndə baş hərfi böyüdür (R9)."""
    if (enabled and replacement and replacement[0].islower()
            and _at_sentence_start(m.string, m.start())):
        return az_upper(replacement[0]) + replacement[1:]
    return replacement


def _render(number_words: str, symbol: str, suffix: str,
            original: str, notes: list[str]) -> str:
    """
    Say + simvol + şəkilçi birləşməsini yekun mətnə çevirir.
    Şəkilçi tanınmasa orijinal parça toxunulmadan qaytarılır.
    """
    stem = number_words
    if symbol:
        stem = stem + " " + SYMBOLS.get(symbol, symbol)
    result = attach_suffix(stem, suffix)
    if result is None:
        notes.append(f"tanınmayan forma '{original}' toxunulmadan saxlanıldı")
        return original
    return result


# ── Regexlər ──────────────────────────────────────────────────────────────────
_S = r"([%₼$€₽]?)"                       # rəqəmə yapışan simvol
_H = r"(-?)"                             # defis
_F = rf"([{AZ_LETTERS}]*)"               # yapışan hərflər (şəkilçi)

RE_DATE = re.compile(r"(?<![\d.])(\d{1,2})\.(\d{1,2})\.(\d{2,4})(?![\d])")
RE_TIME = re.compile(rf"(?<![\d:])(\d{{1,2}}):(\d{{2}})(?::(\d{{2}}))?{_H}{_F}(?![\d:])")
RE_THOUSAND_SPACE = re.compile(r"(?<![\d.,])(\d{1,3}(?: \d{3})*) 000(?![\d.,])")
RE_PLUS = re.compile(r"(?<![\w])\+(\d{1,4})(?![\d])")
RE_RANGE = re.compile(rf"(?<![\d.,\-])(\d+) ?- ?(\d+){_S}{_H}{_F}(?![\d])")
RE_SLASH = re.compile(r"(?<![\d.,/])(\d{1,4})/(\d{1,4})(?![\d/])")
RE_DECIMAL = re.compile(rf"(?<![\d.,])(\d+)([.,])(\d+){_S}{_H}{_F}(?![\d])")
RE_PLAIN = re.compile(rf"(?<![\d.,])(\d+){_S}{_H}{_F}")

# Hərf+rəqəm qarışığı olan kodlar (FİN, kart kodu, "3D Secure", "25MB") — toxunmuruq.
RE_CODE = re.compile(r"\b(?=[A-Za-z0-9]*\d)(?=[A-Za-z0-9]*[A-Z])[A-Za-z0-9]{2,}\b")

PASS_NAMES = ("codes", "thousands", "dates", "times", "plus", "ranges", "fractions",
              "decimals", "plain")

# Kənara qoyulmuş kodlar üçün yer tutucular: Unicode "private use" sahəsi —
# nə rəqəm, nə hərf sayılır, ona görə heç bir regex onlara toxunmur.
_PLACEHOLDER_ORIGIN = 0xE000
_PLACEHOLDER_RE = re.compile("[-]")


def _unstash(text, vault):
    if not vault:
        return text
    return _PLACEHOLDER_RE.sub(
        lambda m: vault[ord(m.group(0)) - _PLACEHOLDER_ORIGIN], text)


def convert_text(text: str, skip: set[str] | None = None,
                 capitalize: bool = True) -> tuple[str, list[str]]:
    """
    Mətndəki bütün rəqəmləri söz formasına çevirir.

    Qaytarır: (yeni_mətn, qeydlər) — qeydlər diqqət tələb edən çevrilmələrdir.
    """
    if not text or not any(ch.isdigit() for ch in text):
        return text, []

    skip = skip or set()
    notes: list[str] = []

    def _cap2(replacement, m):
        return _cap(replacement, m, capitalize)

    # 0) Hərf+rəqəm kodlarını ("2L4SBRX", "3D", "014D") kənara qoyuruq
    vault: list[str] = []
    if "codes" not in skip:
        def _stash(m):
            vault.append(m.group(0))
            notes.append(f"kod '{m.group(0)}' toxunulmadan saxlanıldı")
            return chr(_PLACEHOLDER_ORIGIN + len(vault) - 1)
        text = RE_CODE.sub(_stash, text)
        if not any(ch.isdigit() for ch in text):
            return _unstash(text, vault), notes

    # 1) "20 000" kimi boşluqla ayrılmış minlikləri birləşdiririk ("20000")
    if "thousands" not in skip:
        def _merge(m):
            notes.append(f"minlik ayırıcı: '{m.group(0).strip()}'")
            return m.group(0).replace(" ", "")
        text = RE_THOUSAND_SPACE.sub(_merge, text)

    # 2) Tarixlər: 27.07.1995 / 15.08.74
    if "dates" not in skip:
        def _date(m):
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if not (1 <= d <= 31 and 1 <= mo <= 12):
                return m.group(0)
            if len(m.group(3)) == 2:
                y = 2000 + y if y < 30 else 1900 + y
            notes.append(f"tarix: '{m.group(0)}'")
            return _cap2(f"{cardinal(d)} {MONTHS[mo]} {cardinal(y)}", m)
        text = RE_DATE.sub(_date, text)

    # 3) Saatlar: 14:00 / 01:29-da
    if "times" not in skip:
        def _time(m):
            hh, mm, ss, _hyphen, suffix = m.groups()
            words = cardinal(int(hh))
            if int(mm):
                words += " " + digits_to_words(mm)
            if ss and int(ss):
                words += " " + digits_to_words(ss)
            out = _render(words, "", suffix, m.group(0), notes)
            if out != m.group(0):
                notes.append(f"saat: '{m.group(0)}'")
            return _cap2(out, m)
        text = RE_TIME.sub(_time, text)

    # 4) "+994" kimi ölkə kodları
    if "plus" not in skip:
        def _plus(m):
            notes.append(f"ölkə kodu: '{m.group(0)}' (+ işarəsi silindi)")
            return _cap2(digits_to_words(m.group(1)), m)
        text = RE_PLUS.sub(_plus, text)

    # 5) Aralıqlar: 1-10, 3-4, 18-24 faiz, 1-10-u
    if "ranges" not in skip:
        def _range(m):
            a, b, symbol, _hyphen, suffix = m.groups()
            words = digits_to_words(a) + "-" + digits_to_words(b)
            return _cap2(_render(words, symbol, suffix, m.group(0), notes), m)
        text = RE_RANGE.sub(_range, text)

    # 6) Kəsrlər / 24/7 / 11/26
    if "fractions" not in skip:
        def _slash(m):
            notes.append(f"kəsr: '{m.group(0)}'")
            return _cap2(f"{digits_to_words(m.group(1))} {digits_to_words(m.group(2))}", m)
        text = RE_SLASH.sub(_slash, text)

    # 7) Onluq kəsrlər: 0.5% / 131,68-dir
    if "decimals" not in skip:
        def _decimal(m):
            whole, sep, frac, symbol, _hyphen, suffix = m.groups()
            words = f"{digits_to_words(whole)} {DECIMAL_WORD} {digits_to_words(frac)}"
            out = _render(words, symbol, suffix, m.group(0), notes)
            if sep == "." and out != m.group(0):
                # nöqtə ilə yazılan onluqlar tarix/kart müddəti də ola bilər
                notes.append(f"nöqtəli onluq: '{m.group(0)}' → '{out}'")
            return _cap2(out, m)
        text = RE_DECIMAL.sub(_decimal, text)

    # 8) Adi ədədlər (+ simvol / şəkilçi)
    if "plain" not in skip:
        def _plain(m):
            number, symbol, _hyphen, suffix = m.groups()
            out = _render(digits_to_words(number), symbol, suffix, m.group(0), notes)
            if out != m.group(0) and len(number) >= DIGIT_BY_DIGIT_THRESHOLD:
                notes.append(f"uzun rəqəm silsiləsi rəqəm-rəqəm oxundu: '{number}'")
            return _cap2(out, m)
        text = RE_PLAIN.sub(_plain, text)

    # Çevrilmə nəticəsində yaranan ikiqat boşluqları təmizləyirik
    text = re.sub(r"[ 	]{2,}", " ", text)
    return _unstash(text, vault), notes


# ── JSONL fayl emalı ──────────────────────────────────────────────────────────
def convert_segments(segments: list[dict], skip: set[str] | None = None,
                     capitalize: bool = True) -> tuple[list[dict], list[dict]]:
    """Seqment siyahısındakı `text` sahələrini çevirir. (yeni_seqmentlər, dəyişikliklər)"""
    out, changes = [], []
    for i, seg in enumerate(segments):
        new_seg = dict(seg)
        original = seg.get("text", "") or ""
        converted, notes = convert_text(original, skip, capitalize)
        if converted != original:
            new_seg["text"] = converted
            changes.append({"index": i, "before": original, "after": converted, "notes": notes})
        out.append(new_seg)
    return out, changes


def _read_jsonl(path: str) -> list[dict]:
    segments = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                segments.append(json.loads(line))
    return segments


def _write_jsonl(path: str, segments: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(json.dumps(s, ensure_ascii=False) for s in segments))


# ── Öz-özünü yoxlama ──────────────────────────────────────────────────────────
SELFTESTS = [
    ("1", "bir"),
    ("0", "sıfır"),
    ("10", "on"),
    ("21", "iyirmi bir"),
    ("100", "yüz"),
    ("190", "yüz doxsan"),
    ("326", "üç yüz iyirmi altı"),
    ("1000", "min"),
    ("2004", "iki min dörd"),
    ("2500", "iki min beş yüz"),
    ("10000", "on min"),
    ("20 000", "iyirmi min"),
    ("50000-lik", "əlli minlik"),
    # şəkilçilər
    ("1-i", "biri"),
    ("3-ü", "üçü"),
    ("4-ü", "dördü"),
    ("6-sı", "altısı"),
    ("10-u", "onu"),
    ("29-u", "iyirmi doqquzu"),
    ("10-dan", "ondan"),
    ("1-dən", "birdən"),
    ("3-də", "üçdə"),
    ("2-yə", "ikiyə"),
    ("6-sından", "altısından"),
    ("10-na", "ona"),
    ("1cə", "bircə"),
    # şəkilçi harmoniyasının düzəlişi
    ("10-dir", "ondur"),
    ("100-dir", "yüzdür"),
    # sıra sayları
    ("1-ci", "birinci"),
    ("2-ci", "ikinci"),
    ("3-cü", "üçüncü"),
    ("12-ci", "on ikinci"),
    ("13-cü", "on üçüncü"),
    ("4-cü", "dördüncü"),
    ("9-cu", "doqquzuncu"),
    ("40-cı", "qırxıncı"),
    ("100-cü", "yüzüncü"),
    ("13-cüdən", "on üçüncüdən"),
    # simvollar
    ("24%", "iyirmi dörd faiz"),
    ("0.5%", "sıfır tam beş faiz"),
    ("3000₼-dən", "üç min manatdan"),
    ("3000 AZN-dən", "üç min AZN-dən"),
    # aralıq / kəsr / onluq
    ("1-10", "bir-on"),
    ("1-10-u", "bir-onu"),
    ("3-4", "üç-dörd"),
    ("24/7", "iyirmi dörd yeddi"),
    ("131,68-dir", "yüz otuz bir tam altmış səkkizdir"),
    # baş sıfırlar / telefon
    ("055", "sıfır əlli beş"),
    ("01 qəpik", "sıfır bir qəpik"),
    # tarix / saat
    ("27.07.1995", "iyirmi yeddi iyul min doqquz yüz doxsan beş"),
    ("15:00-da", "on beşdə"),
    ("01:29-da", "bir iyirmi doqquzda"),
    # tanınmayan formalar toxunulmadan qalır
    ("2x", "2x"),
    ("5Z", "5Z"),
    ("2L4SBRX", "2L4SBRX"),
    ("014D", "014D"),
    ("3D Secure", "3D Secure"),
    ("Vəsiqənin FİN-i, 2L4SBRX.", "Vəsiqənin FİN-i, 2L4SBRX."),
    ("25MB", "25MB"),
    # cümlə içində
    ("Mənə 6 rəqəmli kod istəyir.", "Mənə altı rəqəmli kod istəyir."),
    ("ya 29-u idi, ya 28-i idi", "ya iyirmi doqquzu idi, ya iyirmi səkkizi idi"),
    ("3000 AZN-ə qədər komissiyasızdır.", "üç min AZN-ə qədər komissiyasızdır."),
    ("734 manat 01 qəpik", "yeddi yüz otuz dörd manat sıfır bir qəpik"),
]

# Cümlə başındakı rəqəm sözə çevriləndə baş hərf böyüyür (R9); "i" → "İ".
SELFTESTS_CAPITALIZE = [
    ("100 ədəd deyirsiz.", "Yüz ədəd deyirsiz."),
    ("2000 manat. Bəli.", "İki min manat. Bəli."),
    ("Minimal 100 ədəd.", "Minimal yüz ədəd."),
    ("Bəli. 20 manat idi.", "Bəli. İyirmi manat idi."),
    ("Oldu, 3 gün sonra.", "Oldu, üç gün sonra."),
]


def run_selftest() -> int:
    failed = 0
    cases = ([(src, exp, False) for src, exp in SELFTESTS]
             + [(src, exp, True) for src, exp in SELFTESTS_CAPITALIZE])
    for src, expected, capitalize in cases:
        got, _ = convert_text(src, capitalize=capitalize)
        if got != expected:
            failed += 1
            print(f"  FAIL  {src!r}\n         gözlənilən: {expected!r}\n"
                  f"         alınan:     {got!r}")
    print(f"\n{len(cases) - failed}/{len(cases)} test keçdi.")
    return 1 if failed else 0


# ── CLI ───────────────────────────────────────────────────────────────────────
def main(argv=None) -> int:
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    p = argparse.ArgumentParser(
        description="Transkriptlərdəki rəqəmləri Azərbaycan dilində söz formasına çevirir.")
    p.add_argument("--dir", default="transcripts",
                   help="emal olunacaq qovluq (default: transcripts)")
    p.add_argument("--file", action="append", default=[],
                   help="yalnız bu fayl(lar)ı emal et (təkrarlana bilər)")
    p.add_argument("--out", default="normalized",
                   help="nəticələrin yazılacağı qovluq (default: normalized)")
    p.add_argument("--apply", action="store_true",
                   help="dəyişiklikləri fayla yaz (default: yalnız göstər)")
    p.add_argument("--in-place", action="store_true",
                   help="faylların üzərinə yaz (.bak nüsxəsi saxlanılır)")
    p.add_argument("--skip", default="",
                   help=f"söndürüləcək çevrilmələr, vergüllə: {','.join(PASS_NAMES)}")
    p.add_argument("--report", default="",
                   help="dəyişikliklərin tam siyahısını bu fayla yaz")
    p.add_argument("--quiet", action="store_true", help="nümunələri göstərmə")
    p.add_argument("--selftest", action="store_true", help="daxili testləri işlət")
    args = p.parse_args(argv)

    if args.selftest:
        return run_selftest()

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    unknown = skip - set(PASS_NAMES)
    if unknown:
        p.error(f"naməlum --skip dəyəri: {', '.join(sorted(unknown))}")

    if args.file:
        paths = [f if os.path.isabs(f) else os.path.join(base, f) for f in args.file]
    else:
        src_dir = args.dir if os.path.isabs(args.dir) else os.path.join(base, args.dir)
        if not os.path.isdir(src_dir):
            print(f"✕ Qovluq tapılmadı: {src_dir}")
            return 1
        paths = sorted(
            os.path.join(src_dir, f) for f in os.listdir(src_dir)
            if f.lower().endswith((".jsonl", ".json")) and not f.startswith(".")
        )

    if not paths:
        print("Emal ediləcək fayl yoxdur.")
        return 0

    out_dir = args.out if os.path.isabs(args.out) else os.path.join(base, args.out)
    if args.apply and not args.in_place:
        os.makedirs(out_dir, exist_ok=True)

    report_lines: list[str] = []
    total_files = total_changes = touched_files = 0

    for path in paths:
        try:
            segments = _read_jsonl(path)
        except Exception as e:
            print(f"✕ {os.path.basename(path)}: oxunmadı ({e})")
            continue

        total_files += 1
        new_segments, changes = convert_segments(segments, skip)
        if not changes:
            continue

        touched_files += 1
        total_changes += len(changes)
        name = os.path.basename(path)

        report_lines.append(f"\n=== {name}  ({len(changes)} seqment) ===")
        for c in changes:
            report_lines.append(f"  [{c['index']}] - {c['before']}")
            report_lines.append(f"       + {c['after']}")
            for n in c["notes"]:
                report_lines.append(f"       ! {n}")

        if not args.quiet:
            print(f"\n=== {name}  ({len(changes)} seqment dəyişir) ===")
            for c in changes[:3]:
                print(f"  - {c['before']}")
                print(f"  + {c['after']}")
            if len(changes) > 3:
                print(f"  … və daha {len(changes) - 3} seqment")

        if args.apply:
            if args.in_place:
                backup = path + ".bak"
                if not os.path.exists(backup):
                    with open(path, "r", encoding="utf-8") as src, \
                         open(backup, "w", encoding="utf-8") as dst:
                        dst.write(src.read())
                _write_jsonl(path, new_segments)
            else:
                _write_jsonl(os.path.join(out_dir, name), new_segments)

    print(f"\n{'─' * 60}")
    print(f"Fayl: {total_files} baxıldı, {touched_files} dəyişir — {total_changes} seqment.")
    if args.apply:
        where = "yerində (.bak nüsxəsi ilə)" if args.in_place else out_dir
        print(f"Yazıldı → {where}")
    else:
        print("DRY-RUN: heç nə yazılmadı. Yazmaq üçün --apply əlavə edin.")

    if args.report and report_lines:
        report_path = args.report if os.path.isabs(args.report) else os.path.join(base, args.report)
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(report_lines))
        print(f"Hesabat → {report_path}")

    return 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
