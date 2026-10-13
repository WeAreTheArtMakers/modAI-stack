# Güvenlik mimarisi

Bu belge, müşterinin bilgi güvenliği ekibinin sorduğu soruları yanıtlar. Her madde, kodda ya da kurulumda bulunan bir önleme karşılık gelir. Henüz yapılmamış olanlar sonda **açıkça** yazılıdır.

Güvenlik bildirimleri: **admin@wearetheartmakers.com**. Destek: info@wearetheartmakers.com · +90 505 314 9360.

## 1. Veri nerede?

- **Her şey müşterinin makinesindedir.** Bu kapsama belgeler (`modaidata` biriminde), veritabanı (PostgreSQL), arama dizini (Qdrant), dil ve arama modelleri (Ollama, `models/`), ses modelleri ve yedekler girer.
- **Soru ve yanıtlar şirket dışına çıkmaz.** Hiçbir bulut yapay zekâ hizmeti (OpenAI, Google ve benzerleri) çağrılmaz.
- **Dışarıya bağlantı yalnızca müşterinin açtığı özellikler için kurulur:**
  - SSO için şirketin kimlik sağlayıcısı;
  - SharePoint eşitlemesi için `graph.microsoft.com` ve `login.microsoftonline.com`;
  - ACME sertifikası için Let's Encrypt.
- **Çevrimdışı paketle kurulumda internet gerekmez.** Modeller ve imajlar pakettedir; paket SHA256SUMS ile doğrulanır.

## 2. Kimlik ve oturum

- **Giriş yolları:**
  - yerel hesap: e-posta ve şifre, şifreler bcrypt ile saklanır;
  - şirket hesabı: OpenID Connect, PKCE ve state ile;
  - Active Directory / LDAP: önce bir okuma hesabıyla kişi aranır, şifresi dizinde doğrulanır. Şifre modAI'de saklanmaz.
- **SCIM ile hesap yaşam döngüsü:** dizinde kapatılan kişi modAI'de de kapanır. Active Directory'de bu kontrol saatlik eşitlemeyle yapılır.
- **Erişim belirteci** 30 dakika geçerlidir (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- **Yenileme belirteci** `httpOnly` bir çerezde durur. Redis'te tek kullanımlık oturumla eşleşir; her yenilemede döner, çıkışta iptal edilir.
- **Kaba kuvvet denemelerine karşı** giriş, kayıt, davet ve ilk kurulum uçları IP başına Redis'te sınırlanır (`RATE_LIMIT_AUTH_PER_MINUTE`).
- **İlk kurulum kodu** (modAI Kutusu) yaklaşık 79 bit rastgeledir. `.env`'de yalnızca SHA-256 özeti tutulur. İlk platform yöneticisi oluşunca kurulum kalıcı olarak kapanır.
- **SCIM belirteci** yalnızca özetiyle saklanır ve bir kez gösterilir.
- **LDAP bağlantısı** LDAPS ya da StartTLS ister. Düz bağlantı yalnızca açıkça izin verilirse kullanılır (`LDAP_ALLOW_PLAINTEXT`, laboratuvar için).

## 3. Yetki

- **Roller:** platform yöneticisi, organization yöneticisi, workspace rolleri (admin, manager, user). Her API çağrısı workspace ve bilgi tabanı üyeliğini denetler (`app.api.authorization`).
- **Belge düzeyinde erişim:** kısıtlı bir belgeyi yalnızca okuyucu listesindekiler bulur. Okuyucu kişi (e-posta) ya da dizin grubu olabilir. Workspace yöneticileri her zaman görür. Kısıt şu yerlerin hepsinde uygulanır:
  - arama: vektör filtresi;
  - belge listesi;
  - indirme;
  - uzman onaylı yanıtlar;
  - sesli asistan.

  Okuyucular ağ klasörü kurallarından ya da SharePoint paylaşımından gelir. Kaynak bağlamak ve kuralları değiştirmek yalnızca organization ve platform yöneticilerine açıktır. Böylece bir workspace yöneticisi başka bir departmanın dosyalarını kendi bilgi tabanına çekemez.
- **Grup–rol eşlemeleri:** dizin grubundan çıkan kişinin o yoldan aldığı üyelik kalkar.

## 4. Uygulama güvenliği

- **Tarayıcı başlıkları:** Content-Security-Policy (`default-src 'self'`, `frame-ancestors 'none'`), `X-Frame-Options: DENY`, `nosniff` ve sıkı Referrer ve Permissions politikaları (mikrofon yalnızca kendi sitesinde).
- **İstem enjeksiyonu:** belgelerdeki görünmeyen yorumlar ve yapay zekâya hitap eden cümleler modele gönderilmeden çıkarılır. Kalite sayfasındaki güvenlik testleri, etkin modelin talimata uyup uymadığını her çalıştırmada sınar. qwen3.5:9b 9/9 geçti.
- **Yükleme denetimi:** tür ve boyut sınırı uygulanır, metni okunamayan dosya reddedilir. Kopya belge aynı bilgi tabanına ikinci kez girmez.
- **Sesli asistanda sunucuda konuşma tanıma** (`POST /voice/transcribe`): oturum gerekir; yalnızca 16 kHz tek kanallı 16 bit PCM WAV kabul edilir, en çok 60 saniye ve 2,5 MB (fazlası okunmadan reddedilir). Kullanıcı başına dakikada 30 istek sınırı vardır. Ses bellekte yazıya çevrilip bırakılır; ne ses ne metin diske ya da loglara yazılır (loglarda yalnızca süre ve boyut). Bir API süreci aynı anda tek döküm yapar ve en çok 8 soru bekletir; fazlası 503 alır, böylece sesli istekler API'yi kilitleyemez.
- **API başvuru sayfası kapalı:** `/docs`, `/redoc` ve `/openapi.json` bütün uçları listeler. Bu yüzden varsayılan olarak kapalıdır (`API_DOCS_ENABLED`).
- **Otomatik yetki taraması:** her test çalıştırmasında API'nin bütün uçları (160'tan fazla) girişsiz ve sahte bir belirteçle çağrılır (`tests/test_route_auth_sweep.py`). İncelenmiş genel uçlar listesinde olmayan bir uç yanıt verirse test başarısız olur. Genel uçlar: giriş, sağlık ve ilk kurulum. Aynı test güvenlik başlıklarını da denetler.
- **Onaylı iş akışları:**
  - Talep türlerini yalnızca organization yöneticisi kurar. Webhook'lar dışarıya veri gönderdiği için bu sınır önemlidir.
  - Talebi açan kişi kendi talebini onaylayamaz. Bir adımı onaylayan kişi başka bir adımı onaylayamaz.
  - Eşzamanlı iki karar, adım numarasıyla ayrılır (409).
  - Webhook gövdesi HMAC-SHA256 ile imzalanır (`WORKFLOW_WEBHOOK_SECRET`). Yönlendirmeler izlenmez.
  - Onaycılara yalnızca herkesin okuyabildiği belgelerden politika gösterilir.
  - Onaycıya bir model hükmü gösterilmez. Talepten hesaplanan sayılar (kodla) ve politikanın kendi cümleleri yan yana konur. Ölçümde küçük yerel model kural yorumlamada yanıldığı için bu karar bilinçli olarak verildi.
  - Vekâlet dört göz ilkesini bozmaz. Talep sahibi kendi talebini vekâletle de onaylayamaz; bir adımı onaylayan, başka bir adımı vekâletle onaylayamaz. Her vekâlet ve vekâletle verilen her karar kayda geçer.
