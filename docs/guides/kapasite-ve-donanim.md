# Kapasite ve donanım: kaç kişi aynı anda kullanabilir?

## 1. Ölçülen (referans makine)

**Makine:** MacBook Pro M1 Pro (10 çekirdek), 16 GB bellek; aynı makinede başka uygulamalar da açıktı.
**Kurulum:** modAI v1.5.0, gemma3:4b (8K bağlam), çok dilli arama (BGE-M3).
**Yöntem:** `app.tools.load_test`; 25 gerçek Kalite sorusu. Her aşamada N kişi aynı anda, art arda soru sordu. Ölçüm tarihi 12 Ekim 2026.

| Aynı anda soru soran | Yanıt süresi (medyan) | Yanıtların %95'i şu süre içinde | Dakikada yanıt | Hata |
|---|---|---|---|---|
| 1 | 3,3 sn | 3,4 sn | 19 | 0 |
| 2 | 3,0 sn | 5,3 sn | 33 | 0 |
| 4 | 7,8 sn | 9,8 sn | 28 | 0 |
| 8 | 12,7 sn | 16,4 sn | 34 | 0 |
| 16 | 32,7 sn | 36,9 sn | 27 | 0 |

- Sunucu dakikada yaklaşık **30 yanıtta** doyuyor. Daha fazla kişi sorunca yanıt kaybolmuyor, sırada bekliyor; 16 kişide de hata çıkmadı.
- **Güvenli sınır: aynı anda 4 soru.** Yanıtların %95'i 10 saniyenin altında.
- **Kabul edilebilir: aynı anda 8 soru.** Yanıtların %95'i 17 saniyenin altında.
- Modelin ilk yüklenmesi yaklaşık 20 saniye sürer. Bu süre yalnızca model bellekte değilken (sabah ilk soru) yaşanır.
- Bu makinede asıl sınır bellek. Test sırasında boş bellek %23'e indi ve diske yazılan takas (swap) 7 GB'tan 15 GB'a çıktı. modAI'ye ayrılmış bir makinede bu baskı daha düşük olur.
- **Sesli asistanda sunucuda konuşma tanıma** (Whisper Small, işlemcide): M1 Pro 16 GB'ta iki ölçüm var. Docker dışında 3–4 saniyelik bir soru 0,9–1,0 saniyede yazıya çevrildi, model yaklaşık 0,5 saniyede yüklendi. Üretim kurulumunda, Docker Desktop'ın Linux sanal makinesinde ise 2 saniyelik bir soru yaklaşık 3,4 saniye sürdü (int8, 4 iş parçacığı en hızlısıydı; 8 iş parçacığı ve float32 daha yavaştı), modelin ilk yüklenmesi 12–28 saniye. Bu yüzden sesli asistan sayfası açılınca model arka planda yüklenir (`POST /voice/warmup`). Mac'te Docker içinde çalışan bir kurulumda tarayıcıda tanıma (WebGPU, Whisper Tiny) daha hızlı ama daha az doğrudur; Linux sunucuda süre teslimden önce ölçülür. Model yüklüyken API süreci yaklaşık 0,65–0,9 GB daha fazla bellek kullanır; 10 dakika sesli soru gelmezse model bellekten bırakılır. Bir API süreci aynı anda bir soruyu yazıya çevirir, diğerleri sırada bekler (en çok 8); bu süre yanıt süresine eklenir. Eşzamanlı sesli kullanım bu tabloda ölçülmedi; yük testi yazılı sorularla yapıldı.

## 2. Çalışan sayısına çeviri (tahmin)

"Aynı anda soru soran" sayısı, şirketteki çalışan sayısı değildir. Aşağıdaki tablo bilinçli olarak temkinli varsayımlarla hesaplandı:

- çalışanların yarısı her gün kullanır ve günde 8 soru sorar;
- günün sorularının %30'u en yoğun saatte gelir;
- ani yoğunluğa karşı (örneğin bir duyurudan sonra herkesin aynı anda sorması) 3 kat pay bırakılır;
- yanıt 3,3 saniye sürer. Sesli asistan ve uzun yanıtlar daha uzun sürer.

