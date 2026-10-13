# modAI-stack Kurumsal Kullanım Kılavuzu

Bu kılavuz şirket yöneticileri, ekip yöneticileri ve çalışanlar içindir. Ekran adları mevcut Web Console ile eşleşir.

## modAI-stack nedir?

modAI-stack, şirket belgeleri üzerinde yerel yapay zekâ ile soru-cevap yapmanızı sağlar. Belgeler bilgi tabanlarına yüklenir, indekslenir ve RAG Chat yanıtlarında kaynak kartlarıyla gösterilir. Yanıtları önemli kararlardan önce kaynak belgelerle karşılaştırın.

## Giriş ve bilgi hiyerarşisi

Kurulumda şirket hesabıyla giriş (SSO) açıksa giriş sayfasında "Microsoft ile giriş" gibi bir düğme görünür; çalışanlar ayrı parola olmadan şirket hesabıyla girer. Davet edilen çalışan bu düğmeyle girdiğinde davet kendiliğinden kabul edilir.

Size verilen hesapla giriş yapın. Sol üstte erişebildiğiniz **Workspace**'i seçin. Hiyerarşi şöyledir:

**Organization → Workspace → Knowledge Base → Belge**

Organization şirket sınırıdır. Workspace ekip/çalışma alanıdır. Knowledge Base aynı konuya ait belgeleri toplar. Yalnızca üyeliğinizin kapsadığı alanları görür ve sorgularsınız.

## Roller

| Rol | Yetki |
| --- | --- |
| Platform Admin | Platform kullanıcılarını ve Organization yapılandırmasını yönetir; tenant belgelerine otomatik erişmez. |
| Organization Admin | Kendi Organization'ındaki üyelikleri ve çalışma alanlarını yönetir; kapsamındaki belgeleri kullanabilir. |
| Manager | Yetkili Workspace'te Knowledge Base ve belgeleri yönetir, kalite sorularını çalıştırır, RAG kullanır. |
| User | Yetkili Knowledge Base'leri okur ve RAG kullanır; yönetim/yükleme yapmaz. |

## İlk kurulum

1. Platform yöneticisi **Yönetim → Organization'lar** ekranından şirket Organization'ını oluşturur.
2. **Yönetim → Üyelikler** ekranında ilgili Organization'ı seçip **Kendimi Organization Admin yap** düğmesine basar. Bu açık işlem platform rolünü değiştirmez; yalnızca seçili Organization için tenant üyeliği oluşturur veya mevcut Organization üyeliğini yükseltir.
3. **Yönetim → Workspaceler** ekranında Workspace oluşturur. Üyelik güncellenince sol üst Workspace listesi yeniden yüklenir; çıkış/giriş gerekmez.
4. **Knowledge Base'ler → Yeni Knowledge Base** ile ilk bilgi tabanını oluşturur.
5. **Belgeler** veya Knowledge Base ayrıntısından belgeleri yükler: PDF, DOCX, TXT, Markdown, taranmış görseller (PNG, JPG, TIFF) ve ses ya da video kayıtları (MP3, M4A, WAV, OGG, FLAC, MP4, MOV, M4V, WEBM, MKV).

## Taranmış belgeler, ses ve video

