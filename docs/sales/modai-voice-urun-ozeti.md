# modAI-stack ile modAI Voice — ürün özeti

**Şirket belgelerinize Türkçe, sesli ya da yazılı soru sorun; yanıt kendi altyapınızda, kaynağıyla gelsin.**

## Kimin için

- İç politikaları, prosedürleri ve teknik belgeleri çok olan ekipler (İK, finans, BT destek, operasyon).
- Belgelerini bir bulut yapay zekâ servisine göndermek istemeyen kurumlar.
- Türkçe çalışan, ama belgelerinin bir kısmı İngilizce olan şirketler.

## Ne yapar

- **Kaynaklı yanıt:** soru, yetkili bilgi tabanlarındaki belgelerden yanıtlanır. Her yanıtla birlikte kullanılan belgeler gösterilir.
- **Sesli asistan (`/voice`):**
  - Soruyu söylersiniz; konuşma şirketinizin modAI sunucusunda Whisper Small ile yazıya çevrilir. Ses kaydı şirket dışına çıkmaz, yazıya çevrildikten sonra saklanmaz ve loglanmaz. Telefonda ve düşük güçlü bilgisayarlarda da tarayıcı konuşma modeli indirmez.
  - Anlaşılan soru göndermeden önce gösterilir ve düzeltilebilir. İsteyen kullanıcı tanımayı tamamen tarayıcıda yaptırabilir (Whisper Tiny/Base); o zaman ses cihazdan hiç çıkmaz.
  - Yanıt Türkçe nöral sesle okunur, kaynakları gösterilir. Soru bir talebe uyuyorsa (ör. izin) yanıtın altında talebi başlatma önerisi çıkar.
  - Görüşmeler saklanır ve sayfaya dönüldüğünde geri yüklenir.
- **Çok dilli arama:** Türkçe bir soru İngilizce belgede de doğru kaynağı bulur (BGE-M3 profili).
- **Sayısal tablolar:** "40.000 TL'lik alımı kim onaylar" gibi sorularda sayı, tablodaki doğru satırla eşleştirilir. Değer iki satırın sınırındaysa sistem tahmin etmez, bunu söyler.
- **Belge yoksa uydurmaz:** seçili kaynaklarda belge bulunamazsa model çağrılmaz; "belge bulunamadı" denir.
- **Kurumsal yapı:** Organization → Workspace → Knowledge Base hiyerarşisi, rol tabanlı erişim, davetle kullanıcı ekleme, denetim kaydı.
- **Belgeler güncel kalır:** her belgenin bir sahibi ve gözden geçirme tarihi vardır. Tarihi geçmiş belgeye dayanan yanıtta uyarı çıkar. Eski sürümler silinmeden arşivlenir ve yanıtlara girmez. Yüzlerce belge klasörden ya da komut satırından toplu aktarılır.
- **Kalite ölçülür:** kabul soruları Kalite panelinde durur ve kullanıcıların kullandığı arama ve modelle yeniden sorulur; istenirse her gece. Yanıtlanamayan sorular raporu belgelerde eksik olan bilgiyi gösterir.
- **Taranmış belge, ses ve video:** taranmış PDF ve görseller metin tanımayla okunur; şirket videoları ve toplantı kayıtları dakika dakika yazıya dökülür. Yanıtın kaynağı söylendiği dakikayı gösterir.
- **İçeriğe göre yerleştirme ve tek komutla kurulum:** yüklenen belgeler içeriklerine göre doğru departmanın bilgi tabanına yerleşir; kurulum `sh scripts/install.sh` ile tek komuttur.
- **Uzman onaylı yanıtlar ve eksik bilgi konuları:** bir uzmanın onayladığı yanıt aynı soruda modelsiz ve anında verilir, benzer sorularda önerilir; belge değişince ya da süresi dolunca kendiliğinden düşer. Yanıtlanamayan sorular konulara kümelenir, hangi belgenin eksik olduğu görünür.
- **Yanıt izi ve güvenlik:** her yanıtın hangi belge sürümlerine dayandığı kaydedilir. Belgelerdeki gizli talimatlar modele gitmeden ayıklanır ve 9 istem enjeksiyonu senaryosu her Kalite çalıştırmasında yeniden sınanır.
- **Model seçimi kalite kapısıyla:** yönetici makinedeki yerel modeller (Gemma 3/4, Qwen 3.5 ve WATAM uyarlamaları) arasından seçer. Model, kullanıcılara açılmadan önce aynı Kalite ve güvenlik testlerinden geçmek zorundadır. Her modelin lisansı listede görünür; güvenlik eğitimi kaldırılmış varyantlar işaretlenir. Sözleşmenin [model eki](sozlesme-model-eki.md) bütün modelleri kapsar.
- **Güven raporu (PDF):** kurulum, erişim, saklama, Kalite, güvenlik testleri, kapasite ve kullanım tek raporda toplanır; satın alma ve denetim için kanıttır.
- **Kurumsal kimlik:** Microsoft Entra ID, Okta, Google Workspace ya da Keycloak ile şirket hesabıyla giriş (OpenID Connect) ya da doğrudan Active Directory (LDAP) kullanıcı adı ve şifresiyle giriş. Dizin gruplarından çalışma alanı rolleri verilir. SCIM 2.0 ile hesaplar kendiliğinden açılır ve kapatılır: işten ayrılan kişi dizinde kapatılınca modAI'ye de giremez. Hepsi isteğe bağlıdır; kapalıyken parola ile giriş tamamen yerel çalışır.
- **Onaylı iş akışları (Talepler):** modAI işi de başlatır ve yürütür. Örnek akış:
  - Çalışan sohbette "3 gün izin almak istiyorum" yazar. modAI izin talebini önerir ve formu cümleden doldurur.
  - Onaycı talebi görür: talepten hesaplanan sayılar (ör. "başvuru ile başlangıç arasında 4 iş günü") politikanın kendi cümlesinin yanında durur. Kararı onaycı verir.
  - İzindeki yönetici vekâlet verir; bekleyen adımlar için hatırlatma gider. Talepler CSV raporu olarak indirilir.
  - Son onaydan sonra talep imzalı bir webhook'la İK, ERP ya da talep sistemine iletilir; Teams/Slack kanalına haber verilir.

  Dört göz ilkesi uygulanır ve her adım denetim günlüğüne yazılır. İzin, satın alma, masraf ve BT erişimi için şablonlar hazırdır.
