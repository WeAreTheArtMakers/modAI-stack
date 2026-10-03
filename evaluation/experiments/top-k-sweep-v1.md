# Top-k Sweep v1

Tarih: 2026-10-03
Koşu tipi: Yerel, yetkili RAG evaluation

## Sabitler

- Case sayısı: 24
- Dataset fingerprint: `41be34dd1a014ad6f7bfc97218c763277952a228487dfd418dd5ea76b5a18bcc`
- Embedding modeli: `sentence-transformers/all-MiniLM-L6-v2`
- Generation modeli: Yerel Ollama `modAIJet:latest`
- Yalnızca evaluation CLI `--top-k` override’ı değiştirildi. Production `RAG_TOP_K`, embedding modeli, generation modeli ve model parametreleri değiştirilmedi.

Canlı v0.5 corpus’u bu koşu öncesinde mevcut değildi. Aynı yedi private kabul dokümanı (iki aynı-adlı belge dahil) yeniden indekslendi ve aynı 24 vaka yeni ortam kimlikleriyle güvenli biçimde bağlandı. Bu nedenle v0.5 K=5 sonucu fingerprint eşleşmediği için reuse edilmedi; K=5 bu corpus üzerinde yeniden ölçüldü. Dataset ve sonuç JSON’ları private kalır.

## Retrieval-only sonuçları

| top_k | Hit@K | MRR | Source Accuracy | Fact Coverage | Median source/chunk | Retrieval ms | Total ms |
|------:|------:|----:|----------------:|--------------:|--------------------:|-------------:|---------:|
| 1 | 0.875000 | 0.875000 | 0.875000 | 0.875000 | 1 | 2.057 | 38.400 |
| 2 | 0.958333 | 0.916667 | 0.479167 | 0.958333 | 2 | 2.020 | 23.543 |
| 3 | 1.000000 | 0.930556 | 0.333333 | 1.000000 | 3 | 42.917 | 65.824 |
| 5 | 1.000000 | 0.930556 | 0.200000 | 1.000000 | 5 | 43.079 | 67.981 |

## Generation karşılaştırması

Yalnızca retrieval kalitesini koruyan K=3 ve baseline K=5 çalıştırıldı.

| top_k | Groundedness | Generation ms | Total ms | Median source/chunk |
|------:|-------------:|--------------:|---------:|--------------------:|
| 3 | 0.958333 | 7021.712 | 7069.838 | 3 |
| 5 | 0.958333 | 13532.977 | 13617.107 | 5 |

## Ölçüme dayalı karar

- K=1 ve K=2, Hit@K ve fact coverage değerlerini düşürdüğü için uygun production adayları değildir.
- K=3, K=5’in Hit@K, MRR ve fact coverage değerlerini korur; iki daha az source/chunk döndürür.
- K=3 ve K=5 aynı groundedness değerini verdi. Bu koşuda K=3 median generation süresini 6511.265 ms, total süreyi 6547.269 ms azalttı.

Bu ölçümde en güçlü trade-off K=3’tür. Ancak bu yalnızca deney sonucudur: production `RAG_TOP_K` bu branch’te değiştirilmemiştir. Production değişikliği, PR incelemesinden sonra bilinçli olarak yapılmalıdır.