- **Taranmış PDF ve görseller:** metin katmanı olmayan sayfalar OCR ile (Türkçe ve İngilizce) okunur. Metni olan sayfalar olduğu gibi kalır. OCR sayfa başına birkaç saniye sürer; belge bu sırada **İşleniyor** durumundadır.
- **Ses ve video:** kayıt otomatik olarak yazıya dökülür. Ortaya çıkan belge kaydın adıyla başlar ve dakika dakika bölümlere ayrılır ("## 03:00"); bir yanıtın kaynak kartı, söylendiği dakikayı gösterir. Yazıya dökme kaydın uzunluğuna göre birkaç dakika sürebilir. Tek kayıt en çok 200 MB ve 120 dakika olabilir (`MEDIA_MAX_UPLOAD_BYTES`, `TRANSCRIPTION_MAX_MINUTES`). Belgeler en çok 10 MB'tır.
- **Şirketin YouTube videoları:** kanal sahibi videoyu YouTube Studio'dan indirir (İçerik → videonun Seçenekler menüsü → İndir) ve MP4 olarak yükler. Birçok video için klasör yükleme ya da toplu aktarım aracı kullanılır. Videoların bağlantıdan doğrudan indirilmesi bilinçli olarak yoktur: YouTube'un kullanım koşulları buna izin vermez ve bu tür indiriciler YouTube her değiştiğinde bozulur.
- **YouTube videosundan belge (indirmeden):** Belgeler sayfasında **Metinden belge oluştur → YouTube dökümü / özeti**. YouTube'da videonun açıklamasında **Transkripti göster**'e basın, paneldeki metni zaman damgalarıyla kopyalayıp **Döküm** alanına yapıştırın; videonun yapay zekâ özeti varsa **Özet** alanına ekleyin. Başlığı ve video bağlantısını yazın. Zaman damgaları ve "Videoda ara" gibi arayüz satırları temizlenir, metin dakika dakika bölümlere ayrılır ve her bölüm videonun o anına bağlantı alır. **Düz metin** seçeneği herhangi bir metni (e-posta, toplantı notu) belge yapar.
- **İçeriğe göre bilgi tabanını seç:** yükleme alanlarındaki bu seçenekle her belge, açıklaması içeriğine en çok uyan bilgi tabanına yerleşir. Emin olunamayan belgeler seçili bilgi tabanında kalır; yükleme sonunda hangi belgenin nereye gittiği yazılır. Çok dilli arama (BGE-M3) açık olmalı ve bilgi tabanlarının açıklaması yazılmış olmalıdır. Açıklamayı bilgi tabanı sayfasındaki **Açıklamayı düzenle** ile, konuları sayarak yazın (örneğin "Masraf, seyahat, satın alma ve onay limitleri"). Görseller ve kayıtlar yerleştirilmez.
- **Belgeyi aç:** kaynak kartında ve belgeler tablosunda orijinal dosyayı indirir. İndirme denetim kaydına yazılır.
- **Toplantı tutanağı:** belgeler tablosunda hazır bir belgenin satırındaki **Tutanak çıkar** (manager ve admin). Kayıttan ya da notlardan kararlar, aksiyonlar (sorumlu ve tarihle), konuşulan konular, açık sorular ve dakika dakika akış çıkarılır; her madde söylendiği dakikayı, YouTube dökümünde videonun o anına bağlantıyı gösterir. Taslak sunucudaki dil modeliyle bölüm bölüm hazırlanır (bir saatlik kayıtta birkaç dakika) ve kalite çalıştırmalarıyla aynı sırayı kullanır. Taslağı kontrol edip düzeltin; **Bilgi tabanına kaydet** onu "… - Tutanak" adlı bir belge yapar, **İndir** Markdown dosyası verir. Kaydedilmeyen taslak 24 saat sonra silinir. Model yalnızca açıkça söyleneni almaya çalışır ama yanılabilir: sorumlu ve tarihleri mutlaka okuyun.
- **Yanıtlarda kullanım:** manager ve admin, belgeler tablosunun **Yanıtlarda (30 gün)** sütununda her belgenin son 30 günde kaç yanıtta kaynak olduğunu görür; sayıya basınca son yanıtların tarihi, kullanılan belge sürümü ve sonucu listelenir (soru ve yanıt metni saklanmaz, soranın kim olduğu gösterilmez). Tablonun üstünde hiç kullanılmayan belge sayısı yazar: bunlar ya eskidir (arşivleyin) ya da bulunamıyordur (başlıkları ve bilgi tabanı açıklamasını gözden geçirin).
- Otomatik döküm ve OCR hatasız değildir. Önemli bir yanıtı kaynak kartındaki dakikadan ya da sayfadan doğrulayın; gerekirse kaydın düzeltilmiş metnini TXT olarak yükleyin.
6. Belge **Hazır** olunca **RAG Chat**'te Knowledge Base'i seçip soru sorar.

Dashboard'daki **Kurumsal alanınızı hazırlayın** kartı eksik adımları gerçek erişim ve belge durumuna göre gösterir.

## Belge indeks durumu

- **Kuyrukta (queued):** Yükleme kabul edildi, işçi bekleniyor.
- **İşleniyor (processing):** Metin çıkarma, parçalama, embedding ve vektör indeksleme sürüyor.
- **Hazır (ready):** Belge RAG sorgularında kullanılabilir.
- **Hatalı (failed):** Yönetici hata ayrıntısını inceler ve uygun ise yeniden indeksler.

Hazır olmayan bir belgeden yanıt beklemeyin.

## Yeni sürüm mü, eski sürüm arşivi mi?

Bir politikanın güncel hâli geldiğinde iki yol vardır:

