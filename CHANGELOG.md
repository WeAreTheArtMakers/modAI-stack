# Sürüm notları

## v1.12.0 — Lisans anahtarı, sunucuda konuşma tanıma, satışa hazır paket

13 Ekim 2026'da yayımlandı. Migration yok. **Kurulum artık lisans anahtarıyla çalışır:** güncellemeden sonra platform yöneticisi giriş yapar ve WATAM'ın gönderdiği anahtarı **Lisans** ekranına yapıştırır (internet gerekmez). Sunucuda konuşma tanıma, ses ve video belgeleriyle aynı modeli kullanır: `python3 scripts/fetch_transcription_models.py` ile indirilmiş olmalıdır (çevrimdışı pakette zaten vardır). Model yoksa sesli asistan eskisi gibi tarayıcıda çalışır.

### Lisans
- **WATAM imzalı lisans anahtarı:** anahtar lisans sahibini, paketi (Pilot, Business, Enterprise), bitiş tarihini, kullanıcı sınırını ve isteğe bağlı olarak kurulum kimliğini taşır. Kurulum anahtarı Ed25519 imzasıyla, internete çıkmadan doğrular; lisans sunucusu yoktur.
- **Lisanssız kurulum çalışmaz:** geçerli lisans yokken yalnızca giriş, ilk kurulum, sağlık uçları ve lisans ekranı açılır; konsol bir lisans ekranı gösterir. Platform yöneticisi kurulum kimliğini görür ve anahtarı yapıştırır; yeniden kurulum gerekmez.
- **Bitiş ve ek süre:** bitişten 30 gün önce platform yöneticilerine uyarı gösterilir; bitişten sonra 14 gün ek süre vardır. Kurulum gördüğü en geç tarihi saklar; saati geri almak lisansı uzatmaz.
- **Kullanıcı sınırı:** yeni hesap açılırken uygulanır (kayıt, davet, SCIM, Active Directory ve SSO ile ilk giriş, dizinden yeniden etkinleştirme). Devre dışı ve silinmiş hesaplar sayılmaz.
- **Yönetim → Lisans:** durum, lisans sahibi, paket, bitiş, kullanıcı sayısı, kurulum kimliği ve yeni anahtar alanı.
- **Kaynak kodu müşteriye gitmez:** çevrimdışı paket artık yalnızca çalıştırmak için gerekenleri içerir: imajlar, modeller, kurulum, güncelleme ve yedek betikleri, Compose dosyaları, rehberler, demo belgeleri ve lisanslar. Uygulama kaynak kodu, testler ve iç satış belgeleri pakete girmez.

### Sesli asistan
- **Konuşma tanıma sunucuda, Whisper Small ile:** sesli soru artık varsayılan olarak şirketin kendi modAI sunucusunda yazıya çevrilir ("Sunucu · Whisper Small (önerilen)"). Tarayıcıdaki Whisper Tiny Türkçede zayıftı, telefonlarda ve düşük güçlü bilgisayarlarda yavaştı; sunucu seçeneğinde tarayıcı konuşma modeli indirmez, yalnızca Türkçe ses modelini (yaklaşık 63 MB) indirir. Yerel ölçüm (M1 Pro, 3–4 saniyelik sorular): yazıya çevirme 0,9–1,0 sn.
  - Ses kaydı yazıya çevrilip hemen bırakılır: diske, veritabanına ya da loglara yazılmaz. Sayfanın altındaki not artık seçili seçeneğe göre doğruyu söyler: "Ses kaydınız şirketinizin modAI sunucusunda yazıya çevrilir; saklanmaz ve kaydedilmez."
  - Cihazda tanıma (Whisper Tiny/Base) seçenek olarak kalır. Sunucu modeli kurulu değilse ya da sunucuya ulaşılamazsa sayfa bunu Türkçe söyler ve **Cihazda tanımaya geç** düğmesini gösterir.
  - Sunucu tarafı: oturum gerekir; kayıt en çok 60 sn ve 2,5 MB; kullanıcı başına dakikada 30 istek; bir API süreci aynı anda tek döküm yapar, en çok 8 soru bekletir. Model 10 dakika soru gelmezse bellekten bırakılır; yüklüyken API yaklaşık 0,65–0,9 GB daha fazla bellek kullanır.
- **Talep önerisi sesli yanıtta da:** soru bir talep türüne uyuyorsa (örneğin "3 gün izin almak istiyorum") yanıtın altında RAG Chat'teki gibi **… başlat** önerisi çıkar. Uzman onaylı yanıtlar sesli asistanda da rozetle gösterilir.
- **Geliştirici ölçümleri gizlendi:** yanıtların altındaki süre satırı, "Ayrıntılı süreler" ve seslendirilen bölüm sayısı yalnızca `localStorage["modai.voice.debug"] = "1"` olan tarayıcıda görünür. Seçimdeki "(deneme)" etiketi kaldırıldı; seçenekler "Sunucu" ve "Cihazda" diye ayrılır.

### Düzeltildi
- Telefonda "Knowledge Base seçin" uyarısı "sağdan" diyordu; telefonda bilgi kaynakları aşağıdadır.
- "Ayrıntılı süreler"de kırpılmış kaydın süresi tarayıcıda tanımada 0 görünüyordu: süre, ses tanıma worker'ına aktarıldıktan sonra ölçülüyordu.

### Belgeler
- README'deki sesli asistan bölümü ürün olarak yeniden yazıldı. Sürüme bağlı pilot listesi, sürümden bağımsız [sesli asistan kabul listesi](docs/guides/sesli-asistan-kabul-listesi.md) oldu. Kullanım kılavuzuna sesli asistan bölümü eklendi; KVKK veri envanteri, güvenlik mimarisi, kapasite ve lisans belgeleri sunucuda tanımaya göre güncellendi.
- **Satış:** sitede "Bugün sipariş, bugün kurulum" bölümü (beş adım, Türkiye ve yurt dışında ödeme), bulut asistanlarıyla karşılaştırma tablosu, paketlerde kullanıcı sayıları ve lisans/kaynak kodu soruları. WATAM için satış ve dağıtım rehberi ile sipariş formu ve lisans koşulları taslağı (`docs/sales/`). `COMMERCIAL_LICENSING.md` tescilli yazılımı ve lisans anahtarını anlatır.

## v1.11.3 — Satın almada tutarın girdiği limit

13 Ekim 2026'da yayımlandı. Migration yok.

### Yeni
- **Tutarın girdiği kural:** satın alma ve masraf gibi tutarlı taleplerde, tutarın politikadaki hangi aralığa girdiği kodla hesaplanır. İlgili satır onaycıya vurgulanır. Örneğin 100.000 TL için "25.000 TL – 150.000 TL: Departman direktörü ve Satın Alma birimi" ve "50.000 TL'nin üzerindeki alımlarda en az 2 tedarikçi teklifi alınır".

### Düzeltildi
- **Satın alma talebine ilgisiz bölüm geliyordu:** talebe politika olarak lisans destek notları ekleniyor, onay limitleri tablosu gelmiyordu. Arama artık talep türünün açıklamasını da kullanıyor; en iyi eşleşen belgenin bütün bölümleri, başka belgelerden yalnızca neredeyse aynı güçte olanlar alınıyor. Belge üst bilgileri ("Belge no", "Sürüm") kural olarak gösterilmiyor.

## v1.11.2 — Tutarlar doğru okunur, onaycısız adım uyarılır

13 Ekim 2026'da yayımlandı. Migration yok.

### Düzeltildi
- **Tutarlar yanlış okunuyordu:** "100.000" ve "100,000" **100 TL**, "2.500.000" ise geçersiz sayılıyordu. Artık Türkçe ve İngilizce yazımlar doğru okunuyor: 100.000, 1.250,50, 100,000, 1,250.50, 12,5, "100.000 TL", "₺ 40.000".

### Yeni
- **Onaycısız adım uyarısı:** talep türü kaydedilirken her adımı kimin onaylayabileceği kontrol edilir. Onaylayabilecek kimse yoksa ya da adım sayısı kadar farklı onaycı yoksa İş akışları sayfasında uyarı çıkar. Örnek: iki adım var ama onay verebilecek tek kişi var; aynı kişi iki adımı onaylayamadığı için talepler beklerdi.

## v1.11.1 — Formu doldurmada tarihler kodla

13 Ekim 2026'da yayımlandı. Migration yok.

### Düzeltildi
- **Formu doldurmada yanlış tarih:** "Gelecek pazartesiden itibaren 3 gün" denince yerel model başlangıcı bir cumartesi yazıyordu. Tarih ifadeleri artık kodda çözülüyor: "yarın", "öbür gün", "gelecek pazartesi", "haftaya cuma", "20 Ekim". Bitiş, başlangıç ve gün sayısından iş günü olarak hesaplanıyor; iki tarih varsa gün sayısı hesaplanıyor. Cümlede adı geçen seçenek ("mazeret izni") doğrudan seçiliyor. Model yanıt veremese de bu alanlar doluyor.
- "İznim", "izni" gibi ekli sözcükler de İzin talebi şablonunu öneriyor.

## v1.11.0 — Onayda politika yan yana, vekâlet, hatırlatma ve rapor

13 Ekim 2026'da yayımlandı. Kurulumda `alembic upgrade head` gerekir (0023); `sh scripts/upgrade_local.sh` bunu yapar.

### Yeni
- **Talep ve politika yan yana:** onaycı, talepten hesaplanan sayıları politikanın kendi cümlelerinin yanında görür.
  - Hesaplanan sayılar: başvuru ile başlangıç arasındaki iş günü ve izin süresi.
  - Politika cümleleri kelimesi kelimesine gösterilir; örneğin "3 iş günü ve daha uzun izinler için başvuru en az 10 iş günü önce yapılır".
  - Hesap kodla yapılır, modelle değil. Ölçümde küçük yerel model 13 iş günü önceden yapılan bir başvuruyu "geç" saymış, 0 iş günü önceden yapılanı "uygun" bulmuştu. Bu yüzden onaycıya bir model hükmü gösterilmez; karar onaycınındır.
