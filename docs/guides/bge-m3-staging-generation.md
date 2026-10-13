# BGE-M3 çok dilli arama (indeks nesli)

**Durum:** Staging'de denendi ve doğrulandı. Production'da bir çalışma alanı için açılması sahibin ayrı onayını gerektirir (bkz. 7. bölüm). Açılmadıkça hiçbir çalışma alanının davranışı değişmez. Tasarım: balanced-multilingual-migration-v1.md (#27); bu belge tasarımın tek kurulumlu, küçültülmüş uygulamasını anlatır.

## 1. Ne yapar

Bir çalışma alanı (Workspace) RAG aramasını doğrulanmış bir **indeks neslinden** (index generation) yapabilir. Nesil, BGE-M3 ile kendi koleksiyonuna indekslenir. Diğer tüm çalışma alanları eskisi gibi MiniLM `rag_documents` yolunu kullanır.

| | Değer |
|---|---|
| Profil | `balanced-multilingual@1` (inceleme kaydındaki aday) |
| Model | `BAAI/bge-m3`, revizyon `31e47391fcbda65be526abe98e646b3c6cd845a8`, 1024 boyut, cosine, normalize, ön ek yok |
| Model dosyası | `models/compact-multilingual-bge-m3-v1/bge-m3-31e47391…` (yerelde; indirme yok). Yükleyici dizin adındaki revizyonu ve `model.safetensors` boyutunu (2.271.064.456 bayt) doğrular; `local_files_only`, `trust_remote_code=False`, CPU |
| Parçalama | Varsayılan `modai-word-split-v1`, 700/100 kelime: MiniLM yolu ile aynı parçalar. İsteğe bağlı `modai-structured-v1`: satırları ve tabloları korur (9. bölüm) |
| Uzay hash'i | `cf320884e111a07f254895abdf762705027abcbe7f5b3c5047419b6fb7b9da4d` |
| Koleksiyon | `modai_space_cf320884e111a07f2548` (uzay hash'inden türetilir; isim verilemez) |

## 2. Güvenceler

- **Açık bayrak:** nesil yolu yalnızca `RETRIEVAL_GENERATIONS_ENABLED=true` olduğunda kullanılabilir. Bayrak tek başına hiçbir şeyi değiştirmez: her çalışma alanı, yönetici doğrulanmış bir nesli etkinleştirene kadar MiniLM ile hizmet verir. Bayrak kapalıyken panel ve araç hazırlamayı ve etkinleştirmeyi reddeder (API 409 döner); geri alma her zaman çalışır.
- **Yetki:** paneli ve API'yi çalışma alanı üyeliği yönetir. Durumu çalışma alanının her üyesi görür; Hazırla, Etkinleştir ve Geri al yalnızca o çalışma alanında (ya da organization genelinde) `admin` üyeliği olanlara açıktır. Platform yöneticisi rolü tek başına erişim vermez.
- **Vektörler karışmaz:** MiniLM (384) ve BGE-M3 (1024) ayrı koleksiyonlardadır. Sorgu, nesil sözleşmesinin modeliyle gömülür; adaptör, sorgu uzayı ile koleksiyon uzayı aynı değilse Qdrant'a gitmeden hata verir. MiniLM koleksiyonu nesil aracı tarafından okunmaz ve yazılmaz.
- **Geri dönüş yok:** nesil modundaki bir çalışma alanı hiçbir hatada MiniLM'e düşmez. Atama satırı, nesil durumu ya da sözleşme hash'leri tutmazsa ya da bayrak kapalıysa istek 503 alır (WebSocket'te hata olayı döner).
- **Yetki aynı kalır:** önce mevcut Knowledge Base yetkilendirmesi çalışır; arama yalnızca yetkili KB'lerde, kurum, çalışma alanı, nesil ve uzay filtreleriyle yapılır. Her sonuç PostgreSQL'de yeniden kontrol edilir: belge silinmemiş, KB yetkili ve sürümü ile kaynak revizyonu indekslenenle aynı olmalı. Eski bir nokta prompt'a girmez.
- **Eksik indeks etkinleşemez:** etkinleştirme için `ready` durumda, geçmiş bir doğrulama gerekir. Doğrulama sonrası kaynaklar değişmişse veya yeni kaynak olayı varsa etkinleştirme reddedilir.
- **Yeni yüklemeler nesle de yazılır:** nesil modundaki bir çalışma alanında worker yayınladığı her belgeyi hem `rag_documents`'a (geri dönüş kopyası) hem etkin nesle yazar. Bu yazma kaynak durumu değişmeden önce yapılır. Başarısız olursa yayın commit edilmez ve iş yeniden denenir. Yeni noktalar yazıldıktan sonra eski sürümün noktaları temizlenir; belge arada aranamaz hale gelmez. Silinen belge PostgreSQL'de işaretlenir ve noktaları sorguda elenir. Worker açılışta etkin neslin modelini önceden yükler.
- **Kaynak yoksa model çağrılmaz:** hiçbir kaynak getirilmezse (boş KB ya da tüm sonuçlar elendi) yanıt, model çağrılmadan sabit bir "belge bulunamadı" metnidir. Staging'de bu durumda model "yılda 5 gün" diye uydurmuştu.
- **Atomik geçiş:** tek bir `workspace_retrieval_assignments` satırı satır kilidiyle ve beklenen epoch'la değişir. Her istek bu satırı bir kez okur.
- **Denetim kaydı:** `retrieval_migration_started` (panelden hazırlık istendi), `retrieval_migration_created`, `retrieval_migration_validation_passed/failed`, `retrieval_profile_activated`, `retrieval_profile_rollback`. Panelden yapılan işlemlerde işlemi yapan kullanıcı kaydedilir. Kayıtlarda içerik, soru ya da vektör yoktur.

## 3. Yönetim paneli ve komutlar

### Panel: Sistem › Arama profili

Sistem sayfasındaki **Arama profili** paneli, kenar çubuğunda seçili çalışma alanını gösterir:

- **Etkin profil:** "Varsayılan (MiniLM)" ya da "Çok dilli (BGE-M3)".
- **Çok dilli indeks:** nesil durumu (Planlandı, İndeksleniyor, Doğrulanıyor, Hazır, Geri alındı) ve nesil numarası.
- **İndekslenen belgeler:** güncel sürümüyle indekslenmiş belge sayısı / indekslenmesi gereken belge sayısı (`index_generation_items`'tan).
- **Gecikme:** eksik ya da eski kalan belge sayısı ve silinmiş belgelerden kalan nokta sayısı.
- **Son doğrulama:** zamanı, geçip geçmediği ve o zamandan beri belgelerin değişip değişmediği.
- **Son hazırlık:** Sırada, Hazırlanıyor, Tamamlandı ya da Başarısız; başarısızsa hata kodunun Türkçe açıklaması.

Düğmeler yalnızca çalışma alanı yöneticilerine görünür:

| Düğme | Ne yapar |
|---|---|
| **Hazırla** | `plan` (ya da yarım kalan nesli sürdürme), `build` ve `validate` işini worker kuyruğuna (`modai:retrieval:queued`) ekler. Yanıtlar değişmez. API isteği beklemez; panel iş sürerken durumu 3 saniyede bir yeniler. Bir çalışma alanında aynı anda tek hazırlık olabilir. Hazırlık sırasında yeni belge yüklenirse worker indekslemeyi ve doğrulamayı en fazla 3 tur tekrarlar. |
| **Etkinleştir** | Yalnızca doğrulama geçmiş ve hâlâ güncelse açılır. Onay penceresinde çalışma alanının adı aynen yazılır. Yanıtlar hemen BGE-M3 indeksinden gelir. |
| **Geri al** | Çalışma alanı çok dilli profildeyken görünür. Ad yazılarak onaylanır; anında MiniLM'e döner. Bayrak kapatıldıysa da görünür, çünkü bozulan bir çalışma alanının çıkış yolu budur. |

Panel, gösterdiği nesli ve atama epoch'unu gönderir. Bu arada başka biri profili değiştirdiyse ya da belgeler değiştiyse işlem reddedilir ve durum yenilenir. Bayrak kapalıyken Hazırla ve Etkinleştir görünmez.

Hazırlık worker'da çalışır ve BGE-M3'ü (yaklaşık 2 GiB) worker belleğine yükler. Model, worker yeniden başlatılana kadar bellekte kalır. Başarısız bir hazırlık güvenli bir kodla kaydedilir (`items_failed`, `validation_failed`, `model_unavailable`, `timeout`, `interrupted` gibi); belge metni hata kaydına ya da loglara yazılmaz. Yeniden **Hazırla** aynı nesli kaldığı yerden sürdürür. Bir hazırlık en fazla `RETRIEVAL_JOB_TIMEOUT_SECONDS` (varsayılan 21600 sn, 6 saat) sürebilir.

API (kimlik doğrulamalı):

| Yöntem ve yol | Yetki | Sonuç |
|---|---|---|
| `GET /workspaces/{id}/retrieval` | Çalışma alanı üyesi | Durum, gecikme, son doğrulama, son hazırlık, `generations_enabled`, `can_manage` |
| `POST /workspaces/{id}/retrieval/prepare` | Çalışma alanı yöneticisi | 202 ve kuyruğa alınan iş; 409: hazırlık zaten var, profil zaten etkin ya da bayrak kapalı; 503: kuyruk yok |
| `POST /workspaces/{id}/retrieval/activate` | Çalışma alanı yöneticisi | Gövde: `generation_id`, `expected_epoch`, `confirm_workspace_name`. 409: epoch değişti, doğrulama eski, hazırlık sürüyor ya da bayrak kapalı; 422: nesil hazır değil; 400: ad tutmuyor |
| `POST /workspaces/{id}/retrieval/rollback` | Çalışma alanı yöneticisi | Gövde: `expected_epoch`, `confirm_workspace_name`. 409: epoch değişti ya da zaten MiniLM; 400: ad tutmuyor |

Bu sürüm `retrieval_jobs` tablosunu ekler. Güncellemeden sonra `alembic upgrade head` çalıştırılmalıdır; tablo yoksa worker indeksleme işlerine devam eder, yalnızca hazırlıklar çalışmaz.

### Komut satırı (yedek yol)

Panel kullanılamadığında aynı adımlar komut satırından yapılır. Panel ve komutlar aynı servis kodunu kullanır. Ancak ikisi aynı anda aynı çalışma alanı için kullanılmamalıdır: komutlar paneldeki iş kaydını görmez.

Komutlar worker konteynerinde çalışır. Çıktıda yalnızca kimlikler, sayılar ve hash'ler bulunur.

```bash
docker compose exec -T worker python -m app.tools.retrieval_generation status --workspace-id 1
```

Staging'de aynı komut `docker compose -f docker-compose.staging.yml --env-file .env.staging exec -T worker …` ile çalıştırılır. `status`, her nesil için `lag` alanında eksik ya da eski kalan belgeleri gösterir; etkin bir nesilde bu liste boş olmalıdır.

| Komut | Ne yapar |
|---|---|
| `plan --workspace-id N [--materialization structured-v1]` | Nesil kaydını `planned` olarak açar. Parçalama sözleşmesi burada seçilir ve nesil boyunca değişmez (varsayılan `word-split-v1`). Çalışma alanında bitmemiş başka aday varsa reddeder. |
| `build --generation-id G` | Hazır sürümü olan, silinmemiş her belgeyi kaynak dosyasından çıkarıp parçalara ayırır, BGE-M3 ile gömer ve yazar. Belge başına ilerleme `index_generation_items`'a kaydedilir. Yeniden çalıştırılabilir: değişmeyen belgeler atlanır. Bir belge başarısız olursa nesil `building` durumunda kalır. Etkin nesil yeniden oluşturulamaz. |
| `validate --generation-id G` | Etkinleştirme kapısı. Şunları kontrol eder: sözleşme hash'leri; koleksiyon vektör adı, boyutu, metriği ve payload indeksleri; her uygun belgenin güncel sürümüyle eksiksiz olması; tüm noktaların payload'ı; fazla, eksik ya da çift nokta olmaması; 5 smoke araması; başka KB ve çalışma alanından 0 sonuç gelmesi. Geçerse durum `ready` olur. |
| `activate --workspace-id N --generation-id G --expected-epoch E --confirm-workspace N` | Doğrulama hâlâ güncelse atamayı `generation` moduna alır ve epoch'u bir artırır. |
| `rollback --workspace-id N --expected-epoch E --confirm-workspace N` | Atamayı `legacy`'ye döndürür. Nesil `superseded` olur, noktaları silinmez. Bayrak kapalıyken de çalışır. |

Geri almadan sonra BGE-M3'ü yeniden etkinleştirmek için önce `validate` (durum yeniden `ready` olur), sonra `activate` çalıştırılır. Panelde bunun karşılığı önce **Hazırla**, sonra **Etkinleştir**'dir.

## 4. Geri alma

- Worker her yüklemeyi `rag_documents`'a yazmaya devam eder, bu yüzden MiniLM indeksi her zaman günceldir; nesil modunda aynı yükleme etkin nesle de yazılır.
- Geri alma yalnızca bir işaretçi değişikliğidir; yeniden indeksleme gerekmez. Panelde **Geri al**, komut satırında `rollback` ile yapılır. Staging provası 4,2 saniye sürdü (`docker exec` dahil) ve sonraki istek MiniLM kaynaklarıyla yanıtlandı.
- Geri almadan sonra API ve worker süreçleri BGE-M3'ü bellekte tutmaya devam eder. Belleği boşaltmak için bu iki konteyner yeniden başlatılır.
- BGE-M3 koleksiyonunu tamamen kaldırmak ayrı ve onaylı bir işlemdir; bu araç koleksiyon silmez.

## 5. Staging ölçümleri

Ortam: Apple M1 Pro 16 GB, Docker CPU. Çalışma alanı 1'de 24 kurgusal belge var ve her belge tek parça. Sorular `response_length=short` ile, ses istemcisinin gönderdiği gibi soruldu, her biri 2 kez.

### Arama ve yanıt

| Soru | MiniLM: doğru belge ilk 3'te | MiniLM: yanıt | BGE-M3: doğru belge ilk 3'te | BGE-M3: yanıt |
|---|---|---|---|---|
| Kıdemim 3 yıl… | 2/2 (1.) | 2/2 doğru (16) | 2/2 (1.) | 2/2 doğru |
| Kıdemim üç yıl… | 2/2 (1.) | 2/2 doğru | 2/2 (1.) | 2/2 doğru |
| 40.000 TL'lik… | 2/2 (1.) | 2/2 doğru | 2/2 (1.) | 2/2 doğru |
| Kırk bin liralık… | 2/2 (2.) | 1/2 (bir kez "İnsan Kaynakları" eklendi) | 2/2 (1.) | 2/2 doğru |
| VPN aynı anda kaç cihaz | 0/2 | 0/2 ("belirtilmemiş"; bir kez ilgisiz "750 TL") | 2/2 (1.) | 2/2 doğru (2 cihaz) |
| Premium Severity 2 ilk yanıt | 0/2 | **0/2, iki kez "1 saat" (yanlış)** | 2/2 (1.) | 2/2 doğru (2 saat) |
| 30 günüm yok muydu? | 2/2 (3.) | 2/2 doğru (15 gün) | 2/2 (1.) | 2/2 doğru |
| 2027 maaş artışı (belgede yok) | – | 2/2 doğru çekimser | – | 2/2 doğru çekimser |
| Kıdemim tam 5 yıl (tablo sınırı) | 0/2 | 0/2 (genel çekimserlik) | 2/2 (1.) | 2/2 sabit sınır yanıtı (16 / 21 iş günü, model çağrılmadı) |

- Toplam: MiniLM 11/18, BGE-M3 18/18 doğru.
- Kendinden emin yanlış yanıt: MiniLM 3 (iki kez yanlış sayı "1 saat", bir kez fazladan onaylayan), BGE-M3 0.
- Her iki modelde de sonuçlar yalnızca seçilen KB'den geldi.
- Bu küçük kurgusal setteki sonuç üretim güvenilirliğini kanıtlamaz.

Kök neden notu: MiniLM en fazla 256 token görür. Türkçe bir parçada bu yaklaşık ilk 80 kelimedir. Demo belgelerinin hepsi aynı başlık ve uyarı metniyle başladığından MiniLM belgeleri zayıf ayırır. BGE-M3 parçanın tamamını görür (8192 token).

### Yeni yükleme ve silme (staging, BGE-M3 etkin)

- Kurgusal bir test belgesi "General" KB'ye yüklendi. 20,6 saniyede indekslendi; bu süreye worker'ın modeli ilk kez yüklemesi dahil. Belge etkin nesilden hemen bulundu ve yanıt doğruydu ("yılda 3 iş günü").
- Bellek baskısı altında, API ile aynı anda model yüklenirken aynı işlem 108 saniye sürdü. Worker artık modeli açılışta yüklüyor.
- Belge silindikten sonra hiçbir kaynakta görünmedi ve yanıt sabit "belge bulunamadı" metni oldu. Bu düzeltmeden önce model aynı durumda kaynaksız "yılda 5 gün" diye uydurmuştu.

### Bellek ve gecikme

| Ölçüm | MiniLM | BGE-M3 |
|---|---|---|
| API konteyneri | ~440 MiB | ~1,92 GiB (MiniLM + BGE-M3; model dosyasının sayfa önbelleği dahil) |
| İndeksleme süreci (worker konteyneri, tepe) | – | 2,08 GiB (sayfa önbelleği dahil; süreç bittikten sonra kalan 1,3 GiB önbellektir, süreç RSS'i ~126 MB) |
| API'de soğuk yükleme | – | ~16 sn (warm-up ile `/voice` açılışında) |
| 24 belgeyi indeksleme | – | 93 sn (model yükleme dahil); doğrulama 22 sn |
| Qdrant diski | 1,9 MB | 5,3 MB (24 × 1024 vektör) |
| Sorgu embedding, istek başına (sunucu) | medyan ~0,10 sn | medyan ~0,8 sn (tek sorgu 0,4–1,5 sn, bir kez 3,8 sn); iki sorguluk istekte ~1,1–1,8 sn |
| Arama | medyan ~26 ms | medyan ~80 ms |
| İlk token (sunucu) | medyan ~3,5 sn | medyan ~3,9 sn |

Ölçüm koşulu: host swap 9–13,9 GB, boş bellek %16. Gecikmeler bu yüzden üst sınır kabul edilmelidir; aynı makinede swap olmadan yeniden ölçülmelidir.

Pratik kaynak önerisi:
- BGE-M3 yükleyen her süreç için yaklaşık 2 GiB.
- Docker VM sınırı en az 8 GiB, çünkü production'da API ile worker'ın ikisi de modeli tutacaktır.
- Ollama (gemma3:4b yaklaşık 4–4,6 GB) ve tarayıcıdaki ses modeli (1,3–1,8 GB) ayrıca gelir.
- 16 GB'lık tek makinede yalnızca tek yığın çalıştırılmalı; kontrollü pilot için 32 GB önerilir.

## 6. Sayısal güvence incelemesi (gönderilmedi)

Bilinen yanlış sayıların hepsi getirilen ama konu dışı bir belgede gerçekten geçiyordu:
- "Severity 2 → 1 saat": iç BT prosedüründeki "P2 | 1 saat" satırından geldi.
- "tam 5 yıl → 20 iş günü": uzaktan çalışma politikasındaki yurt dışı sınırından geldi.
- VPN sorusuna verilen "750 TL": internet desteğinden geldi.

Yanıttaki her sayının getirilen metinde geçmesini isteyen deterministik bir kontrol, kayıtlı 615 staging yanıtı üzerinde model çağırmadan denendi:
- 97 kendinden emin yanlış yanıtın ve 59 eksik yanıtın **hiçbirini** yakalamadı.
- 407 doğru yanıttan 2'sini (toplam ve çarpım hesapları) engelledi.

Sözcük örtüşmesine dayalı bir kural ise doğru diller arası yanıtları reddederdi; örneğin Türkçe soruya İngilizce "2 devices" satırından verilen yanıtı. Bu yüzden ikisi de eklenmedi. Bu hata türünün ölçülen çözümü doğru belgeyi getirmek: BGE-M3 ile kendinden emin yanlış yanıt 3'ten 0'a indi.

Eklenen tek koruma, hiç kaynak getirilmediğinde modeli çağırmamak. Bu durum kesin olarak tanımlı olduğu için yanlış ret üretmez.

## 7. Production'da açmak (sahip onayıyla)

1. Sürüm dağıtılır (pilot kontrol listesi, 8. bölüm). `docker-compose.yml` API ve worker için `RETRIEVAL_GENERATIONS_ENABLED: "true"` ve `RETRIEVAL_MODEL_ROOT: "/models"` tanımlar. Bu tek başına yanıtları değiştirmez.
2. BGE-M3 dosyası `python3 scripts/fetch_retrieval_models.py` ile indirilir ya da `--check` ile doğrulanır.
3. `alembic upgrade head` ile `retrieval_jobs` tablosu oluşturulur.
4. Çalışma alanı yöneticisi Sistem › Arama profili panelinde **Hazırla**'ya basar ve "Son hazırlık: Tamamlandı" ile "Hazır" durumunu bekler. Doğrulama geçmeden etkinleştirme yapılamaz. (Yedek yol: sırayla `plan`, `build`, `validate`.)
5. **Etkinleştir** ile çalışma alanının adı yazılarak onaylanır. Panelde "Çok dilli (BGE-M3)" ve 0 gecikme görülür. (Yedek yol: `activate`; `status` çıktısında `serving_mode: generation` ve boş `lag`.)
6. Kabul soruları gerçek belgelerle sorulur. Sorun çıkarsa panelde **Geri al** (ya da `rollback`) tek adımdır.

Bellek: API ve worker BGE-M3'ü tutar (her biri yaklaşık 2 GiB). Docker VM sınırı en az 8 GiB olmalı ve aynı makinede staging yığını çalışmamalıdır.

## 8. Bilinen sınırlar

- **Az sayıda çalışma alanı için tasarlandı.** Worker hazırlıkları sırayla çalıştırır; ikinci bir çalışma alanının hazırlığı birincisinin bitmesini bekler. Hazırlık kuyruğunu tek worker sürecinin tükettiği varsayılır (sağlanan compose dosyalarında olduğu gibi). Eski nesilleri silmek (retire) için panel ya da komut yoktur.
- **Model worker'da kalır.** Bir hazırlıktan sonra worker BGE-M3'ü yeniden başlatılana kadar bellekte tutar; profil etkinleştirilmeyecekse worker yeniden başlatılarak bellek boşaltılabilir.
- **Etkinleştirme sırasında yazma kapısı yok.** `validate` ile `activate` arasında gelen bir yükleme etkinleştirmeyi reddettirir; nesil yeniden `build` ve `validate` edilir (panelde yeniden **Hazırla**).
- **Doğrulanmış bir MiniLM nesli yok.** Geri alma, worker'ın sürekli güncel tuttuğu eski `rag_documents` koleksiyonuna yapılır.
- **Ölçümler swap altında alındı.** Kapasite ve gecikme pilot makinesinde, yalnızca production yığını çalışırken yeniden ölçülmelidir.
- **Değerlendirme seti küçük.** 24 kurgusal belge ve 9 soru üretim güvenilirliğini kanıtlamaz; gerçek belgelerle kabul testi gerekir.
- **PDF tabloları düz metindir.** PDF'ler pypdf ile çıkarılır; tablo hücreleri satır satır metin olur. Yapı koruyan parçalama PDF tablolarını düzeltmez (9. bölüm).

## 9. Yapı koruyan parçalama (`structured-v1`)

**Durum:** kodda hazır, hiçbir çalışma alanında açık değil. Açmak sahip onayıyla, çalışma alanı başına yapılır.

### Ne değişir

| | `word-split-v1` (varsayılan) | `structured-v1` |
|---|---|---|
| Parçalayıcı | `chunk_text`: kelimeler tek boşlukla birleşir, satırlar kaybolur | `chunk_structured`: satır ve paragraf sonları korunur, parça cümle sonunda biter |
| Markdown tablosu | tek satıra düzleşir, parça sınırında bölünebilir | 700 kelimeye sığıyorsa tek parçada kalır; sığmıyorsa satırlardan bölünür ve her parça başlık satırını tekrarlar |
| Örtüşme | son 100 kelime | önceki metnin en fazla 100 kelimesi (bütün cümleler); tablo satırları örtüşme olarak tekrarlanmaz |
| Sözleşme hash'i | `94fc0b22…0763` | `dae8298e…fc81` |

Payload alanları aynıdır (`generation-payload-v1`). İki sözleşmenin noktaları aynı BGE-M3 koleksiyonunda durabilir; `materialization_sha256` filtresiyle ayrılır.

DOCX tabloları (bu sürümden itibaren her iki yolda da) Markdown tablosu olarak çıkarılır. Birleşik hücreler kapsadıkları her satır ve sütunda tekrarlanır. Tablonun tamamını kaplayan ilk satır (tablo başlığı) tablonun üstüne satır olarak yazılır.

### Açma adımları (çalışma alanı başına)

```bash
docker compose exec -T worker python -m app.tools.retrieval_generation plan --workspace-id 1 --materialization structured-v1
docker compose exec -T worker python -m app.tools.retrieval_generation build --generation-id G
docker compose exec -T worker python -m app.tools.retrieval_generation validate --generation-id G
docker compose exec -T worker python -m app.tools.retrieval_generation activate --workspace-id 1 --generation-id G --expected-epoch E --confirm-workspace 1
docker compose exec -T worker python -m app.tools.retrieval_generation status --workspace-id 1
```

1. `plan` çıktısında `"materialization": "modai-structured-v1"` görülür.
2. `build` çalışma alanındaki bütün belgeleri kaynak dosyalarından yeniden çıkarır ve BGE-M3 ile yeniden gömer. Süre belge sayısıyla artar (staging'de 24 belge 93 sn).
3. `validate` geçmeden etkinleştirme yapılamaz.
4. `activate` sonrası `status` çıktısında etkin neslin `materialization` alanı `modai-structured-v1` olur ve `lag` boş kalır. Worker yeni yüklemeleri etkin neslin sözleşmesiyle, yani yapı koruyarak yazar.
5. Kabul: tablo soruları gerçek belgelerle sorulur (ör. "40.000 TL'lik alımı kim onaylar?", "Who approves a 40,000 TL purchase?").

Geri alma:
- `rollback` çalışma alanını MiniLM'e döndürür.
- Önceki `word-split-v1` nesline dönmek için: o nesil `validate` edilir. Kaynaklar değiştiyse doğrulama başarısız olur ve nesil `building` durumuna geçer. Bu durumda önce `build`, sonra `validate` çalıştırılır. Son adım `activate`'tir.
- Yeni nesil etkinleşince önceki nesil `superseded` olur. Noktaları silinmez; disk kullanımı iki nesil kadar olur.

### Mevcut belgeler ve nesiller üzerindeki etki

- **Veritabanı migration'ı ve yeni ortam değişkeni yok.**
- **Eski MiniLM indeksi (`rag_documents`):** parçalayıcı değişmedi. Yalnızca DOCX çıkarımı değişti. Yeni yüklenen, değiştirilen ya da yeniden indekslenen DOCX belgelerine tablolar da girer (tek satıra düzleşmiş olarak). Daha önce indekslenmiş DOCX belgeleri, belge bazında yeniden indekslenene kadar tablosuz kalır. TXT, MD ve PDF belgeleri etkilenmez.
- **Mevcut `word-split-v1` nesilleri:** sözleşme hash'i değişmedi; hizmet vermeye devam ederler. `build`, kaynağı değişmeyen belgeleri atladığı için o nesillerdeki DOCX belgeleri tablosuz kalır. Worker'ın yeni yazdığı DOCX belgelerinde ise tablolar vardır. DOCX tablolarını bir nesle almak için yeni bir nesil planlanır; `structured-v1` önerilir.
- **`structured-v1`'e geçiş:** yeni bir nesildir; çalışma alanının bütün belgeleri yeniden gömülür. Etkinleştirilmedikçe yanıtlar değişmez.
- Parçalama ayarı yalnızca nesillerde seçilir. Eski MiniLM yolu için ayar eklenmedi. `rag_documents` hangi parçalayıcıyla yazıldığını kaydetmez, bu yüzden karışık bir durum fark edilemezdi.

### Sınırlar

- PDF tabloları yapılandırılmaz. Değerlendirmede pdfplumber, çizgili tabloları (sarılmış hücreler dahil) doğru okudu. Ancak pdfminer.six ve pypdfium2 ile birlikte 17,2 MB yer kaplıyor (15 MB sınırının üstünde). pypdf'in düzen kipi ise tarayıcıdan basılmış bir PDF'te kelimeleri böldü ("politik  a ş  irk  et"). Bu yüzden ayrı iş olarak bırakıldı.
- Bölünmüş bir tablonun her parçası TABLE LOOKUP'ta ayrı okunur. Sınırdaki bir değerin iki satırı farklı parçalara düşerse çelişki yanıtı yerine iki eşleşme satırı gösterilir. Bu yalnızca 700 kelimeyi aşan tablolarda olur.
- Hücrede `|` geçen bir tablo TABLE LOOKUP'ta okunmaz; tablo yine bağlam olarak modele gider.

## 10. Bölüm bazlı parçalama (`section-v1`)

**Durum:** staging'de çalışma alanı 4'te (11 Ekim 2026), production'da sahip onayıyla çalışma alanı 1'de (12 Ekim 2026) etkin. Başka çalışma alanlarında açmak yine çalışma alanı başına yapılır.

### Neden

Kısa politikalar (175–370 kelime) `word-split-v1` ve `structured-v1` ile tek parça olarak indekslenir. Bir belgenin içindeki iki cümlelik bir kural (ör. "Destek ekibi lisans sayısını değiştirmez") bütün belgenin anlamı içinde kaybolur ve arama o belgeyi getirmez. `section-v1` her Markdown bölümünü ayrı parça yapar ve her parçanın başına belgenin başlığını ve bölümün başlık yolunu yazar:

```
# AtlasDesk Ürün Destek Talimatları
## 3. Lisans değişiklikleri

Lisans sayısını müşteri yöneticisi kendi yönetim panelinden artırabilir. **Destek ekibi lisans sayısını değiştirmez**; ...
```

- **Kısa bölümler:** 8 kelimeden kısa bölümler (ör. başlığın hemen altındaki alt başlık) bir sonrakiyle belge sırasıyla birleşir.
- **Uzun bölümler:** 700 kelimeyi aşan bölümler `structured-v1` ile bölünür ve her parça başlık yolunu tekrarlar. Tablolar bölünmez.
- **Başlıksız metin:** çoğu PDF ve başlıksız TXT, `structured-v1` ile aynı biçimde parçalanır.

Sözleşme hash'i: `189ad82a…ffea`. Payload alanları aynıdır.

### Staging ölçümü (Kalite paneli, 25 soru)

Ölçüm seti: `demo/voice-knowledge-pack/quality-checks.json` (9 Türkçe, 16 İngilizce). Arama dört departman bilgi tabanında yapıldı. Ortam: Gemma 3 4B, `RAG_TOP_K=3`, M1 Pro 16 GB. Parça sayısı 14 belgede 14'ten 98'e çıktı.

| Nesil | Geçen | Soru başına süre (medyan) | Başarısızlar |
|---|---|---|---|
| `word-split-v1` | 23/25 | 5,8 sn | "I lost my company laptop" (doğru belge 2. sırada, model yanıt vermedi); "Can the support team increase the license count?" (doğru belge hiç getirilmedi) |
| `section-v1` | 23/25 | 4,1 sn | Lisans sorusu: doğru bölüm artık getiriliyor, ama demo'da bilerek bırakılan eski v2 önde geliyor ve model ondan yanıtlıyor; 2027 maaş sorusunda modelin "belirlemez" diye verdiği ret, ölçüm modülünde ret sayılmadı (düzeltildi) |
| `section-v1` + eski sürümler arşivde | **25/25** | | |

### Production ölçümü (çalışma alanı 1, 12 Ekim 2026)

Aynı 25 soru, `python -m app.tools.quality_checks` ile tek bilgi tabanına ("Atlasnova Demo", aynı 14 demo belgesi) eşlenerek çalıştırıldı. Nesil 100 parça, doğrulama 5/5 smoke ve 0 izolasyon noktasıyla geçti.

| Nesil | Geçen | Notlar |
|---|---|---|
| `word-split-v1` | 23/25 | VPN sorusu İngilizce yanıtlandı; lisans sorusunda doğru belge getirilmedi |
| `section-v1` | 23/25 | Lisans sorusunda doğru bölüm artık getiriliyor. İki başarısız soru da demoda bilerek bırakılan eski v2 belgesinden yanıtlandı. Makine boştayken soru başına medyan 2,9 sn |

Süreler aynı koşullarda ölçülmedi: `word-split-v1` ölçümü (medyan 12,9 sn) staging yığını da çalışırken yapıldı. Aynı koşullardaki karşılaştırma staging tablosundadır.

Sonuç:
- `section-v1` aramayı kısa kurallara kadar inceltiyor ve parçalar küçüldüğü için yanıtı yaklaşık %29 hızlandırıyor.
- Eski sürüm belgeleri yüklü kaldıkça, doğru bölüm bulunsa bile yanlış yanıt riski sürer. Gerçek kurulumlarda eski sürümler arşivlenmeli ya da "Belgeyi değiştir" ile güncellenmelidir.

### Açma adımları (çalışma alanı başına)

9. bölümdeki komutlar `--materialization section-v1` ile çalıştırılır. Etkinleştirmeden önce ve sonra Kalite panelinde aynı soru seti çalıştırılır; sonuç düşerse `rollback` ile MiniLM'e dönülür ya da önceki nesil yeniden doğrulanıp etkinleştirilir.

### Sınırlar

- **Başlık gerekiyor:** yalnızca Markdown başlıkları (`#`…`######`) bölüm sayılır. DOCX'teki başlık stilleri henüz Markdown başlığına çevrilmiyor; bu belgeler `structured-v1` gibi parçalanır.
- **Çok bölümlü yanıtlar:** birden fazla bölüme yayılan bir yanıt, `RAG_TOP_K=3` ile üç küçük parçaya sığmayabilir. Ölçüm setinde böyle bir soru yoktu; müşteri soru setiyle ayrıca ölçülmelidir.
- **Uyarı paragrafları:** belgenin başındaki uyarı ya da önsöz paragrafları (demo'daki "KURGUSAL DEMO BELGESİ" gibi) kendi parçası olur.