- **Belgeyi değiştir (tercih edilen):** Güncel dosyayı aynı belgenin yeni sürümü olarak yükleyin. Belge kaydı ve sürüm geçmişi korunur; yeni sürüm **Hazır** olunca yanıtlar yalnızca yeni sürümden gelir. Aynı belgenin güncellenmiş hâli için her zaman bu yolu kullanın.
- **Eski sürüm olarak arşivle:** Eski sürüm ayrı bir belge olarak yüklenmişse (örneğin destek talimatlarının v2 ve v3 dosyaları yan yana duruyorsa) eski belgeyi arşivleyin. Arşivlenen belge silinmez, listede **Arşivde** etiketiyle görünmeye devam eder, ancak artık yanıtlarda kaynak olarak kullanılmaz. Gerekirse **Arşivden çıkar** ile hemen geri alınır; yeniden indeksleme gerekmez.

Arşivleme yalnızca manager/admin rolüyle yapılır ve denetim kaydına işlenir. Belgeyi tamamen kaldırmak için **Sil**'i kullanın; silinen belge listeden de kalkar.

## Belge sahibi ve gözden geçirme

Şirket politikalarının sessizce eskimemesi için her belgenin bir **sahibi** ve bir **gözden geçirme tarihi** vardır. Belgeler tablosunda **Sahibi** ve **Gözden geçirme** sütunlarında görünürler. Tarihin yanındaki etiket durumu söyler: **Süresi geçti** (tarih geçti), **Yaklaşıyor** (30 gün ya da daha az kaldı) veya **Tarih yok**. Tarihler takvim günüdür ve UTC tarihiyle karşılaştırılır; belge, tarihinden sonraki gün süresi geçmiş sayılır.

- **Yeni yükleme:** Belgeyi yükleyen kişi sahibi olur. Gözden geçirme tarihi bugünden 12 ay sonrasıdır (sunucudaki `DOCUMENT_REVIEW_DEFAULT_MONTHS`; `0` ise tarih verilmez). Toplu aktarım aracı da aynısını yapar.
- **Belgeyi değiştir:** Yeni sürüm yüklemek gözden geçirme sayılır; tarih bugünden itibaren yeniden 12 ay ileri alınır.
- **Gözden geçirildi:** Belgeyi okuyup hâlâ geçerli olduğunu doğrulayan yönetici satırdaki bu işlemi kullanır. Kim ve ne zaman kaydedilir, sonraki tarih bugünden itibaren ileri alınır.
- **Sahip ve tarih:** Sahibi Workspace üyeleri arasından seçer, tarihi elle değiştirir ya da kaldırır. Sahip, belgenin Workspace'ine erişimi olan biri olmalıdır.

Belgeler sayfasının üstündeki **Tümü / Süresi geçenler / Yaklaşanlar / Tarihsiz** filtresi listeyi daraltır; Knowledge Base seçiminde **Tüm Knowledge Base'ler** Workspace'in bütün belgelerini gösterir. **Genel Bakış**, manager ve admin'lere "Gözden geçirme bekleyen 3 belge" gibi bir satır gösterir; satır süresi geçmiş belgelerin listesine götürür. Arşivdeki belgeler yanıtlarda kullanılmadığı için bu listelerde ve sayılarda yer almaz.

Süresi geçmiş bir belge yanıtlarda **kullanılmaya devam eder**; arama değişmez. Yanıt böyle bir belgeye dayanıyorsa kaynak kartında "Gözden geçirme tarihi geçmiş (dd.MM.yyyy)" uyarısı görünür; içeriği belgenin sahibine doğrulatın. Mevcut belgelerin sahibi onları yükleyen kişidir ve tarihleri boştur (**Tarih yok**); tarihleri bu sayfadan ya da **Gözden geçirildi** ile verin.

Sahip, tarih ve gözden geçirme işlemleri manager/admin rolü gerektirir ve denetim kaydına yalnızca kimlik numaraları ve tarihlerle yazılır. Belge sahibinin e-posta adresini yalnızca o Workspace'in manager ve admin'leri görür; user rolündekiler tabloda **Sahibi** sütununu görmez, API de onlara sahibi göndermez.

## RAG Chat ve kaynak kartları