- **Vekâlet:** izindeki onaycı, onay adımlarını bir meslektaşına bitiş tarihine kadar devreder. Kayıtta "X adına, vekâletle" yazar. Talep sahibi kendi talebini vekâletle de onaylayamaz.
- **Hatırlatma:** belirlenen süreden (varsayılan 24 saat) uzun bekleyen adımlar için Teams/Slack kanalına hatırlatma gider.
- **Talep raporu (CSV):** organization yöneticisi bir workspace'in bütün taleplerini Excel'de açılan bir dosya olarak indirir. Dosyada kararlar, bilgiler ve hesaplanan sayılar yer alır.

### Düzeltildi
- **Belgede olmayan soruya ilgisiz yanıt:** "Ofise evcil hayvan getirebilir miyim?" sorusuna, ilgisiz bir hibrit çalışma bölümüyle yanıt veriliyordu. Yanıt hattında bir ilgililik eşiği yoktu.
  - Artık çok dilli aramada (BGE-M3) ölçülmüş bir taban var: 0,50.
  - En yakın bölüm bunun altındaysa model hiç çağrılmaz, "bu soruyu yanıtlayacak bir belge bulamadım" denir ve soru Yanıtlanamayan sorular raporuna düşer.
  - Ölçüm: Kalite'deki cevaplanabilir 23 soru 0,556–0,768 aldı; konu dışı sorular 0,33–0,51 aldı.
  - Sohbetin devam sorularında taban uygulanmaz. `RAG_RELEVANCE_FLOOR` ile değiştirilebilir (0 kapatır).
- **Formu doldur** üretimde her seferinde "dil modeli formu dolduramadı" diyordu. Uç, modeli çağırmadan önce veritabanı işlemini kapatıyor, sonra talep türünü yeniden yüklemeye çalışıyordu. Artık formun kopyası kullanılıyor. Uç düzeyinde test eklendi.

## v1.10.0 — Onaylı iş akışları: modAI işi de yapar

13 Ekim 2026'da yayımlandı. Kurulumda `alembic upgrade head` gerekir (0022); `sh scripts/upgrade_local.sh` bunu yapar. Webhook kullanılacaksa `.env`'e `WORKFLOW_WEBHOOK_SECRET` yazın.

### Yeni
- **Talepler: onaylı iş akışları.** modAI bilgiyi bulmakla kalmaz, işi başlatır ve onaylı adımlarla yürütür:
  - Sohbette "3 gün izin almak istiyorum" yazan çalışana yanıtın altında **İzin talebi başlat** önerilir.
  - Yerel model formu çalışanın cümlesinden doldurur. Yalnızca cümlede geçen ve alan kontrolünden geçen değerler yazılır; çalışan kontrol edip gönderir.
  - Onaycılar talebin yanında bilgi tabanındaki **ilgili politikayı** görür. Yalnızca herkesin okuyabildiği belgeler gösterilir.
  - Onay adımları sırayla ilerler. Bir adımı workspace rolü (manager, admin), belirli bir kişi ya da Active Directory/SSO grubu onaylayabilir.
  - Dört göz ilkesi uygulanır: kimse kendi talebini onaylayamaz, aynı kişi iki adımı onaylayamaz. Reddetmek için açıklama zorunludur.
  - Son onaydan sonra talep, HMAC ile imzalı JSON olarak webhook'la İK, ERP ya da talep sistemine iletilir. Başarısız gönderim kaydedilir ve yeniden denenebilir. Teams/Slack kanalına kısa bildirim gider.
  - Menüde onayınızı bekleyen talep sayısı görünür. Her adım denetim günlüğüne yazılır.
  - Hazır şablonlar: izin, satın alma (iki onay), masraf, BT erişimi. Organization yöneticisi **Yönetim → İş akışları**'ndan birkaç dakikada kurar.
- **Yedek doğrulama tatbikatı:** `scripts/restore_drill.sh` bir yedeği çalışan sisteme dokunmadan geçici konteynerlere geri yükler ve sayıları karşılaştırır. Üretim yedeği 12 saniyede, bütün sayılar eşleşerek geri yüklendi.
- **Yedek sunucu (sıcak bekleme):** `scripts/standby_sync.sh` ikinci bir makineyi her gece ana makinenin en yeni yedeğiyle günceller. Arızada ad yönlendirilerek devralınır.
- **Otomatik yetki taraması:** her test çalıştırması API'nin bütün uçlarını girişsiz ve sahte belirteçle çağırır. İncelenmemiş bir genel uç testi düşürür.

### Değişti
- **API başvuru sayfası** (`/docs`, `/openapi.json`) artık varsayılan olarak kapalı (`API_DOCS_ENABLED`). Bütün uçları herkese listeliyordu.
- **Güncelleme eski geri alma imajlarını siler:** son iki set kalır (`ROLLBACK_KEEP`). On set diski doldurmuştu.
- Kişisel veri dökümü talepleri de içerir. Hesap silme kişinin taleplerini de siler.

## v1.9.0 — Active Directory, bağlı kaynaklar ve modAI Kutusu

12 Ekim 2026'da yayımlandı. Kurulumda `alembic upgrade head` gerekir (0021); `sh scripts/upgrade_local.sh` bunu yapar. Compose dosyası api ve worker'a salt okunur `/sources` klasörünü ekler. Yükseltme betiği klasörü oluşturur.

### Yeni
- **Active Directory ile doğrudan giriş (LDAP):**
  - Çalışanlar Windows kullanıcı adı ve şifreleriyle girer. Bulut kimlik sağlayıcısı gerekmez.
  - İlk girişte hesap açılır. Gruplar (iç içe olanlar dahil) Kurumsal kimlik sayfasında rollere eşlenir.
  - Saatlik eşitleme, dizinde kapatılan ya da silinen hesapları kapatır.
  - LDAPS ya da StartTLS zorunludur. Şifre saklanmaz.
  - Kurulum rehberi 8.8.
- **Bağlı kaynaklar: ağ klasörü ve SharePoint:**
  - Bir bilgi tabanı, dosya sunucusundaki bir klasörle ya da bir SharePoint kitaplığıyla eşit tutulur: yeni dosya eklenir, değişen dosya yeni sürüm olur, silinen arşivlenir, geri gelen arşivden çıkar.
  - Klasör erişim kuralları ve SharePoint paylaşımları belge okuyucularına aktarılır.
  - Bilgi tabanı sayfasında **Bağlı kaynaklar** bölümünde durum, sayılar, "Şimdi eşitle" ve sıklık yer alır.
  - Kaynağı bağlamak ve erişim kurallarını değiştirmek organization yöneticisinin işidir. Bilgi tabanının manager'ı eşitlemeyi başlatır, duraklatır ve sıklığı değiştirir.
  - Kurulum rehberi 8.9.
- **Belge düzeyinde erişim:**
  - Kısıtlı bir belgeyi aramada, belge listesinde, indirmede, uzman onaylı yanıtlarda ve sesli asistanda yalnızca okuyucuları bulur. Workspace yöneticileri hepsini görür.
  - Belge listesinde 🔒 **Kısıtlı** etiketi görünür.
- **modAI Kutusu ve tarayıcıdan ilk kurulum:**
  - Terminal olmadan kurulan bir sistemde ilk yönetici, şirket ve ilk workspace, tek kullanımlık **kurulum koduyla** tarayıcıda oluşturulur. `.env`'de yalnızca kodun özeti tutulur.
  - `scripts/appliance_setup.sh` cihazı hazırlar: `modai.local` adı, uyku kapalı, elektrik kesintisinden sonra açılış, bekçi, gece yedeği ve etiket metni.
  - `scripts/watchdog.sh` her 5 dakikada bir sağlık kontrolü yapar: takılan servisi yeniden başlatır ve disk dolmadan uyarır.
  - Satış belgesi: `docs/sales/modai-kutusu.md`.
- **Süreklilik:**
  - `BACKUP_MIRROR_DIR` her gece yedeğini ikinci bir diske ya da ağ klasörüne de yazar ve orada da seyreltir.
  - `scripts/restore_local.sh` bir yedeği tek komutla geri yükler: önce güvenlik yedeği alır, sonra şemayı günceller ve hazır olmayı bekler.
- **Tedarik zinciri:**
  - Her pakette `LICENSES/sbom.cdx.json` bulunur: bütün Python ve npm paketlerinin ve imajların CycloneDX 1.5 listesi.
  - CI bağımlılıkları bilinen açıklara karşı tarar (pip-audit, npm audit; bilgilendirme amaçlı).
  - İlk taramada çıkan pypdf açıkları kapatıldı: kötü niyetli PDF ile bellek ve döngü saldırıları (85 bulgu). Bunun için pypdf 6.19+ kullanılıyor. Diğer bulguların değerlendirmesi güvenlik mimarisi belgesindedir.
- **Güvenlik mimarisi belgesi:** `docs/guides/guvenlik-mimarisi.md` güvenlik ekiplerinin sorularını yanıtlar; yapılmamış olanları da (bağımsız sızma testi, yüksek erişilebilirlik) açıkça yazar.

### Değişti
- **Belgeyi değiştir** ve kaynak eşitlemesi aynı sürüm servisini kullanır (`app.services.documents.versions`). İçeriği aynı olan bir dosya için yeni sürüm açılmaz (409).
- **Hesabı sil**, kişinin e-postasını belge okuyucularından ve kaynak kurallarından da siler.

