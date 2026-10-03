# Compact Multilingual embedding benchmark v1 — BLOCKED BY MODEL PROVISIONING

## Decision

No production profile recommendation can be made in this milestone. The pinned E5 weights could not be provisioned, and the original private 92-case corpus was not present in the inspected local evaluation paths. No E5 inference or paired 92-case comparison ran. Keep production on `sentence-transformers/all-MiniLM-L6-v2`, `RAG_TOP_K=3`, and the read-only profile catalog; do not activate Compact Multilingual.

## Machine and model provenance

- Hardware: MacBook Pro, Apple M1 Pro, 16 GB unified memory; arm64.
- Baseline: `sentence-transformers/all-MiniLM-L6-v2`, local pinned snapshot `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, Apache-2.0, 384 dimensions, 256-token SentenceTransformers limit. The official pinned model snapshot is [here](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41).
- Candidate: `intfloat/multilingual-e5-small`, upstream `main` resolved and pinned to `614241f622f53c4eeff9890bdc4f31cfecc418b3`, MIT, 384 dimensions, 512-token maximum, 94 languages. Its SentenceTransformers pooling config specifies 384 dimensions; the upstream card documents the asymmetric `query: ` and `passage: ` prefixes. See the [pinned model snapshot](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3), [pooling configuration](https://huggingface.co/intfloat/multilingual-e5-small/blob/614241f622f53c4eeff9890bdc4f31cfecc418b3/1_Pooling/config.json), and [prefix guidance](https://huggingface.co/intfloat/multilingual-e5-small#faq).
- Intended artifact/backend: upstream `model.safetensors`, SentenceTransformers + PyTorch, loaded with safe weights only, `local_files_only=True`, and `trust_remote_code=False`. Upstream reports a 471 MB safetensors file (SHA-256 `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477`).
- Provisioning: no complete E5 model was found in the Hugging Face, SentenceTransformers, or project model caches. One bounded, revision-pinned five-minute attempt fetched small config/tokenizer files but did not transfer model weights. It ended at the timeout with the safetensors `.incomplete` file at 0 bytes. The task-scoped temporary Hugging Face cache is outside the repository; its partial files were not deleted and are not usable for inference. No further download retry was made.
- The installed PyTorch runtime reports MPS built but unavailable; the measured baseline therefore used CPU. E5 inference backend/device and latency remain **not measured**.

## Main robustness corpus — exact fingerprint retained

The existing aggregate report identifies the private 92-case synthetic corpus by SHA-256 `009f231b51d3b7004fcf7116c9c2f3f248d351d3d2ae4e67d97ca73b170f58cc`: 55 English, 37 Turkish; 55 normal, 20 hard-negative, 15 no-answer, and 2 access probes. Its aggregate baseline remains recorded in [retrieval-robustness-v1](retrieval-robustness-v1.md).

The raw case file was not available in the repository evaluation tree or inspected `/private/tmp` dataset paths, so this run did not recreate, edit, or tune its cases. The historical aggregate does not contain a per-language or explicitly labeled cross-language breakdown, and it did not record the exact baseline model revision. Those omissions cannot be reconstructed from aggregate metrics. The prior overall baseline values below are quoted from that existing report, not freshly rerun in this experiment.

| Main 92-case result | Existing MiniLM aggregate | E5 candidate |
| --- | ---: | ---: |
| Answerable Hit@3 | 73/75 (97.33%) | Not run — model provisioning blocked |
| MRR | 93.33% | Not run |
| Source accuracy | 32.44% | Not run |
| Fact coverage | 97.33% | Not run |
| Median embedding / retrieval / total latency | 24.06 / 43.27 / 68.57 ms | Not run |
| No-answer confusable retrievals | 14/15 | Not run |
| English/Turkish and cross-language split | Not retained in historical aggregate | Not run |
| Hard-negative metric breakdown | Not retained in historical aggregate | Not run |

The original fixed-K=3 report recorded expected-source ranks as rank 1: 67, rank 2: 6, rank 3: 0, miss: 2 among 75 answerable cases. Its separate adaptive holdout experiment rejected gap, ratio, and three-tier policies; production remains fixed at K=3.

## Supplemental private cross-language set

Because the historical aggregate does not identify cross-language directions, a separate synthetic set was created locally rather than modifying the 92-case dataset. It contains 20 Turkish-query → English-document cases and 20 English-query → Turkish-document cases, paired across 20 enterprise-policy scenarios. It has fingerprint `4ccf117362172d4bbd6c7272199c410f0934f6210295ac39e230b9962aef239a`; fixed K=3; no reranker, adaptive logic, BM25, query rewriting, or generation. Case and document contents remain under the ignored local `data/embedding-benchmark/` directory and are not committed.

| Supplemental direction | Cases | MiniLM Hit@3 | MiniLM MRR | E5 candidate |
| --- | ---: | ---: | ---: | ---: |
| Turkish query → English document | 20 | 0/20 (0%) | 0.000 | Not run — model provisioning blocked |
| English query → Turkish document | 20 | 1/20 (5%) | 0.025 | Not run — model provisioning blocked |

For this synthetic cross-language-only set, MiniLM overall Hit@3 was 1/40 (2.5%), MRR 0.0125, source accuracy 0.83%, and fact coverage 2.5%. These results indicate the baseline did not retrieve the paired cross-language evidence in this set; they do not predict E5 performance or general customer quality. This supplemental set contains no hard-negative or no-answer cases, so those metrics are not applicable here.

## Local MiniLM resource measurements

Measured with SentenceTransformers/PyTorch on CPU, using the repository's configured chunk size/overlap and an ephemeral per-model Qdrant local index. The report is retrieval-only and was produced from the private supplemental set above.

| Metric | MiniLM | E5 |
| --- | ---: | ---: |
| Query embedding median / p95 | 10.103 / 12.956 ms | Not measured |
| Retrieval median | 0.386 ms | Not measured |
| Total retrieval median | 10.612 ms | Not measured |
| Document embedding throughput | 120.647 chunks/s | Not measured |
| Document embedding / Qdrant upsert / total indexing | 331.545 / 25.257 / 361.741 ms | Not measured |
| Vectors / dimensions | 40 / 384 | Not measured |
| Raw float32 vector bytes / isolated Qdrant directory bytes | 61,440 / 225,802 | Not measured |
| Process peak RSS | 758,644,736 bytes (~724 MiB) | Not measured |

Peak RSS is the process high-water mark, not model-only memory. Local Qdrant directory size is not a production storage estimate. Candidate latency, memory, indexing, and storage cost cannot be inferred from model file size.

## Reproduction and safety

The experiment runner accepts only an existing local model snapshot and runs offline. Each invocation creates an ephemeral Qdrant directory derived from that profile's model/revision/preprocessing identity; it validates dimensions and rejects a different vector-space identity even when dimensions match. E5 query and passage prefixes are profile-specific; MiniLM uses identity preprocessing.

Example, after the exact private dataset and local snapshots are provisioned:

```bash
python -m app.tools.benchmark_embedding_profile \
  --profile minilm \
  --model-path /local/huggingface/snapshots/1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --dataset /private/path/robustness-92.json \
  --documents /private/path/authorized-document-export.json \
  --output /private/path/minilm-aggregate.json

