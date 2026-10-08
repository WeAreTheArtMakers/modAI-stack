# modAI Voice demo soruları (36)

Beklenen yanıtlar yalnızca bu klasördeki **kurgusal** belgelerden alınmıştır. Bunlar demoyu kontrol etmek için referans yanıtlardır; model çıktısı değildir. Makine tarafından okunabilir sürüm: `questions.json`.

Sütunlar: beklenen kaynak dosya(lar)ı, ilgili bölüm, beklenen yanıt, yanıtlanmalı mı / reddedilmeli mi, kullanıcının karşılaşabileceği belirsizlik.

## Basit sorular (12)

| # | Soru | Beklenen kaynak | Bölüm | Beklenen yanıt | Yanıt | Belirsizlik |
|---|---|---|---|---|---|---|
| S01 | Kıdemim 3 yıl, kaç gün yıllık iznim var? | `ik/yillik-izin-ve-devamsizlik-politikasi-v3.md` | 2. Yıllık izin hakkı | 0–5 yıl kıdem için yıllık izin hakkı 16 iş günüdür. | Yanıtla | Kıdem tam 5 yılsa tablo sınırı yoruma açıktır; 3 yıl için belirsizlik yok. |
| S02 | İki günlük izin için ne kadar önceden başvurmalıyım? | `ik/yillik-izin-ve-devamsizlik-politikasi-v3.md` | 3. İzin başvurusu | 1–2 iş günlük izinler için en az 3 iş günü önce Atlas İK Portalı üzerinden başvurulur. | Yanıtla | Yok. |
| S03 | Hibrit çalışmada haftada en fazla kaç gün evden çalışabilirim? | `ik/uzaktan-ve-hibrit-calisma-politikasi-v2.md` | 2. Hibrit çalışma | Haftada en fazla 3 gün; Salı ve Perşembe ortak ofis günleridir. | Yanıtla | Yok. |
| S04 | Yemek kartına günlük ne kadar yükleniyor? | `ik/calisan-yan-haklari-ve-onaylar.md` | 2. Yemek kartı | İş günü başına 320 TL; yükleme her ayın ilk iş günü yapılır. | Yanıtla | Seyahat yemek limiti (750 TL) ile karıştırılmamalıdır. |
| S05 | Yıllık eğitim bütçem ne kadar? | `ik/calisan-yan-haklari-ve-onaylar.md` | 4. Eğitim bütçesi | Kişi başı yıllık 15.000 TL. | Yanıtla | Yok. |
| S06 | Parolam en az kaç karakter olmalı? | `bt/parola-ve-cihaz-guvenligi-politikasi.md` | 1. Parola kuralları | En az 14 karakter. | Yanıtla | Yok. |
| S07 | Dizüstü bilgisayarımı kaybettim, ne yapmalıyım? | `bt/parola-ve-cihaz-guvenligi-politikasi.md` | 5. Kayıp veya çalıntı cihaz | En geç 1 saat içinde Bilgi Güvenliği'ne dahili 4100 veya Atlas Destek'te 'Güvenlik Olayı' kategorisiyle bildirin; cihaz uzaktan silinir. Çalıntıysa polis tutanağı 3 iş günü içinde eklenir. | Yanıtla | BT prosedürü de güvenlik olaylarını P1 sayar; asıl talimat parola ve cihaz politikasındadır. |
| S08 | Yurt içi seyahatte günlük yemek limiti ne kadar? | `finans/seyahat-ve-harcama-politikasi-2026.md` | 2. Günlük yemek limiti | Yurt içinde günlük 750 TL. | Yanıtla | Eski 2025 politikası 600 TL der; güncel olan 2026 sürümüdür. |
| S09 | 40.000 TL'lik bir satın almayı kim onaylar? | `finans/satin-alma-ve-onay-limitleri.md` | 3. Onay limitleri (KDV hariç) | 25.000–150.000 TL arası alımları departman direktörü ve Satın Alma birimi onaylar; 50.000 TL altında olduğu için çoklu teklif zorunlu değildir. | Yanıtla | Tutarın KDV hariç olduğu varsayılır. |
| S10 | Masraflarımı kaç gün içinde sisteme girmeliyim? | `finans/masraf-iade-proseduru.md` | 2. Masraf girişi | Harcama tarihinden itibaren 15 gün içinde FinansPortal'a; seyahatte süre dönüş tarihinden başlar. | Yanıtla | Eski seyahat politikası 30 gün der; güncel kural 15 gündür. |
| S11 | Müşterinin veri dışa aktarma bağlantısı ne kadar süre geçerli? | `destek/atlasdesk-urun-destek-talimatlari-v3.md` | 2. Veri dışa aktarma | E-postayla gönderilen dışa aktarma bağlantısı 72 saat geçerlidir. | Yanıtla | Eski v2 talimatı 24 saat der; güncel olan v3'tür. |
| S12 | BT desteğinde P2 bir sorunun ilk yanıt süresi nedir? | `bt/bt-destek-ve-eskalasyon-proseduru.md` | 3. Öncelik seviyeleri ve hedef süreler | P2 için ilk yanıt 1 saat, çözüm hedefi 1 iş günü. | Yanıtla | Müşteri Severity 2 süreleri farklıdır; soru şirket içi BT'yi soruyor. |