### Düzeltildi
- **Paket, lisans metni olmayan uyarlamalar için temel lisansı yazar:** studiobrn/modAIJet gibi kendi lisans metnini taşımayan modellerde paketteki lisans dosyası boş kalıyordu. Paket artık mimariye göre temel modelin lisansının tam metnini ve bir açıklamayı yazar: Gemma 4 ve Qwen 3.5 için Apache 2.0, Gemma 1–3 için Gemma Terms of Use. Metinler `deploy/package/licenses/` altındadır.

## v1.8.2 — Model listesinde MLX ayrıntıları

12 Ekim 2026'da yayımlandı. Migration yok.

### Düzeltildi
- Modeller sayfasında MLX modellerinin ailesi boş görünüyordu ve ayrıntı satırı "·" ile başlıyordu. Aile artık Ollama'nın ayrıntılı yanıtından okunuyor (ör. gemma4:12b-mlx için gemma4_unified).

## v1.8.1 — Güncelleme sırasında oturum korunur

12 Ekim 2026'da yayımlandı. Migration yok.

### Düzeltildi
- **Her güncelleme herkesin oturumunu kapatıyordu:** API yeniden başlarken (yaklaşık 10 saniye) ağ geçidi 502 döner. Konsol bunu oturumun bittiği sanıyor, çıkış yapıyor ve sunucudaki oturumu da iptal ediyordu. Artık oturum yalnızca 401 ya da 403'te kapanır. Sunucu kısa süre ulaşılamazken konsol bekler ve kullanıcıyı 3 saniyede bir yeniden okur ("Sunucu yeniden başlıyor"). v1.8.0 kurulumu sırasında üretimde görüldü.

## v1.8.0 — Kurumsal kimlik, model lisansları ve çok modelli paket

12 Ekim 2026'da yayımlandı. Kurulumda `alembic upgrade head` gerekir (0020); `sh scripts/upgrade_local.sh` bunu yapar. Mac'te gece yedeği bu sürümle kurulabilir: `sh scripts/schedule_maintenance.sh`.

### Yeni
- **Kurumsal kimlik (Yönetim → Kurumsal kimlik):**
  - **SCIM 2.0:** Microsoft Entra ID ve Okta hesapları ve grupları kendisi açar, günceller, kapatır (`/api/scim/v2`, belirteçle). Dizinde kapatılan kişi parola ya da şirket hesabıyla giremez ve oturum yenilemesi anında durur. Platform yöneticileri dizinden kapatılmaz.
  - **Gruplardan roller:** SCIM ya da şirket hesabıyla girişteki `groups` bilgisinden gelen gruplar, bir organization ya da çalışma alanında bir role eşlenir. Gruptaki kişi üyeliği kendiliğinden alır, gruptan çıkınca bu üyelik kalkar. Elle verilen üyeliklere dokunulmaz.
  - **Uyumluluk:** bağımsız `scim2-tester` denetiminde 69 kontrolün 63'ü geçti; kalan altısı bilinçli kurallardır. Entra'nın istek biçimleriyle de sınandı.
  - **Kullanıcı adı eşleşmesi:** e-posta olmayan kullanıcı adları ve UPN ile mail adresinin farklı olduğu durumlar şirket hesabıyla ilk girişte eşleşir.
- **Modellerin lisansı ve seçimi:**
  - Modeller sayfası her yerel modelin lisansını gösterir (modelin kendi metninden ya da ailesinden: Gemma 3 → Gemma Terms of Use, Gemma 4 ve Qwen 3.5 → Apache 2.0). Kullanım kısıtı olan lisansları ve güvenlik eğitimi kaldırılmış varyantları işaretler.
  - Sunucunun bellek sınırını aşan modeller (ör. qwen3.5:9b-mlx) ve bu varyantlar artık uyarı onaylanarak sınanıp seçilebilir; onay denetim kaydına yazılır.
  - `install.sh` model sınırını makinenin belleğinin yarısı olarak yazar.
- **Birden fazla modelli paket:** `package_release.sh --model …` birden fazla dil modelini, MLX modelleri dahil, pakete koyar. Kurulum ve güncelleme hepsini internetsiz ekler. Güvenlik eğitimi kaldırılmış varyantlar pakete alınmaz; Llama lisanslı modeller için NOTICE da yazılır.
- **Sözleşme model eki:** `docs/sales/sozlesme-model-eki.md` kurulumdaki bütün modelleri, lisanslarını, model seçim kuralını ve kullanım kısıtlarını kapsar.
- **İletişim:**
  - destek: info@wearetheartmakers.com, +90 505 314 9360;
  - güvenlik: admin@wearetheartmakers.com (`SECURITY.md`).

### Düzeltildi
- **macOS'ta gece yedeği kurulamıyordu:** `schedule_maintenance.sh` launchd dosyasına (plist) kaçışsız `&&` yazıyordu ve launchd dosyayı reddediyordu. Komut artık XML olarak kaçışlanıyor; bir test yazılan dosyayı ayrıştırarak doğruluyor.
- **Site metni:** "hazır kurumsal kimlik entegrasyonlarına ihtiyacınız varsa uygun değil" cümlesi kaldırıldı. Gerçek sınır bulut kaynaklarından hazır eşitlemenin olmaması.

### Değişen ayarlar
- Migration `0020_directory_sync`: `users.disabled_at`, `memberships.source` ve dizin tabloları. Var olan üyelikler değişmez.
- Yeni ortam değişkeni: `OIDC_GROUPS_CLAIM` (varsayılan `groups`).

## v1.7.0 — Çevrimdışı kurulum paketi ve satış kiti

12 Ekim 2026'da yayımlandı. Migration yok. Müşteriye teslim `sh scripts/package_release.sh --ref v1.7.0` ile üretilen paketle yapılır (`releases/modai-1.7.0/`, arm64). Var olan kurulumlar `sh scripts/upgrade_local.sh` ile güncellenir; Sistem sayfası artık sürüm numarasını gösterir.

### Yeni
- **Çevrimdışı kurulum paketi:** `sh scripts/package_release.sh --ref v1.7.0` müşteriye teslim edilecek `releases/modai-1.7.0/` klasörünü üretir. İçinde:
  - sürümün kaynağı;
  - ondan derlenmiş imajlar ve üçüncü taraf imajları;
  - doğrulanmış ses, arama, konuşma tanıma ve MiniLM dosyaları;
  - Ollama'dan alınan dil modeli (Modelfile ve lisansıyla);
  - `VERSION`, müşterinin ilk sayfası `KURULUM.md`, `LICENSES/` ve `SHA256SUMS`.

  `install.sh` paketi tanır:
  - dosyaları `SHA256SUMS` ile ve işlemci mimarisini denetler;
  - imajları derlemek yerine yükler (`scripts/load_package_images.sh`);
  - modelleri ağsız doğrular;
  - eksik dil modelini `ollama create` ile paketten ekler.

  `upgrade_local.sh`, kurulum klasörünün üzerine kopyalanan yeni paketle git olmadan güncelleme yapar; geri alma aynıdır.
- **Sürüm numarası:** sürüm etiketinden ya da paketten derlenen imajlar `APP_VERSION` taşır. `/version` bunu döndürür, Sistem sayfası "modAI 1.7.0" yazar.
- **Denendi:** paket bu Mac'te üretildi (150 sn; 624 dosya, imajlar 1,0 GB, modellerle 6,9 GB). Üretim durdurularak `musteri-sunucusu` adlı bir klasöre paketten kuruldu: 8/8 adım, 80 sn, hiçbir dosya indirilmedi; belge eklendi ve doğru yanıt alındı. Modelsiz ikinci paketle güncelleme ve geri alma da çalıştı. Paketteki dil modeli `ollama create` ile başka bir adla eklenip yanıt verdi.
- **Satış kiti:** [teslim ve kabul formu](docs/sales/teslim-ve-kabul.md) (teslim edilenler, 10 kabul testi, ayarlar, sınırlamalar, imza). Ürün özeti güncel özellikler ve üretim ölçümleriyle yenilendi.

### Düzeltildi
- **Kapasite kartı yeni kurulumda yanılmaz:** günün ilk yanıtı modeli de yüklediği için 15–20 saniye sürer; tek bir yanıt kartı "İzleyin"e çeviriyordu. Yanıt süresi artık 20 yanıttan sonra değerlendirilir; kart ve Güven raporu kaç yanıtın ölçüldüğünü söyler. Paket kurulumu denemesinde bulundu.
- Destek politikasındaki paket adları ticari lisanslamayla aynı: Pilot (2–4 hafta), Business, Enterprise.
- Ürün özeti SSO'nun ürünle gelmediğini söylüyordu; SSO v1.3.0'dan beri var.

### Değişen ayarlar
- `install.sh` ile yazılan yeni `.env` dosyaları `COMPOSE_PROJECT_NAME=modai` içerir; veri birimleri klasör adına bağlı kalmaz. Var olan `.env` değişmez.
- Gemma ağırlıkları paketle dağıtıldığı için paket Gemma Terms of Use'u ve gereken NOTICE dosyasını `LICENSES/` altına koyar. Müşteri sözleşmesi Gemma kullanım kısıtlarını (3.2. madde) içermelidir ([lisanslama](docs/guides/lisanslama.md)).

## v1.6.0 — Kur ve unut: ölçülmüş kapasite, gece yedeği, disk koruması, destek politikası

12 Ekim 2026'da yayımlandı (main `a7f3c568`). Kurulumda `alembic upgrade head` gerekir (0019); `sh scripts/upgrade_local.sh` bunu yapar. Gece yedeği güncellemeyle kurulmaz; mevcut kurulumlarda bir kez `sh scripts/schedule_maintenance.sh` çalıştırın. Production'da güncelleme 64 saniye sürdü; ön yedek modai-20261012T195730.

