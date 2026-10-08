# modAI Voice — Ürün sunumu rehberi

Bu rehber, kurgusal **Atlasnova** bilgi paketiyle yaklaşık 8–10 dakikalık bir canlı sunum içindir. İçe aktarma adımları için `README.md`, tüm 36 soru ve beklenen yanıtlar için `questions.md`.

## Hazırlık (sunumdan önce)

1. Demo Workspace'inde "Atlasnova Demo" Knowledge Base'inin tüm belgeleri **Hazır** durumda olmalı.
2. `/voice` sayfasını bir kez açın ve **Modelleri hazırla**'ya basın. İlk açılıştan sonra modeller tarayıcı önbelleğinden gelir.
3. Yalnızca "Atlasnova Demo" Knowledge Base'ini seçin.
4. Hız için 1,05× ile başlayın. Salon büyükse 1,00× daha anlaşılırdır.
5. Gürültülü bir salonda **Göndermeden önce soruyu göster** seçeneğini açın: yanlış anlaşılan soruyu göndermeden düzeltirsiniz.
6. Masaüstü Chrome veya Edge kullanın. Uygulamayı `https://` ya da aynı cihazda `http://localhost` üzerinden açın, aksi hâlde mikrofon çalışmaz.

## Önerilen 10 soru

Bu sorular, üretimle aynı erişim ayarlarıyla (MiniLM gömme modeli, 700/100 parçalama, ilk 3 parça) yapılan çevrimdışı denemede beklenen belgeyi ilk 3 sonuç içinde buldu. Ayrıntılar aşağıdaki "Bilinen erişim sınırlamaları" bölümünde.

| Sıra | Soru | Gösterdiği şey | Beklenen kısa yanıt |
|---|---|---|---|
| 1 | Kıdemim 3 yıl, kaç gün yıllık iznim var? (S01) | Temel sesli soru-cevap ve kaynak kartı | 16 iş günü |
| 2 | Yemek kartına günlük ne kadar yükleniyor? (S04) | Sayıların doğal okunuşu | İş günü başına 320 TL |
| 3 | Dizüstü bilgisayarımı kaybettim, ne yapmalıyım? (S07) | Adım adım talimat | 1 saat içinde Bilgi Güvenliği'ne (dahili 4100), uzaktan silme |
| 4 | Seyahat masraflarını bildirmek için 30 günüm yok muydu? (D02) | Eski ve güncel sürümü ayırt etme | Hayır; 30 gün 2025 kuralıydı, güncel süre 15 gün |
| 5 | Müşterinin parola sıfırlama bağlantısı 48 saat geçerli, değil mi? (D03) | Yanlış varsayımı düzeltme | Hayır; güncel talimatta 24 saat |
| 6 | Yurt dışından uzaktan çalışma için kaç gün önce başvurmalıyım, bu süre yıllık izin başvurusundan farklı mı? (M04) | İki belgeden birleşik yanıt | 15 iş günü; izinde 3 veya 10 iş günü |
| 7 | 40.000 TL'lik bir satın almayı kim onaylar? (S09) | Onay matrisi | Departman direktörü ve Satın Alma |
| 8 | BT desteğinde P2 bir sorunun ilk yanıt süresi nedir? (S12) | Tablo içinden yanıt | 1 saat; çözüm 1 iş günü |
| 9 | Müşteri lisans sayısını artırmak istiyor; destek ekibi olarak bunu biz yapabilir miyiz? (D04) | Güncel talimatın eskisini geçersiz kılması | Hayır; Satış'a yönlendirilir |
| 10 | Şirketin 2027 maaş artış oranı ne kadar olacak? (N01) | Belgede olmayan bilgiyi uydurmama | Belgelerde bu bilgi yok |

## Bilinen erişim sınırlamaları (ölçülen)

Üretimdeki gömme modeli `sentence-transformers/all-MiniLM-L6-v2` ağırlıklı olarak İngilizce eğitilmiştir. Bu paketle yapılan çevrimdışı denemede (aynı model, aynı parçalama, ilk 3 parça; canlı sisteme dokunulmadan) sonuçlar:

| Soru grubu | Beklenen belgelerden en az biri ilk 3'te | Beklenen belgelerin tümü ilk 3'te |
|---|---|---|
| Basit (12) | 9/12 | 9/12 |
| Çok belgeli (8) | 5/8 | 1/8 |
| Zor (6) | 5/6 | 0/6 |
| Diller arası (4) | 0/4 | 0/4 |

- **İlk 3'te bulunamayanlar:** S02, S08, S10, M01, M05, M08, D01 ve C01–C04. Bu soruları canlı sunumda kullanmayın; asistan yanlış belgeden yanıt verebilir veya bilgi bulamadığını söyleyebilir.
- **Türkçe soru, İngilizce belge** (C01–C04) mevcut modelle çalışmıyor. Bu senaryo, daha önce onaylanmış çok dilli gömme modeli geçişini gerektirir; bu ayrı ve onay gerektiren bir adımdır.
- Bu ölçüm yalnızca erişimi kapsar. Yanıt metninin doğruluğu demo alanına yükledikten sonra ayrıca kontrol edilmelidir.

## Sunum akışı

1. **0:00 — Açılış.** "Bilginiz, altyapınız, sesli asistanınız." Belgelerin ve modelin kendi sunucunuzda kaldığını, sesin tarayıcıdan çıkmadığını söyleyin.
2. **1:00 — Soru 1–2.** Mikrofona basılı tutup sorun. Maskotun dinleme, arama, yanıtlama ve konuşma durumlarını gösterin, sonra sağdaki kaynak kartını açın.
3. **3:00 — Soru 3–5.** Eski sürüm tuzakları: asistan güncel belgeyi seçmeli. Kaynaklar panelinde eski belge görünürse bunun bilerek etiketlenmiş bir eski sürüm olduğunu açıklayın.
4. **5:00 — Soru 6–9.** Çok belgeli yanıtlar ve onay kuralları. Yanıt uzarken **Durdur** ile kesip yeni soru sorarak araya girme davranışını gösterin.
5. **7:00 — Soru 10.** Bilinmeyeni kabul etme.
6. **8:00 — Kapanış.** Konuşma hızı kontrolü, transkripti düzeltme ve yetki sınırları (yalnızca seçili ve yetkili Knowledge Base).

## Dürüst notlar

- Konuşma tanıma Whisper tiny ile tarayıcıda yapılır. Kısa ve net cümleler en iyi sonucu verir. Yanlış anlaşılan soruyu **Düzelt** ile düzeltip yeniden sorun.
- Yanıtın doğruluğu, seçilen yerel dil modeline ve erişilen belge parçalarına bağlıdır. Sunumdan önce bu 10 soruyu kendi kurulumunuzda bir kez deneyin.
- Belgeler kurgusaldır ve hukuki ya da mevzuat bilgisi içermez.
