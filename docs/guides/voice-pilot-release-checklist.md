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
- [ ] Bazı sayısal sorularda tablo bir değeri çözmez: değer iki satırın tam sınırındadır ya da aynı sütunlu iki belge farklı değer verir. Bu durumda model çağrılmaz; tablodan üretilen sabit bir açıklama döner ve kaynaklar yine gösterilir.

## 6. Bilinen sınırlamalar (müşteriye söylenecek)
- **Belge arama:** Türkçe sorularla İngilizce belgeler çoğu zaman bulunmaz (MiniLM). Bazı sözcükle söylenmiş sayılarda ("üç yıl", "on bin lira") doğru belge gelmeyebilir.
- **Sürüm seçimi:** eski ve güncel politika arasında seçim yapılmaz. Sistem iki belgenin farklı olduğunu söyler, ama hangisinin geçerli olduğunu bilemez.
- **Desteklenmeyenler:** hesaplamalar (toplamlar), PDF ya da birleşik hücreli tablolar.
- **Tabloda olmayan sütun:** tabloda olmayan bir bilgi sorulursa model yine de bir satırdan yanıt verebilir.
- **Model değişkenliği:** gemma3:4b aynı soruya farklı ifadeler üretebilir. Sayısal tablo dışındaki ayrıntılar doğrulanmalıdır.
- **Ses tanıma:** Whisper Tiny gürültüde zayıftır; Base daha doğru ama daha yavaştır. Gerçek mikrofon karşılaştırması sahip testindedir.
- **Gecikme (M1 Pro):** model ılıkken ilk token yaklaşık 4,7–8 sn, soğukken 12–18 sn sürer. `/voice` açıldığında ve kayıt başladığında warm-up çalışır.

## 7. Bellek
- **Ölçüm makinesi:** Apple M1 Pro, 16 GB. Docker VM 7,65 GiB sınırında; production yığını yaklaşık 1,2 GB, staging yığını yaklaşık 1,2 GB kullanıyor.
- **Ollama:** gemma3:4b yüklüyken yaklaşık 4,6 GB.
- **Tarayıcı sekmesi:** Tiny ile yaklaşık 1,3 GB, Base ile yaklaşık 1,8 GB.
- **Gözlem:** production, staging ve Chrome birlikte açıkken swap 16–25 GB'a çıktı ve ilk token 20–35 sn'ye uzadı.
- [ ] Demo sırasında yalnızca bir yığın çalıştırılır: production ya da staging, ikisi birden değil. Ağır uygulamalar ve sekmeler kapatılır.
- [ ] Mümkünse 32 GB bellekli bir makine kullanılır.

## 8. Dağıtım ön koşulları (sahip onayıyla)
- [ ] PR #51 sahip tarafından onaylanmış ve merge edilmiş, CI yeşil.
- [ ] Yeni migration yok. Alembic head `0008_assistant_preferences` olarak kalır. Yeni ortam değişkeni yok.
- [ ] Güvenlik başlıkları nginx'te ve FastAPI'de değişir: `microphone=(self)`, `script-src 'self' 'wasm-unsafe-eval'`, `worker-src 'self'`.
- [ ] Ses modelleri build makinesinde `frontend/public/voice-models/` altına indirilmiş ve `--check` ile doğrulanmıştır. Frontend imajı bu dosyaları içerir.
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
