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
8. **Belgeler:** müşteri belgelerini yükleyin ve hepsinin "hazır" olmasını bekleyin.
9. **Çok dilli arama (önerilir):** Türkçe soruların İngilizce belgelerde de doğru kaynağı bulması için çalışma alanına BGE-M3 nesli kurulur. Komutlar ve güvenceler [bge-m3-staging-generation.md](bge-m3-staging-generation.md)'dedir.
   - Sıra: `plan`, `build`, `validate`, `activate`.
   - `status` çıktısında `serving_mode: generation` ve boş `lag` görülmelidir.
   - Bu adım için `RETRIEVAL_GENERATIONS_ENABLED=true` gerekir.
10. **Ses:** `/voice` sayfasında **Modelleri hazırla**'ya basılır. Varsayılan konuşma tanıma modeli Whisper Tiny'dir; Base daha doğru ama daha yavaştır ve isteğe bağlıdır.

## 3. Kabul testi (teslimden önce)

- Müşteriyle birlikte, belgelerinden yanıtı bilinen 10 soru hazırlayın. Bunlar şunları içermeli: en az 2 sayısal tablo sorusu, 1 İngilizce belge sorusu ve belgelerde yanıtı olmayan 1 soru.
- Her yanıtta doğru kaynak gösterilmeli ve sayılar belgeyle aynı olmalıdır. Belgede olmayan soruya "bilgi yok" ya da "belge bulunamadı" denmeli.
- 30 dakikadan uzun süren bir oturumda oturum kapanmamalı; çıkış yapınca oturum gerçekten kapanmalı.
- `/voice`'ta en az 3 soru sesli sorulmalı. Sayfadan çıkıp dönüldüğünde görüşme geri gelmeli.
- Sonuçları teslim notuna yazın. Yanlış bir yanıt varsa kaynağını ve sorunun ifadesini not edin.

## 4. Güvenlik kontrolleri

- Ağdan yalnızca web arayüzüne (5173) ve gerekiyorsa API'ye (8000) erişilmelidir. PostgreSQL (55432), Redis (6379) ve Qdrant (6333) yalnızca `127.0.0.1`'e bağlı olmalıdır. Compose dosyasında bu portlar için `127.0.0.1:` öneki olduğunu kontrol edin.
- **Birden fazla kullanıcının ağdan erişeceği kurulumlarda:**
  - TLS sonlandıran bir ters proxy kullanılır.
  - `APP_ENV=production` ve `REFRESH_COOKIE_SECURE=true` ayarlanır.
  - `TRUSTED_FRONTEND_ORIGINS` yalnızca gerçek adresi içerir.
  - Bu yapılmazsa mikrofon çalışmaz ve oturum çerezleri şifresiz bağlantıdan gider.
- `.env`, model klasörü ve yedekler erişimi sınırlı bir yerde tutulur ve depoya eklenmez.

## 5. Yedekleme, güncelleme ve geri alma

- **Yedekleme:** `scripts/backup_local.sh <klasör>`. Geri yükleme sırası README'deki "Yedekleme ve geri yükleme" bölümündedir.
- **Güncelleme:**
  - Önce çalışan imajları `rollback-<eski-sha>` diye etiketleyin.
  - Kuyrukta indeksleme işi olmadığını doğrulayın.
  - Ardından yeni sürümü `BUILD_SHA` ile derleyip başlatın; adımlar [pilot kontrol listesi](voice-pilot-release-checklist.md)'nin 8–9. bölümlerindedir.
- **Arama profilini geri alma:** `rollback` komutu çalışma alanını tek adımda MiniLM'e döndürür. Yeniden indeksleme gerekmez.

## 6. Destek için toplanacak bilgiler

`GET /version` çıktısı, `retrieval_generation status` çıktısı, `docker compose ps` ve ilgili zaman aralığının logları. Bu çıktılarda parola, belirteç ya da belge içeriği yoktur. `.env` dosyasını destek talebine eklemeyin.

## 7. Müşteriye söylenecek sınırlamalar

- Yanıtlar belgelerden üretilir, ama model yanlış satırı ya da belgeyi seçebilir; önemli kararlardan önce kaynak kartı kontrol edilmelidir.
- Eski ve güncel politika belgeleri birlikte yüklenirse sistem hangisinin geçerli olduğunu bilemez; eski belgeler kaldırılmalı ya da ayrı bir Knowledge Base'te tutulmalıdır.
- PDF ya da birleşik hücreli tablolar ve hesaplama gerektiren sorular desteklenmez.
- Ses tanıma gürültülü ortamda zayıflar; "Göndermeden önce soruyu göster" açık kalmalıdır.
- 16 GB makinede ilk yanıt birkaç saniye sürer; yanıt uzunsa okunması da sürer.