- **Kaynak klasörleri** salt okunur bağlanır (`/sources:ro`). Seçilen klasör, kaynaklar klasörünün dışına çıkamaz. `..`, mutlak yollar ve sembolik bağlantılar reddedilir.

## 5. Ağ

- **HTTPS:** Caddy katmanı (`docker-compose.tls.yml`) üç modda çalışır: şirket sertifikası, iç sertifika otoritesi ya da ACME. Çerezler `Secure` olur; `TRUSTED_FRONTEND_ORIGINS` ile yalnızca kendi kaynağına izin verilir.
- **Açık portlar:** konsol (5173) ya da HTTPS (80/443). Veritabanı, Redis ve Qdrant yalnızca Docker ağı içindedir.
- **modAI Kutusu:** güvenlik duvarında yalnızca konsol portları açık bırakılır (hazırlama listesi).

## 6. Denetim izi ve kayıtlar

- **Denetim günlüğü:** girişler (başarısız olanlar dahil), hesap, üyelik, belge, model, kaynak ve kurulum işlemleri kaydedilir. Kayıtta kim, ne zaman, ne yaptı bilgisi tutulur; şifre ve içerik tutulmaz. IP adresleri 180 gün sonra silinir.
- **Yanıt izi:** hangi belge sürümlerinin kullanıldığı kaydedilir; soru metni saklanmaz.
- **Destek paketi:** parola, belirteç ve içerik içermez; IP ve e-posta adresleri maskelenir.

## 7. Süreklilik

- **Gece yedeği** 03:15'te alınır ve katmanlı tutulur. `BACKUP_MIRROR_DIR` ile ikinci bir diske ya da ağ klasörüne kopyalanır.
- **Geri yükleme:** `scripts/restore_local.sh <yedek> --yes`. Betik önce mevcut durumun güvenlik yedeğini alır, sonra şemayı günceller. Yedek makineye kurulum ve geri yükleme için tahminimiz 1 saattir; süre yedeğin boyutuna bağlıdır. İlk tatbikatta ölçülüp buraya yazılacaktır.
- **Güncelleme ve geri alma:** `upgrade_local.sh` güncellemeden önce yedek alır ve geri alma etiketleri koyar. `rollback_local.sh` ise veritabanını da eski sürüme indirir.
- **Bekçi** (modAI Kutusu): takılan servisi yeniden başlatır ve disk dolmadan uyarır.
- **Yedek doğrulama tatbikatı:** `restore_drill.sh`, bir yedeği çalışan sisteme dokunmadan geçici konteynerlere geri yükler ve sayıları karşılaştırır. 13 Ekim 2026'da üretim yedeği 12 saniyede, bütün sayılar eşleşerek geri yüklendi.
- **Yedek sunucu (sıcak bekleme):** `standby_sync.sh` ikinci bir makineyi her gece en yeni yedekle günceller. Ana makine arızalanırsa ad yönlendirilerek dakikalar içinde devreye alınır.