- **Bağlı kaynaklar ve belge izinleri:** dosya sunucusundaki bir klasör ya da bir SharePoint kitaplığı bilgi tabanıyla eşit kalır: yeni dosya eklenir, değişen yeni sürüm olur, silinen arşivlenir. Klasör kuralları ve SharePoint paylaşımları belgeye taşınır: kısıtlı bir belgeyi aramada yalnızca okuyucuları bulur.
- **modAI Kutusu:** kurulu gelen cihaz. Prize ve ağa takılır, tarayıcıda etiketteki kurulum koduyla açılır. Bekçi, takılan servisi yeniden başlatır ve disk dolmadan uyarır. Ayrıntı: [modai-kutusu.md](modai-kutusu.md).
- **Toplantı tutanakları ve metinden belge:** ses ya da video kaydından tutanak taslağı çıkarılır. YouTube dökümü ya da yapıştırılan metin belgeye çevrilir.
- **Kur ve unut:** gece yedeği kendiliğinden alınır ve diski doldurmayacak şekilde seyreltilir. Disk azalınca yönetici uyarılır. Kapasite kartı ne zaman donanım büyütmek gerektiğini söyler. Destek için maskeli tek bir dosya üretilir.
- **Çevrimdışı kurulum paketi:** her sürüm imajları, modelleri ve sağlama özetleriyle tek klasör olarak teslim edilir. Kurulum ve güncelleme internetsiz yapılır ve tek komutla geri alınır.
- **KVKK araçları:** kişisel veri dökümü, görüşme ve hesap silme yönetim panelindedir. Görüşmelerin saklama süresi ayarlanır; denetim kaydındaki IP adresleri ve yedekler 6 ay sonra silinir. Ürünle bir [veri envanteri](../guides/kvkk-veri-envanteri.md) gelir.

## Neden yerel

- Belge ve soru içeriği varsayılan olarak bir bulut LLM servisine gönderilmez. Dil modeli (Ollama), arama ve veritabanı müşterinin makinesinde çalışır.
- Konuşma tanıma modAI sunucusunda, ses sentezi tarayıcıda çalışır; modeller uygulamanın kendi adresinden yüklenir. Üçüncü taraf çıkarım servisi kullanılmaz.
- Bu bir güvenlik ya da uyumluluk sertifikası iddiası değildir. TLS, yedekleme ve erişim kuralları kurulumda müşteriyle birlikte belirlenir.

## Ölçülen sonuçlar

Ölçümler kurgusal demo belgeleriyle staging ortamında, Apple M1 Pro 16 GB üzerinde yapıldı.

