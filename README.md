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
- **Organization / Workspace üyelik rolü** (`Membership.role`): Tenant kaynaklarını belirler. `admin`, `manager` ve `user` rolleri yalnızca yetkili Organization, Workspace ve Knowledge Base içindeki belge/RAG işlemlerini yönetir.

Bu nedenle bir kullanıcı platform rolü `user` iken kendi workspace’inde üyelik rolü `admin` olabilir. Bu beklenen davranıştır; workspace yöneticiliği platform yöneticiliği vermez.

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
| Belge işleme | `pypdf`, Markdown, TXT | Dosyadan metin çıkarma |
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

Belge yaşam döngüsü için `POST /documents/{id}/reindex`, `POST /documents/{id}/replace`, `GET /documents/{id}/versions` ve `DELETE /documents/{id}` endpoint’leri bulunur. Replace işleminde yeni sürüm indekslenene kadar eski sürüm aktif kalır; başarılı sürüm aktivasyonundan sonra eski Qdrant noktaları temizlenir. Index worker olayları yalnızca yetkili workspace kanalı üzerinden `ws://localhost:8000/ws/indexing?workspace_id=<id>&token=<access-token>` adresinden `queued`, `extracting`, `chunking`, `embedding`, `vector_indexing`, `ready` ve `failed` durumlarıyla yayınlar.

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

Geliştirme varsayılanında `ALLOW_REGISTRATION=true` ile kullanıcılar `POST /auth/register` üzerinden kaydolabilir. Yeni kullanıcıların **platform rolü `user`** olur; kendi oluşturdukları Organization/Workspace için Membership rolü `admin` kalır.

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

Model çekme işlemi `ws://localhost:8000/ws/models/pull?token=<access-token>` WebSocket’iyle yapılır. Admin istemci bağlantıdan sonra `{"model":"llama3.2:3b"}` gönderir; Ollama’nın sağladığı değerler varsa `model_pull_progress` olayları `status`, `completed` ve `total` alanlarıyla iletilir. İstemci sahte ilerleme yüzdesi üretmez. Silme işlemi arayüzde açık onay gerektirir.

## API kullanımı

```bash
curl -X POST http://localhost:8000/auth/register -H 'Content-Type: application/json' -d '{"email":"user@example.com","password":"correct-horse-battery"}'
export TOKEN="<access-token>"
curl http://localhost:8000/auth/me -H "Authorization: Bearer $TOKEN"
curl -X POST http://localhost:8000/auth/refresh -H 'Content-Type: application/json' -d '{"refresh_token":"<refresh-token>"}'
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

WebSocket için `ws://localhost:8000/ws/chat?token=<access-token>` adresine bağlanıp metin gönderin. Sunucu token başına `type: "token"`, tamamlanınca `type: "complete"` olayı gönderir. Gerçek RAG akışında `ws://localhost:8000/ws/rag?token=<access-token>` bağlantısına `{"question":"...","knowledge_base_ids":[1]}` gönderilir; sunucu sırasıyla `sources`, `token`, `complete` veya `error` olaylarını döndürür.

Model API’leri `GET /models/providers`, `GET /models`, `GET /models/{provider}/{model}` ve `GET /models/status` endpoint’lerini sunar. `DELETE /models/{provider}/{model}` yalnızca admin içindir; model çekme uzun sürebildiğinden admin erişimli WebSocket akışıyla yapılır. Embedding durumunda yalnızca yapılandırılmış kimlik/yerel ad, güvenli cache varlığı ve indirme izni döner; keyfi host dizinleri listelenmez.

## Güvenlik ve veri gizliliği

- Parolalar bcrypt ile hash’lenir; düz metin parola saklanmaz.
- Access ve refresh JWT’leri süreli üretilir; rollerle yetkilendirme desteklenir.
- Dosya boyutu ve uzantısı doğrulanır; yüklenen dosyalar çalıştırılmaz.
- JWT secret, bağlantı bilgileri ve parolalar ortam değişkenlerinden okunur.
- Token, parola, stack trace ve hassas belge içeriği loglanmaz veya istemciye döndürülmez.
- Embedding modeli çalışma zamanında varsayılan olarak cache-only yüklenir. Model bulunamazsa API giriş ve sistem ekranları çalışmaya devam eder; yalnızca indexing/RAG işlemleri açık bir provisioning hatasıyla durur.
- Model Manager yalnızca Ollama’nın yerel API’sine erişir; Docker içindeki varsayılan adres `host.docker.internal:11434` olarak yapılandırılabilir. Ollama HTTP istemcileri proxy ortam değişkenlerini kullanmaz (`trust_env=False`).

## Test ve LoRA eğitimi

`pip install -r requirements-dev.txt` sonrasında `python -m pytest -v` ile testleri çalıştırın. LoRA eğitimi için önce `pip install -r requirements-training.txt`, sonra `python training/train_lora.py` kullanın. LoRA, Ollama Modelfile ayarı değildir: prompt/system ayarı çalışma anındaki talimatı değiştirir, RAG bilgiyi sorgu anında sağlar, LoRA adapter ağırlıkları öğrenir, tam fine-tuning ise tüm model ağırlıklarını günceller. Ayrıntılar [`training/README.md`](training/README.md) dosyasındadır.

## Bilinen sınırlamalar

Mevcut sürüm belge metnini PostgreSQL’e kaydeder ve yerel filesystem depolaması kullanır. Gerçek canlı RAG uçtan uca kabul testi, makinede bir embedding modeli hazırlanmasını gerektirir ve [takip maddesi #4](https://github.com/WeAreTheArtMakers/modAI-stack/issues/4) altında beklemektedir. Üretim dağıtımında merkezi log/metrik, secret yönetimi, TLS, nesne depolama, yedekleme, dağıtık rate limiting ve yük testleri ayrıca planlanmalıdır. Alembic migration akışı ve fresh PostgreSQL doğrulaması CI’da çalıştırılır.

Üretim güvenlik sertleştirmesi için sonraki adımlar; refresh token’ın HttpOnly cookie’ye taşınması, access token süresinin kısaltılması ve WebSocket kimlik doğrulamasında uzun ömürlü query-string token yerine daha güvenli bir el sıkışma yönteminin kullanılmasıdır.

## Lisans

Bu proje WATAM lisansı ile sunulmaktadır.

<a href="https://wearetheartmakers.com" target="_blank" rel="noopener noreferrer">We Are The Art Makers</a>