Chat yalnızca seçilen Workspace'teki yetkili Knowledge Base'leri sunar. Birden çok kaynak seçebilirsiniz. Bilgi tabanı ayrıntısındaki **Bu kaynaklarla chat** bağlantısı o bilgi tabanını önceden seçer. Yanıt altında kaynak kartları belge adını, ilgili parça numarasını, skoru ve açılabilir alıntıyı gösterir. Kaynak görünmüyorsa cevabın belgeye dayandığını varsaymayın.

**Yanıtı değerlendirme:** RAG Chat'te ve sesli asistanda her yanıtın altında "Yanıt işinize yaradı mı?" ve 👍 / 👎 vardır. 👎'ye basan çalışan bir neden seçer (Yanlış bilgi, Eksik yanıt, Yanlış kaynak, Güncel değil, Diğer) ve isteğe bağlı olarak doğrusunu yazar. Soru, yanıt ve kaynak adları yöneticilere iletilir; kimin işaretlediği kaydedilmez.

**Örnek sorular:** Henüz soru sorulmamışken sayfada "Örnek sorular" görünebilir. Bunlar Kalite sayfasındaki, son çalıştırmada geçen ve kullanıcının erişebildiği bilgi tabanlarındaki sorulardır. Birine basınca soru alana yazılır ve bilgi tabanları seçilir. Kalite sorusu yoksa ya da hiçbiri geçmediyse bölüm görünmez.

## Sesli asistan

**Sesli Asistan** (`/voice`) RAG Chat'in konuşan hâlidir: soruyu Türkçe söylersiniz, yanıt aynı yetkili Knowledge Base'lerden üretilir, kaynaklarıyla gösterilir ve Türkçe sesle okunur.

- **Konuşmak:** mikrofon düğmesini basılı tutup konuşun ve bırakın ya da bir kez dokunup konuşun, bitince tekrar dokunun. Bir soru en çok 30 saniyedir. **Göndermeden önce soruyu göster** açıkken (varsayılan) anlaşılan soru önce kutuda gösterilir; yanlış duyulan kelimeyi düzeltip **Gönder**'e basın. Gönderilen bir soruyu sonradan **Düzelt** ile değiştirip yeniden sorabilirsiniz.
- **Konuşma tanıma:** varsayılan seçenek "Sunucu · Whisper Small (önerilen)"dır. Ses kaydı şirketinizin modAI sunucusunda yazıya çevrilir; saklanmaz, kaydedilmez ve loglanmaz. "Cihazda" seçenekleri (Whisper Tiny, Whisper Base) tanımayı tarayıcıda yapar: ses kaydı cihazdan hiç çıkmaz, ama Türkçe doğruluk daha düşüktür ve ilk kullanımda model indirilir. Sunucu tanıması kurulu değilse ya da sunucuya ulaşılamazsa sayfa bunu söyler ve **Cihazda tanımaya geç** düğmesini gösterir. Seçiminiz bu tarayıcıda hatırlanır; sayfanın altındaki gizlilik notu seçili seçeneğe göre değişir.
- **İlk kullanım:** **Ses modelini hazırla**'ya basın. Türkçe ses modeli (yaklaşık 63 MB) bir kez indirilir ve tarayıcıda saklanır. Ses modeli başlatılamazsa tarayıcının Türkçe sistem sesi "Sistem sesi (yedek)" etiketiyle kullanılır.
- **Yanıt:** okuma hızı 1,00×–1,15× arasında seçilir; hoparlör düğmesi sesli yanıtı kapatır. **Durdur** sesi ve yanıtı keser. "Yanıt dili" Türkçe'dir; "Soru diline göre" seçilirse konuşulan dil de otomatik algılanır. Soru bir talep türüne uyuyorsa (örneğin izin) yanıtın altında RAG Chat'teki gibi **… başlat** önerisi çıkar.
- **Görüşmeler:** sesli sorular ve tamamlanan yanıtlar görüşme olarak kaydedilir ve sayfaya dönüldüğünde geri gelir; ses kaydı kaydedilmez. **Yeni görüşme**, **Bu görüşmeyi sil** ve **Tüm görüşmelerimi sil** görüşme seçicinin yanındadır. Selamlaşmalar ve durdurulan yanıtlar kaydedilmez.
- **Tarayıcı:** masaüstü Chrome ya da Edge önerilir. Mikrofon yalnızca HTTPS bağlantıda (ya da aynı bilgisayarda `localhost` ile) açılır.

## Yanıtlanamayan sorular

