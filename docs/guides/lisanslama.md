# Lisanslama ve üçüncü taraf bileşenler

Bu belge satış ve kurulum ekipleri için kısa bir özettir. Hukuki tavsiye değildir; ticari sözleşmeden önce hukuk danışmanınızın incelemesi önerilir.

## 1. Ürün lisansı

- **Lisans veren:** modAI'yi **WATAM — We Are The Art Makers** ([wearetheartmakers.com](https://wearetheartmakers.com)) lisanslar.
- **Lisans:** modAI tescilli bir yazılımdır. Kullanım hakkı WATAM ile imzalanan ticari sözleşmeyle ve WATAM'ın imzaladığı **lisans anahtarıyla** verilir. Paketler (Pilot, Business, Enterprise) `COMMERCIAL_LICENSING.md` dosyasındadır.
- **Kaynak kodu dağıtılmaz.** Müşteriye çevrimdışı kurulum paketi (imajlar, modeller, betikler, rehberler) ve lisans anahtarı teslim edilir. Anahtar lisans sahibini, paketi, bitiş tarihini ve kullanıcı sayısını taşır; kurulum onu internete çıkmadan doğrular.
- **Müşteriye verilen:** WATAM ticari lisansı, lisans anahtarı ve kurulum.
- **Üçüncü taraf bileşenler:** veritabanı, arama, kuyruk ve modeller kendi lisanslarıyla gelir. WATAM lisansı bu bileşenlerin koşullarını değiştirmez, kısıtlamaz ve yeniden lisanslamaz.

## 2. Bileşenler ve neden seçildikleri

Hedef, müşterinin hukuk incelemesinde sorun çıkarmayan, izin verici (permissive) lisanslı bileşenlerdir.

| Bileşen | Lisans | Not |
|---|---|---|
| Valkey (kuyruk ve geçici veri) | BSD-3-Clause | Redis'in yerine; ayrıntı 3. bölümde |
| PostgreSQL | PostgreSQL License | İzin verici |
| Qdrant (vektör arama) | Apache-2.0 | İzin verici |
| Ollama (yerel model çalıştırıcı) | MIT | Müşteri makinesine kurulur |
| FastAPI, React, Vite ve diğer kütüphaneler | MIT / Apache-2.0 / BSD | Sürüm başına envanter çıkarılır (`THIRD_PARTY_NOTICES.md`) |
| BGE-M3 (çok dilli arama modeli) | MIT | `scripts/fetch_retrieval_models.py` ile, SHA-256 doğrulamalı indirilir |
| all-MiniLM-L6-v2 (varsayılan arama modeli) | Apache-2.0 | |
| Whisper Tiny / Base (sesli asistanda isteğe bağlı, tarayıcıda konuşma tanıma) | Apache-2.0 | |
| faster-whisper, CTranslate2 ve Whisper small / base ağırlıkları (Systran) | MIT | Ses ve video belgelerinin dökümü ve sesli asistanda sunucuda konuşma tanıma; ağırlıklar `scripts/fetch_transcription_models.py` ile SHA-256 doğrulamalı indirilir |
| PyAV | BSD-3-Clause | İçinde LGPL lisanslı FFmpeg kütüphaneleri vardır; değiştirilmeden, dinamik bağlı kullanılır |
| Tesseract OCR ve Türkçe / İngilizce veri dosyaları | Apache-2.0 | Debian paketleriyle API imajına kurulur |
| pypdfium2 (PDF sayfasını OCR için görüntüye çevirir) | Apache-2.0 / BSD-3-Clause | |
| EMA Lightning (Türkçe ses) | Apache-2.0 | LICENSE ve NOTICE dosyaları ürünle birlikte dağıtılır |
| Yanıt üreten dil modelleri (Gemma 3, Gemma 4, Qwen 3.5 ve WATAM uyarlamaları) | Gemma Terms of Use ya da Apache 2.0 | Ayrıntı 4. bölümde |

## 3. Neden Redis değil, Valkey?

- **Redis'in lisansı değişti.** Redis 7.4 ve sonrası BSD yerine RSALv2/SSPLv1 ile lisanslanır; Redis 8 bunlara AGPLv3 seçeneğini ekledi.
  - RSALv2, Redis'in yönetilen hizmet olarak sunulmasını kısıtlar.
  - SSPL, hizmet olarak sunulduğunda tüm hizmet yığınının kaynak kodunun açılmasını ister.
  - AGPL, ağ üzerinden kullanımda kaynak paylaşımı yükümlülüğü getirir.
  - Ürünümüz Redis'i bu şekilde sunmasa bile bu lisanslar kurumsal hukuk incelemelerinde sıkça "kırmızı bayrak" olur ve satışı yavaşlatır.
