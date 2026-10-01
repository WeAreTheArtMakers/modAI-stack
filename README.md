# modAI-stack

<p align="center"><img src="assets/modai-stack-logo.png" alt="modAI-stack logosu" width="760"></p>

> Yerel LLM, gerçek zamanlı sohbet, belge tabanlı RAG ve vektör aramayı birleştiren modüler yapay zekâ platformu.

[GitHub deposu](https://github.com/WeAreTheArtMakers/modAI-stack)

## Proje hakkında

modAI-stack; Ollama üzerinde yerel model çalıştırmayı, belge yüklemeyi, semantik arama yapmayı ve yanıtları WebSocket ile gerçek zamanlı aktarmayı sağlar. FastAPI ve `asyncio` tabanlıdır. PostgreSQL kalıcı verileri, Qdrant vektör aramayı destekler. Redis Compose içinde hazır tutulur ancak mevcut uygulama akışında henüz kullanılmamaktadır. Model sağlayıcı arayüzü sayesinde Ollama yerine vLLM eklenebilir.

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
| Geçici veri | Redis | Compose içinde hazır; rate limit ve iş durumu entegrasyonu sonraki adımdır |
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
                                      └-> SQLAlchemy -> PostgreSQL
                                          Redis: Compose altyapısında hazır, henüz uygulama akışına bağlı değil
```

Ollama çağrıları yalnızca `app/services/llm/` katmanından yapılır. RAG context’i güvenilmeyen veri olarak sistem talimatlarından ayrılır.

### Gerçek RAG akışı

Belge yükleme akışı şöyledir: `upload → extract → chunk → embed → Qdrant upsert`. Embedding modeli lazy olarak yüklenir, tekrar kullanılır ve senkron model çağrısı `asyncio.to_thread()` ile event loop dışına taşınır. Her Qdrant payload’ında kullanıcı, belge, dosya adı, parça numarası ve metin bulunur.

Sorgu akışı şöyledir: `question → embed → user_id filtreli similarity search → top-k context → Ollama → answer + sources`. Kullanıcı filtreleri sayesinde bir kullanıcı başka bir kullanıcının belge parçalarını arayamaz. Belge silme işlemi de sahiplik kontrolünden sonra PostgreSQL kaydını ve Qdrant vektörlerini birlikte kaldırır.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
ollama pull modAIJet:latest
uvicorn app.main:app --reload
```

Docker için `cp .env.example .env` ve `docker compose up --build` komutlarını çalıştırın. API `http://localhost:8000`, Qdrant `http://localhost:6333`, host PostgreSQL bağlantısı `localhost:55432` adresindedir. Docker içindeki API, Mac üzerinde Ollama’ya `host.docker.internal:11434` adresinden bağlanır.

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
curl -X POST http://localhost:8000/chat -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"prompt":"Embedding nedir?"}'
curl -X POST http://localhost:8000/documents/upload -H "Authorization: Bearer $TOKEN" -F file=@notlar.pdf
curl -X POST http://localhost:8000/rag/query -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"question":"Belgede hangi konular anlatılıyor?"}'
```

Knowledge Base listelemek için `GET /knowledge-bases`, yeni bir Knowledge Base oluşturmak için `POST /knowledge-bases?workspace_id=<id>` kullanılabilir. Belge yüklerken multipart form alanı olarak `knowledge_base_id` gönderilebilir. RAG sorgusunda `knowledge_base_ids` listesiyle seçili bilgi tabanları belirtilir.

WebSocket için `ws://localhost:8000/ws/chat?token=<access-token>` adresine bağlanıp metin gönderin. Sunucu token başına `type: "token"`, tamamlanınca `type: "complete"` olayı gönderir.

## Güvenlik ve veri gizliliği

- Parolalar bcrypt ile hash’lenir; düz metin parola saklanmaz.
- Access ve refresh JWT’leri süreli üretilir; rollerle yetkilendirme desteklenir.
- Dosya boyutu ve uzantısı doğrulanır; yüklenen dosyalar çalıştırılmaz.
- JWT secret, bağlantı bilgileri ve parolalar ortam değişkenlerinden okunur.
- Token, parola, stack trace ve hassas belge içeriği loglanmaz veya istemciye döndürülmez.

## Test ve LoRA eğitimi

`python -m pytest -v` ile testleri, `python training/train_lora.py` ile PEFT/LoRA adapter eğitimini çalıştırın. LoRA, Ollama Modelfile ayarı değildir: prompt/system ayarı çalışma anındaki talimatı değiştirir, RAG bilgiyi sorgu anında sağlar, LoRA adapter ağırlıkları öğrenir, tam fine-tuning ise tüm model ağırlıklarını günceller. Ayrıntılar [`training/README.md`](training/README.md) dosyasındadır.

## Bilinen sınırlamalar

Mevcut sürüm belge metnini PostgreSQL’e kaydeder ve güvenli RAG prompt sınırını gösterir. Üretim için embedding üretimi, Qdrant upsert/silme, arka plan indeksleme worker’ı ve gerçek dağıtık rate-limit middleware’i ayrıca bağlanmalıdır. Üretime geçişte Alembic, merkezi log/metrik, secret yönetimi, TLS, nesne depolama, yedekleme ve yük testleri eklenmelidir.

## Lisans

Bu proje WATAM lisansı ile sunulmaktadır.

<a href="https://wearetheartmakers.com" target="_blank" rel="noopener noreferrer">We Are The Art Makers</a>
