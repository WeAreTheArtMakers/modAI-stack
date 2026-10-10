# Lisanslama ve üçüncü taraf bileşenler

Bu belge satış ve kurulum ekipleri için kısa bir özettir. Hukuki tavsiye değildir; ticari sözleşmeden önce hukuk danışmanınızın incelemesi önerilir.

## 1. Ürün lisansı

- **Lisans veren:** modAI-stack'i **WATAM — We Are The Art Makers** ([wearetheartmakers.com](https://wearetheartmakers.com)) lisanslar.
- **Lisans:** WATAM Source-Available License (`LICENSE`).
- **Kaynak kodun görünmesi kullanım hakkı vermez.** Üretimde ya da ticari kullanım için WATAM ile yazılı bir ticari lisans gerekir. Paketler (Pilot, Business, Enterprise) `COMMERCIAL_LICENSING.md` dosyasındadır.
- **Müşteriye verilen:** WATAM ticari lisansı ve kurulum.
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
| Whisper Tiny / Base (tarayıcıda konuşma tanıma) | Apache-2.0 | |
| EMA Lightning (Türkçe ses) | Apache-2.0 | LICENSE ve NOTICE dosyaları ürünle birlikte dağıtılır |
| Gemma 3 (yanıt üreten dil modeli) | Gemma Terms of Use | Ayrıntı 4. bölümde |

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

## 4. Gemma (dil modeli)

- Gemma modelleri Google'ın **Gemma Terms of Use** ve **Prohibited Use Policy** koşullarıyla kullanılır. Ticari kullanıma izin verir, ama belirli kullanım kısıtları vardır.
- **Önerilen yol:** model müşterinin makinesine kurulumda `ollama pull` ile, müşteri tarafından indirilir. WATAM model ağırlıklarını kendisi dağıtmaz.
- **Ağırlıklar paketle birlikte verilirse:** Gemma koşullarının pakete eklenmesi ve kullanım kısıtlarının müşteriye iletilmesi gerekir.
- Farklı bir dil modeli seçilirse, onun lisansı da aynı şekilde kontrol edilmelidir.

## 5. Satış öncesi kontrol listesi

- [ ] `THIRD_PARTY_NOTICES.md` sürüm için güncellendi: bağımlılık envanteri yeniden çıkarıldı (Python ve npm), lisans metinleri ve atıflar eklendi.
- [ ] Paket, EMA Lightning'in LICENSE ve NOTICE dosyalarını içeriyor (`frontend/public/third-party/`).
- [ ] Gemma modeli WATAM tarafından dağıtılmıyor; dağıtılıyorsa koşulları pakette.
- [ ] Tanıtım videolarında yalnızca ticari kullanıma uygun sesler kullanıldı: EMA Lightning ve Kokoro, ikisi de Apache-2.0. macOS sistem sesleri kullanılmadı.
- [ ] Müşteri sözleşmesi WATAM ticari lisans koşullarına atıf yapıyor.
