# modAI-stack

<p align="center"><img src="assets/modai-stack-logo.png" alt="modAI-stack logosu" width="760"></p>

> Yerel LLM, gerçek zamanlı sohbet, belge tabanlı RAG ve vektör aramayı birleştiren modüler yapay zekâ platformu.

[GitHub deposu](https://github.com/WeAreTheArtMakers/modAI-stack)

## Proje hakkında

modAI-stack; Ollama üzerinde yerel model çalıştırmayı, belge yüklemeyi, asenkron indekslemeyi, semantik aramayı ve yanıtları WebSocket ile gerçek zamanlı aktarmayı sağlar. FastAPI ve `asyncio` tabanlıdır. PostgreSQL kalıcı verileri, Redis indeks iş kuyruğu ve ilerleme olaylarını, Qdrant ise vektör aramayı destekler. Model sağlayıcı arayüzü sayesinde Ollama yerine başka bir sağlayıcı eklenebilir.

Kullanıcı kaydı sırasında başlangıç Organization, Workspace ve Knowledge Base oluşturulur. Knowledge Base erişimi Membership kayıtlarıyla kontrol edilir; kullanıcılar `admin`, `manager` veya `user` rolleriyle sınırlandırılır. Belge ve Qdrant erişimi bu kapsam bilgileriyle ilişkilendirilir.

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
pip install -r requirements.txt
cp .env.example .env
ollama pull modAIJet:latest
uvicorn app.main:app --reload
```

Docker için `cp .env.example .env` ve `docker compose up --build` komutlarını çalıştırın. API `http://localhost:8000`, Qdrant `http://localhost:6333`, host PostgreSQL bağlantısı `localhost:55432` adresindedir. Docker içindeki API, Mac üzerinde Ollama’ya `host.docker.internal:11434` adresinden bağlanır.

## Web Console v1

İlk ürün arayüzü `frontend/` altında React, TypeScript, Vite, React Router, TanStack Query, Tailwind CSS ve Lucide Icons ile geliştirilmiştir. Geliştirme sırasında:

```bash
cd frontend
npm install
npm run dev
```

Vite, `/api` isteklerini FastAPI’ye ve `/ws` bağlantılarını backend WebSocket endpoint’lerine proxy’ler. Console; giriş, workspace seçimi, Knowledge Base yönetimi, sürükle-bırak batch belge yükleme, workspace kapsamlı indeks durumu, kaynaklı RAG chat ve temel sistem durumu sayfalarını içerir. Üretim benzeri Docker kurulumu için `docker compose up --build` sonrasında arayüz `http://localhost:5173` adresinden açılır.

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
```

`GET /auth/me` güvenli kullanıcı, kuruluş ve workspace üyelik özetini; `GET /workspaces` kullanıcının yetkili workspace kayıtlarını; `GET /knowledge-bases` ise yetkili Knowledge Base kayıtlarını döndürür. Yeni bir Knowledge Base oluşturmak için `POST /knowledge-bases?workspace_id=<id>` kullanılabilir. `GET /documents` sayfalı bir `items/total/limit/offset` yanıtı verir; belge listesinde belge içeriği dönmez. Belge yüklerken multipart form alanı olarak `knowledge_base_id` gönderilebilir. RAG sorgusunda `knowledge_base_ids` listesiyle seçili bilgi tabanları belirtilir.

WebSocket için `ws://localhost:8000/ws/chat?token=<access-token>` adresine bağlanıp metin gönderin. Sunucu token başına `type: "token"`, tamamlanınca `type: "complete"` olayı gönderir. Gerçek RAG akışında `ws://localhost:8000/ws/rag?token=<access-token>` bağlantısına `{"question":"...","knowledge_base_ids":[1]}` gönderilir; sunucu sırasıyla `sources`, `token`, `complete` veya `error` olaylarını döndürür.

## Güvenlik ve veri gizliliği

- Parolalar bcrypt ile hash’lenir; düz metin parola saklanmaz.
- Access ve refresh JWT’leri süreli üretilir; rollerle yetkilendirme desteklenir.
- Dosya boyutu ve uzantısı doğrulanır; yüklenen dosyalar çalıştırılmaz.
- JWT secret, bağlantı bilgileri ve parolalar ortam değişkenlerinden okunur.
- Token, parola, stack trace ve hassas belge içeriği loglanmaz veya istemciye döndürülmez.

## Test ve LoRA eğitimi

`python -m pytest -v` ile testleri, `python training/train_lora.py` ile PEFT/LoRA adapter eğitimini çalıştırın. LoRA, Ollama Modelfile ayarı değildir: prompt/system ayarı çalışma anındaki talimatı değiştirir, RAG bilgiyi sorgu anında sağlar, LoRA adapter ağırlıkları öğrenir, tam fine-tuning ise tüm model ağırlıklarını günceller. Ayrıntılar [`training/README.md`](training/README.md) dosyasındadır.

## Bilinen sınırlamalar

Mevcut sürüm belge metnini PostgreSQL’e kaydeder ve yerel filesystem depolaması kullanır. Üretim dağıtımında merkezi log/metrik, secret yönetimi, TLS, nesne depolama, yedekleme, dağıtık rate limiting ve yük testleri ayrıca planlanmalıdır. Alembic migration akışı ve fresh PostgreSQL doğrulaması CI’da çalıştırılır.

Üretim güvenlik sertleştirmesi için sonraki adımlar; refresh token’ın HttpOnly cookie’ye taşınması, access token süresinin kısaltılması ve WebSocket kimlik doğrulamasında uzun ömürlü query-string token yerine daha güvenli bir el sıkışma yönteminin kullanılmasıdır.

## Lisans

Bu proje WATAM lisansı ile sunulmaktadır.

<a href="https://wearetheartmakers.com" target="_blank" rel="noopener noreferrer">We Are The Art Makers</a>
