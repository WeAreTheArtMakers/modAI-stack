# Sözleşme eki: yapay zekâ modelleri

Bu ek, modAI ticari sözleşmesinin (WATAM Source-Available License ve [ticari lisanslama](../../COMMERCIAL_LICENSING.md)) parçası olarak kullanılmak üzere hazırlanmış bir **şablondur**. Kurulumla gelen yerel dil modellerini, lisanslarını, müşterinin model seçme hakkını ve modellerin lisanslarından doğan kullanım kısıtlarını düzenler. Hukuki danışmanlık değildir; imzadan önce hukuk danışmanınızın onayından geçirin.

## 1. Kapsam

1.1. modAI yanıtları müşterinin sunucusunda çalışan yerel dil modelleriyle (Ollama) üretir. Belgeler, sorular ve yanıtlar bu modellere yalnızca müşterinin sunucusunda verilir. WATAM ya da model üreticileri bunlara erişmez. Müşteri verisi model eğitimi için kullanılmaz.

1.2. Bu ekin kapsadığı modeller Ek-1 tablosundaki modellerdir. Kurulum paketi bu modellerin dosyalarını ve lisans metinlerini içerir (`ollama/`, `LICENSES/`).

## 2. Ek-1: Kurulumdaki modeller

| Model | Temel model | Lisans | Lisanstan doğan yükümlülük |
|---|---|---|---|
| gemma3:4b (kurulum varsayılanı) | Google Gemma 3 | Gemma Terms of Use | Kullanım kısıtları (3. madde) bu sözleşmenin hükmüdür; lisans kopyası ve Gemma NOTICE dosyası pakettedir |
| modAI:latest | Google Gemma 3, WATAM uyarlaması | Gemma Terms of Use | Aynı; WATAM'ın değişiklik yaptığı belirtilir |
| studiobrn/modAIJet:latest | Google Gemma 4, WATAM uyarlaması | Apache 2.0 | Lisans kopyası; WATAM'ın değişiklik yaptığı belirtilir |
| gemma4:12b-mlx | Google Gemma 4 | Apache 2.0 | Lisans kopyası |
| qwen3.5:9b | Alibaba Qwen 3.5 | Apache 2.0 | Lisans kopyası |
| qwen3.5:9b-mlx | Alibaba Qwen 3.5 | Apache 2.0 | Lisans kopyası |

Tabloyu teslim edilen pakete göre güncelleyin. **Modeller → Üretim modeli seçimi** sayfası her modelin lisansını gösterir. Lisans metni olmayan uyarlamalarda lisans temel modelin ailesinden çıkarılır ve "model ailesinden" diye işaretlenir; bunlar sözleşmeden önce WATAM tarafından doğrulanır. `-mlx` modelleri yalnızca Apple silicon Mac'lerde çalışır.

## 3. Kullanım kısıtları

3.1. Müşteri, Gemma Terms of Use kapsamındaki modelleri (Ek-1'de "Gemma Terms of Use" yazanlar) **Gemma Prohibited Use Policy**'ye (https://ai.google.dev/gemma/prohibited_use_policy) aykırı amaçlarla kullanmayacağını ve kullandırmayacağını kabul eder. Bu madde Gemma Terms of Use 3.2. maddesinin gerektirdiği bağlayıcı hükümdür. Müşteri bu kısıtları modAI kullanıcılarına bildirir.

3.2. Llama lisanslı bir model kurulumda kullanılırsa, müşteri Meta'nın **Llama Acceptable Use Policy**'sine uymayı kabul eder. Ürün belgelerinde "Built with Llama" ibaresi yer alır.

3.3. Lisansından bağımsız olarak hiçbir model şu amaçlarla tek başına kullanılmaz:
- kişiler hakkında hukuki, tıbbi, finansal ya da istihdamla ilgili sonuç doğuran kararlar (bu kararlarda insan denetimi zorunludur);
- yasa dışı, ayrımcı ya da kişisel verilerin hukuka aykırı işlenmesine yol açan işler.

3.4. Güvenlik eğitimi bilerek kaldırılmış model varyantları ("abliterated", "uncensored" vb.) bu sözleşmenin kapsamında değildir; WATAM bunları pakete koymaz ve desteklemez.

## 4. Model seçimi

4.1. Müşterinin platform yöneticisi, kurulumdaki modeller arasından yanıt üreten modeli seçebilir. Bir model, müşterinin kendi Kalite soruları ve 9 güvenlik senaryosuyla **sınanmadan** etkinleştirilemez. Sınama sonucu ve seçim denetim kaydına yazılır.

4.2. Sunucunun bellek sınırını aşan modeller ve 3.4'teki varyantlar yalnızca yöneticinin uyarıyı açıkça onaylamasıyla seçilebilir. Bu onayla verilen kararların sonuçları (yavaşlama, güvenlik) müşterinin sorumluluğundadır.

4.3. Müşterinin Ek-1 dışında kendi eklediği bir modelin lisans uyumu müşterinin sorumluluğundadır. WATAM, talep edilirse lisans değerlendirmesi ve Kalite sınamasında destek verir.

4.4. Aynı adlı bir model, üreticisinin kayıt defterinde değişebilir. Kurulum ve güncelleme betikleri kurulu bir modeli kendiliğinden değiştirmez. WATAM yeni bir model sürümünü ancak Kalite sınamasından geçirdikten ve müşteri onayladıktan sonra sunar.

## 5. Bildirimler ve lisans metinleri

5.1. Her modelin lisans metni `LICENSES/<model>-LICENSE.txt` dosyasındadır. Gemma Terms of Use kapsamındaki modeller için gereken bildirim `LICENSES/Gemma-NOTICE.txt` dosyasındadır: "Gemma is provided under and subject to the Gemma Terms of Use found at ai.google.dev/gemma/terms".

5.2. WATAM uyarlamaları (Ek-1'de "WATAM uyarlaması" yazanlar) temel modelin lisansına tabidir ve WATAM'ın değişiklik yaptığını belirtir.

## 6. Model çıktıları

6.1. Yanıtlar müşterinin belgelerinden üretilir ve kaynakları gösterilir. Dil modelleri yanılabilir. WATAM yanıtların doğruluğunu garanti etmez; önemli kararlardan önce kaynak kontrol edilir.

6.2. Sorumluluk sınırları ve garantiler ana sözleşmededir.

## 7. İmza

| | WATAM — We Are The Art Makers | Müşteri |
|---|---|---|
| Ad, unvan | | |
| Tarih | | |
| İmza | | |
