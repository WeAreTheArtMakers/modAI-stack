# modAI-stack ile modAI Voice — ürün özeti

**Şirket belgelerinize Türkçe, sesli ya da yazılı soru sorun; yanıt kendi altyapınızda, kaynağıyla gelsin.**

## Kimin için

- İç politikaları, prosedürleri ve teknik belgeleri çok olan ekipler (İK, finans, BT destek, operasyon).
- Belgelerini bir bulut yapay zekâ servisine göndermek istemeyen kurumlar.
- Türkçe çalışan, ama belgelerinin bir kısmı İngilizce olan şirketler.

## Ne yapar

- **Kaynaklı yanıt:** soru, yetkili bilgi tabanlarındaki belgelerden yanıtlanır. Her yanıtla birlikte kullanılan belgeler gösterilir.
- **Sesli asistan (`/voice`):**
  - Soruyu söylersiniz; konuşma tanıma tarayıcıda yapılır ve ses kaydı tarayıcıdan çıkmaz.
  - Yanıt Türkçe nöral sesle okunur.
  - Görüşmeler saklanır ve sayfaya dönüldüğünde geri yüklenir.
- **Çok dilli arama:** Türkçe bir soru İngilizce belgede de doğru kaynağı bulur (BGE-M3 profili).
- **Sayısal tablolar:** "40.000 TL'lik alımı kim onaylar" gibi sorularda sayı, tablodaki doğru satırla eşleştirilir. Değer iki satırın sınırındaysa sistem tahmin etmez, bunu söyler.
- **Belge yoksa uydurmaz:** seçili kaynaklarda belge bulunamazsa model çağrılmaz; "belge bulunamadı" denir.
- **Kurumsal yapı:** Organization → Workspace → Knowledge Base hiyerarşisi, rol tabanlı erişim, davetle kullanıcı ekleme, denetim kaydı.

## Neden yerel

- Belge ve soru içeriği varsayılan olarak bir bulut LLM servisine gönderilmez. Dil modeli (Ollama), arama ve veritabanı müşterinin makinesinde çalışır.
- Ses modelleri uygulamanın kendi adresinden yüklenir; üçüncü taraf çıkarım servisi kullanılmaz.
- Bu bir güvenlik ya da uyumluluk sertifikası iddiası değildir. TLS, yedekleme ve erişim kuralları kurulumda müşteriyle birlikte belirlenir.

## Ölçülen sonuçlar

Ölçümler kurgusal demo belgeleriyle staging ortamında, Apple M1 Pro 16 GB üzerinde yapıldı.

| | Sonuç |
|---|---|
| 9 kabul sorusu × 2 koşu, çok dilli arama (BGE-M3) | 18/18 doğru yanıt; kendinden emin yanlış yanıt yok |
| Aynı sorular, varsayılan model (MiniLM) | 11/18 doğru; 3 kendinden emin yanlış yanıt (2'si yanlış sayı) |
| Model ılıkken ilk token (sunucu) | medyan 3,5–3,9 sn; makine bellek baskısındayken daha uzun |
| Kısa bir belgenin yüklendikten sonra aranabilir olması | yaklaşık 20 sn; bellek baskısında 2 dakikaya kadar |

Bu sonuçlar müşterinin kendi belgeleriyle aynı başarıyı garanti etmez. Pilotta müşterinin belgeleri ve soruları ile kabul testi yapılır.

## Gereksinimler

- macOS (Apple Silicon) ya da Linux; Docker ve Ollama.
- En az 16 GB bellek (bu durumda yalnızca bu sistem çalışmalı); 32 GB önerilir.
- 30 GB boş disk.
- Masaüstü Chrome ya da Edge; ağdan sesli kullanım için HTTPS.

## Pilot

[Ticari lisanslama](../../COMMERCIAL_LICENSING.md)'daki **Pilot** paketi 2–4 haftalık, seçili belgelerle sınırlı bir değerlendirmedir. Pilotta şunlar yapılır:

1. Kurulum ve ön kontrol (`scripts/preflight.py`).
2. Müşteri belgelerinin yüklenmesi ve çok dilli aramanın etkinleştirilmesi.
3. Müşteriyle birlikte hazırlanan 10 soruluk kabul testi; sonuçlar yazılı teslim edilir.
4. Kullanıcı eğitimi ([kurumsal kullanım kılavuzu](../guides/kurumsal-kullanim-kilavuzu.md)).

## Bilinen sınırlamalar

- Model zaman zaman yanlış satırı ya da belgeyi seçebilir; önemli kararlardan önce kaynak kontrol edilmelidir.
- Eski ve güncel politika birlikte yüklenirse sistem hangisinin geçerli olduğunu bilemez.
- PDF ya da birleşik hücreli tablolar ve hesaplama soruları desteklenmez.
- Ses tanıma gürültüde zayıflar; soru göndermeden önce ekranda gösterilir ve düzeltilebilir.
- Çok dilli arama tek kurulum, tek şirket için tasarlandı. Yönetimi komut satırından yapılır; yönetim arayüzü sonraki sürümdedir.
