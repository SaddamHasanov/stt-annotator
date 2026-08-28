# STT Annotator — quraşdırma təlimatı

Azərbaycan dilli zəng transkriptlərini yoxlamaq, düzəltmək və millisaniyə
dəqiqliyində vaxtlandırmaq üçün lokal veb alət. Hər şey öz kompüterinizdə işləyir.

---

## 1. Python quraşdırın (bir dəfəlik)

Python **3.11 və ya daha yeni** lazımdır: https://www.python.org/downloads/

> Quraşdırarkən **"Add Python to PATH"** qutusunu mütləq işarələyin.

Yoxlamaq üçün PowerShell-də: `python --version`

## 2. Proqramı işə salın

Arxivi çıxarın və qovluğun içindəki **`run.bat`** faylına iki dəfə klikləyin.

Skript ilk dəfə özü hər şeyi qurur: virtual mühit yaradır, Flask quraşdırır,
`.env` faylını hazırlayır və serveri başladır. Sonra brauzerdə açın:

```
http://localhost:5000
```

Dayandırmaq üçün pəncərədə `Ctrl+C`.

> PowerShell istifadə edirsinizsə: `.un.ps1`
> "execution policy" xətası verərsə: `powershell -ExecutionPolicy Bypass -File .un.ps1`

## 3. API açarlarınızı yazın

Qovluqda yaranan **`.env`** faylını Notepad ilə açın və öz açarlarınızı yazın.
**Açarlar arxivdə yoxdur — hər kəs özününkünü yazmalıdır.**

### Gemini (AI mətn düzəlişi üçün)

1. https://aistudio.google.com/apikey
2. **Create API key**
3. Açarı kopyalayın və `.env`-də yazın:
   ```
   GEMINI_API_KEY=sizin_acariniz
   ```

### ElevenLabs (millisaniyə vaxtlandırma üçün)

1. https://elevenlabs.io/app/settings/api-keys
2. **Create API key** — icazələrdə **Speech to Text** seçilməlidir
3. ⚠️ **`sk_` ilə başlayan dəyəri** kopyalayın, açarın ID-sini yox.
   Bu dəyər yalnız açar yaradılan anda bir dəfə göstərilir.
   Əldən vermisinizsə, açarı **Rotate** edin — yenisi görünəcək.
   ```
   ELEVENLABS_API_KEY=sk_...
   ```

`.env`-i yadda saxlayın. Gemini açarı dərhal işləyir; ElevenLabs açarı üçün
serveri yenidən başladın (pəncərəni bağlayıb `run.bat`-ı yenidən açın).

> ElevenLabs pulludur: saatı $0.22. Hər kanal ayrıca göndərildiyi üçün
> 5 dəqiqəlik bir zəng təxminən **4 sent** edir. Pulsuz plan ayda ~30 dəqiqə
> verir — yəni cəmi 2-3 fayl. İşləmək üçün ElevenAPI bölməsindən
> **"+ Add credits"** ilə kredit yükləmək lazımdır.

## 4. Fayllarınızı yerləşdirin

Ən sadə yol — arxivdəki hazır qovluqlardan istifadə etmək:

```
audio/         <- .wav fayllar
transcripts/   <- .jsonl fayllar
finished/      <- bitmişlər buraya yığılır (avtomatik)
working/       <- draftlar (avtomatik)
```

Audio və transkript **eyni adda** olmalıdır:
`202501091637.wav` ↔ `202501091637.jsonl`

Fayllarınız başqa qovluqdadırsa, `.env`-də yolları göstərin (nümunələr
`.env.example` faylında şərh şəklində var).

### Transkript formatı (JSONL — hər sətir bir seqment)

```json
{"start_time": "00:02.000", "end_time": "00:05.480", "speaker": "Operator", "text": "Alo, hər vaxtınız xeyir."}
{"start_time": "00:05.480", "end_time": "00:08.120", "speaker": "Müştəri", "text": "Salam."}
```

Köhnə `MM:SS` formatı da oxunur.

---

## Düymələr nə edir

| Düymə | İş |
| :--- | :--- |
| ✨ **AI Correct** | Yalnız mətni `ai/rules.md` qaydalarına görə düzəldir |
| ✨ **AI + Audio** | Audio-nu da dinləyir, vaxtları da yenidən qurur |
| 🕒 **Fix Overlaps** | Üst-üstə düşən vaxtları düzəldir |
| 🔢 **Rəqəm → söz** | `50` → `əlli` (lokal, pulsuz, API işlətmir) |
| 🎯 **Align (ms)** | ElevenLabs ilə millisaniyə dəqiqliyində vaxtlandırma |
| **Save Draft** | Yarımçıq işi saxlayır |
| **Save to Finished** | Hazır faylı `finished/` qovluğuna göndərir |

### Tövsiyə olunan ardıcıllıq

```
AI Correct  ->  Rəqəm → söz  ->  Align (ms)  ->  yoxla  ->  Save to Finished
```

**Sıra vacibdir.** `Align` mətni səslə tutuşdurur. Mətndə `86` yazılıbsa,
audio-da isə *"səksən altı"* səslənirsə, uyğunluq pozulur. Ona görə əvvəlcə
rəqəmləri sözə çevirin, sonra hizalayın.

`Align (ms)` bitəndə şübhəli seqmentləri özü sayır (məsələn `2 need checking`).
Onları brauzerin konsolunda (`F12`) görə bilərsiniz.

---

## Problemlər

**`python` tanınmır** — Python quraşdırılmayıb və ya PATH-ə əlavə edilməyib.
Yenidən quraşdırın, "Add Python to PATH" qutusunu işarələyin.

**Port 5000 məşğuldur** — başqa proqram həmin portu tutub. `app.py`-nin sonunda
`port=5000` dəyərini məsələn `5001` edin.

**"ELEVENLABS_API_KEY .env faylında təyin edilməyib"** — açar yazılmayıb və ya
server açar yazılandan sonra yenidən başladılmayıb.

**"API key ID used as API key"** — açarın ID-sini kopyalamısınız. `sk_` ilə
başlayan dəyər lazımdır (3-cü addıma baxın).

**Növbə boş görünür** — `transcripts/` qovluğunda `.jsonl` fayl yoxdur, ya da
`.env`-dəki yol səhvdir. Server başlayanda hansı qovluqlara baxdığını yazır.

**Audio səslənmir** — audio faylının adı transkript faylı ilə eyni deyil.