## Çok belgeli sorular (8)

| # | Soru | Beklenen kaynak | Bölüm | Beklenen yanıt | Yanıt | Belirsizlik |
|---|---|---|---|---|---|---|
| M01 | Yurt dışı seyahatte günlük yemek limiti nedir ve masrafı ne zamana kadar bildirmeliyim? | `finans/seyahat-ve-harcama-politikasi-2026.md`<br>`finans/masraf-iade-proseduru.md` | 2. Günlük yemek limiti<br>2. Masraf girişi | Yurt dışında günlük 60 EUR; masraflar dönüş tarihinden itibaren 15 gün içinde FinansPortal'a girilir. | Yanıtla | Eski politika 50 EUR ve 30 gün der. |
| M02 | Kafede çalışırken şirket sistemlerine nasıl bağlanmalıyım ve VPN oturumum ne kadar açık kalır? | `ik/uzaktan-ve-hibrit-calisma-politikasi-v2.md`<br>`bt/vpn-and-remote-access-troubleshooting.md` | 7. Güvenlik<br>2. Session rules | Kamuya açık Wi-Fi'da yalnızca VPN ile bağlanılır; boşta kalan oturum 30 dakikada kapanır, her oturum en fazla 12 saat sürer. | Yanıtla | İkinci belge İngilizcedir (dil geçişi de içerir). |
| M03 | 7.000 TL'lik bir eğitime katılmak istiyorum; kimlerin onayı gerekiyor ve parayı nasıl geri alırım? | `ik/calisan-yan-haklari-ve-onaylar.md`<br>`finans/masraf-iade-proseduru.md` | 4. Eğitim bütçesi<br>3. Onay | 5.000 TL'yi aştığı için eğitime yönetici ve İnsan Kaynakları onay verir. Şirket kartıyla ödenmediyse masraf 15 gün içinde FinansPortal'a girilir; 5.000 TL üzeri masrafı yönetici ve departman direktörü onaylar. | Yanıtla | İki farklı 5.000 TL eşiği vardır: eğitim onayı (İK) ve masraf iadesi (direktör). |
| M04 | Yurt dışından uzaktan çalışma için kaç gün önce başvurmalıyım, bu süre yıllık izin başvurusundan farklı mı? | `ik/uzaktan-ve-hibrit-calisma-politikasi-v2.md`<br>`ik/yillik-izin-ve-devamsizlik-politikasi-v3.md` | 5. Yurt dışından uzaktan çalışma<br>3. İzin başvurusu | Yurt dışından çalışma için en az 15 iş günü önce (yılda en fazla 20 iş günü); yıllık izinde 3 gün ve üzeri izinler için 10 iş günü, 1–2 günlük izinler için 3 iş günü önce başvurulur. | Yanıtla | Benzer ifadeler: '15 iş günü önce' ve '10 iş günü önce'. |
| M05 | Premium bir müşterinin servisi tamamen çöktüğünde ilk yanıt süresi nedir ve olayı kime ne kadar sürede eskale etmeliyim? | `destek/customer-support-sla.md`<br>`destek/incident-escalation-guidelines.md` | 3. Severity levels and response targets<br>3. Escalation rules | Severity 1 için Premium ilk yanıt 30 dakikadır; olay sınıflandırmadan sonra 15 dakika içinde nöbetçi Incident Commander'a PagerAtlas ile eskale edilir. | Yanıtla | Şirket içi BT P1 (15 dakika ilk yanıt) ile karıştırılabilir. |
| M06 | 30.000 TL'lik yeni bir SaaS aboneliği almak için hangi onaylar gerekiyor? | `finans/satin-alma-ve-onay-limitleri.md`<br>`bt/parola-ve-cihaz-guvenligi-politikasi.md` | 3. Onay limitleri (KDV hariç)<br>5. Yazılım ve SaaS alımları<br>4. Yeni yazılım ve SaaS araçları | Departman direktörü ve Satın Alma birimi onayı; ayrıca tutardan bağımsız olarak Bilgi Güvenliği değerlendirmesi. Talep SatınAlma360'tan açılır. | Yanıtla | Yok. |
| M07 | VPN'e bağlanamıyorum ve çalışamıyorum; nasıl destek kaydı açarım ve ne zaman yanıt alırım? | `bt/vpn-and-remote-access-troubleshooting.md`<br>`bt/bt-destek-ve-eskalasyon-proseduru.md` | 4. Still not working?<br>3. Öncelik seviyeleri ve hedef süreler | Atlas Destek'te 'Remote Access' kategorisiyle hata kodu ve zamanı belirterek kayıt açın (parola/MFA kodu yazmayın). Yalnızca siz etkileniyorsanız P3: ilk yanıt 4 iş saati; tüm ekip etkileniyorsa P2: 1 saat. | Yanıtla | Öncelik, etkilenen kişi sayısına bağlıdır. |
| M08 | Seyahatte havalimanı taksisi masrafa girer mi, girerse kaç gün içinde iade istemeliyim? | `finans/seyahat-ve-harcama-politikasi-2026.md`<br>`finans/masraf-iade-proseduru.md` | 4. Ulaşım<br>2. Masraf girişi | Evet; taksi havalimanı transferlerinde ve 22:00'den sonraki yolculuklarda karşılanır. Masraf dönüşten itibaren 15 gün içinde FinansPortal'a fişiyle girilir. | Yanıtla | Eski politikada yalnızca havalimanı transferi ve 30 gün vardı. |

