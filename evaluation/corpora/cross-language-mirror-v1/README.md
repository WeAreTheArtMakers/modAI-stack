# Cross-language mirror v1

This is a deterministic, fictional diagnostic corpus for isolating English↔Turkish retrieval direction. It supplements—but never replaces or edits—`compact-multilingual-v1`.

The corpus contains 20 underlying enterprise facts. Each fact has one English and one Turkish document, plus a Turkish-query→English-source case and a semantically paired English-query→Turkish-source case. The opposite-language document for the same fact is listed as a confusable source. All examples are synthetic and numeric/threshold-oriented.

- Dataset: `dataset.json`
- Documents: `documents.json`
- Fingerprint and counts: `manifest.json`
- Fingerprint: `95e188795dd5c493f10d1b6139559e9ffcd71c8dd5f6b8469865b833595e188c`
- 40 documents, 40 cases, 20 mirrored fact pairs

Regenerate from the repository root with:

```bash
python -m evaluation.corpora.cross_language_mirror_v1.generator
```

The evaluator only writes aggregate ranks/scores/token counts to its result artifact; it does not serialize question or document text. The set is diagnostic only and does not affect production retrieval settings.
