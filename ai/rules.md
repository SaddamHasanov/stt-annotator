# Qaydalar (Rules)

## R1
**Faylın Yoxlanılması və Göndərilməsi**
Time stampləri və mətnləri diqqətlə yoxlayın, sonra hazır jsonl faylını "Finished" qovluğuna göndərin.

**Yanlış:** Yoxlanılmamış faylı birbaşa "Finished" qovluğuna göndərmək
**Doğru:** Bütün seqmentləri yoxladıqdan sonra faylı "Finished" qovluğuna göndərmək

## R2
**Məruzəçi Standartı**
Zəng iştirakçılarını yalnız iki formada qeyd edin: 'Operator' (Bank tərəfi) və ya 'Müştəri' (Xidmət alan). Digər daxili kodlar və ya adlar ləğv edilməlidir.

**Yanlış:** "Agent: Salam / Zəng edən: borcum var"
**Doğru:** "Operator: Salam / Müştəri: borcum var"

## R3
**Qrammatik Normalaşdırma**
Şifahi ləhcələr rəsmi yazıya çevrilir. Əgər 'gələjəm, sənnən, gəlirsiz' deyirsə, 'gələcəm, səninlə, gəlirsiniz' şəklində yazın.

**Yanlış:** "Müştəri: gələjəm, sənnən danışacam, gəlirsiz?"
**Doğru:** "Müştəri: gələcəm, səninlə danışacam, gəlirsiniz?"

## R4
**Rəqəmlər və Şəkilçilər**
Rəqəm ifadələrini ardıcıl formata, ərəb rəqəmlərinə çevirin (iyirmi üç -> 23, iyirmi ikinci -> 22-ci). Səslənən şəkilçiləri mütləq defislə əlavə edin: 22-ci, 3-də.

**Yanlış:** "iyirmi üç, iyirmi ikinci, üçdə"
**Doğru:** "23, 22-ci, 3-də"

## R5
**Əlavə Boşluqlar və Sətir Simvolları**
Əlavə boşluqları, tabları və əlavə yeni sətir simvollarını (newline) silin.

**Yanlış:** "Salam   ,\n  necəsiniz?\t"
**Doğru:** "Salam, necəsiniz?"

## R6
**Qeyri-Söz Fraqmentləri və Kəkələmələr**
Qeyri-söz fraqmentləri atılır. Kəkələmədə kəsik hissə real söz deyilsə yazılmır — yalnız tam söz qalır. Yalnız özünüdüzəltmədə hər iki hissə tam, mənalı söz olarsa saxlanılır.

**Yanlış:** "pro proqrama qoşul, m-m-mən gəldim"
**Doğru:** "Proqrama qoşul, Mən gəldim"

**Özünüdüzəltmə nümunəsi (hər iki söz tam və mənalıdır, saxlanılır):**
"Sabah, yox, birisigün"

## R7
**Tərəddüd Səsləri (Qapalı Siyahı)**
Tərəddüd səsləri yalnız bu qapalı siyahıdan etiketlə verilir: [ıı], [ee], [hmm], [aa]. Mətndə plain 'ııı', 'ee' kimi yazılmır. Variantları bunlara yığın (eee/əə -> [ee], mmm -> [hmm]). 'hə, yox, aha' real sözlərdir — etiket deyil.

**Yanlış:** "ııı mən eee karta baxım mmm"
**Doğru:** "[ıı] mən [ee] karta baxım [hmm]"

## R8
**Nitq Olmayan Hadisələr**
Nitq olmayan hadisələr yalnız bu etiketlərlə verilir: [gülüş], [öskürək], [musiqi], [siqnal]. Tək başına olanda ayrıca seqment (text: '[musiqi]'), nitqin içində qısa olanda yerində yerləşdirilir. Nəfəs, fon küyü və xışıltı yazılmır.

**Yanlış:** "(Nəfəs alır) [asqırıq] bəli (Xışıltı) doğrudur."
**Doğru:** "Bəli [gülüş] doğrudur."

## R9
**Böyük Hərflər və Durğu İşarələri**
Whisper durğu işarələrini və cümlə strukturunu yaxşı öyrənir. Buna görə xüsusi isimləri və cümlə başlanğıclarını böyük hərflə yazın. İntonasiyadan asılı olaraq suallar '?' ilə, cümlələr isə '.' ilə bitməlidir. Təsadüfi durğu işarələri (,, və ya ??!!) modelin NLP performansını aşağı salacaq.

