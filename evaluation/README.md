# RAG Evaluation & Quality v0.5

Bu dizin, insan tarafından gözden geçirilmiş RAG değerlendirme veri setlerini saklar. Her veri seti sürümlüdür ve her kayıt; soru, yetkili Knowledge Base kimlikleri, beklenen kaynak belge kimlikleri, geriye uyumlu belge adları, beklenen doğrulanabilir olgular ve `top_k` değerini içerir. Çalıştırılan doğrulanmış veri setinin tamamı, alan sırası veya biçimlendirmeden etkilenmeyen canonical JSON SHA-256 fingerprint’i ile sonuçta kaydedilir.

Değerlendirme motoru yalnızca seçilen Knowledge Base kayıtları için uygulamanın normal `resolve_knowledge_base_scope` yetkilendirmesini kullanır. Başka tenant veya yetkisiz bilgi tabanı için değerlendirme başlatılamaz; yetki reddi retrieval/Qdrant çağrısından önce gerçekleşir. Sonuçlara belge gövdesi, RAG prompt’u, üretilen tam yanıt veya kimlik bilgisi yazılmaz.

## Metrikler ve sınırlar

- **Hit@K:** Beklenen kaynaklardan en az birinin dönen ilk `K` kaynakta olup olmadığını ölçer. `expected_document_ids` sağlanmışsa belge adı değil yalnızca sabit belge kimliği kullanılır; ad yalnızca ID bulunmayan eski veri setleri için fallback’tir. Böylece aynı adlı iki belge yanlış pozitif oluşturamaz.
- **Source accuracy:** Beklenen kaynak kimliği bulunan kayıtlar içindeki eşleşen dönen belge sayısının, yine yalnızca bu kayıtların tüm dönen belge sayısına oranıdır. Kaynak beklentisi olmayan kayıtlar paydaya girmez. Kaynak doğruluğu, yanıtın semantik olarak doğru olduğunu kanıtlamaz.
- **MRR:** İlk doğru kaynak belgenin sırasına göre hesaplanır. Daha yüksek değer, doğru kaynağın listede daha erken göründüğünü ifade eder.
- **Unexpected / no source:** Beklenmeyen kaynak belge sayısını ve hiç kaynak dönmeyen kayıtları açıkça raporlar.
- **Fact coverage:** Beklenen olguların normalize edilmiş metin eşleşmesiyle dönen kaynak metinlerde desteklenme oranıdır. Unicode NFKC, `casefold` ve boşluk normalizasyonu uygulanır; bu bir anlamsal doğruluk ölçümü değildir.
- **Answer fact groundedness:** `--generate` kullanıldığında beklenen olgunun hem yerel Ollama yanıtında hem de retrieval bağlamında bulunma oranıdır. Bulut LLM judge veya gizli bir değerlendirme modeli kullanılmaz.
- **Latency:** Embedding, retrieval, isteğe bağlı generation ve toplam süreler monotonic saatle milisaniye cinsinden ölçülür. Sonuçta güvenli tekrar üretilebilirlik metadatası (`embedding_model`, provider/model, varsayılan `top_k`, uygulama commit’i ve evaluation modu) bulunur. Prompt, token veya kullanıcı içeriği kaydedilmez.

Embedding modeli değişirse aynı vektör uzayını korumak için Knowledge Base’leri yeniden indeksleyin. Aksi halde retrieval metriklerini önceki koşuyla doğrudan karşılaştırmayın.

Başlangıç için 20–30 insan gözden geçirmeli soru ve 50–200 doğrulanmış belge önerilir. `sample_dataset.json` yalnızca şema örneğidir; kendi tenant’ınızdaki gerçek kimliklerle güncellenmeden local modda kullanılamaz.

## Çalıştırma

Gerçek local stack için access JWT’yi yalnızca süreç ortamında tutun; komut satırına veya sonuç dosyasına yazmayın:

