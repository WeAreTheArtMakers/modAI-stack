# Top-k=3 Production Confirmation

Tarih: 2026-10-03
Koşu tipi: Yerel, yetkili RAG evaluation; üçer tekrar, dönüşümlü sıra

## Sabitler ve yöntem

- Case sayısı: 24
- Dataset fingerprint: `41be34dd1a014ad6f7bfc97218c763277952a228487dfd418dd5ea76b5a18bcc`
- Embedding modeli: `sentence-transformers/all-MiniLM-L6-v2`
- Generation modeli: yerel Ollama `modAIJet:latest`
- Sıra: `K=3`, `K=5`, `K=5`, `K=3`, `K=3`, `K=5`
- Her K için üç retrieval-only ve üç generation koşusu çalıştırıldı.
- Sadece evaluation CLI `--top-k` override'ı değiştirildi. Production `RAG_TOP_K`, embedding modeli, generation modeli ve model parametreleri ölçüm sırasında değiştirilmedi.

Dataset ve ham sonuç JSON'ları private kalır. Bu rapor yalnızca güvenli toplu metrikleri; hiçbir soru, prompt, kaynak metni veya üretim yanıtını içerir.

## Retrieval-only tekrarları

Değerler, üç koşunun case-medyanlarının medyanıdır; aralık ilgili üç koşunun min–max değeridir.

| top_k | Hit@K | MRR | Source Accuracy | Fact Coverage | Median source/chunk | Embedding ms | Retrieval ms | Total ms |
|------:|------:|----:|----------------:|--------------:|--------------------:|-------------:|-------------:|---------:|
| 3 | 1.000000 | 0.930556 | 0.333333 | 1.000000 | 3 | 123.349 (64.675–163.437) | 3.175 (2.801–3.375) | 126.689 (72.310–170.181) |
| 5 | 1.000000 | 0.930556 | 0.200000 | 1.000000 | 5 | 45.222 (37.586–89.174) | 2.939 (2.309–3.496) | 68.130 (48.622–94.565) |

Retrieval-only aşamasında embedding süresi baskın ve değişkendir. Saf retrieval medyanları arasındaki 0.236 ms fark pratik bir K avantajı olarak yorumlanmaz; bu koşular K=3 için gecikme iddiası desteklemez. Kalite ve bağlam boyutu için tutarlı sonuç verir: K=3 aynı retrieval/fact metriklerini üç koşuda korur ve iki daha az source/chunk kullanır.

## Generation tekrarları

Değerler yine üç koşunun case-medyanlarının medyanıdır; aralık üç koşunun min–max değeridir. Çıktı boyutu, yanıt metni yerine güvenli karakter sayısıdır.

| top_k | Groundedness | Generation ms | Total ms | Median source/chunk | Answer char count |
|------:|-------------:|--------------:|---------:|--------------------:|------------------:|
| 3 | 1.000000 (0.958333–1.000000) | 8643.333 (6411.758–9225.414) | 8835.000 (6446.572–9350.279) | 3 | 65.0 (57.0–70.0) |
| 5 | 0.958333 (0.958333–1.000000) | 9818.628 (7706.893–11330.299) | 9995.891 (7806.860–11450.548) | 5 | 66.5 (63.5–79.5) |

K=3, K=5'e göre medyan generation süresini 1175.295 ms (%12.0), toplam süreyi 1160.891 ms (%11.6) azalttı. Yanıt boyutu karşılaştırılabilirdir (medyan farkı 1.5 karakter); daha kısa sürenin yalnızca daha kısa yanıt yazmaktan kaynaklandığına dair belirti yoktur.

## Ölçüme dayalı karar

Production varsayılanını `RAG_TOP_K=3` yapmak için koşullar karşılandı:

- Hit@K, MRR ve fact coverage üç tekrarın tamamında K=5 ile eşit kaldı.
- Groundedness korunmuştur: K=3 medyanı 1.000000, K=5 medyanı 0.958333; koşu aralıkları örtüşür.
- K=3 bağlamı %40 azaltır (5 yerine 3 source/chunk) ve source accuracy daha yüksektir (0.333333'e karşı 0.200000).
- Saf retrieval gecikmesinde anlamlı bir avantaj yoktur; buna rağmen dönüşümlü generation tekrarlarında K=3 daha düşük generation ve toplam medyan süre verdi.

Bu ölçüm, mevcut kabul corpus'u ve modelleri için K=3'ü en dengeli production varsayılanı yapar. K=4–5'teki ek bağlam, bu 24 vakada kalite kazancı üretmedi; yeni corpus'lar veya no-answer davranışı için değerlendirme sürdürülmelidir.