| | Sonuç |
|---|---|
| 9 kabul sorusu × 2 koşu, çok dilli arama (BGE-M3) | 18/18 doğru yanıt; kendinden emin yanlış yanıt yok |
| Aynı sorular, varsayılan model (MiniLM) | 11/18 doğru; 3 kendinden emin yanlış yanıt (2'si yanlış sayı) |
| Model ılıkken ilk token (sunucu) | medyan 3,5–3,9 sn; makine bellek baskısındayken daha uzun |
| Kısa bir belgenin yüklendikten sonra aranabilir olması | yaklaşık 20 sn; bellek baskısında 2 dakikaya kadar |
| 25 soruluk demo kabul seti (Kalite paneli, bölüm bazlı arama) | 23/25; eski politika sürümleri arşivlendiğinde 25/25. Soru başına medyan 4,1 sn |

Üretim kurulumunda (Apple M1 Pro 16 GB, gemma3:4b) ölçülenler:

| | Sonuç |
|---|---|
| 25 soruluk Kalite seti | 24/25; güvenlik testleri 8/9; soru başına medyan 3,5 sn |
| Aynı anda soru soranlar (yük testi) | 4 kişide yanıtların %95'i 9,8 sn içinde, 8 kişide 16,4 sn; 16 kişide de hata yok. Yaklaşık 250 çalışana kadar rahat ([kapasite ve donanım](../guides/kapasite-ve-donanim.md)) |
| Şirket hesabıyla giriş | Gerçek bir OpenID Connect sağlayıcısıyla uçtan uca 13/13 kontrol |
| Temiz kurulum | Tek komutla 8/8 adım; güncelleme 64 sn kesintiyle |

Bu sonuçlar müşterinin kendi belgeleriyle aynı başarıyı garanti etmez. Pilotta müşterinin belgeleri ve soruları ile kabul testi yapılır.

## Gereksinimler

- macOS (Apple Silicon) ya da Linux; Docker ve Ollama.
- En az 16 GB bellek (bu durumda yalnızca bu sistem çalışmalı); 250'den fazla çalışan için 32 GB.
- 40 GB boş disk (kurulum paketi yaklaşık 9 GB).
- Kurulum paketi işlemci mimarisine özeldir: Apple silicon ve ARM için `arm64`, x86_64 sunucular için `amd64` paketi.
- Masaüstü Chrome ya da Edge; ağdan sesli kullanım için HTTPS.

## Pilot

[Ticari lisanslama](../../COMMERCIAL_LICENSING.md)'daki **Pilot** paketi 2–4 haftalık, seçili belgelerle sınırlı bir değerlendirmedir. Pilotta şunlar yapılır:

1. Çevrimdışı kurulum paketiyle kurulum ve ön kontrol (`scripts/preflight.py`); ağdan kullanım için HTTPS. Müşterinin makinesinde yük testi (`app.tools.load_test`).
2. Müşteri belgelerinin aktarılması, sahiplerinin ve gözden geçirme tarihlerinin belirlenmesi, çok dilli aramanın panelden etkinleştirilmesi.
3. Müşteriyle birlikte hazırlanan 10 soruluk kabul testi Kalite panelinde; sonuçlar yazılı teslim edilir ve sorular gerilemeleri yakalamak için panelde kalır.
4. Saklama sürelerinin müşterinin politikasına göre ayarlanması ([veri envanteri](../guides/kvkk-veri-envanteri.md)).
5. Kullanıcı eğitimi ([kurumsal kullanım kılavuzu](../guides/kurumsal-kullanim-kilavuzu.md)). Sonraki sürümler yeni paketle ve `scripts/upgrade_local.sh` ile, geri alınabilir şekilde kurulur.
6. Teslim: Güven raporu (PDF), Kalite sonuçları ve [teslim ve kabul formu](teslim-ve-kabul.md). Destek koşulları [destek ve güncelleme politikasında](../guides/destek-ve-guncelleme-politikasi.md).

## Bilinen sınırlamalar

- Model zaman zaman yanlış satırı ya da belgeyi seçebilir; önemli kararlardan önce kaynak kontrol edilmelidir.
- Eski ve güncel politika birlikte yanıtlara açık kalırsa sistem hangisinin geçerli olduğunu bilemez; eski sürüm arşivlenmelidir.
- PDF ya da birleşik hücreli tablolar ve hesaplama soruları desteklenmez.
- Taranmış belgelerin metin tanıması ve ses ya da videonun otomatik dökümü hatasız değildir; önemli yanıtlar kaynak sayfadan ya da dakikadan doğrulanmalıdır.
- Ağ klasörü ve SharePoint eşitlemesi ürünle gelir. Google Drive, Confluence gibi diğer kaynaklar ise ürünle gelmez; bunlardaki belgeler yükleme ya da klasör aktarımıyla eklenir. Gerekirse ayrı proje olarak kapsamlanır. SAML de ürünle gelmez; şirket hesabıyla giriş OpenID Connect ya da LDAP ile yapılır.
- Otomatik devralma (iki sunucu arasında anında geçiş) yoktur. Sıcak bekleme vardır: yedek sunucu her gece kendini ana sunucunun yedeğiyle günceller ve arızada dakikalar içinde devralır. Yedeklerin geri yüklenebildiği `restore_drill.sh` ile düzenli olarak kanıtlanır.
- Bağımsız sızma testi henüz yapılmadı (planlanıyor); her sürümde otomatik yetki taraması, bağımlılık taraması ve SBOM vardır. Güvenlik önlemleri ve eksikler: [güvenlik mimarisi](../guides/guvenlik-mimarisi.md).
- Ses tanıma gürültüde ve özel adlarda yanılabilir; soru göndermeden önce ekranda gösterilir ve düzeltilebilir.
- Çok dilli arama tek kurulum, tek şirket için tasarlandı. Sistem sayfasındaki Arama profili panelinden hazırlanır, etkinleştirilir ve tek adımda geri alınır.