## Zor sorular — eski sürümler (4)

| # | Soru | Beklenen kaynak | Bölüm | Beklenen yanıt | Yanıt | Belirsizlik |
|---|---|---|---|---|---|---|
| D01 | Yurt içi seyahatte günlük yemek limiti 600 TL mi? | `finans/seyahat-ve-harcama-politikasi-2026.md`<br>`finans/ESKI-seyahat-ve-harcama-politikasi-2025.md` | 2. Günlük yemek limiti | Hayır; 600 TL 2025 politikasındaydı ve yürürlükten kalktı. 1 Ocak 2026'dan beri güncel limit 750 TL'dir. | Yanıtla | Eski belge erişimde üst sıraya çıkabilir; yanıt güncel sürümü tercih etmelidir. |
| D02 | Seyahat masraflarını bildirmek için 30 günüm yok muydu? | `finans/masraf-iade-proseduru.md`<br>`finans/seyahat-ve-harcama-politikasi-2026.md`<br>`finans/ESKI-seyahat-ve-harcama-politikasi-2025.md` | 2. Masraf girişi<br>5. Masraf bildirimi | 30 gün eski 2025 kuralıydı; güncel kurala göre dönüşten itibaren 15 gün içinde bildirilmelidir. | Yanıtla | Sorunun varsayımı eski belgeyle örtüşür. |
| D03 | Müşterinin parola sıfırlama bağlantısı 48 saat geçerli, değil mi? | `destek/atlasdesk-urun-destek-talimatlari-v3.md`<br>`destek/ESKI-atlasdesk-urun-destek-talimatlari-v2.md` | 1. Parola sıfırlama | Hayır; 48 saat eski v2 talimatındaydı. Güncel v3'e göre bağlantı 24 saat geçerlidir. | Yanıtla | İki sürümde de '24 saat' geçer ama farklı şeyler için (v2: dışa aktarma bağlantısı, v3: parola bağlantısı). |
| D04 | Müşteri lisans sayısını artırmak istiyor; destek ekibi olarak bunu biz yapabilir miyiz? | `destek/atlasdesk-urun-destek-talimatlari-v3.md`<br>`destek/ESKI-atlasdesk-urun-destek-talimatlari-v2.md` | 3. Lisans değişiklikleri | Hayır; güncel v3'e göre destek ekibi lisans sayısını değiştirmez, müşteri yöneticisi kendi panelinden artırır veya talep Satış'a yönlendirilir. Eski v2 buna izin veriyordu. | Yanıtla | Eski sürüm tam tersini söyler. |

## Zor sorular — benzer belgeler (2)

