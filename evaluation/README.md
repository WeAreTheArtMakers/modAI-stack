# RAG Evaluation & Quality v0.5

Bu dizin, insan tarafından gözden geçirilmiş RAG değerlendirme veri setlerini saklar. Her veri seti sürümlüdür ve her kayıt; soru, yetkili Knowledge Base kimlikleri, beklenen kaynak belgeler, beklenen doğrulanabilir olgular ve `top_k` değerini içerir.

Değerlendirme motoru yalnızca seçilen Knowledge Base kayıtları için uygulamanın normal `resolve_knowledge_base_scope` yetkilendirmesini kullanır. Başka tenant veya yetkisiz bilgi tabanı için değerlendirme başlatılamaz. Sonuçlara belge gövdesi, RAG prompt’u veya üretilen tam yanıt yazılmaz.

## Metrikler ve sınırlar

- **Hit@K:** Beklenen kaynak belgelerden en az birinin dönen ilk `K` kaynakta olup olmadığını ölçer.
- **Source accuracy:** Beklenen kaynak olarak işaretlenmiş dönen belge sayısının tüm dönen belge sayısına oranıdır. Kaynak doğruluğu, yanıtın semantik olarak doğru olduğunu kanıtlamaz.
- **MRR:** İlk doğru kaynak belgenin sırasına göre hesaplanır. Daha yüksek değer, doğru kaynağın listede daha erken göründüğünü ifade eder.
- **Unexpected / no source:** Beklenmeyen kaynak belge sayısını ve hiç kaynak dönmeyen kayıtları açıkça raporlar.
- **Fact coverage:** Beklenen olguların normalize edilmiş metin eşleşmesiyle dönen kaynak metinlerde desteklenme oranıdır. Unicode NFKC, `casefold` ve boşluk normalizasyonu uygulanır; bu bir anlamsal doğruluk ölçümü değildir.
- **Answer fact groundedness:** `--generate` kullanıldığında beklenen olgunun hem yerel Ollama yanıtında hem de retrieval bağlamında bulunma oranıdır. Bulut LLM judge veya gizli bir değerlendirme modeli kullanılmaz.
- **Latency:** Embedding, retrieval, isteğe bağlı generation ve toplam süreler monotonic saatle milisaniye cinsinden ölçülür. Prompt, token veya kullanıcı içeriği kaydedilmez.

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

İki koşuyu nesnel delta olarak karşılaştırın:

```bash
python -m app.tools.compare_rag_evaluations baseline.json candidate.json
```

Araç “daha iyi” yorumu yapmaz; embedding modelinin değiştiği durumda yeniden indeksleme uyarısı verir.