```bash
export MODAI_EVALUATION_ACCESS_TOKEN='<access-jwt>'
python -m app.tools.evaluate_rag --dataset evaluation/sample_dataset.json --output baseline.json
```

Bu varsayılan mod yalnızca cache’te zaten bulunabilen embedding modelini ve yerel servisleri kullanır; model indirme yapmaz. Yanıt destek sinyalini de ölçmek için yerel Ollama üretimini açıkça etkinleştirin:

```bash
python -m app.tools.evaluate_rag --dataset evaluation/sample_dataset.json --generate --json
```

Deterministik CI veya geliştirme denemesi için retrieval fixture’ı ile ağ/model gerektirmeyen mod kullanılabilir:

```bash
python -m app.tools.evaluate_rag --dataset evaluation/sample_dataset.json --mode fixture --fixture retrieval-fixture.json --min-hit-at-k 0.8
```

Eşikler yalnızca açıkça verildiğinde process başarısız olur: `--min-hit-at-k`, `--min-source-accuracy`, `--min-fact-coverage` ve `--max-median-total-ms`.

## Top-k deney override’ı

`--top-k N`, yalnızca o evaluation koşusundaki **tüm** case’lerin `top_k` değerini `N` ile değiştirir. Bu davranış kasıtlı olarak case başına farklı `top_k` tanımlarını da ezer; sweep koşulları böylece doğrudan karşılaştırılabilir olur. Kaynak dataset dosyası, production `RAG_TOP_K` ve dataset fingerprint’i değişmez.

```bash
python -m app.tools.evaluate_rag \
  --dataset private-acceptance-dataset.json \
  --top-k 3 \
  --output top-k-3.json
```

`N` 1–50 aralığında olmalıdır. Kaydedilen sonuçta `top_k_override` ve uniform koşulda `effective_top_k` bulunur; ayrıca case ve özet seviyesinde güvenli retrieved source/chunk sayıları kaydedilir. `--generate` koşularında cevap metni yerine yalnızca `generated_answer_char_count` saklanır. Bu sayımlar kaynak metni veya cevabı içermez. Karşılaştırma aracı, iki koşunun etkin top-k veya override metadatası farklıysa bunu açıkça uyarı olarak bildirir.

İki koşuyu nesnel delta olarak karşılaştırın:

```bash
python -m app.tools.compare_rag_evaluations baseline.json candidate.json
```

Araç “daha iyi” yorumu yapmaz; embedding modeli değiştiğinde yeniden indeksleme, fingerprint eksik olduğunda eşitliğin kanıtlanamadığı, fingerprint değiştiğinde ise aggregate delta’ların doğrudan karşılaştırılamayacağı uyarısını verir.

## Adaptive context experiment (evaluation only)

Evaluation CLI, K=3 retrieval listesinden sorgu içi score-gap, score-ratio veya three-tier kurallarıyla 1–3 kaynaklık bir prefix seçebilir. Bu mod production RAG yollarında kullanılmaz ve `RAG_TOP_K` ayarını değiştirmez. Adaptive koşuda retrieval tabanı açıkça `--top-k 3` olmalıdır.

```bash
python -m app.tools.evaluate_rag \
  --dataset private-acceptance-dataset.json \
  --top-k 3 \
  --adaptive-policy gap \
  --adaptive-threshold 0.02 \
  --output adaptive-candidate.json
```

Evaluation case sonuçları yalnızca ilk üç retrieval skorunu, gap/ratio özetlerini, kaynak rank/eşleşme bayraklarını ve rank başına fact coverage değerlerini sayısal metadata olarak tutar. Kaynak metni, soru, prompt veya tam yanıt bu skor alanlarına eklenmez. Skor eşikleri her sorgunun kendi sıralı skorları üzerinde uygulanmalıdır; mutlak cosine skorlarının sorgular arasında kalibre edildiği varsayılmaz.