**Yönetim → Yanıtlanamayan sorular** sayfası, çalışanların sorduğu ama modAI'ın seçili bilgi tabanlarındaki belgelerden yanıtlayamadığı soruları gösterir. Sayfayı yalnızca o Workspace'te manager veya admin rolü olanlar görür. Amaç eksik belgeyi bulmaktır: İK bilgi tabanında "Babalık izni kaç gün?" sık soruluyorsa izin politikasına bu bilgi eklenmeli ya da ilgili belge yüklenmelidir.

Üstteki satır seçili dönemin özetidir, örneğin "Son 30 günde 412 soru, 23'ü yanıtlanamadı (%5,6)". Dönemi (7, 30 ya da 90 gün), bilgi tabanını ve nedeni seçerek listeyi daraltabilirsiniz; özet satırı her zaman dönemin tamamını gösterir. Aynı soru farklı yazılsa da (büyük/küçük harf, İ/ı, noktalama, boşluk) tek satırda toplanır. Tabloda sorunun en son yazılış biçimi, kaç kez sorulduğu, son soruluş zamanı, nedeni ve aranan bilgi tabanları görünür. Sesli Asistan'a sorulan sorular da konuşmanın yazıya dökülmüş hâliyle sayılır.

Nedenler:

- **Belge bulunamadı:** Seçili bilgi tabanlarında soruyla ilgili hiçbir belge parçası bulunamadı. Çoğunlukla belge eksiktir ya da soru yanlış bilgi tabanında sorulmuştur.
- **Tablo sınırında / çelişkili:** Sorulan değer bir tablo satırının tam sınırında (örneğin "kıdemim tam 5 yıl") ya da iki tablo birbiriyle çelişiyor. Tabloyu netleştirin.
- **Belgede yanıt yok (tahmini):** Belgeler bulundu ama model, yanıtın belgelerde olmadığını söyledi. Bu, yanıtın ifadesinden çıkarıldığı için tahminidir.

Eksik bilgiyi ekledikten sonra satırdaki **Çözüldü** ile soruyu listeden kaldırın. Soru yeniden sorulur ve yine yanıtlanamazsa listeye döner; Çözüldü işaretlemek oranı değiştirmez. **CSV indir**, filtreye uyan tüm soruları Excel'de Türkçe karakterleriyle açılacak biçimde indirir (UTF-8, noktalı virgülle ayrılmış, saatler UTC). **Tümünü sil** yalnızca admin rolüne açıktır ve Workspace adının yazılmasını ister. Çözüldü ve Tümünü sil işlemleri denetim kaydına soru metni olmadan, yalnızca silinen kayıt sayısıyla yazılır.

**Gizlilik:** Soruyu kimin sorduğu kaydedilmez. Yanıtlanan sorular saklanmaz; onlar için yalnızca günlük soru sayısı tutulur. Yanıtlanamayan bir sorunun yalnızca metni (en fazla 2.000 karakter), aranan bilgi tabanları ve nedeni saklanır; modAI'ın yanıtı ve kaynaklar saklanmaz. Kayıtlar ve günlük sayılar `UNANSWERED_RETENTION_DAYS` gün (varsayılan 90) sonra silinir. Çalışanlar soru metnine kişisel bilgi yazabilir; aydınlatma metninizde bu raporu belirtin.

### Yanlış bulunan yanıtlar

Aynı sayfanın altında çalışanların 👎 ile işaretlediği yanıtlar listelenir: neden, çalışanın notu, soru, yanıt, kaynak adları ve bilgi tabanları. Üstte dönemin 👍 ve 👎 sayıları görünür. Belgeyi düzelttikten sonra **Çözüldü** ile kaydı kaldırın ya da **Kalite sorusu yap** ile soruyu Kalite sayfasına ekleyin. Kalite sorusu "Yanıt vermeli" beklentisiyle ve ifade olmadan eklenir; beklenen ifadeleri Kalite sayfasında siz yazarsınız. Böylece aynı soru her çalıştırmada yeniden sorulur. Kayıtlar yanıtlanamayan sorularla aynı süre (`UNANSWERED_RETENTION_DAYS`) tutulur.

**Genel Bakış**'ta manager ve admin'ler son 30 günün kullanım özetini görür: soru sayısı, belgelerden yanıtlanma oranı, yanıtlanamayan soru sayısı ve 👍 / 👎 sayıları, günlük soru grafiğiyle. **CSV indir (90 gün)** aynı bilgiyi gün gün Excel'e verir; aylık yönetim raporu için kullanılır.

