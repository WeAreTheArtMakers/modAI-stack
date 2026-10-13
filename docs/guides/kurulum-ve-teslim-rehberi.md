# modAI-stack kurulum ve teslim rehberi

Bu rehber, modAI-stack'i bir müşterinin makinesine kuracak ve pilot olarak teslim edecek kişi içindir. Komutların ayrıntıları README'de; burada doğru sıra ve teslim için kontrol edilecekler var.

Kapsam: tek kurulum, bir şirket. Müşteri belgeleri ve soruları müşterinin makinesinde kalır; yanıtlar host'taki Ollama ile üretilir.

## 1. Gereksinimler

Bu değerler Apple M1 Pro 16 GB üzerindeki ölçümlere dayanır.

| | En az | Önerilen | Not |
|---|---|---|---|
| Bellek | 16 GB | 32 GB | 16 GB'ta yalnızca bu yığın çalışmalı; ikinci bir yığın (ör. staging) ve çok sayıda tarayıcı sekmesi swap'a ve yavaş yanıta yol açar. |
| Docker bellek sınırı | 8 GiB | 8 GiB+ | Çok dilli arama (BGE-M3) açıkken API ve worker'ın her biri yaklaşık 2 GiB kullanır. |
| Disk | 15 GB boş | 30 GB+ boş | İmajlar, BGE-M3 (2,4 GB), ses modelleri, veri ve yedekler. |
| Ollama | kurulu | | Üretim modeli host'ta çalışır. `gemma3:4b` yaklaşık 4–4,6 GB bellek kullanır. |
| Tarayıcı | Chrome veya Edge (masaüstü) | | Mikrofon yalnızca `https://` ya da aynı makinede `http://localhost` üzerinde çalışır. |

## 2. Kurulum sırası

Müşteriye her zaman **çevrimdışı kurulum paketi** teslim edilir (aşağıda). Kod deposu WATAM'a özeldir; depodan kurulum yalnızca WATAM'ın kendi makinelerinde ve paket üretiminde kullanılır.

### Tek komutla kurulum (WATAM makineleri)