| Çalışan | En yoğun anda aynı anda soran (ortalama / %95) | Beklenen bekleme (referans makine) | Değerlendirme |
|---|---|---|---|
| 50 | 0,2 / 1 | 3–4 sn | Rahat |
| 100 | 0,3 / 2 | 3–5 sn | Rahat |
| 250 | 0,8 / 3 | 5–8 sn | Rahat |
| 500 | 1,7 / 4 | ~10 sn | Güvenli sınırda |
| 1.000 | 3,3 / 7 | ~15 sn | Yoğun anlarda yavaş; daha güçlü donanım önerilir |
| 2.000 | 6,6 / 12 | 25 sn ve üstü | Bu makine için uygun değil |

**Sonuç:** referans makine (16 GB) **250 çalışana kadar rahat**, **500'e kadar güvenli** kullanılır. Bu tahmin; kurulumda yük testini müşterinin kendi makinesinde çalıştırıp doğrulayın (4. bölüm).

## 3. Donanım tablosu

Yalnızca ilk satır ölçüldü; diğerleri ölçülen değerlerden ve bileşenlerin genel davranışından yapılmış **tahmindir**. Satıştan önce hedef donanımda yük testiyle doğrulayın.

| Ölçek | Çalışan | Önerilen donanım | Model | Kaynak |
|---|---|---|---|---|
| Küçük | 250'ye kadar | 16 GB bellek; Apple M1 Pro/M2 ya da 8 çekirdekli x86; 256 GB SSD | gemma3:4b | Ölçüldü |
| Orta | 250–1.000 | 32 GB bellek; Apple M2/M3 Pro ya da x86 ve 12–16 GB bellekli NVIDIA ekran kartı; 512 GB SSD | gemma3:4b, sınanırsa qwen3.5:9b | Tahmin |
| Büyük | 1.000–3.000 | 64 GB bellek ve 24 GB NVIDIA ekran kartı (ör. RTX 4090, L4); 1 TB SSD | qwen3.5:9b (Kalite'de 25'te 24, güvenlikte 9/9) | Tahmin |
| Çok büyük | 3.000+ | Birden fazla sunucu ya da ayrı model sunucusu | — | Ayrı proje (yüksek erişilebilirlik bu sürümde yok) |

**Disk:** belgelerin kendisi, arama dizini ve yedekler. Demo kurulumunda (16 belge) bir yedek yaklaşık 660 MB tuttu; çoğu arama dizini. Gece yedekleri katmanlı tutulur: 14 günlük, 8 haftalık ve 6 aylık, toplam yaklaşık 28 yedek (`scripts/prune_backups.py`). Yedeklerin ikinci bir diske kopyalanması önerilir. En az %20 boş alan bırakın; %15'in altında yöneticiler uyarılır, 5 GB'ın altında yeni yükleme durur.

**Daha büyük model:** qwen3.5:9b güvenlik testlerinde daha iyi (9/9) ama referans makinede yanıt başına medyan 17,7 saniye sürdü (gemma3:4b'de 3,5 saniye). Ekran kartı olan bir sunucuda bu fark kapanır.

## 4. Kendi donanımınızda ölçme

Mesai dışında çalıştırın; sunucuyu tam yükler:

```bash
docker compose exec -T api python -m app.tools.load_test --workspace-id 1
```

- Araç geçici kullanıcılar açar, çalışma alanının Kalite sorularını 1, 2, 4, 8 ve 16 kişi aynı anda soruyormuş gibi sorar ve yukarıdaki tabloyu yazar.
- Bitince kullanıcıları, yanıt izlerini, yanıtlanamayan soru kayıtlarını ve günlük sayacı geri alır.
- Seviyeleri değiştirmek için: `--levels 1x5,4x3,8x3` (aynı anda kişi x kişi başına soru).

## 5. Ne zaman büyütmeli: Kapasite kartı

**Sistem** sayfasındaki **Kapasite (son 7 gün)** kartı ve Güven raporu gerçek kullanımı gösterir:

- yanıt süresinin medyanı ve %95'i;
- en yoğun saatteki yanıt sayısı.

Kartın sonuçları şöyle okunur:
- **Yolunda:** yanıtların %95'i 10 saniyenin altında ve en yoğun saat referans kapasitenin yarısından az.
- **İzleyin:** %95 10 saniyeyi ya da yoğun saat kapasitenin yarısını aşıyor.
- **Büyütün:** %95 20 saniyeyi ya da yoğun saat kapasitenin %80'ini aşıyor. Bir üst donanım satırına geçin.