Rapor varsayılan olarak açıktır. Kapatmak için sunucudaki `.env` dosyasında `UNANSWERED_REPORT_ENABLED=false` yapın ve `docker compose up -d api` ile API'yi yeniden başlatın; kapalıyken hiçbir soru ve sayı kaydedilmez, önceden kaydedilenler saklama süresi dolunca silinir ya da admin tarafından **Tümünü sil** ile hemen silinebilir.

## Uzman onaylı yanıtlar

Bir yanıtın doğruluğu bir uzman tarafından onaylanabilir. Manager ve admin, RAG Chat'te bir yanıtın altındaki **Uzman olarak onayla** ile yanıtı (gerekirse düzelterek) onaylar; yanıtın kaynak belgeleri ve sürümleri kaydedilir. Sonra:
- Aynı soru (büyük/küçük harf ve noktalama farkı önemsizdir) aynı bilgi tabanlarında sorulduğunda onaylı yanıt **modele sorulmadan** verilir ve "Uzman onaylı yanıt" etiketiyle gösterilir.
- Benzer bir soruda model yanıt verir; altında "Benzer bir soru için uzman onaylı yanıt var" kartı çıkar.
- Onay **kendiliğinden düşer**: geçerlilik tarihi (varsayılan 6 ay) geçince ya da kaynak belgenin yeni sürümü yüklenince, belge arşivlenince veya silinince. **Yönetim → Onaylı yanıtlar**'da **Yeniden onayla** ya da **Düzenle** ile yenilenir.
- Onaylı yanıt yalnızca onun bilgi tabanlarında arama yetkisi olanlara verilir.

**Uzmana yönlendirme:** yanıtlanamayan sorular raporunda bir sorunun yanındaki **Uzmana ata** ile soru çalışma alanının bir üyesine (örneğin İK uzmanına) atanır. Uzman kenar çubuğunda **Atanan sorular** bağlantısını görür, yanıtı yazar; yanıt onun adıyla onaylanır ve aynı soruyu soranlara verilir.

## Talepler: onaylı iş akışları

modAI yanıt vermenin ötesinde işi de başlatır: izin, satın alma, masraf ve BT erişim talepleri formla hazırlanır, ilgili politikayla birlikte sırayla onaycılara gider ve son onaydan sonra ilgili sisteme iletilir.

**Çalışan:**
1. Sohbette işi yazın, örneğin "20 Ekim'den itibaren 3 gün izin almak istiyorum". Sorunuz bir talep türüne uyuyorsa yanıtın altında **İzin talebi başlat** çıkar. Menüden **Talepler → Yeni talep** de seçebilirsiniz.
2. Form açılır. **Formu doldur**'a basınca yerel model cümlenizdeki bilgileri alanlara yazar; cümlede olmayan bir şeyi uydurmaz. Alanları kontrol edin, eksikleri tamamlayın.
3. **Onaya gönder**'e basın. Talebin hangi adımda beklediğini, kimin onayladığını ve onaydan sonra ne olduğunu **Talepler → Taleplerim** altında görürsünüz. Onay beklerken talebi geri çekebilirsiniz.

**Onaycı:**
- Onayınızı bekleyen talep sayısı menüde **Talepler (2 onay bekliyor)** diye görünür.
- Talep sayfasında **Talep ve politika yan yana** bölümünde iki şey görürsünüz:
  - talepten hesaplanan sayılar, örneğin "başvuru ile başlangıç arasında 4 iş günü var" ya da "Başlangıç–Bitiş arası: 11 iş günü";
  - politikanın bu konudaki kendi cümleleri, kelimesi kelimesine. Örneğin "3 iş günü ve daha uzun izinler için başvuru en az 10 iş günü önce yapılır."

  Hesap kodla yapılır; hafta sonları sayılmaz, resmî tatiller hesaba katılmaz. Politikanın ilgili bölümlerinin tamamı da açılabilir. Karar sizindir.
- **Onayla** ya da **Reddet** (reddederken açıklama zorunlu) ile karar verirsiniz.
- Kendi talebinizi onaylayamazsınız. Bir talebin bir adımını onaylayan kişi sonraki adımını onaylayamaz (dört göz ilkesi).
- Her karar denetim günlüğüne yazılır.
- **Vekâlet:** izne çıkarken **Talepler** sayfasının altındaki **Vekâlet** bölümünde meslektaşınızın e-postasını ve bitiş tarihini yazın. O tarihe kadar sizin onaylayacağınız adımları o onaylar; kayıtta "sizin adınıza, vekâletle" yazar.
- **Hatırlatma:** bir adım belirlenen süreden (varsayılan 24 saat) uzun beklerse talep türünün Teams/Slack kanalına hatırlatma gider.
- **Rapor:** organization yöneticisi **Talepler → Rapor (CSV)** ile bütün talepleri Excel'de açılan bir dosya olarak indirir.

