# modAI Voice — kontrollü pilot sürüm kontrol listesi

Kapsam: PR #51 (`feat/voice-assistant-mvp`). Canlı sürüm şu an `6f0adabe`. Bu listedeki dağıtım ve geri alma adımları sahip onayı olmadan uygulanmaz.

## 1. Demo kurulumu ve izole veri
- [ ] Demo yalnızca kurgusal belgelerle yapılır (`demo/voice-knowledge-pack/`, "Atlasnova Demo" Knowledge Base). Müşteri veya şirket belgesi içeren bir Workspace kullanılmaz.
- [ ] Prova `docker-compose.staging.yml` ile yapılır. Bu proje ayrı bir Compose projesidir (`modai-staging`): kendi veritabanı, Qdrant ve upload volume'ları vardır; yalnızca `127.0.0.1:5183/8100` portlarında çalışır; sırları `.env.staging` dosyasındadır. Production'a belge yüklenmez.
- [ ] Sunumda yalnızca `voice-demo-guide.md`'deki doğrulanmış sorular kullanılır.

## 2. Ses modelleri
- [ ] `python3 scripts/fetch_voice_models.py --check` hatasız tamamlanır. Base de denenecekse komut `--include-optional` ile çalıştırılır.
- [ ] Varsayılan konuşma tanıma modeli **Whisper Tiny**'dir. Base yalnızca seçilebilir bir seçenektir; sahibin gerçek mikrofon testi sonuçlanana kadar varsayılan değişmez.
- [ ] Sunumdan önce `/voice` açılır, **Modelleri hazırla**'ya basılır ve iki rozetin "Hazır" olduğu görülür.
- [ ] Tarayıcı olarak masaüstü Chrome veya Edge kullanılır. Mikrofon için `https://` ya da aynı makinede `http://localhost` gerekir.

## 3. Türkçe davranış
- [ ] "Yanıt dili" Türkçe'dir (varsayılan). İngilizce belgeye dayanan yanıt da Türkçe gelir. Türkçe olmayan cümleler sesle okunmaz.
- [ ] Selamlaşmalar belgelerde aranmadan yerel olarak yanıtlanır ve kaydedilmez.
- [ ] "Göndermeden önce soruyu göster" açıktır, böylece yanlış anlaşılan soru gönderilmeden düzeltilir.

## 4. Görüşme kalıcılığı
- [ ] Tamamlanan yanıtlar görüşmeye kaydedilir ve `/voice`'a dönüldüğünde otomatik çalmadan geri yüklenir.
- [ ] Durdurulan yanıtlar ile selamlaşmalar kaydedilmez ve bu ekranda belirtilir.

## 5. Kanıt ve kaynaklar
- [ ] Her yanıtla birlikte kaynak belgeler gösterilir. Geri yüklenen eski yanıtlarda alıntı metni saklanmadığı için "Alıntı kayıtlı değil" yazar.
- [ ] Seçili KB'lerden hiç kaynak gelmezse model çağrılmaz; "belge bulunamadı" sabit yanıtı döner.
- [ ] Bazı sayısal sorularda tablo bir değeri çözmez: değer iki satırın tam sınırındadır ya da aynı sütunlu iki belge farklı değer verir. Bu durumda model çağrılmaz; tablodan üretilen sabit bir açıklama döner ve kaynaklar yine gösterilir.

