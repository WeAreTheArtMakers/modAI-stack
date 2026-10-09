# Sürüm notları

## v0.6.0 — modAI Voice ve çok dilli arama (yayın adayı)

Sürüm numarası ve etiket, sahip onayıyla birleştirme sırasında kesinleşir.

### Yeni
- **modAI Voice (`/voice`):** Türkçe sesli soru-cevap. Konuşma tanıma tarayıcıda yapılır; varsayılan Whisper Tiny, isteğe bağlı Whisper Base. Yanıt Türkçe nöral sesle (EMA Lightning) okunur. Görüşmeler kalıcıdır. Gecikmenin her aşaması ölçülür ve gösterilir.
- **Çok dilli arama (BGE-M3):** bir çalışma alanı doğrulanmış bir BGE-M3 indeks neslinden yanıt verebilir. `app.tools.retrieval_generation` ile plan, build, validate, activate ve rollback yapılır. Worker yeni yüklemeleri etkin nesle de yazar; geri alma, sürekli güncel tutulan MiniLM indeksine tek komutla yapılır.
- **Sayısal tablolar:** sorudaki birimli sayı tablodaki satırla eşleştirilir. Sözcükle söylenen sayılar ("üç yıl") rakam biçimiyle de aranır. Çözülemeyen tablo çelişkilerinde model çağrılmadan sabit açıklama döner.
- **Kaynaksız yanıt yok:** seçili bilgi kaynaklarından hiç belge gelmezse model çağrılmaz; "belge bulunamadı" denir.
- **Kurulum araçları:** `scripts/fetch_retrieval_models.py` (BGE-M3, SHA-256 kilitli), `scripts/preflight.py` (kurulum öncesi kontrol). Ayrıca [kurulum ve teslim rehberi](docs/guides/kurulum-ve-teslim-rehberi.md) ve [ürün özeti](docs/sales/modai-voice-urun-ozeti.md).

### Düzeltildi
- Oturum yenileme ve çıkış: nginx `Host` başlığında portu düşürüyordu ve API yenileme çerezini yanlış adla okuyordu. Bu yüzden oturumlar 30 dakikada düşüyordu.
- Tablo yanıtlarında belge adı, parçalanmış metinden değil, dizindeki dosya adından alınır.

### Değişen ayarlar
- Yeni ortam değişkenleri `RETRIEVAL_GENERATIONS_ENABLED` (varsayılan kapalı) ve `RETRIEVAL_MODEL_ROOT` (varsayılan `/models`). Açılmaları tek başına davranışı değiştirmez.
- Veritabanı migration'ı yok (Alembic head `0008_assistant_preferences`).

### Bilinen sınırlamalar
[Kurulum ve teslim rehberi](docs/guides/kurulum-ve-teslim-rehberi.md#7-müşteriye-söylenecek-sınırlamalar) ve [BGE-M3 rehberi](docs/guides/bge-m3-staging-generation.md#8-bilinen-sınırlar).