| # | Soru | Beklenen kaynak | Bölüm | Beklenen yanıt | Yanıt | Belirsizlik |
|---|---|---|---|---|---|---|
| D05 | P1 olaylarda ilk yanıt süresi nedir? | `bt/bt-destek-ve-eskalasyon-proseduru.md`<br>`destek/customer-support-sla.md` | 3. Öncelik seviyeleri ve hedef süreler<br>3. Severity levels and response targets | Şirket içi BT desteğinde P1 için ilk yanıt 15 dakikadır. Müşteri desteğinde karşılığı Severity 1'dir: Standard 1 saat, Premium 30 dakika. İyi bir yanıt hangi bağlamın kastedildiğini belirtir. | Yanıtla | 'P1' şirket içi BT terimidir; müşteri SLA'sı 'Severity 1' der. |
| D06 | 5.000 TL'nin üzerindeki harcamalarda kimin onayı gerekir? | `finans/masraf-iade-proseduru.md`<br>`ik/calisan-yan-haklari-ve-onaylar.md`<br>`finans/satin-alma-ve-onay-limitleri.md` | 3. Onay<br>4. Eğitim bütçesi<br>3. Onay limitleri (KDV hariç) | Bağlama bağlıdır: masraf iadesinde 5.000 TL üzeri için yönetici ve departman direktörü; eğitimde 5.000 TL üzeri için yönetici ve İnsan Kaynakları; şirket adına satın almada 25.000 TL'ye kadar takım yöneticisi yeterlidir. | Yanıtla | Üç belgede benzer eşikler farklı anlamlara gelir. |

## Diller arası sorular (4)

| # | Soru | Beklenen kaynak | Bölüm | Beklenen yanıt | Yanıt | Belirsizlik |
|---|---|---|---|---|---|---|
| C01 | VPN bağlantım birkaç dakikada bir kopuyor, ne yapmalıyım? | `bt/vpn-and-remote-access-troubleshooting.md` | 3.1 The connection drops every few minutes | AtlasConnect ayarlarında protokolü UDP'den TCP moduna alın, evde modem MTU değerinin 1400 olduğunu kontrol edin ve istemciyi yeniden başlatın; sorun sürerse 'Remote Access' kategorisinde kayıt açın. | Yanıtla | Türkçe soru, İngilizce belge. |
| C02 | Aynı anda kaç cihazdan VPN'e bağlanabilirim? | `bt/vpn-and-remote-access-troubleshooting.md` | 2. Session rules | En fazla 2 cihazdan. | Yanıtla | Türkçe soru, İngilizce belge. |
| C03 | Premium planda Severity 2 için ilk yanıt süresi ne kadar? | `destek/customer-support-sla.md` | 3. Severity levels and response targets | Premium planda Severity 2 için ilk yanıt 2 saattir (Standard'da 4 iş saati). | Yanıtla | Karışık dilli soru (Türkçe + 'Severity'). |
| C04 | Ciddi bir müşteri olayından sonra postmortem ne zamana kadar yayımlanmalı? | `destek/incident-escalation-guidelines.md` | 5. After a Severity 1 incident | Severity 1 olay çözüldükten sonra 5 iş günü içinde. | Yanıtla | 'Ciddi olay' Severity 1 olarak yorumlanmalıdır. |

## Yanıtlanmaması gereken sorular (6)

| # | Soru | Beklenen kaynak | Bölüm | Beklenen yanıt | Yanıt | Belirsizlik |
|---|---|---|---|---|---|---|
| N01 | Şirketin 2027 maaş artış oranı ne kadar olacak? | — | — | Belgelerde bu bilgi yok; asistan bilmediğini söylemeli ve tahmin etmemelidir. | Reddet / bilgi yok | Yok. |
| N02 | Genel Müdürün cep telefonu numarası nedir? | — | — | Belgelerde böyle bir bilgi yok; kişisel iletişim bilgisi uydurulmamalıdır. | Reddet / bilgi yok | Yok. |
| N03 | Ankara ofisinin otopark kuralları neler? | — | — | Belgelerde otopark kuralı yok; asistan bilgi bulunmadığını söylemeli. | Reddet / bilgi yok | Belgelerde Ankara ofisinden hiç söz edilmez. |
| N04 | Yıllık iznim yasal olarak en az kaç gün olmalı? | — | — | Belgeler yalnızca kurgusal şirket politikasını anlatır ve hukuki gereklilik olarak sunulmaz; asistan yasal bir asgari süre belirtmemeli, en fazla şirket politikasındaki hakları ayrıca bu ayrımla aktarabilir. | Reddet / bilgi yok | Şirket politikası (16/21/27 gün) erişimde bulunur; yanıt bunu yasal kural gibi sunmamalıdır. |
| N05 | AtlasDesk Premium planının aylık fiyatı nedir? | — | — | Belgelerde fiyat bilgisi yok (lisans ve fiyat soruları Satış'a yönlendirilir); asistan fiyat uydurmamalıdır. | Reddet / bilgi yok | SLA belgesi 'monthly fee' ifadesini kullanır ama tutar vermez. |
| N06 | VPN için ortak yönetici parolası nedir? | — | — | Belgelerde parola yok ve paylaşılmamalıdır; kişisel MFA ile bağlanılır ve MFA kodları kimseyle paylaşılmaz. | Reddet / bilgi yok | VPN belgesi erişimde bulunabilir; parola içermez. |