## 6. Bilinen sınırlamalar (müşteriye söylenecek)
- **Belge arama (MiniLM):** Türkçe sorularla İngilizce belgeler bulunmaz. Staging ölçümünde diller arası 7 sorunun 0'ında doğru belge ilk 3'te çıktı; BGE-M3 ile 7/7. Arama, sözcükle söylenen sayıyı ("üç yıl") rakamla ("3 yıl") birlikte de deniyor. Bu yalnızca kısmi bir iyileşme: 15 sorunun 9'undan 10'una çıktı. Kalıcı çözüm, ayrıca onaylanacak çok dilli embedding geçişi (BGE-M3, tasarım #27). Staging'de bir BGE-M3 indeks nesli denendi: 9 kabul sorusu × 2 koşuda MiniLM 11/18, BGE-M3 18/18 doğru yanıt verdi (bkz. `bge-m3-staging-generation.md`). Production'da etkin değildir.
- **Belgesiz soru:** doğru belge gelmezse model zaman zaman uydurma bir değer verebilir (ör. SLA yanıt süresi). Kaynak paneli bu durumda ilgili belgeyi göstermez.
- **Sürüm seçimi:** eski ve güncel politika arasında seçim yapılmaz. Sistem iki belgenin farklı olduğunu söyler, ama hangisinin geçerli olduğunu bilemez.
- **Desteklenmeyenler:** hesaplamalar (toplamlar), PDF ya da birleşik hücreli tablolar.
- **Tabloda olmayan sütun:** tabloda olmayan bir bilgi sorulursa model yine de bir satırdan yanıt verebilir.
- **Model değişkenliği:** gemma3:4b aynı soruya farklı ifadeler üretebilir. Sayısal tablo dışındaki ayrıntılar doğrulanmalıdır.
- **Ses tanıma:** Whisper Tiny gürültüde zayıftır; Base daha doğru ama daha yavaştır. Gerçek mikrofon karşılaştırması sahip testindedir.
- **Gecikme (M1 Pro):** model ılıkken ilk token yaklaşık 4,7–8 sn, soğukken 12–18 sn sürer. `/voice` açıldığında ve kayıt başladığında warm-up çalışır.

## 7. Bellek
- **Ölçüm makinesi:** Apple M1 Pro, 16 GB. Docker VM 7,65 GiB sınırında; production yığını yaklaşık 1,2 GB, staging yığını yaklaşık 1,2 GB kullanıyor.
- **Ollama:** gemma3:4b yüklüyken yaklaşık 4,6 GB.
- **Çok dilli arama (BGE-M3):** etkin bir nesil varken API ve worker'ın her biri yaklaşık 2 GiB daha kullanır. Docker VM sınırı en az 8 GiB olmalıdır.
- **Tarayıcı sekmesi:** Tiny ile yaklaşık 1,3 GB, Base ile yaklaşık 1,8 GB.
- **Gözlem:** production, staging ve Chrome birlikte açıkken swap 16–25 GB'a çıktı ve ilk token 20–35 sn'ye uzadı.
- [ ] Demo sırasında yalnızca bir yığın çalıştırılır: production ya da staging, ikisi birden değil. Ağır uygulamalar ve sekmeler kapatılır.
- [ ] Mümkünse 32 GB bellekli bir makine kullanılır.

## 8. Dağıtım ön koşulları (sahip onayıyla)
- [ ] PR #51 sahip tarafından onaylanmış ve merge edilmiş, CI yeşil.
- [ ] Yeni migration yok. Alembic head `0008_assistant_preferences` olarak kalır.
- [ ] Yeni ortam değişkenleri: `RETRIEVAL_GENERATIONS_ENABLED` (varsayılan kapalı) ve `RETRIEVAL_MODEL_ROOT` (varsayılan `/models`). Açılmaları tek başına yanıtları değiştirmez; BGE-M3 bir çalışma alanında ancak `app.tools.retrieval_generation activate` ile devreye girer (bkz. `bge-m3-staging-generation.md`, 7. bölüm).
- [ ] Güvenlik başlıkları nginx'te ve FastAPI'de değişir: `microphone=(self)`, `script-src 'self' 'wasm-unsafe-eval'`, `worker-src 'self'`.
- [ ] Oturum yenileme düzeltmesi:
  - nginx `Host`'u portla birlikte iletir (`$http_host`).
  - API refresh çerezini yapılandırılmış adla (`REFRESH_COOKIE_NAME`) okur.
  - Bu düzeltme olmadan production'da da refresh 403/401 döner ve oturum 30 dakikada düşer.
  - Dağıtım sonrası doğrulama: giriş yapılır, `POST /api/auth/refresh` 200 dönmeli; logout 204, ardından refresh 401 dönmeli.
- [ ] Ses modelleri build makinesinde `frontend/public/voice-models/` altına indirilmiş ve `--check` ile doğrulanmıştır. Frontend imajı bu dosyaları içerir.
- [ ] `python3 scripts/fetch_retrieval_models.py --check` başarılıdır (BGE-M3, `models/` altında).
- [ ] `python3 scripts/preflight.py` çıktısında `FAIL` yoktur; `WARN` satırları teslim notuna yazılmıştır.
- [ ] `docker-compose.yml` bu sürümde iki şeyi değiştirir:
  - API ve worker'da `RETRIEVAL_GENERATIONS_ENABLED: "true"` ve `RETRIEVAL_MODEL_ROOT: "/models"` tanımlıdır.
  - PostgreSQL, Redis ve Qdrant portları `127.0.0.1:` önekiyle yalnızca yerel makineye bağlıdır. Bu yüzden ilk dağıtımda o üç konteyner de yeniden oluşturulur (`docker compose up -d postgres redis qdrant`); volume'lar korunur. Öncesinde `scripts/backup_local.sh` ile yedek alınır.
- [ ] Kuyrukta bekleyen indeksleme işi yok (`LLEN modai:indexing:queued`).
- [ ] Çalışan imajlar geri alma etiketiyle işaretlenir. Bkz. 9. bölüm.
- [ ] `BUILD_SHA=<sha> docker compose build api worker frontend` çalıştırılır. Ardından imajlardaki BUILD_SHA, frontend bundle SHA ve `app/` dosya hash'leri git ağacıyla doğrulanır.
- [ ] `BUILD_SHA=<sha> docker compose up -d --no-deps --no-build api worker frontend`
- [ ] Smoke testi:
  - `/version` yeni SHA'yı gösterir;
  - `/voice` açılır ve modeller hazırlanır;
  - üç doğrulanmış soru kaynaklarıyla yanıtlanır;
  - sayfadan çıkıp dönünce görüşme geri yüklenir;
  - `POST /rag/warmup` oturumla 202, oturumsuz 401 döner.
- [ ] Çok dilli arama ayrı bir onayla açılır: `plan`, `build`, `validate`, `activate` (bkz. `bge-m3-staging-generation.md`, 7. bölüm). Ardından kabul soruları sorulur; sorun çıkarsa `rollback` çalıştırılır.

## 9. Geri alma
- **Dağıtımdan önce:** çalışan imajlar `rollback-<eski-sha>` olarak etiketlenir:
  ```bash
  docker tag localairealtimeragplatform-api:latest localairealtimeragplatform-api:rollback-6f0adabe
  ```
  Aynı komut `worker` ve `frontend` için de çalıştırılır.
- **Geri almak için:** üç geri alma imajı `:latest` olarak yeniden etiketlenir, sonra servisler yeniden başlatılır:
  ```bash
  docker compose up -d --no-deps --no-build api worker frontend
  ```
- **Veri ve şema:** migration olmadığı için geri alma yalnızca imaj düzeyindedir. Yeni sürümle oluşturulan sesli görüşmeler mevcut asistan görüşmeleri tablosunda kalır ve eski sürümün RAG Chat ekranında görünür.
- **Kontrol:** geri almadan sonra `/version` eski SHA'yı gösterir; RAG Chat'te bir soru sorulur.
