# BGE-M3 staging indeks nesli

**Durum:** Yalnızca staging. Production'da etkin değil; production embedding ayarı, `rag_documents` koleksiyonu ve veritabanı değişmez. Tasarım: [balanced-multilingual-migration-v1.md](../architecture/balanced-multilingual-migration-v1.md) (#27). Bu belge tasarımın küçültülmüş bir staging uygulamasını anlatır, production geçişi için yetki vermez.

## 1. Ne yapar

Bir çalışma alanı (Workspace) RAG aramasını doğrulanmış bir **indeks neslinden** (index generation) yapabilir. Nesil, BGE-M3 ile kendi koleksiyonuna indekslenir. Diğer tüm çalışma alanları eskisi gibi MiniLM `rag_documents` yolunu kullanır.

| | Değer |
|---|---|
| Profil | `balanced-multilingual@1` (inceleme kaydındaki aday) |
| Model | `BAAI/bge-m3`, revizyon `31e47391fcbda65be526abe98e646b3c6cd845a8`, 1024 boyut, cosine, normalize, ön ek yok |
| Model dosyası | `models/compact-multilingual-bge-m3-v1/bge-m3-31e47391…` (yerelde; indirme yok). Yükleyici dizin adındaki revizyonu ve `model.safetensors` boyutunu (2.271.064.456 bayt) doğrular; `local_files_only`, `trust_remote_code=False`, CPU |
| Parçalama | `modai-word-split-v1`, 700/100 kelime: MiniLM yolu ile aynı parçalar |
| Uzay hash'i | `cf320884e111a07f254895abdf762705027abcbe7f5b3c5047419b6fb7b9da4d` |
| Koleksiyon | `modai_space_cf320884e111a07f2548` (uzay hash'inden türetilir; isim verilemez) |

## 2. Güvenceler

- **Yalnızca staging:** nesil yolu `RETRIEVAL_GENERATIONS_ENABLED=true` **ve** `APP_ENV=staging` birlikte olduğunda açılır. İkisi `docker-compose.staging.yml`'de tanımlıdır. Production bu bayrağı tanımlamaz ve `APP_ENV=development` ile çalışır; bu durumda araç plan/build/validate/activate komutlarını reddeder.
- **Vektörler karışmaz:** MiniLM (384) ve BGE-M3 (1024) ayrı koleksiyonlardadır. Sorgu, nesil sözleşmesinin modeliyle gömülür; adaptör, sorgu uzayı ile koleksiyon uzayı aynı değilse Qdrant'a gitmeden hata verir. MiniLM koleksiyonu nesil aracı tarafından okunmaz ve yazılmaz.
- **Geri dönüş yok:** nesil modundaki bir çalışma alanı hiçbir hatada MiniLM'e düşmez. Atama satırı, nesil durumu ya da sözleşme hash'leri tutmazsa ya da bayrak kapalıysa istek 503 alır (WebSocket'te hata olayı döner).
- **Yetki aynı kalır:** önce mevcut Knowledge Base yetkilendirmesi çalışır; arama yalnızca yetkili KB'lerde, kurum, çalışma alanı, nesil ve uzay filtreleriyle yapılır. Her sonuç PostgreSQL'de yeniden kontrol edilir: belge silinmemiş, KB yetkili ve sürümü ile kaynak revizyonu indekslenenle aynı olmalı. Eski bir nokta prompt'a girmez.
- **Eksik indeks etkinleşemez:** etkinleştirme için `ready` durumda, geçmiş bir doğrulama gerekir. Doğrulama sonrası kaynaklar değişmişse veya yeni kaynak olayı varsa etkinleştirme reddedilir.
- **Atomik geçiş:** tek bir `workspace_retrieval_assignments` satırı satır kilidiyle ve beklenen epoch'la değişir. Her istek bu satırı bir kez okur.
- **Denetim kaydı:** `retrieval_migration_created`, `retrieval_migration_validation_passed/failed`, `retrieval_profile_activated`, `retrieval_profile_rollback`. Kayıtlarda içerik, soru ya da vektör yoktur.

## 3. Komutlar

Komutlar staging worker konteynerinde çalışır. Çıktıda yalnızca kimlikler, sayılar ve hash'ler bulunur.

```bash
docker compose -f docker-compose.staging.yml --env-file .env.staging exec -T worker python -m app.tools.retrieval_generation status --workspace-id 1
```

| Komut | Ne yapar |
|---|---|
| `plan --workspace-id N` | Nesil kaydını `planned` olarak açar. Çalışma alanında bitmemiş başka aday varsa reddeder. |
| `build --generation-id G` | Hazır sürümü olan, silinmemiş her belgeyi kaynak dosyasından çıkarıp parçalara ayırır, BGE-M3 ile gömer ve yazar. Belge başına ilerleme `index_generation_items`'a kaydedilir. Yeniden çalıştırılabilir: değişmeyen belgeler atlanır. Bir belge başarısız olursa nesil `building` durumunda kalır. Etkin nesil yeniden oluşturulamaz. |
| `validate --generation-id G` | Etkinleştirme kapısı. Şunları kontrol eder: sözleşme hash'leri; koleksiyon vektör adı, boyutu, metriği ve payload indeksleri; her uygun belgenin güncel sürümüyle eksiksiz olması; tüm noktaların payload'ı; fazla, eksik ya da çift nokta olmaması; 5 smoke araması; başka KB ve çalışma alanından 0 sonuç gelmesi. Geçerse durum `ready` olur. |
| `activate --workspace-id N --generation-id G --expected-epoch E --confirm-workspace N` | Doğrulama hâlâ güncelse atamayı `generation` moduna alır ve epoch'u bir artırır. |
| `rollback --workspace-id N --expected-epoch E --confirm-workspace N` | Atamayı `legacy`'ye döndürür. Nesil `superseded` olur, noktaları silinmez. Bayrak kapalıyken de çalışır. |

Sonuç: BGE-M3'ü yeniden etkinleştirmek için önce `validate` (durum yeniden `ready` olur), sonra `activate` çalıştırılır.

## 4. Geri alma

- Worker her yüklemeyi `rag_documents`'a yazmaya devam eder, bu yüzden MiniLM indeksi her zaman günceldir.
- Geri alma yalnızca bir işaretçi değişikliğidir; yeniden indeksleme gerekmez. Staging provası 4,2 saniye sürdü (`docker exec` dahil) ve sonraki istek MiniLM kaynaklarıyla yanıtlandı.
- Geri almadan sonra API süreci BGE-M3'ü bellekte tutmaya devam eder. Belleği boşaltmak için yalnızca staging API konteyneri yeniden başlatılır.
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
- Kendinden emin yanlış sayı: MiniLM 3 (iki kez "1 saat", bir kez fazladan onaylayan), BGE-M3 0.
- Her iki modelde de sonuçlar yalnızca seçilen KB'den geldi.
- Bu küçük kurgusal setteki sonuç üretim güvenilirliğini kanıtlamaz.

Kök neden notu: MiniLM en fazla 256 token görür. Türkçe bir parçada bu yaklaşık ilk 80 kelimedir. Demo belgelerinin hepsi aynı başlık ve uyarı metniyle başladığından MiniLM belgeleri zayıf ayırır. BGE-M3 parçanın tamamını görür (8192 token).

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

Sözcük örtüşmesine dayalı bir kural ise doğru diller arası yanıtları reddederdi; örneğin Türkçe soruya İngilizce "2 devices" satırından verilen yanıtı. Bu yüzden ikisi de eklenmedi. Bu hata türünün ölçülen çözümü doğru belgeyi getirmek: BGE-M3 ile kendinden emin yanlış sayı 3'ten 0'a indi.

## 7. Production için eksikler (ayrı onay gerektirir)

- **Yeni yüklemeler nesle yazılmaz.** Nesil modunda yeni yüklenen ya da değiştirilen bir belge, nesil yeniden oluşturulana kadar aranamaz. Değişen belgenin eski noktaları sorguda elenir. `status` komutu bunu `validation_current: false` olarak gösterir. Production'da gerekenler: tasarımdaki çift indeksleme, olay kuyruğunu yeniden oynatma, yazma kapısı ve kaynak olayları için alındı kayıtları.
- **Yönetim yüzü yok.** Komut satırı dışında yönetim API'si, arayüz ve rol kontrolü yok.
- **Doğrulanmış MiniLM nesli yok.** Bu yapılmadan "anında geri alma" production'da tasarımın istediği biçimde iddia edilemez; staging'de geri alma, sürekli güncel tutulan eski koleksiyona yapılır.
- **Ölçümler eksik.** Kapasite ve gecikme hedef donanımda swap olmadan ölçülmeli. Eşzamanlılık ve uzun belgeler ölçülmedi.
- **Değerlendirme seti küçük.** Gerçek, yetkili bir belge setiyle değerlendirme yapılmalı; 24 kurgusal belge ve 9 soru yeterli değil.