### Yeni
- **Kapasite ölçümü ve rehberi:** `python -m app.tools.load_test` aynı anda 1–16 kişinin soru sorduğu durumu ölçer ve bıraktığı her kaydı geri alır. Referans makinede (MacBook Pro M1 Pro, 16 GB, gemma3:4b) ölçülen: tek kişide yanıt 3,3 sn; aynı anda 4 kişide yanıtların %95'i 9,8 sn içinde, 8 kişide 16,4 sn, 16 kişide 36,9 sn; dakikada yaklaşık 30 yanıtta doyuyor; hiçbir seviyede hata yok. Çalışan sayısına göre senaryolar ve donanım tablosu: `docs/guides/kapasite-ve-donanim.md` (16 GB: 250 çalışana kadar rahat, 500'e kadar güvenli; diğer satırlar tahmin).
- **Kapasite kartı:** yanıt izi artık yanıt süresini de tutar (migration `0019_answer_durations`); **Sistem → Kapasite (son 7 gün)** ve Güven raporu medyan ve %95 yanıt süresini, en yoğun saati ve "Yolunda / İzleyin / Büyütün" önerisini gösterir.
- **Disk uyarısı:** boş alan %15'in ya da 15 GB'ın altında platform yöneticileri konsolda uyarı görür; 5 GB'ın altında yeni yüklemeler 507 ile durur, yanıtlar ve yedekler sürer. `/ready` disk düzeyini de bildirir.
- **Kendiliğinden gece yedeği:** `scripts/schedule_maintenance.sh` her gece 03:15'te yedek alır (cron ya da launchd); kurulum betiği bunu kurar (`--no-schedule`). Yedekler katmanlı tutulur (48 saat hepsi, 14 gün, 8 hafta, 6 ay; yaklaşık 28 yedek), çünkü 660 MB'lık yedeğin 180 gecesi 120 GB ederdi.
- **Destek paketi:** `sh scripts/support_bundle.sh` sürüm, servisler, disk, bellek, ön kontrol ve son 24 saatin hata satırlarını, IP, e-posta ve belirteçleri maskeleyerek tek dosyada toplar.
- **Destek ve güncelleme politikası:** `docs/guides/destek-ve-guncelleme-politikasi.md` (paketler, öncelikler ve yanıt süreleri, sürüm ve destek süresi, müşteri sorumlulukları, RPO/RTO).
- **Sohbette yoğunluk bildirimi:** ilk kelime 6 saniye gecikirse "Sistem şu anda yoğun; sorunuz sırada…" yazar.

### Düzeltildi
- **Kurulum betiği kurulu modeli değiştirmez:** `install.sh` yeniden çalıştırıldığında `ollama pull` kurulu gemma3:4b'nin yerine kayıt defterindeki daha yeni yapıyı indirmeye başlıyordu (temiz kurulum denemesinde 3,3 GB'lık farklı bir dosya); kullanıcılar Kalite'nin hiç görmediği ağırlıklarla yanıt alacaktı. Artık yalnızca eksik model indirilir (`scripts/pull_model.sh`); model güncellemesi bilinçli yapılır ve Kalite'den geçer.
- **SSO ile kurum içi alan adları:** şirket dizininden `ayse@sirket.local` gibi bir adresle açılan hesap konsolu açamıyordu (`/auth/me` 500) ve yönetici kullanıcı listesini bozuyordu. Yanıtlar artık kayıtlı adresi olduğu gibi gösterir; böyle bir hesap Üyelikler'den e-postayla eklenebilir. Gerçek bir OpenID Connect sağlayıcısıyla (Dex, bu makinede) yapılan uçtan uca denemede bulundu; deneme 13/13 geçti.
- Kalite sayfası, son çalıştırma bir aday modelin sınamasıysa bunu ve kullanıcıların hangi modelle yanıt aldığını söyler.
- Güven raporu ve Belgeler sayfası, henüz hiç yanıt yokken "— belgeden" ve "16 belge kullanılmadı" yerine yanıt olmadığını yazar.

### Denendi
- **Temiz kurulum:** sıfır bir kopyada tek komutla `install.sh`. Linux (Alpine, dash) kabında 1–5. adımlar geçti; ön kontrol, kabın gördüğü 8 GB bellekte doğru olarak durdu ("en az 16 GiB"). Bu Mac'te 8 adımın tamamı geçti: 19 migration, servisler hazır, belge eklendi ve yanıt alındı, Kapasite ve Disk kartları göründü. İmajların sıfırdan derlenmesi bu bağlantıda 21,5 dakika sürdü; modeller önceden hazırdı.
- **SSO:** gerçek bir OpenID Connect sağlayıcısıyla (Dex) betikle 13/13 ve tarayıcıda giriş sayfasından uçtan uca.

### Değişen ayarlar
- Migration `0019_answer_durations`. Yeni ortam değişkenleri: `DISK_WARNING_FREE_RATIO` (0.15), `DISK_WARNING_FREE_BYTES` (15 GB), `DISK_CRITICAL_FREE_BYTES` (5 GB), `BACKUP_KEEP_DAILY` (14), `BACKUP_KEEP_WEEKLY` (8), `BACKUP_KEEP_MONTHLY` (6).
- `scripts/backup_local.sh` eski yedekleri artık katmanlı siler (python3 yoksa eskisi gibi yalnızca yaşa göre).

## v1.5.0 — Model seçimi, uzman onaylı yanıtlar, eksik bilgi konuları ve güven raporu

12 Ekim 2026'da yayımlandı (main `ffc8d57a`). Kurulumda `alembic upgrade head` gerekir (0017, 0018); `sh scripts/upgrade_local.sh` bunu yapar. Her istek artık bağlam sınırı gönderdiği için güncellemeden sonra bir Kalite çalıştırması önerilir. Production ölçümü (ws1): gemma3:4b 8K bağlamla 24/25 soru, 8/9 güvenlik, medyan 3,5 sn; aday qwen3.5:9b 24/25, 9/9, medyan 17,7 sn (etkinleştirilmedi).

### Yeni
- **Üretim modeli seçimi:** platform yöneticisi Modeller sayfasında Ollama'da yüklü bir modeli bir çalışma alanının Kalite soruları ve 9 güvenlik testiyle **Sınar**, sonra **Etkinleştirir**; seçim yeniden başlatma olmadan birkaç saniyede bütün API ve worker süreçlerine geçer, önceki model bellekten boşaltılır. Belgeler yeniden indekslenmez (arama modeli aynı kalır). Sınanmamış model etkinleştirilemez; `OLLAMA_MAX_MODEL_BYTES` üstü modeller sunulmaz. Kalite çalıştırmaları ve yanıt izi hangi modelin yanıt verdiğini kaydeder. CLI: `quality_checks run --model`.
- **Her modele güvenli ayarlar:** "düşünme" yeteneği olan modellere `think: false`, her isteğe `num_ctx` = `OLLAMA_NUM_CTX` (8192). Ölçüm (16 GB Mac): studiobrn/modAIJet aynı 9 soruyu düşünerek 52 sn'de, düşünmeden 12 sn'de yanıtladı; qwen3.5:9b varsayılan 256K bağlamla 16,2 GB yükledi ve 9 yanıt 10 dakika sürdü, 8192 ile 5,8 GB ve yanıt başına ~5 sn, güvenlik testlerinde 9/9.
- **Uzman onaylı yanıtlar:** RAG Chat'te **Uzman olarak onayla** (manager); aynı soru aynı bilgi tabanlarında yeniden sorulunca onaylı yanıt modele sorulmadan "Uzman onaylı yanıt" etiketiyle verilir, benzer sorularda modelin yanıtının yanında öneri kartı çıkar. Onay geçerlilik tarihinde (6 ay) ya da kaynak belge değişince, arşivlenince veya silinince düşer; **Yönetim → Onaylı yanıtlar**'da yenilenir. Yanıtlanamayan sorular raporunda **Uzmana ata**: üye soruyu **Atanan sorular**'da yanıtlar, yanıt onun adıyla onaylanır. Bilgi tabanı yetkileri korunur (migration `0018_verified_answers`).
- **Eksik bilgi konuları:** yanıtlanamayan sorular **Konulara göre** görünümünde aynı konudaki farklı sorular birlikte, en çok sorulan üstte; konuya en uyan bilgi tabanı önerilir. Arama modeliyle (BGE-M3) gruplanır, yeni model yüklenmez; eski dizindeki çalışma alanlarında ortak kelimelerle.
- **Güven raporu:** **Yönetim → Güven raporu**: kurulum ve veri yerleşimi, erişim denetimi, saklama süreleri, son Kalite çalıştırması ve eğilimi, güvenlik testleri, son 30 günün kullanımı ve denetim kaydı, sınırlamalar; tarayıcıdan PDF olarak kaydedilir. Hiçbir şey saklanmaz; görüntüleme denetime yazılır.

### Düzeltildi
- Güven raporunun "Yanıt kalitesi" bölümü, bir aday modelin sınamasını son çalıştırma olarak gösteriyordu; artık etkin modelin son çalıştırmasını gösterir (aday sınamaları eğilim tablosunda modeliyle birlikte kalır).

### Değişen ayarlar
- Migration `0017_generation_model_choice` (`platform_settings`, `quality_runs.model`, `answer_traces.model`) ve `0018_verified_answers`. Yeni ortam değişkenleri: `OLLAMA_NUM_CTX` (8192), `OLLAMA_MAX_MODEL_BYTES` (8000000000).
- Her istek artık `num_ctx` gönderir; gemma3:4b için bellek kullanımı değişebilir. Güncellemeden sonra bir Kalite çalıştırması önerilir.

## v1.4.0 — Toplantı tutanağı, yanıt izi ve güvenlik testleri

