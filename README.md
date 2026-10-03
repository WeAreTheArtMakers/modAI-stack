# modAI-stack

<p align="center"><img src="assets/modai-stack-logo.png" alt="modAI-stack logosu" width="760"></p>

> Yerel LLM, gerçek zamanlı sohbet, belge tabanlı RAG ve vektör aramayı birleştiren modüler yapay zekâ platformu.

[GitHub deposu](https://github.com/WeAreTheArtMakers/modAI-stack)

## Proje hakkında

modAI-stack; Ollama üzerinde yerel model çalıştırmayı, belge yüklemeyi, asenkron indekslemeyi, semantik aramayı ve yanıtları WebSocket ile gerçek zamanlı aktarmayı sağlar. FastAPI ve `asyncio` tabanlıdır. PostgreSQL kalıcı verileri, Redis indeks iş kuyruğu ve ilerleme olaylarını, Qdrant ise vektör aramayı destekler. Model sağlayıcı arayüzü sayesinde Ollama yerine başka bir sağlayıcı eklenebilir.

Kullanıcı kaydı sırasında başlangıç Organization, Workspace ve Knowledge Base oluşturulur. Knowledge Base erişimi Membership kayıtlarıyla kontrol edilir; `admin`, `manager` ve `user` üyelik rolleri belge, Knowledge Base, RAG ve workspace işlemlerini tenant kapsamı içinde sınırlar. Belge ve Qdrant erişimi bu kapsam bilgileriyle ilişkilendirilir.

### Platform rolü ve tenant üyeliği

Sistemde birbirinden bağımsız iki yetki alanı bulunur:

- **Platform rolü** (`User.role`): Makine genelindeki işlemleri belirler. Yalnızca platform `admin`, Ollama model çekme/silme ve gelecekteki platform yönetimi gibi host düzeyindeki işlemleri yapabilir.
- **Tenant üyelik rolü** (`Membership.role`): `workspace_id=NULL` olan kayıt Organization-genelidir; belirli bir `workspace_id` ise yalnızca o Workspace için geçerlidir. `admin`, `manager` ve `user` rolleri yalnızca yetkili Organization, Workspace ve Knowledge Base içindeki belge/RAG işlemlerini yönetir.

Bu nedenle bir kullanıcı platform rolü `user` iken kendi workspace’inde üyelik rolü `admin` olabilir. Bu beklenen davranıştır; workspace yöneticiliği platform yöneticiliği vermez. Ayrıca workspace-scoped `admin`, Organization yöneticisi değildir: workspace oluşturma, Organization-geneli üyelik yönetimi ve davet yönetimi yalnızca platform `admin` veya `workspace_id=NULL` olan Organization-geneli `admin` üyeliğiyle yapılabilir. Organization yöneticiliği de platform yöneticiliği vermez.

## v0.3 — Enterprise Local AI Platform

v0.3, yerel-öncelikli kurumsal RAG platformu kilometre taşıdır. Production hardening ve Model Manager v0.3 bu sürümde tamamlandı. Mevcut backend doğrulama paketi **85 test** içerir ve son doğrulamada geçmiştir.

- Çok tenantlı Organization → Workspace → Knowledge Base hiyerarşisi, Membership tabanlı yetkilendirme ve tenant izolasyonu kullanılmaktadır.
- Gerçek canlı RAG kabulü tamamlandı: TXT, PDF ve DOCX yükleme/çıkarma, Qdrant retrieval, kaynaklı HTTP ve WebSocket yanıtları doğrulandı.
- Reindex, replace/sürüm aktivasyonu ve belge silme/Qdrant vektör temizliği gerçek servislerle doğrulandı; [Issue #4](https://github.com/WeAreTheArtMakers/modAI-stack/issues/4) kapatıldı.
- Embedding modeli bağlı kurulumda önceden hazırlanabilir; çalışma zamanında varsayılan olarak cache-only/offline davranışı korunur.
- WebSocket bağlantıları normal access JWT yerine kısa ömürlü, tek kullanımlık ticket ile kurulur.

Bu durum bir güvenlik veya uyumluluk sertifikası iddiası değildir. Dağıtımın TLS, yedekleme, erişim sınırları ve secret yönetimi gereksinimleri işletmecinin sorumluluğundadır.

## v0.4 — Enterprise Administration

Enterprise Administration; platform kullanıcı dizini, Organization ve Workspace yönetimi, scope’lu Membership yönetimi, Audit Log ve yönetim arayüzünü ekler. Davet token’ları yüksek entropili üretilir, yalnızca SHA-256 hash’i saklanır, tek kullanım ve son kullanma süresiyle korunur. Kabul sırasında hedef e-posta karşılaştırması normalize edilir ve davet satırı transaction içinde kilitlenir.

- Son platform yöneticisi düşürülemez; her Organization’da en az bir Organization-geneli `admin` üyeliği korunur.
- PostgreSQL’de `workspace_id IS NULL` Organization üyelikleri için kısmi unique index bulunur. Migration, önceden oluşmuş çift Organization-geneli üyelikleri silmez; operatörden önce bunları düzeltmesini ister.
- Yönetim arayüzü Organization-geneli işlemleri yalnızca gerçek Organization-geneli admin üyelerine veya platform admin’lere gösterir. Backend bu sınırı ayrıca zorunlu olarak uygular.
- Yerleşik SMTP dağıtımı yoktur; davet token’ı yalnızca oluşturulurken bir kez gösterilir ve kurumun seçtiği güvenli kanal üzerinden iletilir.

## v0.5 geliştirme — RAG Evaluation & Quality

Bu geliştirme dalı, mevcut RAG davranışını değiştirmeden retrieval ve cevap desteğini ölçülebilir, tekrar çalıştırılabilir hale getirir. Sürümlü, insan gözden geçirmeli evaluation dataset’leri; deterministik kaynak/fact metrikleri; JSON sonuç şeması; eşik kontrollü CLI ve baseline/candidate karşılaştırması bulunur. Bulut LLM judge kullanılmaz. Değerlendirme çalıştıran kullanıcı, RAG endpoint’iyle aynı Knowledge Base yetkilendirmesine tabidir; sonuç dosyaları belge gövdesi, prompt veya üretilmiş tam yanıt içermez.

Detaylı şema, metrik sınırları, embedding modeli değiştiğinde reindex uyarısı ve komut örnekleri için [evaluation/README.md](evaluation/README.md) dosyasına bakın.

## Kullanılan teknolojiler

| Katman | Teknolojiler | Kullanım amacı |
| --- | --- | --- |
| Dil ve API | Python 3.11+, FastAPI, Pydantic, Uvicorn | Asenkron REST API ve doğrulama |
| Asenkron mimari | `asyncio`, bounded queue, worker, timeout, cancellation | Eşzamanlılık ve backpressure |
| LLM | Ollama, `LLMProvider` | Yerel model ve sağlayıcı soyutlaması |
| RAG | Sentence Transformers, metin parçalama | Belge kaynaklı yanıt üretimi |
| Vektör arama | Qdrant, cosine similarity, metadata filtreleri | Embedding saklama ve arama |
| Kalıcı veri | PostgreSQL, SQLAlchemy Async ORM, asyncpg | Kullanıcı, belge, oturum ve mesajlar |
| Geçici veri ve işler | Redis | Asenkron indeks kuyruğu, retry ve workspace kapsamlı ilerleme olayları |
| Gerçek zamanlı iletişim | WebSocket | Token akışı ve canlı sohbet |
| Güvenlik | JWT, access/refresh token, bcrypt, RBAC | Kimlik doğrulama ve yetkilendirme |
| Belge işleme | `pypdf`, `python-docx`, Markdown, TXT | Dosyadan metin çıkarma |
| Model uyarlama | Transformers, Datasets, PEFT / LoRA | Adapter eğitimi |
| Altyapı | Docker, Docker Compose, kalıcı volume | Yerel servis kurulumu |
| Test | pytest, pytest-asyncio, httpx | Birim ve entegrasyon testleri |

## Mimari

```text
İstemci -> FastAPI REST/WebSocket -> JWT/RBAC -> LLMProvider -> Ollama
                                      |              |
                                      |              └-> RAG -> Embedding -> Qdrant
                                      ├-> SQLAlchemy -> PostgreSQL
                                      └-> Redis -> indeks worker / WebSocket ilerleme olayları
```

Ollama çağrıları yalnızca `app/services/llm/` katmanından yapılır. RAG context’i güvenilmeyen veri olarak sistem talimatlarından ayrılır.

### Gerçek RAG akışı

Belge yükleme akışı şöyledir: `upload → extract → chunk → embed → Qdrant upsert`. Embedding modeli lazy olarak yüklenir, tekrar kullanılır ve senkron model çağrısı `asyncio.to_thread()` ile event loop dışına taşınır. Her Qdrant payload’ında kullanıcı, belge, dosya adı, parça numarası ve metin bulunur.

Sorgu akışı şöyledir: `question → embed → yetkili Organization/Workspace/Knowledge Base filtreli similarity search → top-k context → Ollama → answer + sources`. Qdrant filtreleri kullanıcı ve kurumsal kapsamla sınırlandırılır; RAG isteğinde seçilen tüm Knowledge Base kayıtları önce Membership üzerinden yetkilendirilir. Belge silme işlemi de yetkilendirme kontrolünden sonra PostgreSQL kaydını ve Qdrant vektörlerini birlikte kaldırır.

## Asenkron indeksleme ve dosya depolama

Upload isteği artık embedding çalıştırmaz. API dosyayı güvenli, üretilmiş bir adla `DATA_DIR/uploads/` altına atomik olarak kaydeder; PostgreSQL’de belge sürümü ve `IndexJob` oluşturur; işi Redis kuyruğuna bırakır ve `queued` durumuyla döner. Ayrı worker süreci `queued → processing → ready` akışında extraction, chunking, embedding ve Qdrant upsert işlemlerini yürütür. Hatalar güvenli `failed` durumuna alınır ve sınırlı retry uygulanır.

Desteklenen dosya türleri PDF, TXT, Markdown ve DOCX’tir. Kullanıcı dosya adı yalnızca metadata olarak saklanır; filesystem yolu hiçbir zaman istemciden alınmaz. Docker Compose içinde `api`, `worker`, PostgreSQL, Redis ve Qdrant servisleri bulunur; kaynak dosyalar `modaidata` volume’unda kalıcıdır.

Belge yaşam döngüsü için `POST /documents/{id}/reindex`, `POST /documents/{id}/replace`, `GET /documents/{id}/versions` ve `DELETE /documents/{id}` endpoint’leri bulunur. Replace işleminde yeni sürüm indekslenene kadar eski sürüm aktif kalır; başarılı sürüm aktivasyonundan sonra eski Qdrant noktaları temizlenir.

İndeks ilerleme WebSocket’i için istemci önce access JWT ile yetkili `POST /auth/ws-ticket` çağrısı yapar ve `{"scope":"indexing","workspace_id":<id>}` gönderir. Backend, ticket üretmeden önce workspace erişimini doğrular. Dönen kısa ömürlü, tek kullanımlık ticket yalnızca `ws://localhost:8000/ws/indexing?ticket=<ticket>` adresinde kullanılır. Bu kanal `queued`, `extracting`, `chunking`, `embedding`, `vector_indexing`, `ready` ve `failed` olaylarını yayınlar; access JWT ve workspace kimliği WebSocket URL’sine konmaz.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-runtime.txt
cp .env.example .env
ollama pull modAIJet:latest
uvicorn app.main:app --reload
```

Bağımlılıklar kullanım amacına göre ayrılmıştır:

```bash
# API, worker ve RAG runtime
pip install -r requirements-runtime.txt

# Runtime + backend test araçları
pip install -r requirements-dev.txt

# Runtime + LoRA/PEFT eğitim araçları
pip install -r requirements-training.txt
```

`requirements.txt`, eski tam kurulum alışkanlığı için uyumluluk giriş noktasıdır; runtime, geliştirme ve eğitim bağımlılıklarını birlikte kurar. Production API/worker imajı yalnızca `requirements-runtime.txt` kullanır. SentenceTransformers için gereken `torch` ve `transformers` runtime'da kalır; `datasets`, `peft` ve `accelerate` ise LoRA eğitim ortamına bilinçli olarak ayrılmıştır.

Docker için `cp .env.example .env` ve `docker compose up --build` komutlarını çalıştırın. API `http://localhost:8000`, Qdrant `http://localhost:6333`, host PostgreSQL bağlantısı `localhost:55432` adresindedir. Docker içindeki API, Mac üzerinde Ollama’ya `host.docker.internal:11434` adresinden bağlanır.

### Kayıt ve ilk platform yöneticisi

Geliştirme varsayılanında `ALLOW_REGISTRATION=true` ile kullanıcılar `POST /auth/register` üzerinden kaydolabilir. Yeni kullanıcıların **platform rolü `user`** olur; kendi oluşturdukları Organization için `workspace_id=NULL` olan Organization-geneli Membership rolü `admin` atanır. Bu üyelik mevcut Workspace’e erişim verir, ancak platform rolünü yükseltmez.

Kurumsal üretimde `ALLOW_REGISTRATION=false` ayarlanmalıdır. Bu durumda kayıt endpoint’i `403` döndürür, mevcut kullanıcıların girişi çalışmaya devam eder. İlk platform yöneticisini public bir HTTP endpoint’i kullanmadan, uygulamanın erişebildiği güvenli terminalde oluşturun veya yükseltin:

```bash
# Var olan kullanıcıyı platform admin yapar.
python -m app.tools.create_platform_admin --email admin@example.com

# Kullanıcı yoksa yalnızca açık --create tercihiyle oluşturur.
# Parola komut satırına yazılmaz; güvenli etkileşimli giriş istenir.
python -m app.tools.create_platform_admin --create --email admin@example.com

# Mevcut platform admin e-posta kayıtlarını parolasız listeler.
python -m app.tools.list_platform_admins
```

Mevcut kurulumlarda migration gerekmez: `users.role` kolonu zaten şemadadır. Bu güncelleme mevcut `admin` kayıtlarını otomatik olarak düşürmez. Yükseltme sonrasında `python -m app.tools.list_platform_admins` ile platform yöneticilerini inceleyin; gerekli olmayanları güvenli işletim prosedürünüzle platform `user` rolüne alın. Rolü değişen kullanıcıların güncel JWT rolünü alabilmesi için yeniden giriş yapması veya refresh token akışını kullanması gerekir.

### Embedding modeli: bağlı ve air-gapped kurulum

Repository model ağırlıklarını içermez. Embedding modeli, Ollama modelinden ayrı bir gereksinimdir: Ollama LLM yanıtı üretir; SentenceTransformer ise belge ve soru embedding'lerini üretir.

**Bağlı / online kurulumda**, bağımlılıkları kurduktan sonra modelin bir kez indirilmesi ve doğrulanması için aşağıdaki komutu çalıştırın:

```bash
python -m app.tools.prefetch_embedding_model
```

Bu komut `EMBEDDING_MODEL` değerini kullanır, küçük bir test embedding'i üretir ve cache'e yazar. Normal uygulama çalışma zamanında varsayılan `EMBEDDING_ALLOW_DOWNLOAD=false` ayarıyla cache-only davranır; cache'te model yoksa indeksleme ve RAG, güvenli ve açık bir model-provisioning hatası döndürür. İndirmeye çalışma zamanında bilinçli olarak izin vermek gerekirse `EMBEDDING_ALLOW_DOWNLOAD=true` ayarlanabilir.

**Offline / air-gapped kurulumda**, uyumlu SentenceTransformer model dizinini host üzerinde `./models/<model>` altına kopyalayın ve Docker için aşağıdaki ayarı kullanın:

```dotenv
MODEL_DIR=./models
EMBEDDING_MODEL=/models/<model>
```

Compose, `MODEL_DIR` dizinini hem API hem worker içinde `/models` olarak mount eder. `/models/cache` SentenceTransformer ve Hugging Face cache'i için kalıcıdır; worker container'ı yeniden oluşturulduğunda model yeniden indirilmez. Yerel model yolu eksikse sistem başka bir modele sessizce geçmez ve ağdan alternatif indirme denemez. `models/` Git tarafından yok sayılır; model ağırlıklarını depoya eklemeyin.

## Web Console v1

İlk ürün arayüzü `frontend/` altında React, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS ve Lucide Icons ile geliştirilmiştir. Console; giriş, workspace seçimi, Knowledge Base yönetimi, sürükle-bırak batch belge yükleme, workspace kapsamlı indeks durumu, kaynaklı RAG chat, Model Manager ve temel sistem durumu sayfalarını içerir. Geliştirme sırasında:

```bash
cd frontend
npm install
npm run dev
```

Vite, `/api` isteklerini FastAPI’ye ve `/ws` bağlantılarını backend WebSocket endpoint’lerine proxy’ler. Üretim benzeri Docker kurulumu için `docker compose up --build` sonrasında arayüz `http://localhost:5173` adresinden açılır.

Frontend doğrulama komutları:

```bash
cd frontend
npm run typecheck
npm run build
npm run lint
npm run test
```

### RAG kalite değerlendirmesi

Önce kendi tenant’ınızdaki insan tarafından doğrulanmış soru, kaynak belge ve olgu beklentileriyle sürümlü bir dataset oluşturun. Local çalıştırma access JWT’yi yalnızca ortam değişkeninden alır ve normal Knowledge Base yetkilendirmesini uygular:

```bash
export MODAI_EVALUATION_ACCESS_TOKEN='<access-jwt>'
python -m app.tools.evaluate_rag --dataset evaluation/sample_dataset.json --output baseline.json
python -m app.tools.compare_rag_evaluations baseline.json candidate.json
```

Varsayılan değerlendirme yalnızca retrieval/source/fact metriklerini çalıştırır. Yerel Ollama ile üretilmiş yanıttaki deterministic destek sinyalini ölçmek için açıkça `--generate` ekleyin. CI ve model indirmeyen geliştirme denemeleri `--mode fixture --fixture retrieval-fixture.json` ile yapılabilir. Eşikler (`--min-hit-at-k`, `--min-source-accuracy`, `--min-fact-coverage`, `--max-median-total-ms`) yalnızca verildiğinde komutu başarısız yapar.

Gerçek JWT secret ve parolaları yalnızca `.env` içine yazın. `.env`, `.venv`, yerel veritabanı ve eğitim çıktıları Git’e alınmaz.

Şema değişiklikleri için uzun vadeli migration aracı Alembic’tir:

```bash
alembic upgrade head
```

Eski geliştirme veritabanlarında migration çalıştırmadan önce yedek alın. `create_all()` yalnızca geriye dönük geliştirme kolaylığı olarak tutulur; üretimde şema yönetimi Alembic ile yapılmalıdır.

## Model Manager v0.3

Model Manager, yerel AI çalışma zamanını yönetmek için ilk sağlayıcı katmanını sunar. İlk ve tek aktif sağlayıcı Ollama’dır; `app/services/models/` altındaki `ModelProvider` soyutlaması daha sonra vLLM, LM Studio / OpenAI-uyumlu sunucular, MLX veya llama.cpp-uyumlu uç noktalar eklenebilmesi için tasarlanmıştır. Bu sürüm bir model marketi değildir ve herhangi bir harici sağlayıcı kurmaz.

Console’daki **Modeller** ekranı Ollama bağlantı durumunu ve endpoint’ini, yapılandırılmış generation modelini, Ollama’nın bildirdiği yüklü modelleri ve embedding modelinin cache/yerel hazırlık durumunu gösterir. Generation ve embedding modelleri ayrı kavramlardır: Ollama yanıt üretir, SentenceTransformer belge ve soru embedding’lerini üretir.

Model listesi ve durum bilgisi giriş yapmış kullanıcılar tarafından okunabilir. Model çekme ve silme yalnızca **platform `admin`** rolüne açıktır; workspace/Organization `admin` üyeliği bu yetkiyi vermez ve backend yetkiyi zorunlu olarak doğrular. Model adı uzunluk, güvenli karakter kümesi ve path traversal kurallarıyla kontrol edilir; API shell komutu veya keyfi filesystem yolu kabul etmez. Aktif `OLLAMA_MODEL` silinemez ve aktif generation model seçimi bu sürümde yalnızca yapılandırmadan okunur; HTTP üzerinden `.env` değiştirilmez.

Model çekme işlemi, önce platform admin yetkisiyle `POST /auth/ws-ticket` üzerinden alınan kısa ömürlü ve tek kullanımlık `models_pull` ticket’ı ile `ws://localhost:8000/ws/models/pull?ticket=<tek-kullanimlik-ticket>` bağlantısına yapılır. Normal access JWT URL’ye konmaz. Admin istemci bağlantıdan sonra `{"model":"llama3.2:3b"}` gönderir; Ollama’nın sağladığı değerler varsa `model_pull_progress` olayları `status`, `completed` ve `total` alanlarıyla iletilir. İstemci sahte ilerleme yüzdesi üretmez. Silme işlemi arayüzde açık onay gerektirir.

## API kullanımı

```bash
curl -X POST http://localhost:8000/auth/register -H 'Content-Type: application/json' -d '{"email":"user@example.com","password":"correct-horse-battery"}'
export TOKEN="<access-token>"
curl http://localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
# Login/register yanıtındaki HttpOnly refresh cookie için cookie jar kullanın.
curl -c cookies.txt -X POST http://localhost:8000/auth/login -H 'Content-Type: application/json' -d '{"email":"user@example.com","password":"correct-horse-battery"}'
curl -b cookies.txt -c cookies.txt -X POST http://localhost:8000/auth/refresh
curl http://localhost:8000/workspaces -H "Authorization: Bearer $TOKEN"
curl http://localhost:8000/knowledge-bases -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8000/chat -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"prompt":"Embedding nedir?"}'
curl -X POST http://localhost:8000/documents/upload -H "Authorization: Bearer $TOKEN" -F knowledge_base_id=1 -F file=@notlar.pdf
curl 'http://localhost:8000/documents?knowledge_base_id=1&limit=50&offset=0' -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8000/rag/query -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"question":"Belgede hangi konular anlatılıyor?","knowledge_base_ids":[1]}'
curl http://localhost:8000/models/status -H "Authorization: Bearer $TOKEN"
curl 'http://localhost:8000/models?provider=ollama' -H "Authorization: Bearer $TOKEN"
```

`GET /auth/me` güvenli kullanıcı, kuruluş ve workspace üyelik özetini; `GET /workspaces` kullanıcının yetkili workspace kayıtlarını; `GET /knowledge-bases` ise yetkili Knowledge Base kayıtlarını döndürür. Yeni bir Knowledge Base oluşturmak için `POST /knowledge-bases?workspace_id=<id>` kullanılabilir. `GET /documents` sayfalı bir `items/total/limit/offset` yanıtı verir; belge listesinde belge içeriği dönmez. Belge yüklerken multipart form alanı olarak `knowledge_base_id` gönderilebilir. RAG sorgusunda `knowledge_base_ids` listesiyle seçili bilgi tabanları belirtilir.

WebSocket bağlantılarında access JWT URL’ye eklenmez. İstemci önce yetkili `POST /auth/ws-ticket` çağrısıyla `{"scope":"chat"}`, `{"scope":"rag"}` veya indeks ilerlemesi için `{"scope":"indexing","workspace_id":<id>}` gönderir. Dönen kısa ömürlü, tek kullanımlık ticket bağlantıda kullanılır: `ws://localhost:8000/ws/chat?ticket=<ticket>`, `ws://localhost:8000/ws/rag?ticket=<ticket>` veya `ws://localhost:8000/ws/indexing?ticket=<ticket>`. Chat bağlantısında metin gönderilir ve sunucu `token`/`complete` olaylarını döndürür. RAG bağlantısında `{"question":"...","knowledge_base_ids":[1]}` gönderilir; sunucu sırasıyla `sources`, `token`, `complete` veya `error` olaylarını döndürür. Ticket üretiminde RAG/chat için oturum, indexing için ayrıca workspace yetkisi doğrulanır.

Model API’leri `GET /models/providers`, `GET /models`, `GET /models/{provider}/{model}` ve `GET /models/status` endpoint’lerini sunar. `DELETE /models/{provider}/{model}` yalnızca admin içindir; model çekme uzun sürebildiğinden admin erişimli WebSocket akışıyla yapılır. Embedding durumunda yalnızca yapılandırılmış kimlik/yerel ad, güvenli cache varlığı ve indirme izni döner; keyfi host dizinleri listelenmez.

## Güvenlik ve veri gizliliği

- Parolalar bcrypt ile hash’lenir; düz metin parola saklanmaz.
- Access ve refresh JWT’leri süreli üretilir; rollerle yetkilendirme desteklenir.
- Dosya boyutu ve uzantısı doğrulanır; yüklenen dosyalar çalıştırılmaz.
- JWT secret, bağlantı bilgileri ve parolalar ortam değişkenlerinden okunur.
- Token, parola, stack trace ve hassas belge içeriği loglanmaz veya istemciye döndürülmez.
- Embedding modeli çalışma zamanında varsayılan olarak cache-only yüklenir. Model bulunamazsa API giriş ve sistem ekranları çalışmaya devam eder; yalnızca indexing/RAG işlemleri açık bir provisioning hatasıyla durur.
- Model Manager yalnızca Ollama’nın yerel API’sine erişir; Docker içindeki varsayılan adres `host.docker.internal:11434` olarak yapılandırılabilir. Ollama HTTP istemcileri proxy ortam değişkenlerini kullanmaz (`trust_env=False`).

## Production hardening ve işletim

### Oturumlar ve WebSocket kimlik doğrulaması

Access token kısa ömürlüdür ve frontend’in yaptığı yetkili API çağrıları için bellekte/yerel tarayıcı deposunda tutulur. Refresh token ise API yanıt gövdesine veya JavaScript’e hiç verilmez: `HttpOnly` cookie içinde döndürülür. Her refresh JWT benzersiz bir `jti` taşır; Redis sadece `jti → user_id` ve JWT ömrüne eşit TTL tutar. `/auth/refresh` eski `jti` kaydını atomik olarak tüketir, yeni `jti` ve cookie üretir. Bu nedenle başarılı biçimde döndürülmüş eski refresh token tekrar kullanılamaz. Cookie ayarları `REFRESH_COOKIE_NAME`, `REFRESH_COOKIE_SAMESITE` ve `REFRESH_COOKIE_SECURE` ile yönetilir. Üretimde HTTPS zorunlu olduğundan `REFRESH_COOKIE_SECURE=true` olmalıdır; bu değer kapalıysa production başlangıcı durur.

Cookie refresh akışı aynı-origin kullanım ve `SameSite` politikası için tasarlanmıştır. `/auth/refresh` ve `/auth/logout` cookie-mutating POST uçları `Origin` başlığı varsa yalnızca kendi origin’iyle veya `TRUSTED_FRONTEND_ORIGINS` içinde açıkça listelenen virgülle ayrılmış origin’lerle eşleştiğinde kabul edilir; diğer cross-origin istekler `403` alır. TLS termination kullanan reverse proxy, API’ye `X-Forwarded-Proto` değerini iletmelidir; sağlanan Nginx bunu yapar. Origin’siz istekler browser olmayan yerel CLI/otomasyon istemcileri için kabul edilir; bu durum wildcard CORS açmaz ve tarayıcı isteklerinde `SameSite` savunması devam eder. Ayrı frontend origin’i kullanmak istendiğinde CORS’u genişletmek yerine TLS terminasyonu altında aynı origin reverse-proxy düzeni tercih edilmelidir. Logout, geçerli cookie varsa ilgili `jti` Redis kaydını siler ve cookie’yi her durumda temizler; çağrı idempotenttir.

WebSocket bağlantılarında normal access JWT URL’ye konmaz. İstemci önce yetkili `POST /auth/ws-ticket` çağrısıyla `chat`, `rag`, `indexing` veya `models_pull` kapsamlı bir ticket alır. Ticket Redis’te tutulur, varsayılan 60 saniyede dolar ve ilk kullanımda silinir. Indexing ticket’ı workspace kapsamına, model pull ticket’ı platform admin rolüne bağlıdır.

### Limitler, denetim ve gözlemlenebilirlik

Redis tabanlı sayaçlar login, registration, refresh, WebSocket ticket üretimi, RAG başlangıcı ve model pull için uygulanır. Sayaç artışı ve yeni bucket TTL ataması tek Redis Lua işlemiyle atomiktir; yarım kalan `INCR` sonucu süresiz key bırakmaz. Limitler `RATE_LIMIT_AUTH_PER_MINUTE`, `RATE_LIMIT_RAG_PER_MINUTE` ve `RATE_LIMIT_MODEL_PULL_PER_HOUR` ile ayarlanır. Aşım güvenli bir `429` yanıtı üretir.

Audit trail Alembic ile oluşturulan `audit_events` tablosuna yazılır. Login, registration, platform-admin promotion, Knowledge Base oluşturma, belge upload/replace/reindex/delete, WebSocket ticket ve model pull/delete gibi güvenlik veya yönetim olayları yapılandırılmış şekilde saklanır. Parolalar, JWT’ler, refresh cookie’leri, belge içerikleri, prompt’lar ve model dosyaları metadata’ya alınmaz. Platform admin kullanıcıları olayları `GET /audit?limit=50&offset=0&action=<name>` ile okuyabilir; endpoint tenantlar arası erişime açılmaz.

Her HTTP isteği güvenli gelen `X-Request-ID` değerini korur veya yeni bir kimlik üretir; yanıt aynı başlığı taşır. Production’da JSON loglar request ID, bileşen, durum ve süre bilgisini içerir; hassas istek gövdeleri loglanmaz. `GET /metrics` Prometheus metin formatında düşük-cardinality HTTP ve güvenli olay sayaçlarını sunar ve platform admin ile korunur. Metrik endpoint’ini ayrıca reverse proxy/ağ seviyesinde yalnızca izleme sistemine açın.

`GET /health` yalnızca API liveness bilgisidir. `GET /ready`, PostgreSQL, Redis ve Qdrant için zararsız kontrolleri yapar; Ollama ve embedding hazırlığı ayrı alanlarda bildirilir. Ollama erişilemez olsa da yönetim ekranı ve API process’i ayakta kalır.

### Production yapılandırması ve TLS

Üretimde en az aşağıdaki değerleri açıkça ayarlayın: benzersiz `JWT_SECRET`, güçlü `POSTGRES_PASSWORD`, `ALLOW_REGISTRATION=false`, `REFRESH_COOKIE_SECURE=true`, uygun `REFRESH_COOKIE_SAMESITE`, rate-limit değerleri, `MODEL_DIR` ve embedding cache yolu. Bilinen JWT placeholder değeri veya güvenli olmayan refresh cookie ile `APP_ENV=production` başlangıcı bilerek başarısız olur.

Önerilen dağıtım düzeni şudur: **TLS termination (Nginx/Caddy/Traefik) → frontend reverse proxy → API/worker ve iç servisler**. Frontend Nginx yapılandırması CSP, nosniff, referrer, permissions ve frame koruma başlıklarını uygular. CSP, React’in yalnızca dinamik progress style değeri için `style-src 'unsafe-inline'` içerir; script kaynağı yalnızca same-origin’dir. Local HTTP geliştirme akışı korunur, ancak Secure cookie gerçek üretimde yalnızca HTTPS altında çalışır.

### Yedekleme ve geri yükleme

`scripts/backup_local.sh <backup-directory>` çalışan Compose servislerinden PostgreSQL dump’ı, Qdrant storage ve `modaidata` kaynak dosyalarını alır. Komut gerçek credential istemez; çalışan container ortamındaki PostgreSQL ayarlarını kullanır. Model/cache dizini ve `.env` dosyası ayrı, erişimi sınırlı bir yere kopyalanmalıdır; bunları kaynak depoya eklemeyin.

Geri yükleme sırası: önce aynı sürümde PostgreSQL’i geri yükleyin, sonra Qdrant storage ve `modaidata`yı **aynı zaman noktasına ait** yedeklerden geri koyun, ardından model/cache’i ve güvenli ortam değişkenlerini yerleştirin. Veritabanı, aktif vector index ve stored source dosyaları farklı yedek anlarından karıştırılırsa replace/reindex yaşam döngüsü tutarsızlaşabilir. Geri yükleme ardından `alembic upgrade head`, readiness kontrolleri ve Issue #4’teki gerçek RAG kabul akışı çalıştırılmalıdır.

## Test ve LoRA eğitimi

`pip install -r requirements-dev.txt` sonrasında `python -m pytest -v` ile testleri çalıştırın; mevcut backend paketi 85 test içerir. LoRA eğitimi için önce `pip install -r requirements-training.txt`, sonra `python training/train_lora.py` kullanın. LoRA, Ollama Modelfile ayarı değildir: prompt/system ayarı çalışma anındaki talimatı değiştirir, RAG bilgiyi sorgu anında sağlar, LoRA adapter ağırlıkları öğrenir, tam fine-tuning ise tüm model ağırlıklarını günceller. Ayrıntılar [`training/README.md`](training/README.md) dosyasındadır.

## Bilinen sınırlamalar

Mevcut sürüm belge metnini PostgreSQL’e kaydeder ve yerel filesystem depolaması kullanır. Gerçek canlı RAG kabulü tamamlandı; TXT/PDF/DOCX retrieval ile reindex, replace ve delete/vectors cleanup yaşam döngüsü doğrulandı. Üretim dağıtımında merkezi secret vault entegrasyonu, TLS işletimi, nesne depolama, yedekleme/restore tatbikatı ve yük testleri ayrıca planlanmalıdır. Alembic migration akışı ve fresh PostgreSQL doğrulaması CI’da çalıştırılır.

## Lisans

Bu proje WATAM lisansı ile sunulmaktadır.

<a href="https://wearetheartmakers.com" target="_blank" rel="noopener noreferrer">We Are The Art Makers</a>
