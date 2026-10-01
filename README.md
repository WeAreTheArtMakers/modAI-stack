# modAI-stack

<p align="center"><img src="assets/modai-stack-logo.png" alt="modAI-stack logosu" width="760"></p>

> Yerel LLM, gerçek zamanlı sohbet, belge tabanlı RAG ve vektör aramayı birleştiren modüler yapay zekâ platformu.

[GitHub deposu](https://github.com/WeAreTheArtMakers/modAI-stack)

## Proje hakkında

modAI-stack; Ollama üzerinde yerel model çalıştırmayı, belge yüklemeyi, semantik arama yapmayı ve yanıtları WebSocket ile gerçek zamanlı aktarmayı sağlar. FastAPI ve `asyncio` tabanlıdır. PostgreSQL kalıcı verileri, Qdrant vektör aramayı, Redis ise geçici durum ve koordinasyonu destekler. Model sağlayıcı arayüzü sayesinde Ollama yerine vLLM eklenebilir.

## Kullanılan teknolojiler

| Katman | Teknolojiler | Kullanım amacı |
| --- | --- | --- |
| Dil ve API | Python 3.11+, FastAPI, Pydantic, Uvicorn | Asenkron REST API ve doğrulama |
| Asenkron mimari | `asyncio`, bounded queue, worker, timeout, cancellation | Eşzamanlılık ve backpressure |
| LLM | Ollama, `LLMProvider` | Yerel model ve sağlayıcı soyutlaması |
| RAG | Sentence Transformers, metin parçalama | Belge kaynaklı yanıt üretimi |
| Vektör arama | Qdrant, cosine similarity, metadata filtreleri | Embedding saklama ve arama |
| Kalıcı veri | PostgreSQL, SQLAlchemy Async ORM, asyncpg | Kullanıcı, belge, oturum ve mesajlar |
| Geçici veri | Redis | Rate limit, iş durumu ve koordinasyon |
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
                                          Redis: geçici durum, rate limit, koordinasyon
```

Ollama çağrıları yalnızca `app/services/llm/` katmanından yapılır. RAG context’i güvenilmeyen veri olarak sistem talimatlarından ayrılır.

## Kurulum

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
ollama pull llama3.2:3b
uvicorn app.main:app --reload
```

Docker için `cp .env.example .env` ve `docker compose up --build` komutlarını çalıştırın. API `http://localhost:8000`, Qdrant `http://localhost:6333`, host PostgreSQL bağlantısı `localhost:55432` adresindedir. Docker içindeki API, Mac üzerinde Ollama’ya `host.docker.internal:11434` adresinden bağlanır.

Gerçek JWT secret ve parolaları yalnızca `.env` içine yazın. `.env`, `.venv`, yerel veritabanı ve eğitim çıktıları Git’e alınmaz.

## API kullanımı

```bash
curl -X POST http://localhost:8000/auth/register -H 'Content-Type: application/json' -d '{"email":"user@example.com","password":"correct-horse-battery"}'
export TOKEN="<access-token>"
curl -X POST http://localhost:8000/chat -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"prompt":"Embedding nedir?"}'
curl -X POST http://localhost:8000/documents/upload -H "Authorization: Bearer $TOKEN" -F file=@notlar.pdf
curl -X POST http://localhost:8000/rag/query -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"question":"Belgede hangi konular anlatılıyor?"}'
```

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