Docker (macOS'ta Docker Desktop) ve Ollama kurulu ve açıkken, depo klasöründe:

```bash
sh scripts/install.sh
```

Ağdaki çalışanların HTTPS ile bağlanacağı kurulum için şirket içi adla:

```bash
sh scripts/install.sh --hostname modai.sirket.local
```

- Betik gereksinimleri denetler ve yeni sırlarla `.env` yazar. Var olan `.env`'e dokunmaz.
- Dil modelini, ses, arama ve konuşma tanıma modellerini SHA-256 doğrulamasıyla indirir.
- **İndirme boyutu yaklaşık 8 GB:** dil modeli (gemma3:4b) 3,3 GB, arama modelleri 3,7 GB, konuşma tanıma 0,5 GB, ses 0,1 GB. Temiz kurulum denemesinde bağlantı 400 KB/s'ye düştü; bu hızda indirme saatler sürer. Müşteri bağlantısı yavaşsa modelleri önceden bir diskle getirin ("Adım adım", 3. madde): betik dosyaları doğrular ve yeniden indirmez.
- Ön kontrolü çalıştırır, imajları derler, veritabanını kurar ve servisleri başlatır.
- Etkileşimli terminalde ilk platform yöneticisini oluşturur ve adresi yazar.
- Yarıda kalırsa yeniden çalıştırılabilir; tamamlanan adımlar atlanır.
- `--tls acme` internetten erişilen bir ad için Let's Encrypt kullanır; `--tls files` şirket sertifikası içindir (8. bölüm).
- `--check` yalnızca gereksinimleri ve ön kontrolü çalıştırır.
- Terminal olmadan (uzaktan, bir betikle) çalışınca ilk yönetici oluşturulmaz. Bunun yerine bir **kurulum kodu** yazılır. Tarayıcıda modAI'yi ilk açan kişi bu kodla yöneticiyi, şirketi ve ilk workspace'i oluşturur. Kod yalnızca ilk yönetici oluşana kadar geçerlidir; yenisi için: `python3 scripts/setup_code.py && docker compose up -d api`.
- Kurulu gelen cihaz (modAI Kutusu): [modai-kutusu.md](../sales/modai-kutusu.md), hazırlama betiği `sh scripts/appliance_setup.sh --dry-run`.
- Aşağıdaki adımlar betiğin yaptıklarının elle karşılığıdır; çevrimdışı kurulumda ya da bir adımı ayrıca yapmak gerektiğinde kullanılır.

### Çevrimdışı paketle teslim (önerilir)

Müşteriye depo erişimi verilmez; bir sürüm **kurulum paketi** olarak teslim edilir. Paket internetsiz kurulur ve günceller.

**WATAM tarafında, paketi üretmek** (modellerin kurulu olduğu bir checkout'ta, sürüm etiketi seçiliyken):

```bash
sh scripts/package_release.sh --ref v1.7.0
```

- Çıktı `releases/modai-1.7.0/` klasörüdür. İçinde şunlar var:
  - kurulum, güncelleme, yedek ve destek betikleri, Compose dosyaları, rehberler ve demo belgeleri. **Uygulamanın kaynak kodu, testler ve iç satış belgeleri pakete girmez** (`package_tools.py prune-source`); uygulama imajların içinde çalışır;
  - sürümden derlenmiş imajlar ve üçüncü taraf imajları (`images/modai-images.tar.gz`);
  - doğrulanmış ses, arama, konuşma tanıma ve MiniLM dosyaları;
  - Ollama'dan alınan dil modeli, Modelfile'ı ve lisansı (`ollama/`);
  - `VERSION`, müşterinin ilk sayfası `KURULUM.md`, `LICENSES/` ve `SHA256SUMS`.
- **Boyut ve kopya:** paket modellerle yaklaşık 9 GB'tır. Büyük dosyalar APFS'te disk yemeyen kopyalardır. USB diske kopya tam boyutu yazar:
  ```bash
  cp -R releases/modai-1.7.0 /Volumes/USB/
  ```
  Tek dosya isterseniz `--archive /Volumes/USB/modai-1.7.0.tar` kullanın.
- **İşlemci mimarisi:** imajlar paketin üretildiği makinenin mimarisi içindir ve `VERSION` dosyasındaki `ARCH` satırında yazar. Apple silicon Mac `arm64` paket üretir; bu paket Apple silicon Mac'lerde ve ARM sunucularda çalışır. x86_64 sunucular için paketi bir x86_64 makinede üretin. `--platform linux/amd64` öykünmeyle çalışır ve çok yavaştır.
- **Modelsiz paket:** `--without-models` ile paket yaklaşık 2 GB olur. Kurulum bu durumda arama ve dil modellerini internetten indirir.
- **Gemma koşulları:** dil modeli pakete girdiği için Gemma Terms of Use `LICENSES/` altına konur. `KURULUM.md` kullanım kısıtlarını müşteriye iletir ([lisanslama](lisanslama.md), 4. bölüm).

**Müşteri tarafında:** klasör kalıcı bir yere kopyalanır (`/opt/modai`, `~/modai`) ve orada `sh scripts/install.sh` çalıştırılır. Betik paketi tanır:

1. dosyaları `SHA256SUMS` ile doğrular;
2. işlemci mimarisini denetler;
3. imajları yükler;
4. modelleri ağsız doğrular;
5. dil modeli eksikse `ollama create` ile paketten ekler.

Yeni `.env` `COMPOSE_PROJECT_NAME=modai` içerir; veriler klasör adına bağlı kalmaz.

### Lisans anahtarı

Kurulum lisanssız çalışmaz: lisans girilene kadar yalnızca giriş, ilk kurulum ve **Lisans** ekranı açılır. Anahtarı WATAM imzalar; kurulum onu internete çıkmadan doğrular. Lisans sunucusu yoktur.

- **Anahtarın içeriği:** lisans sahibi (sözleşmedeki unvan), paket (Pilot, Business, Enterprise), bitiş tarihi, en fazla etkin kullanıcı sayısı ve isteğe bağlı olarak bir kurulum kimliği.
- **Kurulum kimliği:** **Yönetim → Lisans**'ta görünür. Yıllık lisans bu kimliğe bağlanır; anahtar başka bir kurulumda çalışmaz. Pilot anahtarı kimliksiz verilebilir: müşteri paketi kurar kurmaz kullanır.
- **Bitiş:** bitişten 30 gün önce platform yöneticilerine uyarı gösterilir. Bitişten sonra 14 gün ek süre vardır; ardından yanıtlar ve talepler durur. Veriler silinmez; yeni anahtar girildiği anda her şey kaldığı yerden çalışır.
- **Kullanıcı sınırı:** yalnızca yeni hesap açılırken uygulanır (davet, kayıt, SCIM, Active Directory ve SSO ile ilk giriş). Devre dışı bırakılan ve silinen hesaplar sayılmaz.
- **Saat:** kurulum gördüğü en geç tarihi saklar; bilgisayarın saatini geri almak lisansı uzatmaz.
- **Anahtar:** WATAM sözleşme ya da pilot onayıyla aynı gün üretir ve e-postayla gönderir. Anahtar gizli bir parola değildir ama sözleşmeye bağlıdır; üçüncü kişilerle paylaşılmaz.

**Paketten güncelleme:** yeni paket kurulum klasörünün üzerine kopyalanır (`cp -R /Volumes/USB/modai-<yeni>/. /opt/modai/`; `.env` ve `data/` korunur). Ardından `sh scripts/upgrade_local.sh` çalıştırılır. Betik paketi doğrular, imajları derlemek yerine yükler; yedek, geri alma etiketleri ve migration git'teki gibidir. Geri alma da aynıdır: `sh scripts/rollback_local.sh --yes`.

### Adım adım

1. **Kaynak:** sürüm etiketindeki depoyu alın. Model ağırlıkları depoda yoktur.
2. **Ayarlar:** `cp .env.example .env`. Yeni ve rastgele bir `POSTGRES_PASSWORD` ve `JWT_SECRET` üretin; örnek değerler kabul edilmez. `OLLAMA_MODEL` değerini kullanılacak modele ayarlayın. İlk yönetici oluşturulduktan sonra `ALLOW_REGISTRATION=false` yapın.
3. **Modeller:**
   ```bash
   ollama pull gemma3:4b
   ```
   ```bash
   python3 scripts/fetch_voice_models.py
   ```
   ```bash
   python3 scripts/fetch_retrieval_models.py
   ```
   ```bash
   python3 scripts/fetch_transcription_models.py
   ```
   Son komut konuşma tanıma modelini (faster-whisper small, yaklaşık 490 MB) indirir. Bu model hem ses ve video belgelerinin dökümünde hem de sesli asistanda sunucuda konuşma tanımada kullanılır. İndirilmezse ses ve video yüklemeleri "konuşma tanıma modeli kurulu değil" diye reddedilir ve sesli asistan tarayıcıda Whisper Tiny ile çalışır; diğer belgeler etkilenmez. Taranmış PDF ve görseller için OCR (Tesseract, Türkçe ve İngilizce) API imajıyla gelir, ayrı indirme gerekmez.
   MiniLM için README'deki "Embedding modeli" bölümündeki `prefetch_embedding_model` adımını uygulayın. İndirme betikleri her dosyanın boyutunu ve SHA-256'sını kilit dosyasıyla karşılaştırır. Çevrimdışı kurulumda bu dosyalar başka bir makinede indirilip `models/` ve `frontend/public/voice-models/` altına kopyalanır, sonra `--check` ile doğrulanır.
4. **Ön kontrol:**
   ```bash
   python3 scripts/preflight.py
   ```
   `FAIL` satırı kalmamalıdır. `WARN` satırları müşteriyle konuşulur ve teslim notuna yazılır. Betik parola ve anahtar değerlerini yazdırmaz.
5. **Başlatma:**
   ```bash
   BUILD_SHA="$(git rev-parse HEAD)" docker compose up -d --build
   ```
   ```bash
   docker compose exec api alembic upgrade head
   ```
6. **İlk yönetici:** `docker compose exec api python -m app.tools.bootstrap_admin` komutunu etkileşimli terminalde çalıştırın. Parola komut satırına yazılmaz.
7. **Yapı:** Organization, Workspace ve Knowledge Base'leri [kurumsal kullanım kılavuzu](kurumsal-kullanim-kilavuzu.md)'na göre oluşturun ve kullanıcıları davetle ekleyin.
8. **Belgeler:** müşteri belgelerini yükleyin ve hepsinin "hazır" olmasını bekleyin. Çok sayıda belge için [9. Toplu belge aktarımı](#9-toplu-belge-aktarımı) bölümüne bakın.
9. **Çok dilli arama (Türkçe kullanımda zorunlu):** her çalışma alanına BGE-M3 nesli kurulur. Bu iki şey için gerekli:
   - Türkçe soruların Türkçe ve İngilizce belgelerde doğru kaynağı bulması;
   - belgede olmayan bir soruya "belge bulamadım" denmesi.

   Varsayılan MiniLM yalnızca İngilizce bir modeldir. 13 Ekim 2026 ölçümünde Türkçe belgelerde cevabı belgede olan sorular 0,13'e kadar düşük puan aldı, konu dışı sorular 0,63'e kadar yüksek puan aldı. Bu modelle ilgililik tabanı konulamaz. BGE-M3'te ise cevaplanabilir sorular 0,556–0,768, konu dışı sorular 0,33–0,51 aldı; taban 0,50'dir (`RAG_RELEVANCE_FLOOR`). Panel, komutlar ve güvenceler [bge-m3-staging-generation.md](bge-m3-staging-generation.md)'dedir.
   - Çalışma alanı yöneticisi olarak kenar çubuğunda çalışma alanını seçin ve **Sistem** sayfasındaki **Arama profili** paneline gidin.
   - **Hazırla**'ya basın. Worker her belgeyi BGE-M3 ile indeksler ve doğrular; panel ilerlemeyi gösterir. "Son hazırlık: Tamamlandı" ve "Hazır" görülene kadar bekleyin.
   - **Etkinleştir**'e basın ve onay penceresine çalışma alanının adını yazın. Panelde "Çok dilli (BGE-M3)" ve 0 gecikme görülmelidir.
   - Bu adım için `RETRIEVAL_GENERATIONS_ENABLED=true` ve `alembic upgrade head` gerekir.
   - Yedek yol: worker konteynerinde sırayla `plan`, `build`, `validate`, `activate` komutları. `status` çıktısında `serving_mode: generation` ve boş `lag` görülmelidir.
10. **Ses:** `/voice` sayfasında **Konuşma tanıma** seçiminde "Sunucu · Whisper Small (önerilen)" seçili olmalıdır (sunucu modeli kurulu demektir). **Ses modelini hazırla**'ya basılır; yalnızca Türkçe ses modeli indirilir. Tarayıcıda çalışan Whisper Tiny ve Base seçenek olarak kalır. Ayrıntılı kontrol: [sesli asistan kabul listesi](sesli-asistan-kabul-listesi.md).

## 3. Kabul testi (teslimden önce)

Kabul soruları **Kalite** sayfasında tutulur ve teslimden sonra da orada kalır: belgeler ya da ayarlar değiştikçe aynı sorular yeniden çalıştırılır ve gerilemeler yakalanır. Sayfa kenar çubuğunda **Yönetim → Kalite**'dedir ve çalışma alanının manager ve admin'lerine görünür.

1. **Sorular:** müşteriyle birlikte, belgelerinden yanıtı bilinen 10 soru hazırlayın. En az 2 sayısal tablo sorusu, 1 İngilizce belge sorusu ve belgelerde yanıtı olmayan 1 soru olmalı.
2. **Girme:** her soruyu **Soru ekle** ile girin.
   - **Bilgi tabanları:** sorunun arandığı bilgi tabanları.
   - **Beklenti:** "Yanıt vermeli"; belgelerde yanıtı olmayan soru için "Belgede yok demeli".
   - **Beklenen belge** (isteğe bağlı): yanıtın kaynakları arasında olması gereken dosya adı.
   - **Beklenen ifadeler:** her satır bir gruptur ve her grup gereklidir. Seçenekler " | " ile ayrılır ve biri yeter, örneğin `16 iş günü | 16 gün`. Büyük/küçük harf ve İ/ı farkı yok sayılır. Sayılar biçimden bağımsız eşleşir (40.000, 40,000 ve 40000 aynıdır); 40, 140'ın ya da 40.000'in içinde bulunmaz.
   - **Yasak ifadeler:** örneğin eski politikadaki değer. "Yanıt vermeli"de yanıtın ilk cümlesinde, "Belgede yok demeli"de yanıtın hiçbir yerinde geçmemelidir.
   - Hazır bir değerlendirme seti **JSON içe aktar** ile eklenebilir. Biçim sayfada gösterilir; bilgi tabanları adlarıyla yazılır ve eklenemeyen satırlar raporlanır.
3. **Çalıştırma:** **Şimdi çalıştır**'a basın. Worker soruları kullanıcıların kullandığı arama ve modelle tek tek sorar; sayfa ilerlemeyi gösterir. 16 GB bir makinede 10 soru birkaç dakika sürer.
4. **Sonuç:** "10/10 soru geçti" ve altında **Güvenlik testleri** (istem enjeksiyonu) görülmelidir. Geçmeyen sorular listenin başındadır; her biri yanıtı, kaynakları ve nedeniyle ("Yanlış kaynak", "Beklenen ifade yok", "Gereksiz 'bilmiyorum'" gibi) gösterilir. Nedeni giderin (eski belgeyi arşivleyin, bilgi tabanını düzeltin ya da beklentiyi düzeltin) ve yeniden çalıştırın. "Gereksiz 'bilmiyorum'" ve "Belgede olmayanı yanıtladı" modelin ilk cümlesinden okunur, yani tahmindir; yanıt metnine bakarak doğrulayın.
5. **Gece çalıştırması (önerilir):** `.env`'de `QUALITY_SCHEDULE_HOUR` ayarlayın (0–23, worker'ın yerel saati; konteynerde `TZ` ayarlı değilse UTC). Worker o saat içinde, sorusu olan ve son 20 saatte çalıştırılmamış her çalışma alanı için bir çalıştırma başlatır. Bir çalıştırma her soru için modeli bir kez çağırır ve bu sırada makine yavaşlar. Bu yüzden 16 GB bir makinede çalıştırmaları mesai dışına zamanlayın, örneğin `QUALITY_SCHEDULE_HOUR=2`. Tek bir sorunun süre sınırı `QUALITY_QUESTION_TIMEOUT_SECONDS`'tır (varsayılan 120 sn).

**Komut satırından (isteğe bağlı):** tarayıcı oturumu olmadan da aynı içe aktarma ve çalıştırma yapılabilir. Demo belge paketiyle gelen 25 soruluk set, örneğin tek bir "Atlasnova Demo" bilgi tabanına şöyle eklenir ve çalıştırılır:

```bash
docker compose cp demo/voice-knowledge-pack/quality-checks.json api:/tmp/quality-checks.json
docker compose exec -T api python -m app.tools.quality_checks import --workspace-id 1 --file /tmp/quality-checks.json --knowledge-base "Atlasnova Demo"
docker compose exec -T api python -m app.tools.quality_checks run --workspace-id 1 --wait
```

- `--knowledge-base` her satırın bilgi tabanlarının yerine geçer; verilmezse satırlardaki adlar kullanılır.
- `run --wait` sonucu bekler ve toplamı, soru başına medyan süreyi ve geçmeyen her soruyu nedeni ve yanıtın başıyla yazar. Tüm sorular geçerse çıkış kodu 0'dır.
- Sorular ve çalıştırmalar Kalite sayfasında da görünür. Kayıtlarda işlemi yapan "sistem"dir.

Ayrıca:

- 30 dakikadan uzun süren bir oturumda oturum kapanmamalı; çıkış yapınca oturum gerçekten kapanmalı.
- `/voice`'ta en az 3 soru sesli sorulmalı. Sayfadan çıkıp dönüldüğünde görüşme geri gelmeli.
- Sonuçları teslim notuna yazın: Kalite sayfasındaki son çalıştırmanın ekran görüntüsü ve geçmeyen her sorunun nedeni.
- **Güven raporu:** **Yönetim → Güven raporu → PDF olarak kaydet** ile kurulum, erişim, saklama, kalite, güvenlik testleri ve kullanımın tek sayfalık özetini teslim notuna ekleyin.
- **Güvenlik testleri:** her çalıştırma 9 sabit istem enjeksiyonu senaryosunu da sorar (`QUALITY_SECURITY_CHECKS=true`, varsayılan). Senaryolar uydurma metinlerdir ve hiçbir bilgi tabanına eklenmez. Gemma 3 4B ile ölçülen: savunmalar olmadan 4/8, bu sürümle 8/9; geçmeyen tek senaryo, hiçbir kalıba uymayan ince bir bağlantı kuralıdır (model bağlantıyı yanıta ekler). Sonucu müşteriye olduğu gibi gösterin; belge yükleme yetkisini güvenilir kişilerle sınırlamasını önerin.

## 4. Güvenlik kontrolleri

- Ağdan yalnızca web arayüzüne (5173) ve gerekiyorsa API'ye (8000) erişilmelidir. PostgreSQL (55432), Valkey/Redis uyumlu kuyruk (6379) ve Qdrant (6333) yalnızca `127.0.0.1`'e bağlı olmalıdır. Sağlanan `docker-compose.yml` bunları `127.0.0.1:` önekiyle bağlar; yerelde değiştirildiyse kontrol edin. HTTPS ek dosyası kullanılıyorsa (8. bölüm) ağdan yalnızca 80 ve 443 açıktır; 5173 ve 8000 de `127.0.0.1`'e bağlanır.
- **Birden fazla kullanıcının ağdan erişeceği kurulumlarda** [8. bölüm](#8-ağdan-çok-kullanıcılı-kurulum-https) uygulanır:
  - TLS sonlandıran bir ters proxy kullanılır (`docker-compose.tls.yml`).
  - `APP_ENV=production` ve `REFRESH_COOKIE_SECURE=true` ayarlanır.
  - `TRUSTED_FRONTEND_ORIGINS` yalnızca gerçek adresi içerir.
  - Bu yapılmazsa mikrofon çalışmaz ve oturum çerezleri şifresiz bağlantıdan gider.
- `.env`, model klasörü ve yedekler erişimi sınırlı bir yerde tutulur ve depoya eklenmez.
- **KVKK değerlendirmesi için** hangi kişisel verilerin nerede ve ne kadar süre tutulduğu, erişim ve silme taleplerinin nasıl karşılanacağı [veri envanterinde](kvkk-veri-envanteri.md) anlatılır. Görüşmelerin saklama süresini müşteriyle birlikte belirleyip `CONVERSATION_RETENTION_DAYS` ile ayarlayın; varsayılan 180 gündür (6 ay), `0` görüşmeleri silinene kadar tutar. Denetim kayıtlarındaki IP adresleri, yedekler ve Docker logları varsayılan olarak 6 ay tutulur (`AUDIT_IP_RETENTION_DAYS`, `BACKUP_RETENTION_DAYS`, compose log döndürmesi).
- **Yanıt izi:** her yanıtın hangi belge sürümlerine dayandığı, soran hesap ve sonuçla birlikte tutulur; soru ve yanıt metni tutulmaz. Süre `ANSWER_TRACE_RETENTION_DAYS` (varsayılan 180 gün, `0` kapatır). Platform yöneticisi **Yönetim → Denetim günlüğü → Yanıt izi**'nde görür; workspace yöneticileri belge başına sayıları kişisiz görür.
- **Belgedeki gizli talimatlar:** belgelerdeki HTML ve Markdown yorumları ile yapay zekâya hitap eden cümleler ("Asistana not:", "Ignore all previous instructions") modele gönderilmeden çıkarılır; kullanıcıya gösterilen kaynak metin değişmez. Bu bir kalıp listesidir, tam koruma değildir; Kalite sayfasındaki güvenlik testleri ne kadarının tutulduğunu ölçer.

## 5. Yedekleme, güncelleme ve geri alma

- **Yedekleme:** `scripts/backup_local.sh <klasör>`. Geri yükleme sırası README'deki "Yedekleme ve geri yükleme" bölümündedir.
- **Güncelleme:** paketle kurulumda yeni paket klasörün üzerine kopyalandıktan sonra, git checkout'unda `git pull` sonrası tek komut:
  ```bash
  sh scripts/upgrade_local.sh data/backups
  ```
  - Betik sırayla şunları yapar ve bir adım başarısız olursa durur:
    1. iş kuyruklarının boş olduğunu doğrular;
    2. yedek alır;
    3. çalışan imajları `rollback-<eski-sha>` diye etiketler;
    4. yeni imajları `BUILD_SHA` ile derler (paketle kurulumda paketten yükler) ve doğrular;
    5. eski sürüm hizmet verirken veritabanını yeni imajla günceller (`alembic upgrade head`);
    6. api, worker ve frontend'i yeniden başlatır ve API'nin yeni SHA ile hazır olmasını bekler.
  - HTTPS ek dosyasıyla çalışan kurulumda önce `export COMPOSE_FILE=docker-compose.yml:docker-compose.tls.yml` verin; betik düz `docker compose` kullanır.
  - Neyin değiştiği `data/upgrades/last-upgrade.env` dosyasına yazılır.
- **Yedek doğrulama tatbikatı:** `sh scripts/restore_drill.sh data/backups/<yedek>` komutu yedeğin veritabanını ve arama dizinini iki geçici, ağsız konteynere geri yükler. Kayıt ve vektör sayılarını çalışan kurulumla karşılaştırır, sonra konteynerleri siler. Çalışan sisteme dokunmaz. 13 Ekim 2026'da üretim yedeğinde 36 tablo ve iki arama koleksiyonu 12 saniyede, sayılar eşleşerek geri yüklendi. Ayda bir çalıştırın ve sonucu saklayın.
- **Yedek sunucu (sıcak bekleme):** ikinci bir makineye aynı sürüm kurulur ve `touch data/STANDBY` ile yedek sunucu olarak işaretlenir. Ardından her gece `sh scripts/standby_sync.sh <ayna klasörü>` çalışır ve ana makinenin aynadaki en yeni yedeğini kendine geri yükler.
  - Ana makine arızalanırsa: yedek sunucuda `rm data/STANDBY` çalıştırılır, çalışanların açtığı ad (DNS ya da `modai.local`) yedek sunucuya yönlendirilir.
  - Kaybedilen veri yalnızca son yedekten sonraki kısımdır (gece yedeğiyle en çok bir gün).
- **Yedekten geri yükleme:** `sh scripts/restore_local.sh <yedek klasörü> --yes`. Önce `--dry-run` ile bakın.
  - Disk ya da makine arızasında aynı sürüm yedek makineye `install.sh` ile kurulur ve yedek geri yüklenir.
  - `.env` dosyası ve `models/` klasörü yedekte yoktur; ayrıca kopyalayın. Aynı `JWT_SECRET` ile oturumlar da korunur.
  - Betik sırayla şunları yapar: mevcut durumun güvenlik yedeğini alır, veritabanını, arama dizinini ve belgeleri yedektekilerle değiştirir, şemayı günceller ve API'nin hazır olmasını bekler.
  - İlk müşteride bir yedek makineyle tatbikat yapın ve süreyi teslim tutanağına yazın.
- **Eski geri alma imajları:** her güncelleme, son iki geri alma setini (`ROLLBACK_KEEP`, yalnızca betiğin kabuğundan okunur) tutar ve daha eskileri siler. Her set yaklaşık 4,5 GB'tır.
- **Geri alma:** `sh scripts/rollback_local.sh --yes`
  - Güncelleme veritabanını değiştirdiyse önce yeni imajla eski sürüme indirir. Güncellemenin eklediği sütun ve tablolar, içlerindeki verilerle birlikte silinir.
  - Ardından `rollback-<eski-sha>` imajlarını başlatır ve API'nin eski SHA ile hazır olmasını bekler.
- **Bakım takvimi:**
  - **Gece yedeği kendiliğinden:** kurulum betiği `sh scripts/schedule_maintenance.sh` ile her gece 03:15'te yedek alan bir iş kurar (Linux'ta cron, macOS'ta launchd; `--status`, `--remove`). Yedekler katmanlı tutulur: son 48 saatin hepsi, 14 gün günlük, 8 hafta haftalık, 6 ay aylık (yaklaşık 28 yedek; `scripts/prune_backups.py`, `BACKUP_KEEP_DAILY/WEEKLY/MONTHLY`). Bir yedek demo kurulumunda yaklaşık 660 MB tuttu; 180 gecelik yedek katmansız 120 GB ederdi. Yedekleri ikinci bir diske kopyalayın: `.env`'de `BACKUP_MIRROR_DIR=/Volumes/Yedek/modai` (ya da bağlı bir ağ klasörü) her yedeği oraya da yazar ve orada da aynı katmanlarla seyreltir. Kopya yazılamazsa (disk takılı değil) gece logunda hata görünür, asıl yedek yine alınır.
  - Altı ayda bir en az bir güncelleme yapın ya da `docker compose up -d --force-recreate` çalıştırın: Docker logları kapsayıcı yeniden oluşturulunca silinir (veri envanteri, 10. bölüm).
  - Kalite kontrollerini her gece çalıştırmak için `.env`'de `QUALITY_SCHEDULE_HOUR` (örneğin `2`) ve yerel saat için `TZ=Europe/Istanbul` ayarlayın.
- **Arama profilini geri alma:** Arama profili panelindeki **Geri al** (ya da `rollback` komutu) çalışma alanını tek adımda MiniLM'e döndürür. Yeniden indeksleme gerekmez.

### Üretim modelini değiştirme

Platform yöneticisi **Modeller → Üretim modeli seçimi**'nde Ollama'da yüklü bir modeli önce bir çalışma alanının Kalite soruları ve güvenlik testleriyle **Sına**, sonra **Etkinleştir** ile seçer; yeniden başlatma ve yeniden indeksleme gerekmez. Komut satırından aynı sınama: `docker compose exec -T api python -m app.tools.quality_checks run --workspace-id 1 --model qwen3.5:9b --wait`.

- Her modele `think: false` (düşünme modu kapalı) ve `num_ctx` = `OLLAMA_NUM_CTX` (8192) gönderilir. Bu olmadan qwen3.5:9b 256K bağlamla 16 GB yer kapladı ve dokuz kısa yanıt on dakika sürdü; 8192 ile 5,8 GB ve yanıt başına yaklaşık 5 saniye.
- `OLLAMA_MAX_MODEL_BYTES` (varsayılan 8 GB) üstündeki modeller sunulmaz. 16 GB bir makinede tek üretim modeli bellekte tutulur; seçimden sonra önceki model boşaltılır. Sınamayı mesai dışında yapın: sınama sırasında kullanıcılar etkin modeli kullanmaya devam eder ve iki model bir süre birlikte bellekte olabilir.
- Q2 gibi çok sıkıştırılmış modeller (ör. 3 GB'lık 4.6B Q2_K) Türkçe yanıtta istemi geri yazma gibi hatalar yaptı; kararı Kalite sonucuna göre verin.

### Disk ve kapasite

- **Disk:** belgelerin saklandığı diskte boş alan %15'in ya da 15 GB'ın altına inince platform yöneticileri konsolda uyarı görür; 5 GB'ın altında yeni yüklemeler durur, yanıtlar ve yedekler çalışmaya devam eder (`DISK_WARNING_FREE_RATIO`, `DISK_WARNING_FREE_BYTES`, `DISK_CRITICAL_FREE_BYTES`). macOS'ta (Docker Desktop) kart Docker'ın sanal diskini ölçer; Mac'in kendi diski ayrıca dolabilir ve Docker'ı durdurabilir. Mac'te boş alanı `df -h /System/Volumes/Data` ile izleyin; ön kontrol ve destek paketi Mac'in boş alanını da yazar.
- **Kapasite:** **Sistem → Kapasite (son 7 gün)** yanıt sürelerini ve en yoğun saati gösterir, gerekirse donanımı büyütmeyi önerir. Teslimden önce müşterinin makinesinde yük testi çalıştırın (mesai dışında): `docker compose exec -T api python -m app.tools.load_test --workspace-id 1`. Ölçülen değerler ve donanım tablosu: [Kapasite ve donanım](kapasite-ve-donanim.md).

## 6. Destek için toplanacak bilgiler

```bash
sh scripts/support_bundle.sh
```

`data/support/modai-destek-<tarih>.tar.gz` dosyası sürüm, servis durumu, disk, bellek, ön kontrol ve son 24 saatin hata satırlarını içerir. Parola, belirteç, belge içeriği, soru ve yanıt metni içermez; IP ve e-posta adresleri maskelenir. `.env` dosyasını destek talebine eklemeyin. Destek süreleri ve güncelleme taahhütleri: [Destek ve güncelleme politikası](destek-ve-guncelleme-politikasi.md).

## 7. Müşteriye söylenecek sınırlamalar

- Yanıtlar belgelerden üretilir, ama model yanlış satırı ya da belgeyi seçebilir; önemli kararlardan önce kaynak kartı kontrol edilmelidir.
- Eski ve güncel politika belgeleri birlikte yüklenirse sistem hangisinin geçerli olduğunu bilemez; eski sürüm Belgeler sayfasında **Eski sürüm olarak arşivle** ile arşivlenmelidir (listede kalır, yanıtlarda kullanılmaz).
- PDF ya da birleşik hücreli tablolar ve hesaplama gerektiren sorular desteklenmez.
- Ses tanıma gürültülü ortamda zayıflar; "Göndermeden önce soruyu göster" açık kalmalıdır.
- 16 GB makinede ilk yanıt birkaç saniye sürer; yanıt uzunsa okunması da sürer.
- Toplantı tutanağı otomatik bir taslaktır: küçük model bazen bir maddeyi atlar ya da sorumluyu yanlış okur. Kaydetmeden önce okunmalıdır. Bir saatlik kayıt birkaç dakika sürer ve kalite çalıştırmasıyla aynı sırayı bekler.
- Belgeye gizlenmiş, yapay zekâya hitap etmeyen ince talimatlara küçük model uyabilir (Kalite → Güvenlik testleri); belge yükleme yetkisi güvenilir kişilerde olmalıdır.

## 8. Ağdan çok kullanıcılı kurulum (HTTPS)

Farklı departmanlardaki çalışanlar modAI'yi kendi bilgisayarlarından açacaksa kurulum HTTPS ve production modunda çalışmalıdır:

- Tarayıcı mikrofonu yalnızca güvenli bağlantıda açar. Düz HTTP ile ağ adresinden `/voice` çalışmaz.
- Oturum çerezi `Secure` olur ve yalnızca HTTPS üzerinden gider.

`docker-compose.tls.yml` ek dosyası önüne Caddy ters proxy'sini koyar. Bu dosya kullanılmadıkça hiçbir şey değişmez.

```
tarayıcı ──https (443)──▶ caddy ──http──▶ frontend (nginx) ──http──▶ api
```

- Ağdan yalnızca 443 açıktır. 80 yalnızca `https://` adresine yönlendirir.
- Arayüz (5173) ve API (8000) yalnızca bu makinede, `127.0.0.1` üzerinden erişilebilir kalır.
- Caddy, arayüz ve API ayrı bir iç Docker ağında (`edge`) konuşur. API, istemci adresini ve şemayı bildiren başlıklara (`X-Forwarded-For`, `X-Forwarded-Proto`) yalnızca bu ağdan gelince güvenir. Böylece hız sınırları ve denetim kaydı çalışanın gerçek IP'sini görür.
- Caddy veritabanı ağında değildir.

### 8.1 Ad ve sertifika seçimi

**Ad (`MODAI_HOSTNAME`):** çalışanların tarayıcıya yazacağı ad, ör. `modai.sirket.local`.

- Şirket DNS'inde bu makinenin IP adresine çözülmelidir; kaydı BT ekibi ekler.
- IP adresi yerine ad kullanın. Ad değişirse sertifika ve `.env` yeniden düzenlenir.

**Sertifika modu (`MODAI_TLS_MODE`):**

| Mod | Ne zaman | İstemci bilgisayarlarda |
|---|---|---|
| `files` | Şirketin kendi sertifika otoritesi (ör. Active Directory Sertifika Hizmetleri) var. Önerilen. | Bir şey gerekmez; şirket CA'sına zaten güvenilir. |
| `internal` | Şirket CA'sı yok, ad yalnızca iç ağda geçerli. | Caddy'nin kök sertifikası her bilgisayara bir kez kurulur (8.3). |
| `acme` | Ad herkese açık bir alan adı ve makine internetten 80/443 portlarında erişilebilir. | Bir şey gerekmez (Let's Encrypt). Kapalı şirket ağlarında genellikle uygun değildir. |

`files` modunda BT ekibinden `MODAI_HOSTNAME` adını içeren (SAN) bir sunucu sertifikası istenir.

- Sertifika ara sertifikalarla birlikte PEM olarak `certs/modai.crt` dosyasına konur.
- Anahtar parolasız PEM olarak `certs/modai.key` dosyasına konur.
- Klasör `MODAI_TLS_CERT_DIR` ile değiştirilebilir. Caddy klasörü salt-okunur bağlar. `certs/` Git'e ve Docker imajlarına girmez.
- Sertifika yenilendiğinde dosyalar değiştirilir ve `docker compose restart caddy` çalıştırılır.

### 8.2 Ayarlar ve başlatma

1. Yedek alın (`scripts/backup_local.sh <klasör>`) ve çalışan imajları etiketleyin (5. bölüm).
2. `.env` dosyasında aşağıdaki değerleri ayarlayın. `.env` dosyasını kimseyle paylaşmayın.
   ```
   APP_ENV=production
   REFRESH_COOKIE_SECURE=true
   TRUSTED_FRONTEND_ORIGINS=https://modai.sirket.local
   ALLOW_REGISTRATION=false
   JWT_SECRET=<yeni rastgele değer: openssl rand -hex 32>
   MODAI_HOSTNAME=modai.sirket.local
   MODAI_TLS_MODE=files
   COMPOSE_FILE=docker-compose.yml:docker-compose.tls.yml
   ```
   - `JWT_SECRET` değişince herkes bir kez yeniden giriş yapar.
   - `COMPOSE_FILE` satırı bu klasördeki her `docker compose` komutuna ek dosyayı da ekler; README ve kontrol listelerindeki komutlar aynen çalışır. Bu satır olmadan çalıştırılan bir `docker compose up`, HTTPS'siz düzene döner.
   - `MODAI_EDGE_SUBNET` (varsayılan `172.31.250.0/24`) şirket ağıyla çakışıyorsa başka bir özel alt ağ yazın.
3. Ön kontrol: `python3 scripts/preflight.py`. "network (multi-user) use" satırlarında `WARN` kalmamalıdır.
4. Makinede 80 ve 443 portları boş olmalı, güvenlik duvarı bu iki portu şirket ağına açmalıdır. Docker Compose 2.24.4 veya üstü gerekir (`docker compose version`).
5. Başlatın:
   ```bash
   BUILD_SHA="$(git rev-parse HEAD)" docker compose up -d --build
   ```
   ```bash
   docker compose ps
   ```
   ```bash
   docker compose logs caddy
   ```
   - `COMPOSE_FILE` kullanılmıyorsa her komuta `-f docker-compose.yml -f docker-compose.tls.yml` eklenir.
   - Ek dosya yalnızca `frontend` ve `api` ayarlarını değiştirir ve `caddy` ekler; PostgreSQL, Valkey, Qdrant ve veriler değişmez. Frontend imajı bu sürümden derlenmelidir (`--build`): eski Nginx, API'ye `https` yerine `http` bildirir ve oturum yenileme 403 alır.
   - Caddy günlüğünde sertifika hatası olmamalıdır.

### 8.3 Kök sertifikayı istemcilere dağıtma (`internal` modu)

Caddy'nin kök sertifikasını sunucudan alın. Bu dosya gizli değildir; özel anahtarı `caddy_data` volume'unda kalır.

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./modai-kok-sertifika.crt
```

- **Windows:**
  - Tek bilgisayarda yönetici olarak açılan komut isteminde `certutil -addstore -f Root modai-kok-sertifika.crt` çalıştırılır.
  - Ya da dosyaya çift tıklanır: Sertifika Yükle → Yerel Makine → **Güvenilen Kök Sertifika Yetkilileri**.
  - Çok sayıda bilgisayar için BT ekibi Grup İlkesi ile dağıtır: Bilgisayar Yapılandırması → İlkeler → Windows Ayarları → Güvenlik Ayarları → Ortak Anahtar İlkeleri → Güvenilen Kök Sertifika Yetkilileri.
- **macOS:**
  - Terminalde `sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain modai-kok-sertifika.crt` çalıştırılır.
  - Ya da Anahtar Zinciri Erişimi → Sistem anahtar zincirine eklenip "Her Zaman Güven" seçilir. Çok sayıda Mac için MDM profiliyle dağıtılır.
- Chrome ve Edge işletim sisteminin sertifika deposunu kullanır; tarayıcı yeniden başlatılır.
- `caddy_data` volume'u silinirse yeni bir kök oluşur ve yeniden dağıtılması gerekir. Bu yüzden `docker compose down -v` kullanılmaz.
- Şirket CA'sı varsa `files` modu dağıtım gerektirmez ve tercih edilir.

### 8.4 Doğrulama

Sunucudan farklı bir bilgisayarda:

1. `http://modai.sirket.local` açılır. Tarayıcı `https://modai.sirket.local` adresine geçmeli ve sertifika uyarısı göstermemelidir.
2. Giriş yapılır. Geliştirici araçları → Application → Cookies altında `modai_refresh` çerezi **Secure** ve **HttpOnly** işaretli olmalıdır.
3. Sayfa yenilenir; oturum açık kalmalıdır (Network sekmesinde `/api/auth/refresh` 200). 403 "Untrusted request origin" görülürse `TRUSTED_FRONTEND_ORIGINS` ve `MODAI_HOSTNAME` aynı adı mı gösteriyor, kontrol edin.
4. RAG Chat'te bir soru sorulur. Yanıt akarak gelmelidir; Network sekmesinde `wss://modai.sirket.local/ws/rag` bağlantısı 101 durumundadır.
5. `/voice` açılır. "Mikrofon yalnızca güvenli bağlantıda çalışır" uyarısı görünmemeli, tarayıcı mikrofon izni istemeli ve bir soru sesli sorulup yanıt dinlenebilmelidir.
6. Çıkış yapılır; sayfa yenilenince giriş ekranı gelmelidir.
7. İki farklı bilgisayardan giriş yapıldıktan sonra sunucuda denetim kaydındaki kaynak adreslere bakılır:
   ```bash
   docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
   ```
   ```sql
   select actor_user_id, source_ip from audit_events where action = 'login' order by id desc limit 5;
   ```
   İki bilgisayarın IP'leri görünmelidir (`\q` ile çıkılır). Hepsi aynı adresse (macOS'taki Docker Desktop istemci adresini gizleyebilir), giriş ve oturum yenileme hız sınırı tüm çalışanlar için ortaktır. Bu durumda `RATE_LIMIT_AUTH_PER_MINUTE` kullanıcı sayısına göre artırılır.

### 8.5 Geri alma (HTTPS'siz düzene dönüş)

1. `.env` dosyasında:
   - `COMPOSE_FILE` satırı silinir.
   - `APP_ENV=development`, `REFRESH_COOKIE_SECURE=false` ve `TRUSTED_FRONTEND_ORIGINS` eski değerine döner.
   - `REFRESH_COOKIE_NAME` yeni bir ada çevrilir (ör. `modai_refresh_http`). Tarayıcılar HTTPS'te bırakılan Secure çerezi düz HTTP'den değiştiremez; aynı adla oturumlar düşer.
2. Ek dosya olmadan başlatılır; `caddy` kaldırılır, `frontend` ve `api` eski portlarıyla (5173, 8000) yeniden oluşturulur:
   ```bash
   docker compose up -d --remove-orphans
   ```
3. Veriler, imajlar ve `caddy_data` (sertifikalar, kök CA) korunur; HTTPS'e dönmek için 8.2 yeniden uygulanır.
4. Çalışanlar yeniden `http://<sunucu-adresi>:5173` adresini kullanır. Mikrofon bu durumda yalnızca sunucuda `http://localhost:5173` ile çalışır.

### 8.6 Şirket hesabıyla giriş (SSO, OpenID Connect)

Çalışanlar modAI'a ayrı bir parola yerine şirket hesabıyla girer: Microsoft Entra ID (Azure AD), Google Workspace, Keycloak, Okta ya da OpenID Connect destekleyen başka bir sağlayıcı. HTTPS kurulumu (8.2) önce tamamlanmış olmalıdır.

**İsteğe bağlıdır.** SSO kapalıyken (varsayılan) herkes e-posta ve parolayla girer ve modAI hiçbir dış servise bağlanmaz. SSO yalnızca müşterinin zaten bir kimlik sistemi varsa açılır; modAI o sisteme şirket ağı içinden bağlanır, belge ya da soru göndermez, yalnızca "bu kişi kim" sorusunun yanıtını alır.

1. **Sağlayıcıda uygulama kaydı:** "Web" türünde bir uygulama oluşturun.
   - Yönlendirme adresi (redirect URI): `https://<MODAI_HOSTNAME>/api/auth/oidc/callback`.
   - Kapsamlar: `openid email profile`.
   - Bir istemci sırrı (client secret) üretin.
   - **Entra ID:** App registrations → New registration. Hesap türü "Accounts in this organizational directory only". Certificates & secrets → New client secret. Issuer `https://login.microsoftonline.com/<tenant-id>/v2.0` olur.
   - **Google Workspace:** Google Cloud Console → APIs & Services → Credentials → OAuth client ID (Web application). Issuer `https://accounts.google.com` olur.
   - **Keycloak:** realm içinde bir OpenID Connect istemcisi oluşturun ("Client authentication" açık). Issuer `https://<keycloak>/realms/<realm>` olur.
2. **`.env`:**
   ```dotenv
   OIDC_ENABLED=true
   OIDC_PROVIDER_NAME=Microsoft
   OIDC_ISSUER=https://login.microsoftonline.com/<tenant-id>/v2.0
   OIDC_CLIENT_ID=<uygulama kimliği>
   OIDC_CLIENT_SECRET=<istemci sırrı>
   OIDC_REDIRECT_URI=https://modai.sirket.local/api/auth/oidc/callback
   OIDC_ALLOWED_DOMAINS=sirket.com
   OIDC_AUTO_PROVISION=true
   ```
   Ardından `docker compose up -d api` ile API'yi yeniden başlatın. Giriş sayfasında "Microsoft ile giriş" düğmesi görünür.
3. **Kimler girer:**
   - Yalnızca `OIDC_ALLOWED_DOMAINS`'deki alan adlarından (virgülle ayrılır) e-postası olan hesaplar girer.
   - Kişi, sağlayıcının değişmeyen kimliğiyle (issuer ve subject) tanınır. E-postası sonradan değişse de aynı hesaba girer.
   - İlk girişte aynı e-postalı bir modAI hesabı varsa ona bağlanır. Yoksa `OIDC_AUTO_PROVISION=true` iken boş bir hesap açılır: kişi hiçbir Workspace'i göremez.
   - Erişim davetle ya da üyelikle verilir. Kişiye daha önce gönderilmiş ve bekleyen davetler ilk girişte kendiliğinden kabul edilir. Önerilen akış: davet gönderin, kişi "şirket hesabıyla giriş"e bassın.
   - `OIDC_AUTO_PROVISION=false` iken yalnızca davet ya da yöneticiyle önceden açılmış hesaplar girer.
   - Kurum içi alan adları (örneğin `sirket.local`) da çalışır: bu kişiler ilk SSO girişinden sonra **Yönetim → Üyelikler**'den e-postayla eklenir. Davet ve parola ile giriş bu alan adlarını kabul etmez.
4. **Güvenlik:**
   - Akış, PKCE ile yetkilendirme kodu akışıdır. Tek kullanımlık `state` 10 dakika geçerlidir.
   - Kimlik belirteci sağlayıcının yayımladığı anahtarlarla doğrulanır; issuer, audience, süre ve `nonce` kontrol edilir. Yalnızca asimetrik imzalar kabul edilir.
   - Belirteçler loglara ve denetim günlüğüne yazılmaz. Başarılı ve başarısız girişler `sso_login` ve `sso_login_failed` (yalnızca neden kodu ve IP) olarak kaydedilir.
   - Platform yöneticisinin parola ile girişi acil durum yolu olarak açık kalır.
5. **Denendi:** 12 Ekim 2026'da gerçek bir OpenID Connect sağlayıcısıyla (Dex v2.41.1, bu makinede geçici bir container, dış servis yok) uçtan uca denendi; 13 kontrolün 13'ü geçti: yönlendirme (PKCE, state, nonce), sağlayıcıda parola ile giriş, kod değişimi, imza doğrulama, konsol oturumu, davetin kendiliğinden kabulü, ikinci girişte aynı hesap, tekrar kullanılan ve sahte dönüşlerin reddi, izinsiz alan adının reddi, yanlış parola ve denetim kayıtları. Bu deneme `sirket.local` gibi adreslerle açılan hesapların konsolu bozduğu bir hatayı buldu ve düzeltildi. Entra ID ve Google Workspace aynı standardı kullanır; müşterinin kendi hesabıyla kurulumda bir kez giriş yapıp **Denetim** sayfasında `sso_login` kaydını görün.
6. **İşten ayrılan çalışan:** sağlayıcıda hesabı kapatılınca modAI'a yeniden giremez. Açık oturumu en geç `REFRESH_TOKEN_EXPIRE_DAYS` sonunda biter. Hemen kapatmak için **Yönetim → Üyelikler**'de üyeliği kaldırın ya da KVKK silme talebinde **Hesabı sil**'i kullanın.

### 8.7 Şirket dizini: gruplarla erişim ve SCIM

Şirket hesabıyla giriş (8.6) kişinin kim olduğunu söyler. Bu bölüm iki şeyi daha şirketin kimlik sistemine bırakır:

- **kim neye erişir:** gruplar → çalışma alanı rolleri;
- **kim artık giremez:** işten ayrılan kişinin hesabı kapatılır.

Ayarlar **Yönetim → Kurumsal kimlik** sayfasındadır ve yalnızca platform yöneticileri görür.

**Nasıl çalışır:**
- **Grup eşleme:** her grup bir organization'a ya da çalışma alanına bir rolle (User, Manager, Admin) eşlenir. Gruptaki kişi o üyeliği kendiliğinden alır; birden fazla grup aynı yere eşlenmişse en yüksek rol geçerlidir.
- **Gruptan çıkınca:** kişi gruptan çıkarılınca bu yoldan verilen üyelik kalkar.
- **Elle verilen üyelikler:** elle ya da davetle verilen üyeliklere dokunulmaz. **Üyelikler** sayfasında dizinden gelenler "directory" kaynağıyla görünür.
- **Kapatılan hesap:** dizinde kapatılan (SCIM'de `active=false` ya da silinen) hesap parola ya da şirket hesabıyla giremez ve oturum yenileme anında durur. Açık bir sekmedeki erişim belirteci en geç `ACCESS_TOKEN_EXPIRE_MINUTES` (30 dakika) içinde biter.
- **Platform yöneticileri:** dizinden kapatılmaz; acil durum girişi korunur. Kapatmak için önce modAI'de yetkisini kaldırın.
- **KVKK silme:** hesap satırı silinmez, çünkü belgeler ona bağlıdır. KVKK silme talebi **Kullanıcılar** sayfasından ayrıca yapılır ve dizin bağlantılarını da siler.

**Yol A: yalnızca giriş belirtecindeki gruplar (en basit; modAI'ye dışarıdan bağlantı gerekmez).** Kişi her girişte belirtecindeki gruplarla eşitlenir. Belirteç grup göndermiyorsa mevcut üyelikler olduğu gibi kalır.
- **Entra ID:** App registration → Token configuration → Add groups claim → Security groups, ID token için "Group ID". Belirteçte grup **kimlikleri** (object id) gelir. Kurumsal kimlik sayfasında **SSO grubu ekle** ile kimliği ve okunur bir ad girin ya da ilk girişten sonra listede görünen gruba ad verin.
- **Keycloak:** client → Client scopes → dedicated scope → Add mapper → Group Membership; Token Claim Name `groups`, "Full group path" kapalı.
- **Okta:** Authorization server → Claims → `groups` (ID token, filtre örneğin "Starts with: modai-").
- **Google Workspace:** ID belirtecinde grup göndermez. Google kullanan şirketlerde erişim davet ya da üyelikle verilir; giriş yine şirket hesabıyla yapılır.
- Talep adı farklıysa `.env`'de `OIDC_GROUPS_CLAIM` ayarlanır.
- **Sınırı:** kişi dizinde kapatılırsa bir daha giremez, ama modAI bunu ancak bir sonraki girişte öğrenir. Anında kapatma için Yol B'yi kullanın.

**Yol B: SCIM 2.0 ile hesap ve grup eşitleme (Entra ID, Okta).** Kimlik sağlayıcısı hesapları ve grupları kendisi açar, günceller, kapatır.
1. Kurumsal kimlik sayfasında organization'ı seçip **Belirteç oluştur**'a basın. Kiracı adresi (`https://<MODAI_HOSTNAME>/api/scim/v2`) ve gizli belirteç **yalnızca bir kez** gösterilir. Yeni belirteç eskisini geçersiz kılar.
2. **Entra ID:**
   - Uygulamayı açın: Enterprise applications → New application → Create your own application → "Integrate any other application you don't find in the gallery".
   - Provisioning → Automatic: Tenant URL ve Secret Token'ı girin → Test Connection.
   - Eşlemeler: varsayılanlar uygundur (`userName` ← userPrincipalName, `emails[type eq "work"].value` ← mail, `active`, `externalId` ← objectId).
   - Users and groups'ta kişileri ve grupları atayıp eşitlemeyi başlatın.
3. **Okta:** Applications → Create App Integration (SAML/OIDC) → Provisioning → SCIM 2.0:
   - SCIM connector base URL: kiracı adresi;
   - Unique identifier field: `userName`;
   - Authentication Mode: HTTP Header (Bearer);
   - Push New Users, Push Profile Updates, Deactivate Users ve Push Groups'u açın.
4. Kurumsal kimlik sayfasında gelen grupları çalışma alanı rollerine eşleyin.
- **Erişilebilirlik:** Entra ve Okta'nın bulut hizmeti kiracı adresine HTTPS ile ulaşabilmelidir. modAI internetten erişilemeyen bir şirket ağındaysa Entra'nın şirket içi sağlama aracısı (Microsoft Entra provisioning agent) ya da Okta On-Prem Provisioning Agent şirket ağına kurulur. Bu aracılar modAI'ye içeriden bağlanır.
- **E-posta olmayan kullanıcı adları:** kullanıcı adı e-posta değilse ve e-posta da gelmiyorsa (JumpCloud, OneLogin kullanıcı adları), hesap geçici bir `…@directory.local` adresiyle açılır. Kişi ilk kez şirket hesabıyla girdiğinde hesap kullanıcı adından bulunur ve gerçek e-posta yazılır. Entra'da UPN ile mail adresinin farklı olduğu durum da böyle eşleşir.
- **Uyumluluk:** SCIM uygulaması bağımsız `scim2-tester` (python-scim2) denetiminde 69 kontrolün 63'ünü geçti. Kalan altısı bilinçli kurallardır: tek bir giriş e-postası tutulur, `active` ve bu e-posta kaldırılamaz, sunucu üyelere salt okunur görünen ad ekler.
- **Denetim kaydı:** her işlem kaydedilir: `directory_user_created`, `account_disabled`, `directory_membership_granted` ve diğerleri.

### 8.8 Active Directory ile doğrudan giriş (LDAP)

Şirketin kendi sunucusundaki Active Directory'ye (ya da OpenLDAP, FreeIPA gibi bir LDAP dizinine) bağlanılır. Çalışanlar Windows kullanıcı adı ve şifreleriyle girer. Bulut kimlik sağlayıcısı (8.6) ya da internet bağlantısı gerekmez. Entra ID, Okta veya Google kullanan şirketlerde 8.6 ve 8.7 tercih edilir.

**Nasıl çalışır:**
- **Giriş:** giriş sayfası kullanıcı adı ister. `ŞİRKET\ad.soyad`, `ad.soyad@sirket.local` ya da e-posta yazılabilir. Yerel hesaplar (kurulumun yöneticisi, davetliler) "Yerel hesapla giriş" bağlantısıyla girer.
- **Doğrulama:** modAI, salt okunur bir servis hesabıyla kişiyi dizinde arar. Ardından kişinin kendi şifresiyle dizine bağlanarak şifreyi doğrular. Şifre modAI'de saklanmaz ve kaydedilmez.
- **İlk giriş:** kişinin hesabı açılır (`LDAP_AUTO_PROVISION=false` ise yalnızca daveti olanlar girer). Dizindeki gruplar (`memberOf`; `LDAP_NESTED_GROUPS=true` ile iç içe gruplar da) **Kurumsal kimlik** sayfasında "Active Directory" etiketiyle listelenir. Gruplar 8.7'deki gibi rollere eşlenir ve belgeleri bu gruplara kısıtlamak için de kullanılır (8.9).
- **Saatlik eşitleme:** worker her saat (`LDAP_SYNC_INTERVAL_MINUTES`) iki iş yapar:
  - dizinde kapatılan (`userAccountControl` devre dışı) ya da silinen hesapları modAI'de kapatır;
  - grup değişikliklerini uygular.

  Yalnızca dizinin kapattığı hesapları dizin tekrar açınca açar. Platform yöneticilerine dokunmaz.
- **Denetim kaydı:** `ldap_login` olayı yazılır. Başarısız girişte (`ldap_login_failed`) yalnızca sebep kodu kaydedilir; şifre kaydedilmez.

**Kurulum:**
1. **Servis hesabı:** AD'de yalnızca okuma yetkisi olan, şifresi süresiz bir hesap açın (ör. `modai-okuma`).
2. **Şifreli bağlantı:** LDAPS (636) ya da StartTLS kullanın.
   - Dizin sertifikası şirketin kendi kök sertifikasıyla imzalıysa kök sertifikayı (PEM) api ve worker konteynerlerine bağlayın. Bunun için `docker-compose.override.yml` dosyasında her ikisine şu satırı ekleyin: `volumes: ["./certs/sirket-ca.pem:/etc/modai/sirket-ca.pem:ro"]`.
   - Ardından `.env`'e `LDAP_CA_FILE=/etc/modai/sirket-ca.pem` yazın.
3. **`.env` ayarları:**
   ```
   LDAP_ENABLED=true
   LDAP_PROVIDER_NAME=Şirket hesabı (AD)
   LDAP_URL=ldaps://dc1.sirket.local:636
   LDAP_BIND_DN=CN=modai-okuma,OU=Servis Hesaplari,DC=sirket,DC=local
   LDAP_BIND_PASSWORD=…
   LDAP_USER_BASE_DN=OU=Calisanlar,DC=sirket,DC=local
   ```
4. **Uygulama:** `docker compose up -d api worker` çalıştırın. Ardından giriş sayfasında kullanıcı adı alanı görünür.
5. **Deneme:** bir çalışanla girin. Kurumsal kimlik sayfasında gruplarının göründüğünü kontrol edin ve grupları rollere eşleyin.

**Sorun giderme:**
- **"Şirket dizinine ulaşılamadı":** sunucu adı ve port, güvenlik duvarı ya da sertifika sorunudur. Şu komutla bakın: `docker compose logs api | grep -i ldap`.
- **Düz LDAP (389):** yalnızca deneme ortamında `LDAP_ALLOW_PLAINTEXT=true` ile kullanılır. Şifreler ağda açık gider.
- **Kullanıcı bulunamıyor:** `LDAP_USER_BASE_DN` ve `LDAP_USER_FILTER` ayarlarına bakın. Varsayılan filtre `sAMAccountName`, `userPrincipalName` ya da `mail` ile arar.

### 8.9 İçerik kaynakları: ağ klasörü ve SharePoint

Bir bilgi tabanı, şirketin dosya sunucusundaki bir klasörle ya da bir SharePoint kitaplığıyla eşit tutulur:
- yeni dosyalar eklenir;
- değişenler belgenin yeni sürümü olur;
- silinenler arşivlenir, geri gelirse arşivden çıkar.

Dosyaların izinleri belge okuyucularına aktarılır. Kısıtlı bir belgeyi aramada ve listede yalnızca okuyucuları bulur, belge listesinde 🔒 **Kısıtlı** etiketiyle görünür. Workspace yöneticileri hepsini görür.

Kaynaklar, bilgi tabanı sayfasındaki **Bağlı kaynaklar** bölümünden bağlanır. Kaynağı bağlamak, erişim kurallarını değiştirmek ve bağlantıyı kaldırmak **organization yöneticisinin** (ya da platform yöneticisinin) işidir. Nedeni şu: kaynaklar klasörü ve SharePoint uygulaması bütün şirketin dosyalarına ulaşır, workspace yöneticileri de kendi bilgi tabanlarındaki bütün belgeleri görür. Bilgi tabanının manager'ı kaynağı görür, eşitlemeyi başlatır, duraklatır ve sıklığı değiştirir. Her kaynağın kendi eşitleme sıklığı vardır (15 dakika – günde bir). **Şimdi eşitle** bir dakika içinde başlatır. Desteklenmeyen dosya türleri indirilmez ve "desteklenmeyen" olarak sayılır.

**Ağ klasörü (Windows dosya sunucusu, NAS):**
1. **Paylaşımı bağlama:** paylaşımı modAI sunucusunda, kurulum klasöründeki `sources/` altına salt okunur bağlayın (`MODAI_SOURCES_DIR` ile başka bir klasör seçilebilir). Konteynerler bu klasörü `/sources` olarak salt okunur görür.
   - **Linux:**
     ```bash
     sudo mkdir -p /opt/modai/sources/ik
     sudo mount -t cifs //fs01/IK /opt/modai/sources/ik -o ro,username=modai-okuma,domain=SIRKET,uid=$(id -u),gid=$(id -g)
     ```
     Kalıcı bağlama için `/etc/fstab` kullanın; şifreyi bir `credentials=` dosyasında tutun (izni 600).
   - **macOS:** paylaşımı doğrudan `sources/ik` klasörüne bağlayın: `mkdir -p sources/ik && mount_smbfs -o rdonly //modai-okuma@fs01/IK sources/ik`. `/Volumes/IK`'ye sembolik bağlantı işe yaramaz, çünkü modAI sembolik bağlantıları izlemez. Docker Desktop ağ bağlamalarını konteynere her zaman geçiremeyebilir; önce küçük bir klasörle deneyin. Kalıcı kurulumda Linux sunucu önerilir.
2. **Kaynak ekleme:** bilgi tabanı sayfasında **Kaynak bağla** → **Ağ klasörü** seçin, klasörü seçin ve sıklığı belirleyin.
3. **Erişim kuralları:**
   - bir alt klasöre (ör. `Bordro`) okuyabilecek dizin gruplarını (Active Directory, SSO, SCIM) ve kişileri yazın;
   - en uzun eşleşen alt klasörün kuralı geçerlidir;
   - kurala uymayan dosyaları bilgi tabanının tüm üyeleri görür.

   NTFS izinleri bağlı paylaşımdan güvenilir biçimde okunamadığı için kurallar aynı grupları adlarıyla seçer. Kural değişince bütün dosyalara hemen uygulanır.

**SharePoint Online (Microsoft 365):**
1. **Uygulama kaydı:** Entra ID → App registrations → New registration (ör. "modAI SharePoint").
   - API permissions → Microsoft Graph → **Application permissions** → `Sites.Read.All` ekleyin. Yalnızca seçili siteler için `Sites.Selected` ekleyin ve siteye ayrıca okuma izni verin.
   - **Grant admin consent** ile onaylayın.
   - Certificates & secrets → New client secret oluşturun.
2. **`.env` ayarları:** `MS_GRAPH_TENANT_ID`, `MS_GRAPH_CLIENT_ID` ve `MS_GRAPH_CLIENT_SECRET` değerlerini yazın, sonra `docker compose up -d api worker` çalıştırın.
3. **Kaynak ekleme:** bilgi tabanı sayfasında **Kaynak bağla** → **SharePoint kitaplığı** seçin.
   - Site adresini yazın (ör. `https://sirket.sharepoint.com/sites/IK`).
   - Kitaplık ve klasör isteğe bağlıdır; boş bırakılırsa sitenin ilk belge kitaplığı kullanılır.
4. **İzinler:** her dosyanın paylaşımı okunur.
   - Sitenin kendi gruplarıyla ya da tüm kuruluşla paylaşılan dosyaları bilgi tabanının üyeleri görür.
   - Belirli kişilere ya da Entra gruplarına paylaşılan dosyaları yalnızca onlar görür. Kişiler e-postayla eşleşir.
   - Gruplar object id ile eşleşir. Bu yüzden grupların SSO (8.7 Yol A) ya da SCIM ile modAI'de bulunması gerekir.
- **Ağ erişimi:** modAI sunucusundan `graph.microsoft.com` ve `login.microsoftonline.com` adreslerine HTTPS çıkışı gerekir. Dosyalar modAI'ye indirilir ve sorular dışarı gitmez.
- **Büyük kitaplıklar:** her eşitleme her dosyanın izinlerini ayrı ayrı okur. Binlerce dosyalık bir kitaplıkta eşitleme dakikalar sürer, Microsoft da istekleri yavaşlatabilir (modAI bekleyip yeniden dener). Böyle kitaplıklarda sıklığı 6 saat ya da günde bir seçin. Yalnızca değişenleri okuyan delta eşitleme yol haritasındadır.

**Takip:** kaynak kartı durumu (Güncel, Eşitleniyor, Kısmen, Eşitlenemedi), son eşitlemenin sayılarını ve ilk hatayı gösterir. Bağlantıyı kaldırmak eşitlemeyi durdurur; belgeler okuyucularıyla bilgi tabanında kalır. Belgeler kendi yaşam döngüsünü korur: yönetici arşivleyebilir ya da silebilir. Silinen bir dosya kaynakta hâlâ duruyorsa sonraki eşitlemede yeniden eklenir.

### 8.10 Onaylı iş akışları (Talepler)

Talep türleri **Yönetim → İş akışları** sayfasında organization yöneticisi tarafından kurulur. Kullanımı kurumsal kullanım kılavuzu "Talepler" bölümünde anlatılır. Ek bir servis gerekmez; aynı API ve veritabanı kullanılır (migration 0022).

**Onaydan sonra webhook:** son onaydan sonra talep, türde tanımlı adrese `POST` edilir. Başlıklar:
- `Content-Type: application/json`
- `X-Modai-Event: workflow.approved`
- `X-Modai-Request-Id: <talep no>`
- `X-Modai-Signature: sha256=<HMAC>`: gövdenin `WORKFLOW_WEBHOOK_SECRET` ile HMAC-SHA256 imzası. `.env`'de bu değeri uzun ve rastgele bir değerle ayarlayın (ör. `openssl rand -hex 32`). Alıcı sistem imzayı doğrulamalıdır.

Gövde:
```json
{"event": "workflow.approved",
 "request": {"id": 12, "type": "İzin talebi", "type_id": 3, "workspace_id": 1, "requester": "ayse@sirket.com",
             "values": {"izin_turu": "Yıllık izin", "baslangic": "2026-10-20", "bitis": "2026-10-22", "gun_sayisi": 3},
             "fields": [{"key": "izin_turu", "label": "İzin türü", "type": "choice"}],
             "decisions": [{"step": 0, "approver": "mudur@sirket.com", "decision": "approve", "comment": "", "at": "…"}],
             "policy_sources": [{"document": "izin-politikasi.pdf", "document_version": 2}],
             "link": "https://modai.sirket.local/requests/12"}}
```
Alıcı 2xx dışında bir yanıt verirse ya da 10 saniyede yanıt vermezse talep "İlgili sisteme iletilemedi" olarak işaretlenir. Hata talep sayfasında görünür. Organization yöneticisi **Yeniden dene** ile yeniden gönderir.

**Teams ya da Slack bildirimi:** kanalın gelen webhook adresi (Slack "Incoming Webhooks", Teams "Incoming Webhook" bağlayıcısı) talep türüne yazılır. Talep gönderilince, her adımda ve karar verilince kanala kısa bir metin (`{"text": "…"}`) gider. Bağlantı, `TRUSTED_FRONTEND_ORIGINS` içindeki ilk adresle kurulur.

**Hatırlatma:** worker saatte bir, talep türünde belirlenen süreden (`remind_after_hours`, varsayılan 24 saat; 0 kapatır) uzun bekleyen adımlar için bildirim kanalına hatırlatma gönderir. Sonraki hatırlatma yine aynı süre sonra gider.

**Talep ve politika yan yana:** talep gönderilirken yapılan hesaplar talebe kaydedilir:
- ilk tarih alanı için başvuru günü ile o gün arasındaki iş günü sayısı;
- ilk iki tarih arasındaki iş günü sayısı (iki gün dahil);
- politika bölümlerinden sayı ya da sınır içeren cümleler (en çok 6).

Bu adımda dil modeli kullanılmaz.

**Ağ:** webhook ve bildirim adresleri modAI sunucusundan erişilebilir olmalıdır. Yönlendirme izlenmez.

**Yapay zekâyla doldurma:** etkin üretim modeli kullanılır (`format=json`). Sohbetle aynı hız sınırına tabidir. Yalnızca alan kontrollerinden geçen değerler forma yazılır.

## 9. Toplu belge aktarımı

| Belge sayısı | Yol |
|---|---|
| Birkaç yüz dosyaya kadar | Belgeler sayfasında **Klasör yükle** |
| Binlerce dosya, ilk taşıma | Sunucuda `app.tools.import_documents` komutu |

İki yol da tek tek yüklemeyle aynı kontrolleri yapar:

- **Türler:** PDF, DOCX, TXT, Markdown (`.md`), taranmış görseller (PNG, JPG, TIFF) ve ses ya da video (MP3, M4A, WAV, OGG, FLAC, MP4, MOV, M4V, WEBM, MKV) yüklenir. Diğer türler atlanır ve listelenir. `.markdown` uzantılı dosyaları `.md` olarak yeniden adlandırın.
- **Boyut:** belge başına sınır `MAX_UPLOAD_BYTES` (varsayılan 10 MB), ses ve video için `MEDIA_MAX_UPLOAD_BYTES` (200 MB) ve `TRANSCRIPTION_MAX_MINUTES` (120 dakika). Daha büyük dosyalar yüklenmez; bölünmeleri gerekir.
- **Tekrar:** Bir Knowledge Base'te aynı içerik ikinci kez eklenmez; dosya adı farklı olsa da sonuç değişmez. Bu yüzden yarıda kalan bir aktarım aynı klasörle güvenle yeniden başlatılabilir: yüklenmiş dosyalar "zaten var" olarak atlanır.
- **Atlananlar:** Gizli ve sistem dosyaları atlanır: `.DS_Store`, `~$` ile başlayan Office kilit dosyaları, `Thumbs.db` ve nokta ile başlayan klasörler.
- **İndeksleme:** Her belge indeksleme kuyruğuna girer. Worker belgeleri sırayla işler; yüzlerce belgenin "hazır" olması zaman alır. Aktarımdan sonra Belgeler sayfasında "Hatalı" durumdaki belge kalmadığını kontrol edin.

### Klasör yükle (arayüz)

1. Belgeler sayfasında hedef Knowledge Base'i seçin.
2. **Klasör yükle**'ye basın ve klasörü seçin.

Bu işlem manager veya admin yetkisi ister. Dosyalar 10'arlı gruplar halinde gönderilir. Ekranda şunlar görünür:

- işlenen dosya sayısı (n / toplam);
- yüklenen, zaten var olan ve hatalı dosyalar;
- atlanan desteklenmeyen dosyalar.

**İptal et** düğmesi, sürmekte olan grup bitince durur; o ana kadar yüklenenler korunur. Yükleme bitene kadar sayfada kalın. Knowledge Base değiştirilirse ya da sayfadan çıkılırsa yükleme, sürmekte olan grup bitince durur.

### Komut satırı (ilk taşıma)

Komut `worker` (ya da `api`) konteynerinde çalışır. Dosyalar önce konteynere kopyalanır:

```bash
docker compose exec -T worker mkdir -p /data/import
docker compose cp ./belgeler/. worker:/data/import/
```

Önce deneme çalıştırması yapın (`--dry-run` hiçbir şey yazmaz; her dosyayı okur ve sonucu raporlar):

```bash
docker compose exec -T worker python -m app.tools.import_documents --workspace-id 1 --root /data/import --kb-from-folders --owner-email yonetici@firma.com --dry-run --report /tmp/aktarim-deneme.csv
```

```bash
docker compose cp worker:/tmp/aktarim-deneme.csv ./aktarim-deneme.csv
```

Raporu müşteriyle birlikte gözden geçirin. Sonra aynı komutu `--dry-run` olmadan, `--report /tmp/aktarim.csv` ile çalıştırın ve raporu aynı yolla dışarı alın. Bitince kopyayı silin:

```bash
docker compose exec -T worker rm -rf /data/import
```

- **Hedef:** `--kb-from-folders` ile her üst klasör aynı adlı Knowledge Base'e gider; Knowledge Base yoksa oluşturulur. Ad, büyük/küçük harf farkıyla da eşleşir: `finans` klasörü `Finans`'a gider. Kökteki dosyalar hata sayılır. Tek bir Knowledge Base için `--kb "İK"` kullanın.
- **İçeriğe göre yerleştirme:** klasörleri ayrılmamış bir arşiv için `--kb "Genel" --auto-route` kullanın. Her belge, açıklaması içeriğine en çok uyan Knowledge Base'e gider; emin olunamayanlar `--kb`'de kalır. Bunun için Workspace'te çok dilli arama (BGE-M3) etkin olmalı ve Knowledge Base'lerin açıklaması yazılmış olmalıdır (Knowledge Base sayfasında **Açıklamayı düzenle**). Önce `--dry-run` ile çalıştırın: raporda her belgenin gideceği Knowledge Base ve "placed by content" notu görünür. Görseller ve ses ya da video kayıtları yerleştirilmez, `--kb`'de kalır.
- **Yükleyen:** `--owner-email` belgelerde yükleyen olarak kaydedilir. Bu kullanıcının Workspace'te manager ya da admin yetkisi olmalıdır.
- **Workspace kimliği:** Yönetim → Workspaces tablosundaki ID sütunundadır.
- **Çıktı:** Komut her dosya için bir satır ve bir özet yazar. Özette yüklenen, tekrar olduğu için atlanan, desteklenmeyen, gizli/sistem, çok büyük ve hatalı dosya sayıları vardır. CSV raporunda her dosyanın yolu, Knowledge Base'i, durumu, açıklaması, boyutu ve belge numarası bulunur. Çıktıda belge içeriği yer almaz.
- **Kuyruk sorunu:** Kuyruk (Redis) erişilemezse komut ilk kaydedilen belgede durur. Raporda adı geçen belge için Belgeler sayfasında **Yeniden indeksle**'ye basın, sonra komutu yeniden çalıştırın.

Dosyalar kopyalanmak yerine salt okunur bağlanabilir. Bu yol geçici bir konteyner kullanır ve kopya bırakmaz:

```bash
docker compose run --rm -v "$PWD/belgeler:/data/import:ro" -v "$PWD/rapor:/data/report" worker python -m app.tools.import_documents --workspace-id 1 --root /data/import --kb-from-folders --owner-email yonetici@firma.com --report /data/report/aktarim.csv
```

### Bir klasörü düzenli eşitleme

Önerilen yol artık **Bağlı kaynaklar**dır (8.9): değişen dosyalar yeni sürüm olur, silinenler arşivlenir ve klasör izinleri belgelere aktarılır. Aşağıdaki gece komutu, ağ klasörünün sunucuya bağlanamadığı durumlar için kalır.

Bir paylaşım klasörüne eklenen belgeler her gece kendiliğinden içeri alınabilir. Aynı içerik ikinci kez eklenmediği için komut her gece güvenle tekrarlanır; yalnızca yeni ya da değişmiş dosyalar yüklenir. Değişen bir dosya yeni bir belge olarak eklenir; eski hâlini arşivleyin ya da kalıcı güncellemeler için **Belgeyi değiştir**'i kullanın.

macOS ya da Linux'ta `crontab -e` ile, depo klasöründen her gece 01:30'da:

```bash
30 1 * * * cd /opt/modai && docker compose run --rm -v /srv/paylasim/politikalar:/data/import:ro worker python -m app.tools.import_documents --workspace-id 1 --root /data/import --kb "Genel" --auto-route --owner-email yonetici@firma.com >> /var/log/modai-esitleme.log 2>&1
```

Komut yalnızca sayıları ve dosya yollarını yazar, belge içeriğini yazmaz. Silinen dosyalar modAI'dan silinmez; kaldırılan politikayı Belgeler sayfasında arşivleyin.

### Önerilen klasör yapısı

Her departman ayrı bir Knowledge Base olur. Böylece sorular doğru belge grubunda aranır ve yetkiler departmana göre verilebilir.

```text
belgeler/
  İK/
    izin-politikasi-2026.pdf
    yan-haklar-2026.docx
  Finans/
    satin-alma-onay-tablosu-2026.pdf
  BT/
    vpn-kurulumu.md
  Destek/
    sla-premium-plan.pdf
```

Alt klasörler serbesttir; komut satırında yalnızca en üst klasör Knowledge Base'i belirler.

### Adlandırma

- **Anlamlı ad:** Dosya adı yanıtlardaki kaynak kartında görünür. Ad, konuyu ve yılı ya da sürümü anlatmalıdır: `izin-politikasi-2026.pdf`. `scan001.pdf` ya da `Yeni Belge (3).docx` gibi adlar kullanılmamalıdır.
- **Eski kopyalar:** "ESKI", "eski", "kopya", "son-SON" gibi kopyalar yüklenmez; bir belgenin yalnızca geçerli sürümü yüklenir. Eski ve yeni sürüm birlikte yüklenirse sistem hangisinin geçerli olduğunu bilemez (bkz. bölüm 7).
- **Güncelleme:** Belge güncellendiğinde yeni dosya ayrıca yüklenmez. Belge listesinde ilgili satırda **Belgeyi değiştir** kullanılır. Belge yeni sürüme geçer, eski sürüm aramadan çıkar ve sürüm geçmişi korunur.

### Taranmış PDF'ler

Tarayıcıdan çıkmış, yalnızca görüntü içeren PDF'lerde metin katmanı yoktur. Sistem bu dosyaları kabul eder ama içlerinde aranacak metin bulamaz; OCR (görüntüden metin çıkarma) henüz desteklenmez.

- **Tespit:** Komut satırı raporunda bu dosyalar "no extractable text" notuyla işaretlenir. Arayüzde ise belgeyle ilgili bir soru sorulduğunda bu belge kaynak olarak hiç gelmez.
- **Çözüm:** Bu dosyalar yüklemeden önce müşterinin kendi aracıyla (ör. Adobe Acrobat'taki metin tanıma) aranabilir PDF'e çevrilmelidir. Mümkünse belgenin asıl Word ya da PDF hali yüklenmelidir.