12 Ekim 2026'da yayımlandı (main `36b0cb8d`). Kurulumda `alembic upgrade head` gerekir (0016); `sh scripts/upgrade_local.sh` bunu yapar. RAG istemi değiştiği için güncellemeden sonra bir Kalite çalıştırması önerilir.

### Yeni
- **Toplantı tutanağı:** belgeler tablosunda hazır bir belge için **Tutanak çıkar** (manager ve admin). Worker belgenin metnini bölüm bölüm dil modeline sorar (JSON) ve kararları, aksiyonları (sorumlu, tarih), konuşulan konuları, açık soruları ve dakika dakika akışı sabit bir Markdown düzeninde toplar. Her madde, kelimeleri en çok örtüşen dökümdeki dakikayı (YouTube dökümünde videonun o anına bağlantıyla) alır. Taslak Redis'te 24 saat durur; düzenlenip **Bilgi tabanına kaydet** ile belge olur (`kind: "markdown"`, Markdown olduğu gibi korunur) ya da indirilir. İş kalite sırasını kullanır: model aynı anda tek toplu iş yapar. Gemma 3 4B ile 7 dakikalık örnek toplantının iki koşusunda 6 aksiyonun hepsi doğru dakikayla çıktı; bir koşuda bir sorumlu yanlış okundu ("Eylül" ayı kişi adı sanıldı), bir koşuda bir bilgi karar olarak yazıldı. Taslak bu yüzden kaydetmeden önce düzenlenmek üzere gösterilir.
- **Yanıt izi:** her yanıtın hangi belge sürümlerine dayandığı, ne zaman, hangi bilgi tabanlarında, kimin için ve hangi sonuçla (migration `0016_answer_traces`). Soru ve yanıt metni saklanmaz. Belgeler tablosunda **Yanıtlarda (30 gün)** sütunu ve hiç kullanılmayan belge sayısı; sayıya basınca son yanıtların sürüm ve sonucu (yöneticiler, kişisiz). Platform yöneticisi **Denetim günlüğü → Yanıt izi**'nde hesapla birlikte görür. `ANSWER_TRACE_RETENTION_DAYS` (varsayılan 180); hesap silme kişi bağını kaldırır.
- **Güvenlik testleri (istem enjeksiyonu):** her Kalite çalıştırması sorulardan sonra 9 sabit senaryoyu da sorar: "önceki talimatları yok say", sahte giriş bağlantısı, gizli görselle soru sızdırma, gizli talimatları açıklatma, tutarı değiştirtme, İngilizce talimat, görünmeyen HTML yorumu, talimat gibi görünmeyen bağlantı kuralı ve bilgi yokken uydurma baskısı. Uydurma metinler yalnızca istemde bulunur, hiçbir bilgi tabanına eklenmez. Sonuçlar gizlenen talimatla birlikte Kalite sayfasında; soru eklenmemiş bir çalışma alanında da çalışır.
- **Belgedeki gizli talimatlara karşı savunma:** HTML ve Markdown yorumları ile yapay zekâya hitap eden cümleler modele gönderilmeden çıkarılır (`app/services/rag/injection.py`); kullanıcının gördüğü kaynak metin değişmez. İstemin sonuna, yanıta en yakın yere bir hatırlatma eklendi. Gemma 3 4B ile ölçüm: önce 4/8, sonra 8/9 (dört tekrarda aynı). Geçmeyen tek senaryo hiçbir kalıba uymayan bağlantı kuralıdır; dürüstçe gösterilir. Production'daki ilk çalıştırmada (ws1, run 37) sorular 25'te 24 geçti (önce 23) ve medyan süre 7,2 sn oldu.

### Düzeltildi
- "Bilgi yokken uydurma baskısı" senaryosu, yanıtın ilk cümlesi başka bir şey söyleyip ikinci cümlesi "belgede yer almamaktadır" dediğinde yanlışlıkla geçmedi sayılıyordu (production run 37). Artık yanıtın herhangi bir cümlesindeki "belgede yok" ifadesi ve uydurulmuş bir değer olmaması yeterli.

### Değişen ayarlar
- Migration `0016_answer_traces` (üç boş tablo: `answer_traces`, `answer_trace_sources`, `quality_security_results`). Yeni ortam değişkenleri: `QUALITY_SECURITY_CHECKS` (true), `ANSWER_TRACE_RETENTION_DAYS` (180), `MINUTES_MAX_CHARS` (200000).
- RAG istemi değişti (temizlenmiş parçalar ve sondaki hatırlatma): kurulumdan sonra Kalite çalıştırması önerilir.

## v1.3.0 — Şirket hesabıyla giriş, YouTube metninden belge ve içeriğe göre yerleştirme düzeltmesi

12 Ekim 2026'da yayımlandı (main `2b738eb8`). Kurulumda `alembic upgrade head` gerekir (0015); `sh scripts/upgrade_local.sh` bunu yapar. SSO kapalı gelir; açmak için [rehber 8.6](docs/guides/kurulum-ve-teslim-rehberi.md#86-şirket-hesabıyla-giriş-sso-openid-connect).

