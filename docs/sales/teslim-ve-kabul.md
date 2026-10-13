# modAI teslim ve kabul formu

Bu form, modAI kurulumunun müşteriye teslim edildiğini ve kabul testlerinin sonuçlarını kayda geçirir. Teslimde iki tarafça doldurulur. Ekleri: **Güven raporu (PDF)** ve Kalite sayfasının son çalıştırması. Adımların nasıl yapılacağı [kurulum ve teslim rehberindedir](../guides/kurulum-ve-teslim-rehberi.md).

| | |
|---|---|
| Müşteri | |
| Kurulum yeri (sunucu adı, adres) | |
| Sürüm (Sistem sayfası: "modAI …") | |
| Paket (`VERSION`: sürüm, `ARCH`) | |
| Paket | Pilot / Business / Enterprise |
| Teslim tarihi | |

## 1. Teslim edilenler

- [ ] Kurulum paketi, `python3 scripts/package_tools.py verify .` ile doğrulandı ("Package intact").
- [ ] Belgeler: kurulum ve teslim rehberi, kurumsal kullanım kılavuzu, KVKK veri envanteri, kapasite ve donanım, destek ve güncelleme politikası.
- [ ] Lisanslar: WATAM lisansı, ticari sözleşme, üçüncü taraf bildirimleri, **Gemma Terms of Use** ve Gemma NOTICE (paketin `LICENSES/` klasörü).
- [ ] [Sözleşme model eki](sozlesme-model-eki.md) teslim edilen modellerle dolduruldu ve imzalandı; Gemma kullanım kısıtları kullanıcılara bildirildi.
- [ ] İlk platform yöneticisi müşterinin kendi e-postasıyla açıldı. Parolayı yalnızca müşteri biliyor.
- [ ] Gece yedeği kuruldu (`sh scripts/schedule_maintenance.sh --status`). Yedeklerin ikinci bir diske kopyalanması müşteriyle planlandı.
- [ ] Ağdan kullanımda HTTPS açık (`https://…`), ya da kullanım yalnızca bu makinede.
- [ ] Şirket hesabıyla giriş (SSO): kullanılmıyor / kuruldu ve bir kullanıcıyla denendi (Denetim sayfasında `sso_login` kaydı).

## 2. Kabul testleri

| # | Test | Hedef | Sonuç |
|---|---|---|---|
| 1 | Kurulum (`sh scripts/install.sh`) | 8/8 adım, ön kontrolde FAIL yok | |
| 2 | Sağlık (`/ready`, Sistem sayfası) | Tüm servisler "Hazır" | |
| 3 | Kalite: müşteriyle hazırlanan sorular (en az 10) | Müşteriyle belirlenen eşik, örneğin 9/10 | ___ / ___ |
| 4 | Güvenlik testleri (aynı çalıştırma) | Sonuç müşteriye gösterildi | ___ / 9 |
| 5 | Yük testi, müşterinin makinesinde (`app.tools.load_test`, mesai dışında) | Aynı anda 4 soruda yanıtların %95'i ≤ 10 sn | ___ sn |
| 6 | Sesli asistan (`/voice`): 3 soru | Doğru yanıt, görüşme sayfaya dönüldüğünde geri geliyor | |
| 7 | Erişim: bir kullanıcı davet edildi, yalnızca kendi çalışma alanını görüyor | Evet | |
| 8 | Yedek: `sh scripts/backup_local.sh data/backups` | Yedek oluştu | |
| 9 | Destek paketi: `sh scripts/support_bundle.sh` | Dosya oluştu, içinde belge ya da parola yok | |
| 10 | Güven raporu: **Yönetim → Güven raporu → PDF olarak kaydet** | Bu forma eklendi | |

Geçmeyen testler ve kararlaştırılan çözümler:

|Test|Neden|Çözüm ve tarih|
|---|---|---|
| | | |

## 3. Ayarlar

| Ayar | Değer |
|---|---|
| Görüşmelerin saklama süresi (`CONVERSATION_RETENTION_DAYS`) | ___ gün (varsayılan 180) |
| Denetim IP'leri, yedekler, loglar | ___ gün (varsayılan 180) |
| Gece Kalite çalıştırması (`QUALITY_SCHEDULE_HOUR`) | kapalı / saat ___ |
| Yanıt üreten model | gemma3:4b / ___ (Kalite'den geçti) |
| Arama profili | Çok dilli (BGE-M3) — Türkçe kullanımda zorunlu |

## 4. Müşteriye söylenen sınırlamalar

- [ ] Yanıtlar belgelerden üretilir ama model yanılabilir; önemli kararlardan önce kaynak kontrol edilir.
- [ ] Eski politika sürümleri arşivlenmezse yanıtlar eski bilgiyi kullanabilir.
- [ ] Taranmış belge ve ses dökümü hatasız değildir.
- [ ] Otomatik devralma yoktur. Yedek ikinci bir diske kopyalanır (`BACKUP_MIRROR_DIR`). İstenirse ikinci bir makine sıcak beklemede tutulur (`standby_sync.sh`). Yedek doğrulama tatbikatı teslimde çalıştırılır ve sonucu tutanağa yazılır: `sh scripts/restore_drill.sh data/backups/<son yedek>`.
- [ ] Kapasite: bu donanımda yaklaşık ___ çalışana kadar (yük testi, satır 5). Sistem sayfasındaki Kapasite kartı "Büyütün" derse donanım büyütülür.

## 5. Onay

Teslim edilenler alındı, kabul testleri yukarıdaki sonuçlarla yapıldı.

| | WATAM | Müşteri |
|---|---|---|
| Ad, unvan | | |
| Tarih | | |
| İmza | | |