**Yönetici (organization yöneticisi):** **Yönetim → İş akışları** sayfasında şablondan (izin, satın alma, masraf, BT erişimi) talep türü eklenir. Sonra şunlar ayarlanır:
- form alanları;
- onay sırası: workspace rolü, belirli bir kişi ya da Active Directory/SSO grubu;
- onaycılara gösterilecek politika bilgi tabanları;
- sohbette talebi önerecek kelimeler;
- onaydan sonra çağrılacak webhook (İK, ERP ya da talep sistemi) ve Teams/Slack bildirimi.

Kurulum ayrıntıları: kurulum rehberi 8.10.

## Güven raporu

**Yönetim → Güven raporu** satın alma ve güvenlik değerlendirmesi için tek sayfalık bir özettir: kurulum ve veri yerleşimi, erişim denetimi, saklama süreleri, son Kalite çalıştırması ve eğilimi, güvenlik testleri, son 30 günün kullanımı ve denetim kaydı, sınırlamalar. **PDF olarak kaydet** tarayıcının yazdırma penceresini açar; hedef olarak "PDF olarak kaydet"i seçin. Rapor açıldığı anda sistemin kendi kayıtlarından üretilir, hiçbir şey saklanmaz; görüntüleme denetim kaydına yazılır.

Yanıtlanamayan sorular sayfasındaki **Konulara göre** görünümü aynı konudaki farklı soruları birlikte gösterir ve eksik belgenin hangi bilgi tabanına konacağını önerir (açıklaması konuya en çok uyan bilgi tabanı). Gruplama arama modeliyle yapılır ve yaklaşıktır.

## Kalite: yanıtların doğruluğunu ölçme

**Yönetim → Kalite** sayfası Workspace'in kabul sorularını tutar; manager ve admin rolü gerekir. Her soru için şunlar yazılır: hangi Knowledge Base'lerde aranacağı, yanıt mı yoksa "belgede yok" mu beklendiği, yanıtta geçmesi ve geçmemesi gereken ifadeler ve isteğe bağlı olarak beklenen kaynak belge.

**Şimdi çalıştır** bütün soruları kullanıcıların aldığı yanıt yoluyla sorar ve puanlar. Sonuç "18/20 soru geçti" gibi özetlenir ve son 10 çalıştırmanın eğilimi gösterilir. Geçmeyen her soru yanıtı, kaynakları ve nedeniyle listelenir: "Yanlış kaynak", "Beklenen ifade yok", "Yasak ifade var", "Gereksiz 'bilmiyorum'", "Belgede olmayanı yanıtladı", "Hata" ya da "Zaman aşımı".

Her çalıştırma sorulardan sonra **Güvenlik testleri**ni (istem enjeksiyonu) de çalıştırır: belgeye gizlenmiş "önceki talimatları yok say", sahte giriş bağlantısı, gizli görselle veri sızdırma, gizli talimatları açıklatma, tutarı değiştirtme ve uydurma baskısı gibi talimatlar içeren uydurma metinlerle aynı model sınanır. Model talimata uymamalı ve soruyu yine belgeden yanıtlamalıdır. Bu metinler hiçbir bilgi tabanına eklenmez. Görünmeyen yorumlar ve yapay zekâya hitap eden cümleler modele gönderilmeden çıkarılır; geri kalanı modelin kurallarına kalır. Geçmeyen bir test, modelin o tür bir talimata uyabildiğini gösterir: belge yükleme yetkisini güvendiğiniz kişilerle sınırlayın. Soru eklemeden de **Şimdi çalıştır** yalnızca güvenlik testlerini çalıştırır.

Belge yükledikten, değiştirdikten ya da arşivledikten sonra ve arama profili değiştiğinde çalıştırın. Önceden geçen bir sorunun artık geçmemesi bir gerilemedir. Kurulumda gece çalıştırması da açılabilir. Bir soruyu arşivlemek onu sonraki çalıştırmalardan çıkarır, eski sonuçlar korunur. Sorular ve yanıtlar loglara yazılmaz; denetim kaydında yalnızca sayılar tutulur.