### Yeni
- **Şirket hesabıyla giriş (SSO, OpenID Connect):** Microsoft Entra ID, Google Workspace, Keycloak, Okta ve diğer OIDC sağlayıcılarıyla giriş. PKCE ile yetkilendirme kodu akışı, tek kullanımlık state, sağlayıcı anahtarlarıyla imza, issuer, audience, süre ve nonce doğrulaması. Kişi sağlayıcının değişmeyen kimliğiyle tanınır (migration `0015_user_identities`); ilk girişte aynı e-postalı hesaba bağlanır ya da `OIDC_AUTO_PROVISION` ile hesap açılır. Yalnızca `OIDC_ALLOWED_DOMAINS` alan adları girer; bekleyen davetler kendiliğinden kabul edilir. Giriş sayfasında "<sağlayıcı> ile giriş" düğmesi. Hesap silme SSO bağlantılarını da siler. [Rehber, 8.6](docs/guides/kurulum-ve-teslim-rehberi.md#86-şirket-hesabıyla-giriş-sso-openid-connect).
- **YouTube videosundan belge, indirmeden:** Belgeler sayfasında **Metinden belge oluştur**: YouTube'daki döküm ya da yapay zekâ özeti yapıştırılır; zaman damgaları ve arayüz satırları temizlenir, metin dakika dakika bölümlere ayrılır ve her bölüm videonun o anına bağlantı alır. Düz metin de belge yapılabilir (`POST /documents/from-text`). Video dosyası yükleyip yazıya dökme aynen sürer.
- **Web sitesi:** video ve taranmış belge, şirket hesabıyla giriş ve "Şirket içinde nerede işe yarar?" bölümü eklendi; SSS'deki SSO yanıtı güncellendi.

### Düzeltildi
- **İçeriğe göre yerleştirme production'da hiç çalışmıyordu:** gömme modeli çözümlenirken boş bilgi tabanı listesi verildiği için her yükleme "kullanılamıyor" nedeniyle seçilen bilgi tabanında kalıyordu. Artık aday bilgi tabanlarının kapsamı veriliyor; production'daki deneme bunu doğruladı.

### Değişen ayarlar
- Migration `0015_user_identities` (boş başlar). Yeni ortam değişkenleri `OIDC_ENABLED` (false), `OIDC_PROVIDER_NAME`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI`, `OIDC_SCOPES`, `OIDC_ALLOWED_DOMAINS`, `OIDC_AUTO_PROVISION` (true). `scripts/preflight.py` yarım kalmış SSO ayarlarını uyarır.

## v1.2.0 — Taranmış belge, ses ve video, içeriğe göre yerleştirme ve tek komutla kurulum

12 Ekim 2026'da yayımlandı (main `5ea2ffc1`). Migration yoktur; ses ve video için `python3 scripts/fetch_transcription_models.py` gerekir.

### Yeni
- **Taranmış belgeler (OCR):** metin katmanı olmayan PDF sayfaları ve PNG, JPG, TIFF görseller Tesseract ile Türkçe ve İngilizce okunur. Metni olan sayfalar olduğu gibi kalır. OCR worker'da çalışır; API imajı Tesseract'ı ve Türkçe verisini içerir.
- **Ses ve video belgeleri:** MP3, M4A, WAV, OGG, FLAC, MP4, MOV, M4V, WEBM ve MKV dosyaları faster-whisper ile yazıya dökülür (varsayılan model small). Döküm kaydın adıyla başlar ve dakika dakika bölümlere ayrılır; bölüm bazlı aramada kaynak kartı yanıtın söylendiği dakikayı gösterir. Şirketin YouTube videoları YouTube Studio'dan indirilip yüklenir. Kayıt başına en çok 200 MB ve 120 dakika. Model `scripts/fetch_transcription_models.py` ile SHA-256 doğrulamalı indirilir; kurulu değilse ses ve video yüklemeleri açık bir iletiyle reddedilir.
- **İçeriğe göre yerleştirme:** yükleme alanlarında ve toplu aktarımda (`--auto-route`, `--dry-run` ile önizleme) her belge, açıklaması içeriğine en çok uyan bilgi tabanına gider; emin olunamayanlar seçilen bilgi tabanında kalır. Demo paketinde 14 belgenin 13'ü doğru yerleşti; yanlış olan, eşiğin altında kaldığı için yerinde kalırdı. Çok dilli arama (BGE-M3) ve bilgi tabanı açıklamaları gerekir. Bilgi tabanı sayfasında **Açıklamayı düzenle** eklendi (`PATCH /knowledge-bases/{id}`).
- **Tek komutla kurulum:** `sh scripts/install.sh` (HTTPS için `--hostname modai.sirket.local`) gereksinimleri denetler, yeni sırlarla `.env` yazar, modelleri indirir, ön kontrolü çalıştırır, derler, veritabanını kurar, servisleri başlatır ve ilk platform yöneticisini oluşturur. Yeniden çalıştırılabilir.
- **Belgeyi aç:** kaynak kartlarında ve belgeler tablosunda orijinal dosya indirilir (`GET /documents/{id}/file`, denetim kaydına yazılır).
- **Kullanım raporu CSV:** Genel Bakış'taki kullanım kartında **CSV indir (90 gün)**: gün gün soru, yanıtlanan, yanıtlanamayan, 👍 ve 👎 (`GET /workspaces/{id}/usage-report.csv`).
- **Klasör eşitleme:** toplu aktarım aracının her gece cron ile çalıştırılması kurulum rehberinde anlatıldı; aynı içerik ikinci kez eklenmez.

### Değişen ayarlar
- Yeni ortam değişkenleri: `OCR_ENABLED` (true), `OCR_LANGUAGES` (`tur+eng`), `OCR_MAX_PAGES` (200), `TRANSCRIPTION_MODEL` (`small` ya da `base`), `TRANSCRIPTION_MODEL_ROOT` (`/models`), `TRANSCRIPTION_MAX_MINUTES` (120), `MEDIA_MAX_UPLOAD_BYTES` (200 MB). Arayüzün nginx gövde sınırı 210 MB'a çıktı.
- API imajı Tesseract'ı ve yeni Python bağımlılıklarını (faster-whisper, pypdfium2) içerir; ilk derleme bunları indirir. Torch artık ayrı bir katmandadır; bağımlılık değişikliklerinde yeniden indirilmez.
- Migration yoktur. `scripts/preflight.py` konuşma tanıma modeli eksikse uyarır.

### Düzeltildi
- Gözden geçirme tarihi testleri İstanbul saatiyle 00:00–03:00 arasında başarısız oluyordu (saat dilimi olmayan UTC zamanı yerel saat sanılıyordu).

## v1.1.0 — Yanıt geri bildirimi, kullanım özeti ve örnek sorular

12 Ekim 2026'da yayımlandı (main `056dc066`). Kurulumda `alembic upgrade head` gerekir (0014); `sh scripts/upgrade_local.sh` bunu yapar.

### Yeni
- **Yanıtı değerlendirme (👍 / 👎):** RAG Chat'te ve sesli asistanda her yanıtın altında "Yanıt işinize yaradı mı?" vardır. 👎 bir neden (Yanlış bilgi, Eksik yanıt, Yanlış kaynak, Güncel değil, Diğer) ve isteğe bağlı bir not ister; soru, yanıt ve kaynak adları yöneticilere iletilir. Kimin işaretlediği kaydedilmez; 👍 için yalnızca sayı tutulur.
- **Yanlış bulunan yanıtlar:** **Yönetim → Yanıtlanamayan sorular** sayfasının altında 👎 kayıtları nedeni, notu ve kaynaklarıyla listelenir. **Çözüldü** kaydı kaldırır, **Kalite sorusu yap** soruyu Kalite sayfasına ekler; böylece aynı soru her çalıştırmada yeniden sorulur.
- **Kullanım özeti:** Genel Bakış'ta manager ve admin'ler son 30 günün soru sayısını, belgelerden yanıtlanma oranını, yanıtlanamayan soruları ve 👍 / 👎 sayılarını günlük grafikle görür.
- **Örnek sorular:** RAG Chat ve sesli asistan, henüz soru sorulmamışken Kalite sayfasında son çalıştırmada geçen soruları önerir (yalnızca kullanıcının erişebildiği bilgi tabanlarından). Birine basmak soruyu yazar ve bilgi tabanlarını seçer.

### Değişen davranış
- **Görüşme saklama süresi varsayılan 6 ay:** `CONVERSATION_RETENTION_DAYS` artık 180'dir (boş değer de 180). Worker günde bir kez, son etkinliği 180 günden eski sesli asistan ve modAI Asistan görüşmelerini siler. `0` görüşmeleri silinene kadar tutar.

### Değişen ayarlar
- Migration `0014_answer_feedback`: `answer_feedback` tablosu (kullanıcı kimliği yok), boş başlar. Kurulumda `alembic upgrade head` gerekir; güncelleme betiği bunu yapar.
- Geri bildirimler yanıtlanamayan sorularla aynı süre tutulur (`UNANSWERED_RETENTION_DAYS`, varsayılan 90 gün). Kullanıcı başına dakikada 30 geri bildirim sınırı vardır.

## v1.0.0 — Satışa hazır sürüm: belge yaşam döngüsü, KVKK araçları ve bölüm bazlı arama

12 Ekim 2026'da yayımlandı. Kurulumda `alembic upgrade head` gerekir (0013). Güncelleme artık `sh scripts/upgrade_local.sh` ile yapılır.

### Yeni
- **Hesabı sil (KVKK silme talebi):** platform yöneticisi **Yönetim → Kullanıcılar**'da kişinin satırında **Hesabı sil**'e basar ve e-posta adresini yazarak onaylar (`DELETE /admin/users/{id}`). Hesap anonimleştirilir: e-posta `silinmis-<id>@silinmis.modai` olur, hesap bir daha giriş yapamaz ve oturumları iptal edilir. Görüşmeleri, üyelikleri, asistan tercihleri ve bu adrese gönderilmiş davetler kalıcı olarak silinir; açık kayıtla açılmış ve adında e-posta geçen Organization yeniden adlandırılır. Yüklediği belgeler şirket içeriği olarak kalır; sahibi olduğu belgelerin sahibi boşalır. Platform yöneticileri ve kişinin kendisi silinemez. Denetim kaydına `user_account_erased` olarak yalnızca sayılar yazılır.
- **Güncelleme ve geri alma betikleri:** `scripts/upgrade_local.sh` iş kuyruklarını denetler, yedek alır, çalışan imajları `rollback-<eski-sha>` diye etiketler, yeni sürümü `BUILD_SHA` ile derleyip doğrular, eski sürüm hizmet verirken veritabanını günceller, servisleri yeniden başlatır ve API'nin yeni SHA ile hazır olmasını bekler. `scripts/rollback_local.sh --yes` gerekiyorsa şemayı indirir ve önceki imajlara döner. [Rehber, 5. bölüm](docs/guides/kurulum-ve-teslim-rehberi.md#5-yedekleme-güncelleme-ve-geri-alma).
- **Kalite kontrolleri komut satırında:** `python -m app.tools.quality_checks import` bir değerlendirme setini ekler (`--knowledge-base` ile başka bilgi tabanı adlarına eşler), `run --wait` bir çalıştırmayı kuyruğa koyup sonucu bekler ve geçmeyen soruları nedenleriyle yazar. Kabul testi tarayıcı oturumu olmadan da yapılabilir.
- **Bölüm bazlı parçalama (`section-v1`):** BGE-M3 nesli `plan --materialization section-v1` ile planlanabilir. Her Markdown bölümü, başına belge başlığı ve bölüm yolu yazılmış ayrı bir parça olur. Kısa politikaların içindeki kurallar artık aranabilir. Staging'de 25 soruluk Kalite setinde soru başına süre 5,8 sn'den 4,1 sn'ye indi; eski sürümler arşivlendiğinde 25/25. Varsayılan nesiller ve eski MiniLM yolu değişmedi. [BGE-M3 rehberi, 10. bölüm](docs/guides/bge-m3-staging-generation.md#10-bölüm-bazlı-parçalama-section-v1).
- **Demo kabul seti:** `demo/voice-knowledge-pack/quality-checks.json`, Kalite sayfasına içe aktarılabilen 25 soru (Türkçe ve İngilizce).
- **Belge sahibi ve gözden geçirme:** her belgenin bir sahibi ve bir gözden geçirme tarihi vardır. Belgeler tablosunda **Sahibi** ve **Gözden geçirme** sütunları ile **Süresi geçti**, **Yaklaşıyor** (30 gün ya da daha az) ve **Tarih yok** etiketleri görünür; sayfada **Tümü / Süresi geçenler / Yaklaşanlar / Tarihsiz** filtresi ve **Tüm Knowledge Base'ler** seçeneği vardır. Yeni yüklenen belgenin sahibi yükleyendir ve tarihi 12 ay sonrasıdır; **Belgeyi değiştir** ile yeni sürüm yüklemek gözden geçirme sayılır. Manager ve admin satırdaki **Gözden geçirildi** ile tarihi ileri alır, **Sahip ve tarih** ile sahibi Workspace üyeleri arasından seçer ve tarihi değiştirir. **Genel Bakış** onlara "Gözden geçirme bekleyen 3 belge" gibi bir satırla süresi geçmiş belgelerin listesini açar. Süresi geçmiş belge aramada kullanılmaya devam eder; yanıt ona dayanıyorsa kaynak kartında "Gözden geçirme tarihi geçmiş (dd.MM.yyyy)" uyarısı çıkar ve kayıtlı görüşmede de kalır. İşlemler denetim kaydına yalnızca kimlik numaraları ve tarihlerle yazılır. [Kılavuz](docs/guides/kurumsal-kullanim-kilavuzu.md#belge-sahibi-ve-gözden-geçirme).
- **Görüşmelerimi sil:** sesli asistanda görüşme seçicisinin yanında **Bu görüşmeyi sil** ve **Tüm görüşmelerimi sil** vardır. RAG Chat sayfası kendi sorularını saklamaz. Bu sayfada **Kayıtlı görüşmeleriniz** bölümü, Workspace'teki sesli asistan ve modAI Assistant görüşmelerini aynı iki işlemle listeler. İkisi de onay ister ve sorular ve yanıtlarla birlikte kalıcı olarak siler. **Tüm görüşmelerimi sil**, kullanıcının tüm Workspace'lerdeki görüşmelerini kapsar. Liste ve açık maskot paneli hemen güncellenir. Kullanıcı yalnızca kendi görüşmelerini silebilir. API: `DELETE /assistant/conversations/{id}` ve `DELETE /assistant/conversations` (isteğe bağlı `workspace_id`).
- **KVKK talepleri için yönetici araçları:** **Yönetim → Kullanıcılar** ve **Yönetim → Üyelikler** tablolarında her kişi için **Kişisel veri dökümü (JSON)** ve **Görüşmelerini sil** vardır.
  - Döküm: hesap, üyelikler, davetler, asistan tercihleri, tüm görüşmeler (soru ve yanıtlar, zamanlarıyla) ve yüklenen belgelerin adları. Parola özeti ve belirteçler dökümde yer almaz.
  - Platform yöneticisi her şeyi görür. Tenant yöneticisi yalnızca yönettiği Organization'ların üyelerini ve yalnızca o Organization'ların verilerini görür.
  - API: `GET /admin/users/{id}/personal-data` ve `DELETE /admin/users/{id}/conversations`.
  - Yanıtlanamayan sorular raporu kullanıcı kimliği saklamadığı için dökümde yer almaz.
- **Görüşme saklama süresi:** `CONVERSATION_RETENTION_DAYS` 0'dan büyükse worker günde bir kez, son etkinliği bu süreden eski görüşmeleri mesajlarıyla birlikte, gruplar hâlinde kalıcı olarak siler.
- Tüm silme ve döküm işlemleri denetim günlüğüne metin olmadan, yalnızca sayılarla yazılır: `assistant_conversation_deleted`, `assistant_conversations_deleted`, `personal_data_export`, `user_conversations_deleted` ve `conversation_retention_purge` (işlemi yapan: sistem).
- **KVKK değerlendirmesi için veri envanteri:** [docs/guides/kvkk-veri-envanteri.md](docs/guides/kvkk-veri-envanteri.md). Hangi kişisel verinin nerede, neden ve ne kadar süre tutulduğunu, nasıl silindiğini ve dışa aktarıldığını, erişim ve silme taleplerinin nasıl karşılanacağını anlatır.

### Değişen davranış
- **Belge sahibinin e-postası** yalnızca o Workspace'in manager ve admin'lerine gösterilir. User rolündekiler belgeler tablosunda **Sahibi** sütununu görmez; API de onlara sahibi göndermez. Gözden geçirme tarihi ve "Süresi geçti" uyarısı herkese görünmeye devam eder.
- **Altı aylık saklama:** denetim kayıtlarındaki IP adresleri 180 gün sonra silinir (kayıt kalır); `scripts/backup_local.sh` 180 günden eski yedekleri aynı klasörden siler; her servisin Docker logu en çok 5 × 10 MB tutulur. [Veri envanteri](docs/guides/kvkk-veri-envanteri.md).

### Düzeltildi
- API imajı yerel `.claude/` klasörünü de içeriyordu (5b6abf7e imajında 214 MB eski çalışma kopyası; gizli bilgi yoktu). Klasör artık derleme bağlamına alınmaz.
- "Bu belgedeki bilgiler … belirlemez" ya da "belgeler bundan bahsetmiyor" gibi ret yanıtları "belgede yanıt yok" sayılmıyordu; yanıtlanamayan sorular raporu ve Kalite paneli bunları artık doğru okuyor.
- Telefonda Modeller, Sistem ve Genel bakış sayfaları ile Knowledge Base kartları ekrandan taşıyordu: dar ekrandaki tek sütun, tek satırda tutulan uzun model ya da belge adına göre uzuyordu (390 px'lik ekranda sayfa 590–660 px'e çıkıyordu). Kolonunu yalnızca belli bir genişlikten sonra tanımlayan bütün ızgaralar artık ekranı aşmaz; `/chat` ve `/voice` bilgi tabanı listesinde, Kalite sayfasının sorularında, sonuçlarında ve soru formunda uzun dosya ve bilgi tabanı adları satır kırar. Yönetim sayfaları, giriş ve davet sayfası dahil yönlendirilen her sayfa 320 ve 390 px'te yana kaymaz. Masaüstü düzeni değişmedi.
- Sağ alttaki maskot, sayfanın son satırındaki düğmelerin üstüne biniyordu (örneğin 1440 px'te Kalite sayfasındaki **Arşivle**, telefonda `/voice` kaynak listesinin sonu). Her sayfanın altında artık maskot kadar boşluk kalır; sayfa sonuna kaydırılınca hiçbir düğme ya da alan maskotun altında kalmaz. Telefonda maskot daha küçüktür (48 px). Gizleme düğmesi ve sürükleme eskisi gibi çalışır.
- Türkçe sayfalarda kalan İngilizce etiketler Türkçeleştirildi: Modeller sayfasında "Model Manager", "Provider durumu", "Generation modeli", "Embedding modeli" ve "Quantization" yerine "Model yönetimi", "Sağlayıcı durumu", "Üretim modeli", "Vektör modeli" ve "Niceleme"; Sistem sayfasında "Release / Build" ve "Search / Retrieval Profile" yerine "Sürüm ve derleme" ve "Arama profilleri"; maskot panelinde "modAI Assistant · Local RAG" yerine "modAI Asistan · Yerel RAG".
- Roller API kodu olarak ("user", "manager", "admin") gösteriliyordu. Kenar çubuğu, Knowledge Base kartları, kaynak listeleri, yönetim ekranlarındaki rol seçimleri, davet listesi ve davet sayfası artık kullanım kılavuzundaki ve Kullanım Rehberi'ndeki adları gösterir: User, Manager, Admin. API değerleri değişmedi.
- Büyük harfle yazılan etiketlerde İngilizce sözcükler Türkçe kurala göre büyütülüyordu ("redis" → "REDİS"). İngilizce etiketler Türkçeleştirildi; Platform sayfasındaki bağımlılık adları (postgres, redis, qdrant) İngilizce olarak işaretlendi ve "REDIS" diye yazılır.

### Değişen ayarlar
- Migration `0013_document_review`: `documents` tablosuna `owner_user_id`, `review_due_on`, `reviewed_at` ve `reviewed_by_user_id` sütunları (kullanıcı silinince boşalır) ve canlı belgeler için `(workspace_id, review_due_on)` indeksi. Mevcut belgelerin sahibi yükleyen kişi olur, tarihleri boş kalır ("Tarih yok"). Dağıtımda `alembic upgrade head` gerekir.
- Yeni ortam değişkeni `DOCUMENT_REVIEW_DEFAULT_MONTHS` (varsayılan 12, 0–120): yeni yükleme, belge değiştirme ve **Gözden geçirildi** sonrası tarih bu kadar ay ileri alınır; `0` iken tarih verilmez.
- Yeni ortam değişkeni `CONVERSATION_RETENTION_DAYS`: varsayılan `0`, görüşmeleri silinene kadar tutar (önceki davranış). Değişiklik worker yeniden başlatılınca geçerli olur. Migration yoktur.
- Yeni ortam değişkeni `AUDIT_IP_RETENTION_DAYS` (varsayılan 180; `0` IP adreslerini süresiz tutar). Worker günde bir kez uygular; ilk çalıştırmada 180 günden eski kayıtların IP adresleri silinir.
- `scripts/backup_local.sh` kendi kabuğundan `BACKUP_RETENTION_DAYS` okur (varsayılan 180; `0` hepsini tutar). Değer geçersizse yedek alınmadan durur.
- Compose dosyalarına log döndürme eklendi (`x-logging`: json-file, 10 MB × 5). Ayar, kapsayıcı yeniden oluşturulunca geçerli olur: güncelleme betiği api, worker ve frontend'i yeniden oluşturur; PostgreSQL, Valkey ve Qdrant için bir kez `docker compose up -d postgres redis qdrant` çalıştırın (birkaç saniyelik kesinti, volume'lar korunur).

## v0.8.0 — Güven paketi: yanıtlanamayan sorular, kalite paneli ve okunur kaynaklar

11 Ekim 2026'da yayımlandı (main `5b6abf7e`). Kurulumda `alembic upgrade head` gerekir (0011 ve 0012).

### Yeni
- **Yanıtlanamayan sorular raporu:** çalışma alanının manager ve admin'leri **Yönetim → Yanıtlanamayan sorular** sayfasında modAI'ın belgelerden yanıtlayamadığı soruları görür: aynı soru tek satırda toplanır, neden (Belge bulunamadı, Tablo sınırında / çelişkili, Belgede yanıt yok (tahmini)) ve aranan bilgi tabanları gösterilir, özet satırı yanıtlanamama oranını verir. **Çözüldü**, **CSV indir** (Excel'de Türkçe karakterlerle açılır) ve yalnızca admin için **Tümünü sil** vardır. Soruyu kimin sorduğu kaydedilmez; yanıtlanan sorular için yalnızca günlük sayı tutulur. [Kılavuz](docs/guides/kurumsal-kullanim-kilavuzu.md#yanıtlanamayan-sorular).
- **Kalite paneli:** çalışma alanının manager ve admin'leri **Yönetim → Kalite** sayfasında kabul sorularını tutar: bilgi tabanları, beklenti ("Yanıt vermeli" ya da "Belgede yok demeli"), beklenen belge, gerekli ve yasak ifadeler. **Şimdi çalıştır** her soruyu kullanıcıların aldığı arama ve model yoluyla sorar ve puanlar. Puanlamada Türkçe büyük/küçük harf ve sayı biçimi (40.000 = 40,000 = 40000) gözetilir. Sayfa son sonucu ("18/20 soru geçti"), son 10 çalıştırmanın eğilimini ve geçmeyen her soruyu yanıtı, kaynakları ve nedeniyle gösterir. Değerlendirme seti JSON olarak içe aktarılabilir; isteğe bağlı bir gece çalıştırması vardır. Soru ve yanıt metni loglara yazılmaz, denetim kayıtlarında yalnızca sayılar tutulur. [Rehber, 3. bölüm](docs/guides/kurulum-ve-teslim-rehberi.md#3-kabul-testi-teslimden-önce).

### Düzeltildi
- Telefonda `/voice`, yanıtın kaynakları listelenince ekrandan taşıyor ve sağ tarafı kesiliyordu: dar ekrandaki tek sütun, kaynak kartında tek satırda tutulan belge adının genişliğine uzuyordu. Sütun artık ekranı aşmaz; `/voice` ve `/chat` 320 px'ten itibaren yana kaymaz, uzun sözcükler ve dosya adları balonlarda satır kırar. Masaüstü düzeni değişmedi.
- Kaynak panelindeki **Alıntıyı gör**, getirilen parçayı düz metin olarak döküyordu: Markdown tabloları tek satıra yığılıyor, `##` ve `**` işaretleri görünüyor, yanıtı hangi satırın desteklediği belli olmuyordu. Parça artık başlık, paragraf, liste ve tablo olarak gösterilir; eski sözcük parçalayıcısının tek satıra indirdiği tablolar da okunur. Yanıt tamamlanınca yanıtla aynı sayıyı (40.000 / 40,000 / 40000, "0–5" gibi aralıklar) ya da en az iki içerik sözcüğünü paylaşan satırlar işaretlenir ve önce **İlgili bölüm** olarak gösterilir; **Tamamını göster** parçanın tamamını işaretler korunarak açar. Eşleşen satır yoksa parçanın ilk 400 karakteri kadarı gösterilir. Belge metni HTML olarak değil, düz metin olarak işlenir.
- Türkçe sayfalarda İngilizce cümleler kalmıştı: `/voice` başlık açıklaması ("Your knowledge. Your infrastructure. Your voice assistant."), üst çubuk ("Local-first enterprise AI"), giriş sayfası ("Local-first RAG platform"), RAG Chat paneli ("Local RAG assistant") ve Sistem sayfasındaki sürüm durumu ("Synced", "Version mismatch", "Development build"). Hepsi Türkçeleştirildi; Knowledge Base, Workspace ve Organization gibi ürün terimleri değişmedi.

### Değişen ayarlar
- Migration `0011_unanswered_questions`: `unanswered_questions` (yanıtlanamayan sorunun metni, aranan bilgi tabanları, neden; kullanıcı yok) ve `question_daily_counts` (çalışma alanı ve gün başına soru sayıları) tabloları, boş başlar. Dağıtımda `alembic upgrade head` gerekir. Yeni ortam değişkenleri `UNANSWERED_REPORT_ENABLED` (varsayılan `true`; `false` iken hiçbir şey kaydedilmez) ve `UNANSWERED_RETENTION_DAYS` (varsayılan 90; kayıtlar ve sayılar bu süreden sonra silinir).
- Migration `0012_quality_checks`: `quality_checks`, `quality_runs` (çalışma alanı başına en fazla bir bekleyen ya da çalışan çalıştırma) ve `quality_results` tabloları. Dağıtımda `alembic upgrade head` gerekir. Çalıştırmalar worker'da, Valkey'deki `modai:quality:queued` kuyruğundan birer birer çalışır.
- Yeni ortam değişkenleri `QUALITY_QUESTION_TIMEOUT_SECONDS` (bir sorunun süre sınırı, varsayılan 120) ve `QUALITY_SCHEDULE_HOUR` (gece çalıştırmasının saati, 0–23, worker'ın yerel saati; boşsa kapalı). Her çalıştırma her soru için modeli bir kez çağırır; 16 GB makinede mesai dışına zamanlayın.

## v0.7.0 — Ağ kurulumu, toplu aktarım, arşiv ve arama profili paneli

10 Ekim 2026'da yayımlandı (main `cfd6ae86`). Kurulumda `alembic upgrade head` gerekir.

### Yeni
- **Ağdan çok kullanıcılı kurulum (HTTPS):** isteğe bağlı `docker-compose.tls.yml`, önüne Caddy koyar (443; 80'den yönlendirme). Şirket sertifikası, Caddy iç CA'sı ya da Let's Encrypt seçilebilir. Arayüz ve API yalnızca `127.0.0.1`'e bağlanır. API istemci IP'sini görür. `preflight.py` production ayarları için uyarır. [Rehber, 8. bölüm](docs/guides/kurulum-ve-teslim-rehberi.md#8-ağdan-çok-kullanıcılı-kurulum-https).
- **Toplu belge aktarımı:** Belgeler sayfasında **Klasör yükle**: seçilen klasördeki PDF, DOCX, TXT ve Markdown dosyaları 10'arlı gruplar hâlinde yüklenir; gizli, sistem, desteklenmeyen ve 10 MB'tan büyük dosyalar atlanır ve raporlanır. Yüzlerce belgeden büyük ilk taşımalar için komut satırı aracı `python -m app.tools.import_documents` (`--kb-from-folders`, `--dry-run`, CSV raporu); yeniden çalıştırılınca yüklenmiş belgeler atlanır. [Rehber, 9. bölüm](docs/guides/kurulum-ve-teslim-rehberi.md#9-toplu-belge-aktarımı).
- **Eski sürümü arşivleme:** yönetici bir belgeyi silmeden **Eski sürüm olarak arşivle** ile arşive alabilir. Arşivdeki belge hiçbir arama yolunda (MiniLM ve BGE-M3) kullanılmaz, tabloda "Arşivde" etiketiyle görünür ve geri alınabilir; işlemler denetim kaydına yazılır. Bir belgenin yeni sürümü için önerilen yol yine **Belgeyi değiştir**'dir. Mevcut belgeler arşivlenmez.
- **Yapı koruyan parçalama (`structured-v1`):** bir indeks nesli `plan --materialization structured-v1` ile planlanabilir. Satırlar, paragraflar ve Markdown tabloları korunur; sığmayan tablo satırlardan bölünür ve her parçada başlık tekrarlanır. Varsayılan `word-split-v1` ve eski MiniLM yolu değişmedi. Bkz. [BGE-M3 rehberi, 9. bölüm](docs/guides/bge-m3-staging-generation.md#9-yapı-koruyan-parçalama-structured-v1).
- **DOCX tabloları:** paragraflarla birlikte belge sırasında Markdown tablosu olarak çıkarılır. Önceden yalnızca paragraflar okunuyordu. Mevcut DOCX belgeleri yeniden indekslenene kadar etkilenmez.
- **Arama profili paneli:** çalışma alanı yöneticisi **Sistem** sayfasından BGE-M3 çok dilli aramayı hazırlar (**Hazırla**: worker kuyruğunda indeksleme ve doğrulama, ilerleme panelde), **Etkinleştir** ile açar ve **Geri al** ile MiniLM'e döner. Etkinleştirme ve geri alma, çalışma alanının adının yazılmasını ister. Komut satırı aracı `app.tools.retrieval_generation` yedek yol olarak aynı argümanlarla kalır.

### Düzeltildi
- HTTPS proxy arkasında Nginx, API'ye `https` yerine `http` bildiriyordu; `https://` adresinden oturum yenileme ve çıkış reddedilirdi. Nginx artık önündeki proxy'nin gönderdiği `X-Forwarded-Proto` değerini (`http`/`https`) iletir; başlık yoksa eskisi gibi kendi şemasını gönderir.
- `upload-batch` içinde tek bir dosya reddedilince tüm istek 500 hatası veriyordu; artık yalnızca o dosya atlanır.
- Belge kaydı veritabanında başarısız olduğunda 503 yerine 500 dönüyordu.
- Arayüzün Nginx'i 1 MB'tan büyük yüklemeleri 413 ile reddediyordu; `/api/` için sınır 25 MB'tır. Etkili olması için frontend imajı yeniden derlenir.
- Art arda gelen iki Markdown tablosu tablo aramasında tek tablo gibi okunuyordu.

### Değişen ayarlar
- Yalnızca HTTPS ek dosyasıyla kullanılan değişkenler: `MODAI_HOSTNAME`, `MODAI_TLS_MODE`, isteğe bağlı `MODAI_TLS_CERT_DIR` ve `MODAI_EDGE_SUBNET`.
- Migration `0009_document_archive`: `documents.archived_at` (boş olabilir) ve indeksi. Dağıtımda `alembic upgrade head` gerekir.
- Migration `0010_retrieval_jobs`: `retrieval_jobs` tablosu (çalışma alanı başına en fazla bir bekleyen ya da çalışan hazırlık). Yeni ortam değişkeni `RETRIEVAL_JOB_TIMEOUT_SECONDS` (varsayılan 21600, 6 saat). Hazırlıklar Valkey'deki `modai:retrieval:queued` kuyruğundan çalışır.

## v0.6.1 — Lisans uyumu ve İngilizce sayı düzeltmesi

- **Redis yerine Valkey:** kuyruk ve geçici veri için `valkey/valkey:8.1-alpine` (BSD-3-Clause) kullanılır. Redis 7.4 ve sonrası RSALv2/SSPLv1 lisanslıdır ve kurumsal hukuk incelemelerinde sorun çıkarabilir. Valkey aynı protokolü konuşur; kod değişikliği yoktur. Geçişten sonra kullanıcılar bir kez yeniden giriş yapar. Gerekçe: [lisanslama](docs/guides/lisanslama.md).
- **İngilizce binlik ayırıcı:** "40,000 TL" artık 40 bin TL olarak okunur; önceden 40 TL sayılıyor ve yanlış onay satırı veriliyordu.
- **Lisans veren:** WATAM — We Are The Art Makers ([wearetheartmakers.com](https://wearetheartmakers.com)).

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
