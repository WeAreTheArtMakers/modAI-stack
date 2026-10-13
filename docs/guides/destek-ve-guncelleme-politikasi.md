# modAI destek ve güncelleme politikası

Bu belge, müşterinin kendi sunucusuna kurulan modAI için WATAM'ın destek ve güncelleme taahhütlerini ve müşterinin sorumluluklarını anlatır. Süreler ve kanallar **önerilen varsayılanlardır**; sözleşmede başka değerler yazılmışsa sözleşme geçerlidir. İletişim: destek **info@wearetheartmakers.com**, **+90 505 314 9360**; güvenlik bildirimleri **admin@wearetheartmakers.com**.

## 1. İlke: veri müşteride kalır

- modAI müşterinin sunucusunda çalışır. WATAM'ın müşteri belgelerine, sorulara ve yanıtlara **varsayılan olarak erişimi yoktur**; uzaktan bağlantı kurulmaz ve kullanım verisi toplanmaz.
- Destek, müşterinin gönderdiği **destek paketi** ile verilir (`sh scripts/support_bundle.sh`, 6. bölüm). Paket parola, belirteç, belge içeriği, soru ve yanıt metni içermez; IP ve e-posta adresleri maskelenir.
- Uzaktan erişim gerekirse yalnızca müşterinin yazılı izniyle, süreli, müşterinin gözetiminde (ekran paylaşımı) ve kayıt altına alınarak yapılır. Bu durumda WATAM KVKK açısından veri işleyen olur; erişimden önce veri işleme sözleşmesi imzalanır.

## 2. Destek paketleri

Paketler [ticari lisanslama](../../COMMERCIAL_LICENSING.md) belgesindeki Pilot, Business ve Enterprise paketleridir; fiyatlar orada.

| | Pilot | Business | Enterprise |
|---|---|---|---|
| Süre | Pilot süresi (2–4 hafta) | Yıllık | Yıllık |
| Kanal | E-posta, haftalık görüşme | E-posta, telefon | E-posta, telefon, adanmış iletişim kişisi |
| Destek saatleri | İş günleri 09:00–18:00 | İş günleri 09:00–18:00 | İş günleri 08:00–20:00 |
| Kurulum ve ilk yapılandırma | Dahil (yerinde ya da uzaktan, müşteri gözetiminde) | Dahil | Dahil |
| Güncellemeler | Dahil | Dahil | Dahil, bakım penceresi birlikte planlanır |
| Kalite ve güven raporu değerlendirmesi | Pilot başında ve sonunda | Üç ayda bir | Ayda bir |

İletişim: info@wearetheartmakers.com, +90 505 314 9360.

## 3. Öncelikler ve yanıt süreleri

| Öncelik | Tanım | İlk yanıt (Pilot / Business / Enterprise) | Hedef çözüm ya da geçici çözüm |
|---|---|---|---|
| **P1 Kritik** | Sistem kimse için çalışmıyor, veri kaybı ya da güvenlik açığı riski | 4 / 4 / 2 iş saati | 1 iş günü |
| **P2 Yüksek** | Önemli bir işlev çalışmıyor (yükleme, yanıt, ses, giriş), geçici yol yok | 1 iş günü / 1 iş günü / 4 iş saati | 3 iş günü |
| **P3 Normal** | Küçük hata ya da geçici yolu olan sorun, kullanım sorusu | 2 iş günü / 2 iş günü / 1 iş günü | Sonraki sürüm |
| **P4 Öneri** | Yeni özellik isteği | 5 iş günü | Yol haritasında değerlendirilir |

Süreler destek saatleri içinde, destek paketi ya da eşdeğer bilgiyle açılan talepler için geçerlidir.

## 4. Kapsam

**Kapsam içi:** modAI yazılımındaki hataların giderilmesi; kurulum, güncelleme ve geri alma desteği; yapılandırma soruları (`.env`, HTTPS, SSO, saklama süreleri); Kalite ve güvenlik testi sonuçlarının yorumlanması; üretim modeli sınamasında rehberlik.

**Kapsam dışı:** sunucu donanımı, işletim sistemi, ağ, güvenlik duvarı ve sertifika altyapısı; müşterinin belgelerinin içeriği ve doğruluğu; yerel dil modelinin her yanıtının doğruluğu (yanıtlar belgelerden üretilir ama model yanılabilir); müşteriye özel geliştirme (ayrıca tekliflendirilir).

## 5. Sürümler ve güncellemeler

- **Sürüm numarası:** ANA.ARA.YAMA (örneğin 1.5.0).
  - **Yama** (1.5.1): hata ve güvenlik düzeltmesi; gerektiğinde, güvenlik açıklarında birkaç gün içinde.
  - **Ara** (1.6.0): yeni özellikler; en fazla ayda bir.
  - **Ana** (2.0.0): uyumluluğu bozan değişiklik; en fazla yılda bir, geçiş rehberiyle.