**Yanlış:** "salam... borcum nə gədərdi xanım??!!"
**Doğru:** "Salam, borcum nə qədərdir xanım?"

## R10
**Anlaşılmayan və Çətin Sözlər**
Səs-küy, sətir fasilələri və ya diksiya səbəbindən tamamilə anlaşılmaz olan sözləri təxmin etməyə çalışmayın. Bunun əvəzinə həmin hissəni '[unclear]' adlandırın və ayrıca vaxt möhürü (time stamp) kimi qeyd edin. Əgər audio-nun böyük hissəsi bu cür isə, həmin hissəni dataset-dən tamamilə çıxarmaq daha yaxşıdır.

**Yanlış:** "Küy səbəbindən başa düşülməyən sözü təxmin etmək"

**Doğru:**
```json
{"start_time": "01:32", "end_time": "01:34", "speaker": "Müştəri", "text": "Bir dənə bax görüm."}
{"start_time": "01:34", "end_time": "01:35", "speaker": "Müştəri", "text": "[unclear]"}
{"start_time": "01:35", "end_time": "01:37", "speaker": "Müştəri", "text": "Mənim nə qədər kreditim qalıb?"}
```

## R11
**Eyni Anda Danışma (Qarşılıqlı Söhbət)**
Əgər iki nəfər eyni anda danışırsa (qarşılıqlı söhbət), hər iki nitqi ayrı-ayrı seqment kimi, eyni və ya üst-üstə düşən vaxt möhürləri ilə yazın.

**Doğru:**
```json
{"start_time": "01:34", "end_time": "01:36", "speaker": "Müştəri", "text": "Buna klikləyirəm"}
{"start_time": "01:34", "end_time": "01:36", "speaker": "Operator", "text": "Bəli, doğrudur"}
```

## R12
**Xarici Dillər və Alınma Sözlər**
Bütöv fraza rus və ya başqa dildədirsə, ayrı vaxt möhürü kimi verin və mətnə yalnız '[another_language]' yazın. Cümlə içində işlənən tək alınma söz (karoçe, vobşe) isə Azərbaycan əlifbası ilə yazılır və cümlədə saxlanılır.

**Yanlış:** "Müştəri: raboçi dindirildi da karoçe" (bütöv frazanın rus dilində olan hissəsi tərcümə/etiketlənmədən saxlanılıb)

**Doğru (tək alınma söz cümlədə qalır):**
"Müştəri: dindirildi da karoçe"

**Doğru (bütöv fraza başqa dildədirsə, ayrıca qeyd olunur):**
```json
{"start_time": "01:32", "end_time": "01:34", "speaker": "Müştəri", "text": "Bir dənə bax görüm."}
{"start_time": "01:34", "end_time": "01:35", "speaker": "Müştəri", "text": "[another_language]"}
{"start_time": "01:35", "end_time": "01:37", "speaker": "Müştəri", "text": "Mənim nə qədər kreditim qalıb?"}
```

## R13
**Maksimum Seqment Davamiyyəti**
Start və end time arasındakı vaxt intervalı maksimum 30 saniyə olmalıdır.

**Yanlış:** "start_time: 00:01, end_time: 00:45 (44 saniyə)"
**Doğru:** "start_time: 00:01, end_time: 00:30 (29 saniyə)"

## R14
**Fasilə Nöqtələri (...) — Vergül və ya Nöqtəyə Çevrilməsi**
Mətndə "..." (üç nöqtə) işlədilmir. Danışıqdakı qısa fasilə (eyni fikrin davamı, fikirləşmə) vergül `,` ilə əvəz olunur. Əgər fasilədən sonra yeni, ayrı bir cümlə başlayırsa, nöqtə `.` qoyulur və yeni cümlə böyük hərflə başlayır. Təsadüfi və ya çoxsaylı nöqtələr ("....", "..") heç bir halda saxlanılmır.

**Yanlış:** "Deyəsən.... kartım evdə qaldı"
**Doğru:** "Deyəsən, kartım evdə qaldı."

**Yanlış:** "Gözdə baxım..... Hə burdadı."
**Doğru (fasilə + davam edən fikir, vergüllə):** "Gözdə baxım, hə burdadı."
**Doğru (fasilə + ayrı cümlə, nöqtə ilə):** "Gözdə baxım. Hə burdadı."

> Qeyd: Hansı formanın seçiləcəyi intonasiyadan asılıdır — əgər səsdə aydın fasilə var və ikinci hissə müstəqil fikirdirsə nöqtə, əgər fikir bir nəfəsdə davam edirsə vergül istifadə olunur.