## Çalışan ekleme ve davet kabulü

**Üyelikler → Mevcut hesabı ekle**, yalnızca platformda zaten kayıtlı bir hesaba üyelik verir. Yeni çalışan için **Yeni çalışan davet et** bağlantısıyla **Davetler** ekranını kullanın. Davet e-postasını, rolünü ve gerekiyorsa Workspace kapsamını seçin. Oluşan tek kullanımlık bağlantıyı güvenli bir kanaldan iletin; bağlantı yalnızca oluşturulurken gösterilir.

Davetli kişi bağlantıyı açıp mevcut hesabıyla giriş yapar veya yeni hesap için kendi şifresini belirler. Davet e-postaya bağlıdır, süreli ve tek kullanımlıktır. Davet bağlantısını genel kanallarda paylaşmayın.

## Model ve Sistem ekranları

**Modeller** ekranı yerel üretim ve embedding modelinin durumunu gösterir. Model yönetimi platform yetkisine bağlıdır.

**Üretim modeli seçimi** (platform yöneticisi): sunucuda yüklü Ollama modellerinden biri yanıtları üretmek için seçilebilir. Belgeler yeniden indekslenmez; arama modeli (BGE-M3) aynı kalır, bu yüzden daha önce yüklenen belgeler yeni modelle de kullanılır. Adımlar:
1. Bir çalışma alanı seçip modelin satırında **Sına**: o çalışma alanının Kalite soruları ve 9 güvenlik testi bu modelle sorulur; kullanıcılar bu sırada etkin modeli kullanmaya devam eder. Sonuç satırda görünür ("24/25 soru · 9/9 güvenlik · medyan 5,5 sn"); yanıtların kendisi o çalışma alanının Kalite sayfasındadır.
2. Sınanan model **Etkinleştir** ile seçilir. Değişiklik yeniden başlatma olmadan birkaç saniyede bütün servislere geçer, önceki model bellekten boşaltılır. Kurulum varsayılanına dönmek için onun satırında **Etkinleştir**.

Sistem her modele aynı güvenli ayarları verir: "düşünme" (thinking) modu kapatılır, bağlam 8.192 token'la sınırlanır (`OLLAMA_NUM_CTX`). 16 GB bir makinede 8 GB'tan büyük modeller sunulmaz (`OLLAMA_MAX_MODEL_BYTES`). Büyük bir model daha iyi yanıt verebilir ama yavaşlar: qwen3.5:9b bu sunucuda güvenlik testlerinde 9/9 aldı, yanıt başına yaklaşık 5 saniye sürdü (gemma3:4b: 8/9, yaklaşık 2,5 saniye). **Sistem** ekranı API, PostgreSQL, Redis, Qdrant, Ollama ve embedding hazırlığını gösterir; arama profili burada salt okunurdur.

## Güvenlik notları

Her yanıtın hangi belge sürümlerine dayandığı **Yanıt izi** olarak tutulur (soru ve yanıt metni olmadan, varsayılan 180 gün); platform yöneticisi **Yönetim → Denetim günlüğü**'nde soran hesapla birlikte görür. Platform yöneticiliği Organization belgelerine örtük erişim vermez. Üyelikleri yalnızca gerekli Organization/Workspace kapsamına verin. Davet bağlantısı bir erişim sırrıdır; kopyalarken dikkatli olun. Şifreleri veya erişim bağlantılarını destek mesajlarına yapıştırmayın.

## Sık karşılaşılan durumlar

**Workspace neden boş?** Hesabınıza henüz Workspace erişimi verilmemiş olabilir. Platform yöneticisiyseniz Organization üyeliğinizi ve Workspace'i hazırlayın; çalışan iseniz Organization yöneticinize başvurun.

**Knowledge Base oluştur butonu neden görünmüyor?** Workspace'te manager/admin rolü gerekir. User rolü yalnızca okuma ve sorgulama içindir.

**RAG Chat neden pasif?** Erişilebilir Workspace veya Knowledge Base olmayabilir. Önce bu alanları hazırlayın ve en az bir belgenin hazır olmasını bekleyin.

**“User not found” ne anlama geliyor?** E-posta ile mevcut hesap bulunamadı. Yeni çalışan için Davetler ekranından davet oluşturun.

**Belgem ne zaman kullanılabilir?** Belgeler ekranında durum **Hazır** olunca. Uzun süre İşleniyor veya Hatalı kalırsa yöneticinize bildirin.