- **Desteklenen sürümler:** son iki ara sürüm (örneğin 1.5 ve 1.4). Bir sürüm, yerine geçen sürüm yayımlandıktan **6 ay** sonra destek dışı kalır; güvenlik yamaları yalnızca desteklenen sürümlere verilir.
- **Nasıl güncellenir:**
  - **Kurulum paketi (varsayılan teslim):** WATAM her sürümü imajları, modelleri ve sağlama özetleriyle tek bir çevrimdışı paket olarak verir (`scripts/package_release.sh`). Müşteri yeni paketi kurulum klasörünün üzerine kopyalar ve `sh scripts/upgrade_local.sh` çalıştırır. İnternet gerekmez. Betik paketi doğrular, önce yedek alır, çalışan imajları geri alma için etiketler ve yeni imajları eski sürüm çalışırken yükler. Kesinti yalnızca yeniden başlatma süresidir; üretimde 64 saniye ölçüldü.
  - **Kaynaktan kurulum** (WATAM'ın kendi sunucuları): `git pull` ve `sh scripts/upgrade_local.sh data/backups`; imajlar yerinde derlenir.
- **Geri alma:** her güncelleme `sh scripts/rollback_local.sh --yes` ile tek komutla geri alınır; veritabanı değişiklikleri de geri çevrilir.
- **Ne değişti:** her sürümün notları `CHANGELOG.md` dosyasında ve GitHub sürüm sayfasındadır: yeni özellikler, düzeltmeler, veritabanı değişikliği (migration) ve yeni ayarlar.
- **Model güncellemeleri:** yanıt üreten model müşterinin onayıyla ve **Modeller → Sına** ile Kalite ve güvenlik testlerinden geçtikten sonra değiştirilir. Arama modelinin değişmesi yeniden indeksleme gerektirdiği için ayrıca planlanır. Aynı adlı bir model de (örneğin `gemma3:4b`) kayıt defterinde sessizce yenilenebilir; `ollama pull` kurulu modelin yerine yenisini koyar. Bu yüzden kurulum betiği kurulu bir modeli yeniden indirmez; bir modelin yenisi de aynı sınamadan geçer.

## 6. Destek paketi

```bash
sh scripts/support_bundle.sh
```

`data/support/modai-destek-<tarih>.tar.gz` oluşturur. İçinde: sürüm ve veritabanı revizyonu, servislerin durumu, disk ve bellek, ön kontrol (`preflight`) çıktısı, yüklü modellerin adları ve son 24 saatin hata ve uyarı satırları. **İçinde olmayanlar:** `.env`, parolalar, belirteçler, belgeler, soru ve yanıt metinleri; loglardaki IP ve e-posta adresleri maskelenir. Göndermeden önce dosyayı açıp inceleyebilirsiniz.

## 7. Kendiliğinden çalışan bakım ("kur ve unut")

Kurulumdan sonra müdahale gerektirmeden çalışanlar:

- **Gece yedeği:** `sh scripts/schedule_maintenance.sh` her gece 03:15'te yedek alır (Linux'ta cron, macOS'ta launchd); 180 günden eski yedekler silinir. Kurulum betiği bunu kurar (`--no-schedule` ile atlanır).
- **Disk uyarısı:** boş disk %15'in ya da 15 GB'ın altına inince yöneticiler konsolda uyarı görür; 5 GB'ın altında yeni yükleme kabul edilmez (veri bütünlüğü için).
- **Saklama süreleri:** görüşmeler, IP adresleri, yanıt izi ve yanıtlanamayan sorular süreleri dolunca her gün kendiliğinden silinir; loglar boyutla sınırlıdır.
- **Yeniden başlama:** servisler çökerse ya da sunucu yeniden başlarsa kendiliğinden ayağa kalkar (`restart: unless-stopped`; Docker sistem açılışında başlamalı).
- **Kalite:** `QUALITY_SCHEDULE_HOUR` ayarlıysa Kalite ve güvenlik testleri her gece çalışır; sonuç Güven raporunda görünür.

## 8. Müşterinin sorumlulukları

- Sunucunun, işletim sisteminin ve Docker'ın güncel ve çalışır tutulması; Docker'ın sistem açılışında başlaması.
- Yedeklerin ikinci bir yere (başka disk ya da sunucu) kopyalanması.
- En az %20 boş disk alanı.
- `.env` dosyasının ve yedeklerin erişiminin sınırlandırılması.
- Kullanıcı hesaplarının ve yetkilerin yönetimi; işten ayrılanların hesaplarının kapatılması (SSO kullanılıyorsa şirket hesabının kapatılması yeterlidir).
- Belgelerin güncelliği: eski sürümlerin arşivlenmesi, gözden geçirme tarihlerinin izlenmesi.

## 9. Yedekleme ve kurtarma hedefleri

- **Veri kaybı hedefi (RPO):** en fazla 24 saat (gece yedeği).
- **Yeniden çalışır hale getirme hedefi (RTO):** güncellemeden dönmek için 15 dakika (`rollback_local.sh`); yedekten tam geri yükleme için 4 saat (README, "Yedekleme ve geri yükleme").

## 10. Güvenlik açıkları

Bir güvenlik açığı admin@wearetheartmakers.com adresine bildirilir. WATAM 2 iş günü içinde değerlendirir, ciddiyetine göre yama ya da geçici önlem yayımlar ve etkilenen müşterileri doğrudan bilgilendirir.