## 8. Tedarik zinciri

- Her sürüm paketinde `LICENSES/sbom.cdx.json` bulunur: bütün Python ve npm paketlerinin ve imajların CycloneDX 1.5 listesi. Müşterinin tarayıcısıyla (Dependency-Track, Trivy, Grype) okunabilir.
- CI her değişiklikte bağımlılıkları bilinen açıklara karşı tarar (pip-audit, npm audit).
- Model lisansları pakette yer alır (`LICENSES/`). Üçüncü taraf bileşenler `THIRD_PARTY_NOTICES.md` dosyasında listelenir.

**İlk taramanın sonucu (v1.9.0, 12 Ekim 2026):**
- Üretim npm bağımlılıklarında bilinen açık yok.
- Python tarafında 6 pakette 103 bulgu çıktı (pip dahil):

| Paket | Bulgu | Karar |
|---|---|---|
| pypdf 5.9 | 85 bulgu: kötü niyetli bir PDF bellek tüketimi ya da sonsuz döngüyle hizmeti yavaşlatabilir. | **Düzeltildi:** v1.9.0 ile pypdf 6.19+ kullanılıyor. Yüklenen PDF'ler bu kütüphaneyle okunur. |
| python-jose 3.5 | CVE-2026-85394: algoritma kısıtlanmazsa açık anahtarla HS256 belirteci üretilebilir. | **Bizde sömürülemez.** modAI'nin kendi belirteçleri yalnızca HS256 ve gizli anahtarla doğrulanır. SSO kimlik belirteçleri yalnızca asimetrik algoritmalarla (RS, PS, ES) doğrulanır. PyJWT'ye geçiş planlıdır. |
| ecdsa 0.19 | Minerva zamanlama saldırısı: imzalama sırasında anahtar sızabilir. | **Bizde sömürülemez.** modAI ECDSA ile imza atmaz, yalnızca doğrular; doğrulama etkilenmez. |
| transformers 4.57, sentence-transformers 3.4 | Güvenilmeyen model dosyası ya da yapılandırması yüklenirken kod çalıştırma veya aşırı kaynak kullanımı. | **Risk düşük, yükseltme planlı.** Arama modelleri kurulumda SHA-256 ile doğrulanan yerel dosyalardan yüklenir. Çalışırken indirme kapalıdır (`EMBEDDING_ALLOW_DOWNLOAD=false`). 5.x'e geçiş arama vektörlerini değiştirebilir; bu yüzden yeniden indeksleme ve Kalite ölçümüyle ayrı bir sürümde yapılacak. |
| pip 24.0 (temel imaj) | Paket kurulumu sırasında yol ve arşiv açıkları. Çalışma anında kullanılmaz. | **Düzeltildi:** imajda pip 26.1.2+ kullanılıyor. |
| torch | PyPI dışından (CPU tekerleği) kurulduğu için taranamadı. | Sürüm takibi SBOM'dadır. |

Değerlendirilen bulgular CI taramasında kimlikleriyle hariç tutulur (`.github/workflows/ci.yml`, `ACCEPTED`). Yeni bir bulgu çıkarsa tarama yine kırmızı yanar. Bir bulgu düzeltildiğinde listeden çıkarılır.

## 9. Henüz yapılmamış olanlar (dürüstçe)

| Konu | Durum | Plan |
|---|---|---|
| Bağımsız sızma testi | **Yapılmadı.** Bunun yerine iç kontroller var: otomatik yetki taraması (her uç), güvenlik başlıkları, bağımlılık taraması, SBOM. | Bağımsız bir firmaya yaptırılacak (sahip işi). Bulgular bu belgeye eklenecek. |
| Yüksek erişilebilirlik (otomatik devralma) | Otomatik devralma yok. **Sıcak bekleme var:** yedek sunucu her gece kendini günceller, devralma elle (ad yönlendirme) birkaç dakikada yapılır. | Otomatik devralma (veritabanı replikasyonu) müşteri talebiyle proje olarak yapılır. |
| Bekleyen veri şifrelemesi | modAI'de değil, işletim sisteminde | Diskte FileVault (macOS) ya da LUKS (Linux) açılır. modAI Kutusu şifreli diskle teslim edilir. |
| Merkezi gizli anahtar kasası (Vault) | Yok; `.env` (yalnızca sahibi okur, 600) | Yol haritasında. |
| ISO 27001 / SOC 2 | Yok | Müşterinin kendi ISMS kapsamına alınır. Bu belge ve veri envanteri ([kvkk-veri-envanteri.md](kvkk-veri-envanteri.md)) kanıt olarak kullanılır. |