- **Redis 7.2'de kalmak da iyi bir çözüm değil.** 7.2 serisi BSD lisanslıdır, ama artık güncel sürüm hattı değil; uzun vadede güvenlik güncellemesi alması belirsizdir.
- **Valkey:**
  - Linux Foundation altında geliştirilen, BSD-3-Clause lisanslı bir Redis çatalıdır.
  - Aynı protokolü konuştuğu için uygulamada kod değişikliği gerekmez: istemci kütüphanesi, Lua betikleri ve TTL'ler aynen çalışır.
  - `redis-cli` gibi araç adları da uyumluluk için korunur.
- **Sürüm:** v0.6.1 ve sonrası `valkey/valkey:8.1-alpine` kullanır (8.1.10 doğrulandı). Docker servisinin adı uyumluluk için `redis` olarak kaldı.
- **Geçişte veri:** Valkey'de kalıcı veri yoktur; içinde oturum yenileme kayıtları, sayaçlar ve kuyruk bulunur. Geçişten sonra kullanıcıların bir kez yeniden giriş yapması gerekir. Kuyrukta bekleyen indeksleme işi olmamalıdır.

## 4. Dil modelleri

Yönetici kurulumdaki modeller arasından seçim yapabildiği için (**Modeller → Üretim modeli seçimi**), sözleşme yalnızca varsayılan modeli değil teslim edilen bütün modelleri kapsamalıdır. Sözleşme eki şablonu: [sözleşme model eki](../sales/sozlesme-model-eki.md).

| Aile | Örnek modeller | Lisans | Dağıtımda gereken |
|---|---|---|---|
| Gemma 1–3 | gemma3:4b, modAI:latest (WATAM uyarlaması) | Gemma Terms of Use | Koşulların kopyası, "Notice" dosyası, kullanım kısıtlarının sözleşmede bağlayıcı hüküm olması (3.1 ve 3.2. maddeler); uyarlamalarda değişiklik bildirimi |
| Gemma 4 | gemma4:12b-mlx, studiobrn/modAIJet (WATAM uyarlaması) | Apache 2.0 (Mart 2026'dan beri) | Lisans kopyası, varsa NOTICE içeriği, değişiklik bildirimi |
| Qwen 3 / 3.5 | qwen3.5:9b, qwen3.5:9b-mlx | Apache 2.0 | Lisans kopyası, varsa NOTICE içeriği |
| Llama 3.x | mOpenAI, watamRole | Llama Community License | Lisans kopyası, "Notice" dosyası, "Built with Llama" ibaresi, Acceptable Use Policy |

- **Uygulamada:** Modeller sayfası her modelin lisansını gösterir. Lisans, modelin taşıdığı metinden okunur; metin yoksa model ailesinden çıkarılır ve "model ailesinden" diye işaretlenir. Kullanım kısıtı olan lisanslar (Gemma Terms, Llama) ayrıca işaretlenir.
- **Paket:** `scripts/package_release.sh --model …` her model için lisans metnini `LICENSES/<model>-LICENSE.txt` olarak, Gemma ve Llama için gereken NOTICE dosyalarını da ayrıca yazar. Gemma bildirimi tam olarak şu cümledir: "Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms".
- **Sözleşme:** Gemma Terms of Use kapsamındaki bir model teslim ediliyorsa kullanım kısıtları sözleşmede bağlayıcı hüküm olmalıdır. Paket bunu yapamaz; [sözleşme model eki](../sales/sozlesme-model-eki.md) 3. madde.
- **Güvenlik varyantları:** "abliterated", "uncensored" gibi güvenlik eğitimi kaldırılmış modeller pakete alınmaz. Uygulama bunları işaretler ve ancak açık onayla seçtirir.
- **Modelsiz paket** (`--without-models`) ağırlık dağıtmaz; model kurulumda `ollama pull` ile müşteri tarafından indirilir.
- Bu tablo bir özettir, hukuki görüş değildir. Gemma 4'ün Apache 2.0'a geçişi Google'ın duyurusuna dayanır; teslimden önce modelin kendi lisans dosyası kontrol edilir.

## 5. Satış öncesi kontrol listesi

- [ ] `THIRD_PARTY_NOTICES.md` sürüm için güncellendi: bağımlılık envanteri yeniden çıkarıldı (Python ve npm), lisans metinleri ve atıflar eklendi.
- [ ] Paket, EMA Lightning'in LICENSE ve NOTICE dosyalarını içeriyor (`frontend/public/third-party/`).
- [ ] Paketteki her modelin lisansı `LICENSES/` altında; Gemma ve Llama NOTICE dosyaları pakette; [sözleşme model eki](../sales/sozlesme-model-eki.md) teslim edilen modellerle dolduruldu ve Gemma kullanım kısıtlarını (3.2. madde) içeriyor.
- [ ] Tanıtım videolarında yalnızca ticari kullanıma uygun sesler kullanıldı: EMA Lightning ve Kokoro, ikisi de Apache-2.0. macOS sistem sesleri kullanılmadı.
- [ ] Müşteri sözleşmesi WATAM ticari lisans koşullarına atıf yapıyor.