python -m app.tools.benchmark_embedding_profile \
  --profile e5-small \
  --model-path /local/huggingface/snapshots/614241f622f53c4eeff9890bdc4f31cfecc418b3 \
  --dataset /private/path/robustness-92.json \
  --documents /private/path/authorized-document-export.json \
  --output /private/path/e5-aggregate.json
```

The outputs contain aggregate metrics and dataset fingerprint only; no questions, document text/names/IDs, answers, prompts, local model paths, credentials, or raw per-case records are serialized. Authorization-negative probes are skipped before isolated retrieval; use the existing authorized evaluation path for tenant-access assertions.

Production application code, APIs, and `.env` were not changed. The repository Settings default and checked `.env.example` remain `sentence-transformers/all-MiniLM-L6-v2` with `RAG_TOP_K=3`; profile switching remains disabled, and no production vectors or collections were read or modified. The experiment runner enforces K=3 independently of environment overrides.

## Conclusion and next milestone

1. Did E5 materially improve Turkish retrieval? **Unknown; E5 was not run.** MiniLM scored 0/20 on the supplemental Turkish-query → English-document direction.
2. Did it improve cross-language retrieval? **Unknown; E5 was not run.**
3. Did English retrieval regress? **Unknown; no paired E5 run.**
4. What resource cost did it add? **Unknown; no E5 inference.**
5. Is it suitable for M1 Pro 16 GB? **Not established.** The verified runtime had MPS unavailable; the candidate did not load on CPU.
6. Should E5 become the Compact Multilingual candidate mapping? **Not yet.** Keep the profile experimental until paired quality/resource evidence exists.
7. Should production remain on English Optimized? **Yes**, until a separate controlled profile migration and reindex lifecycle is approved and implemented.
8. Single next milestone: **Provision the pinned E5 safetensors artifact and restore the exact private 92-case corpus plus matching authorized document export, then run the paired offline K=3 benchmark and review the aggregate-only report.**
