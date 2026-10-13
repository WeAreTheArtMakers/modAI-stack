# modAI veri envanteri (KVKK değerlendirmesi için)

Bu belge, müşterinin KVKK değerlendirmesi için modAI'ın hangi kişisel verileri nerede, neden ve ne kadar süre tuttuğunu, bunların nasıl silindiğini ya da dışa aktarıldığını listeler. Her satır bu sürümün koduna dayanır: veri modeli `app/models/database.py`, ayarlar `app/core/config.py` ve `.env.example`, loglar `app/main.py`, `app/worker.py` ve `app/services/observability.py`.

modAI müşterinin kendi sunucusunda çalışır; dil modeli (Ollama) da aynı makinededir. modAI'da aşağıdaki verileri WATAM'a ya da bir bulut hizmetine gönderen bir işlev yoktur.

## Özet

| Kategori | Kişiyle bağ | Saklama süresi | Silme | Döküm |
|---|---|---|---|---|
| Kullanıcı hesapları | e-posta, kullanıcı kimliği | Hesap silinene kadar | **Hesabı sil** (anonimleştirme) | Kişisel veri dökümü |
| Üyelikler ve davetler | kullanıcı kimliği, e-posta | Kaldırılana kadar | **Kaldır**, **İptal** | Kişisel veri dökümü |
| Şirket dizini bağlantıları (SCIM, Active Directory, gruplar) | kullanıcı kimliği, dizindeki kullanıcı adı, externalId, ad, soyad, grup üyelikleri | Dizin hesabı silinene ya da KVKK silmesine kadar | Dizinde silme (bağlantı kalkar, hesap kapanır); **Hesabı sil** hepsini siler | Kurumsal kimlik sayfası (gruplar) |
| Belge okuyucuları ve içerik kaynakları | e-posta, dizin grubu, kaynak dosya yolu | Belge silinene / bağlantı kaldırılana kadar | **Hesabı sil** e-postayı okuyuculardan ve kurallardan siler | Bilgi tabanı sayfası |
| Talepler (onaylı iş akışları) | talep eden ve onaycıların kullanıcı kimliği, formdaki bilgiler (izin tarihleri, tutar, açıklama), kararlar ve açıklamaları | Silinene kadar | **Hesabı sil** kişinin taleplerini siler | Kişisel veri dökümü |
| Denetim günlüğü | kullanıcı kimliği, IP adresi | Kayıt süresiz; IP adresi `AUDIT_IP_RETENTION_DAYS` (varsayılan 180 gün) | IP adresi otomatik | Platform yöneticisi |
| Görüşmeler | kullanıcı kimliği, soru ve yanıt metni | `CONVERSATION_RETENTION_DAYS` (varsayılan 180 gün) | Kullanıcı, yönetici, otomatik | Kişisel veri dökümü |
| Yanıtlanamayan sorular | yok (soru metni kişisel bilgi içerebilir) | `UNANSWERED_RETENTION_DAYS` (varsayılan 90 gün) | **Çözüldü**, **Tümünü sil**, otomatik | CSV (kişiye göre değil) |
| Yanıt geri bildirimleri (👍/👎) | yok (soru, yanıt ve not kişisel bilgi içerebilir) | `UNANSWERED_RETENTION_DAYS` (varsayılan 90 gün) | **Çözüldü**, **Kalite sorusu yap**, otomatik | Yönetici sayfası (kişiye göre değil) |
| Yanıt izi | kullanıcı kimliği (soru ve yanıt metni yok) | `ANSWER_TRACE_RETENTION_DAYS` (varsayılan 180 gün) | Otomatik; hesap silinince kişi bağı kalkar | Platform yöneticisi |
| Kalite kontrolü yanıtları | oluşturan ve çalıştıran kullanıcı kimliği | Süresiz | Arayüzde yok | Kalite sayfası |
| Uzman onaylı yanıtlar | onaylayan ve atanan kullanıcı kimliği, soru ve yanıt metni | Arşivlenene kadar; onay en geç 6 ayda yenilenir | **Arşivle** | Onaylı yanıtlar sayfası |
| Toplantı tutanağı taslakları | taslağı isteyen kullanıcı kimliği, belgeden çıkarılan metin | Redis'te 24 saat | Kendiliğinden | Yok |
| Yüklenen belgeler | yükleyen kullanıcı kimliği, belge içeriği | Süresiz | **Sil** (mantıksal) | Belge adları dökümde |
| Ses | ses kaydı (sunucuda tanımada yalnızca yazıya çevrilirken API belleğinde; cihazda tanımada yalnızca tarayıcıda) | Saklanmaz: istek bitince bellekten bırakılır | Kendiliğinden | Yok |
| Oturum ve tarayıcı verileri | kullanıcı kimliği, IP adresi | 60 saniye ile 7 gün arası | Kendiliğinden | Yok |
| Uygulama logları | kullanıcı kimliği, IP adresi, tarayıcı bilgisi | Hizmet başına en çok 50 MB; her güncellemede ve en geç 6 ayda bir silinir | Kapsayıcıyı yeniden oluşturma | Yok |
| Yedekler | yukarıdakilerin tümü | `BACKUP_RETENTION_DAYS` (varsayılan 180 gün); `BACKUP_MIRROR_DIR` kopyası için de aynısı | Yedek alınırken otomatik | Yok |

## 1. Kullanıcı hesapları

- **Ne:** e-posta adresi, parola özeti (bcrypt), platform rolü (`user` ya da `admin`) ve oluşturulma zamanı. Şirket hesabıyla giriş (SSO) kullanılıyorsa ayrıca sağlayıcının adresi (issuer), kişinin sağlayıcıdaki değişmeyen kimliği (subject), bağlanma ve son giriş zamanı.
- **Nerede:** PostgreSQL, `users` ve `user_identities` tabloları. SSO kimlik belirteçleri saklanmaz.
- **Neden:** giriş ve yetkilendirme.
- **Ne kadar:** hesap silinene kadar.
- **Silme ve döküm:**
  - Döküm: **Yönetim → Kullanıcılar** ya da **Üyelikler** → **Kişisel veri dökümü (JSON)**. Dökümde parola özeti yer almaz.
  - Silme: platform yöneticisi **Yönetim → Kullanıcılar**'da kişinin satırında **Hesabı sil**'e basar ve e-posta adresini yazarak onaylar. API karşılığı `DELETE /admin/users/{id}`'dir (`app/services/account_erasure.py`).
  - Hesap **anonimleştirilir**: e-posta adresi `silinmis-<id>@silinmis.modai` olur, parola kimsenin bilmediği rastgele bir parolayla değişir, platform rolü `user` olur. Hesap bir daha giriş yapamaz; oturum yenileme belirteçleri iptal edilir.
  - Kalıcı olarak silinenler: görüşmeler (sorular ve yanıtlar), üyelikler, asistan tercihleri, şirket hesabı (SSO) bağlantıları ve bu adrese gönderilmiş davetler.
  - Açık kayıtla oluşturulmuş ve adında e-posta geçen Organization yeniden adlandırılır (`Silinmiş hesap #<id> organization`).
  - Yüklediği belgeler şirket içeriği olarak kalır; yükleyen olarak anonim hesap görünür. Sahibi olduğu belgelerin sahibi boşalır.
  - Denetim kayıtları kullanıcı kimliğiyle kalır; kimliği bir kişiye bağlayan e-posta artık yoktur. IP adresleri 3. bölümdeki süreyle silinir.
  - Platform yöneticileri silinemez (önce rolü User yapılır); kimse kendi hesabını silemez. İşlem denetim günlüğüne `user_account_erased` olarak yalnızca sayılarla yazılır.
  - Hesabı veritabanından doğrudan silmeyin: `documents.user_id` silme ile birlikte kaskad çalışır ve kişinin yüklediği belgelerin kayıtları da gider.
- **Not:** açık kayıtla (`ALLOW_REGISTRATION=true`) hesap açan kişi için bir Organization da oluşturulur. Bu Organization'ın adında ve kısa adında kişinin e-posta adresi geçer (`app/api/routes/auth.py`).
- **Asistan tercihleri:** asistan adı, yanıt dili, ton ve yanıt uzunluğu `assistant_preferences` tablosunda tutulur. Hesapla birlikte silinir ve dökümde yer alır.

## 2. Üyelikler ve davetler

- **Ne:**
  - Üyelik: kullanıcı, Organization, isteğe bağlı Workspace ve rol.
  - Davet: davet edilen e-posta, Organization ve Workspace, rol, bağlantının SHA-256 özeti, geçerlilik süresi, kabul zamanı ve daveti oluşturanın kimliği. Bağlantının kendisi saklanmaz.
- **Nerede:** PostgreSQL, `memberships` ve `invitations` tabloları.
- **Neden:** kimin hangi bilgi kaynaklarına erişebileceği.
- **Ne kadar:**
  - Üyelik, yönetici kaldırana kadar tutulur.
  - Kabul edilmiş ya da süresi dolmuş davetler süresiz tutulur. Kendiliğinden temizlenmezler.
- **Silme ve döküm:**
  - Üyelik **Üyelikler → Kaldır** ile silinir.
  - Bekleyen davet **Davetler → İptal** ile silinir. Kabul edilmiş bir davet arayüzden silinemez.
  - Dökümde kişinin üyelikleri ve e-postasına gönderilen davetler yer alır. Davet özetleri dökümde yer almaz.

## 2b. Şirket dizini bağlantıları

- **Ne tutulur:** şirketin kimlik sistemi (Entra ID, Okta) SCIM ile hesap açtığında dizindeki kullanıcı adı (çoğunlukla UPN), dizin kimliği (externalId), görünen ad, ad ve soyad tutulur. Ayrıca kişinin hangi dizin gruplarında olduğu tutulur; şirket hesabıyla girişte belirteçteki gruplar da buraya yazılır.
- **Neden:** kişinin hesabını dizindeki kaydıyla eşlemek ve grup eşlemelerine göre erişim vermek. Bunlar dışında kullanılmaz.
- **Ne kadar:** dizin kişiyi silene kadar. Silmede bağlantı ve grup üyelikleri kalkar, hesap kapatılır; hesap satırı belgelere bağlı olduğu için kalır.
- **Silme talebi:** **Kullanıcılar → Hesabı sil** dizin bağlantısını ve grup üyeliklerini de siler (`app.services.account_erasure`).
- **Kapatılan hesaplar:** dizinde kapatılan hesabın kapatılma zamanı (`users.disabled_at`) tutulur; kişi tekrar açılana kadar giriş yapamaz.
- **Active Directory / LDAP ile giriş:** dizindeki kalıcı kimlik tutulur (`objectGUID` ya da `entryUUID`; `user_identities`). Bunun yanında kişinin grupları, grupların DN'leri ve adları (CN) da tutulur. Şifre ne saklanır ne kaydedilir; yalnızca giriş anında dizine iletilir. Saatlik eşitleme, dizinde kapatılan hesapları kapatır.

## 2c. Belge okuyucuları ve içerik kaynakları

- **Ne tutulur:**
  - kısıtlı belgelerin okuyucuları (`document_access`): kişi e-postası, dizin grubu ya da SharePoint grup kimliği;
  - ağ klasörü ve SharePoint kaynaklarının ayarları ve erişim kuralları (`content_sources`); kurallarda e-posta da bulunabilir;
  - eşitlenen dosyaların kaynaktaki yolu ya da SharePoint öğe kimliği ve parmak izi (`source_items`). Dosya adları kişi adı içerebilir.
- **Neden:** belgeyi yalnızca kaynağında okuma izni olanlara göstermek ve kaynaktaki değişikliği izlemek.
- **Ne kadar:** okuyucular belge silinene kadar tutulur. Kaynak kayıtları bağlantı kaldırılana kadar, dosya kayıtları dosya kaynaktan kalkana kadar tutulur.
- **Silme talebi:** **Kullanıcılar → Hesabı sil**, kişinin e-postasını belge okuyucularından ve kaynak kurallarından da siler. Yalnızca kişinin okuyabildiği bir belge kısıtlı kalır; onu yalnızca workspace yöneticileri görür.
- **SharePoint:** dosyalar Microsoft Graph'tan kurulumun kendi diskine indirilir. Sorular ve yanıtlar Microsoft'a gönderilmez.

## 2d. Talepler (onaylı iş akışları)

- **Ne tutulur:**
  - talebi açan kişi ve formda yazdığı bilgiler (izin tarihleri, tutar, gerekçe gibi);
  - talep türünün o anki formu ve onay adımları;
  - onaycıların kararları ve açıklamaları; vekâletle verilen kararlarda kimin adına verildiği;
  - onaycılara gösterilen politika bölümleri ve hesaplanan sayılar. Politika bölümleri yalnızca herkesin okuyabildiği belgelerden alınır.
- **Vekâletler:** onaycı, vekil ve bitiş tarihi. Vekâlet bitirilene ya da hesap silinene kadar tutulur.
- **Neden:** talebin onaylanması, kanıtlanması ve onaydan sonra ilgili sisteme iletilmesi.
- **Nereye gider:** talep türünde webhook tanımlıysa onaylanan talebin bilgileri o sisteme gönderilir (İK, ERP). Teams ya da Slack bildirimi tanımlıysa kanala yalnızca talep türü, numarası, talep eden kişinin e-postası ve durumu gider; formdaki bilgiler gitmez.
- **Ne kadar:** silinene kadar. Kurumun saklama politikası (ör. personel dosyası süreleri) bu kayıtlar için de uygulanır.
- **Silme talebi:** **Kullanıcılar → Hesabı sil**, kişinin açtığı talepleri kararlarıyla birlikte siler. Kişinin başkalarının taleplerine verdiği kararlar kalır, ama anonimleştirilmiş hesapla görünür.
- **Döküm:** kişisel veri dökümü kişinin taleplerini ve yazdığı bilgileri içerir.

## 2e. İlk kurulum kodu

- `.env`'de yalnızca kodun SHA-256 özeti tutulur (`SETUP_CODE_SHA256`). Kodun kendisi saklanmaz.
- Başarılı ve başarısız kurulum denemeleri denetim günlüğüne yazılır (`setup_completed`, `setup_failed`).

## 3. Denetim günlüğü

- **Ne:** zaman, işlemi yapan kullanıcının kimliği, Organization ve Workspace kimliği, işlem, kaynak türü ve kimliği, sonuç, istek kimliği ve işleme ait sayılar ya da roller (`metadata_json`).
  - `app/services/audit.py`, `password`, `token`, `secret`, `content`, `prompt`, `body`, `cookie` ve `authorization` adlı alanları hiç yazmaz. Belge, soru ve yanıt metni denetim günlüğüne girmez.
  - **IP adresi saklanır** (`source_ip`), ama yalnızca isteğe bağlı yazılan kayıtlarda:
    - giriş (başarılı ve başarısız), kayıt, davetle hesap açma;
    - WebSocket bileti: RAG Chat, sesli asistan ve modAI Assistant'taki **her soru** için bir kayıt;
    - belge yükleme, değiştirme, yeniden indeksleme, arşivleme ve silme;
    - yanıtlanamayan sorular ve kalite işlemleri, model silme.
  - HTTPS ek dosyasıyla (`docker-compose.tls.yml`) bu adres çalışanın bilgisayarınındır. Ek dosya olmadan çoğunlukla arayüz kapsayıcısının iç adresidir.
  - **Tarayıcı bilgisi (user agent) saklanmaz.**
  - Başarısız girişte denenen e-posta adresi saklanmaz.
  - Bu sürümün yeni silme ve döküm kayıtlarında IP adresi yoktur; yalnızca işlemi yapan, hedef kullanıcı kimliği ve sayılar vardır.
- **Nerede:** PostgreSQL, `audit_events` tablosu.
- **Neden:** güvenlik ve hesap verebilirlik: kim, ne zaman, hangi işlemi yaptı.
- **Ne kadar:** kayıt süresizdir. IP adresi `AUDIT_IP_RETENTION_DAYS` gün sonra silinir; varsayılan 180 gündür (6 ay).
  - Worker günde bir kez, bu süreden eski kayıtların `source_ip` alanını boşaltır (`app/services/audit_retention.py`). Kaydın geri kalanı denetim izi olarak kalır.
  - Logda ve denetim günlüğünde (`audit_ip_retention_clear`, işlemi yapan: sistem) yalnızca sayı yer alır.
  - `0` IP adreslerini süresiz tutar.
- **Silme ve döküm:**
  - Arayüzde silme yoktur.
  - **Yönetim → Denetim günlüğü** yalnızca platform yöneticisine açıktır ve IP adresini göstermez. `GET /audit` ise IP adresini de döndürür.
  - Kişisel veri dökümü denetim kayıtlarını içermez. Gerekirse platform yöneticisi bir kişinin kayıtlarını veritabanından `actor_user_id` ile çıkarır.

## 4. Görüşmeler

- **Ne:**
  - Görüşme (`chat_sessions`): kullanıcı, Workspace, başlık, oluşturulma, son etkinlik ve arşiv zamanı. Sesli görüşmenin başlığı ilk sorunun ilk 80 karakteridir ("Sesli görüşme: …").
  - Mesaj (`messages`): soru ve yanıtın tam metni, zamanı ve kaynak özeti (belge adı, kimliği, parça sırası, skor). Kaynak alıntısının metni saklanmaz.
- **Nerede:** PostgreSQL, `chat_sessions` ve `messages` tabloları. Sesli asistan (`/voice`) ve modAI Assistant (maskot) görüşmeleri saklanır. **RAG Chat sayfasındaki sorular saklanmaz.**
- **Neden:** görüşmeye kalınan yerden devam etmek. Son altı mesaj sonraki sorunun bağlamı olarak modele verilir.
- **Ne kadar:** `CONVERSATION_RETENTION_DAYS` ile belirlenir.
  - Varsayılan `180` (6 ay); boş değer de 180 sayılır. Şirket politikasına göre değiştirin.
  - `0`: kullanıcı ya da yönetici silene kadar.
  - `N > 0`: worker günde bir kez, son etkinliği N günden eski görüşmeleri mesajlarıyla birlikte siler. Silme kalıcıdır, 500'erli gruplar hâlinde yapılır (`app/services/conversation_retention.py`). Logda ve denetim günlüğünde (`conversation_retention_purge`, işlemi yapan: sistem) yalnızca sayılar yer alır.
  - Ayar değişikliği worker yeniden başlatılınca geçerli olur (`docker compose up -d worker`).
  - Arşivlemek görüşmeyi silmez.
- **Silme ve döküm:**
  - Kullanıcı: sesli asistanda görüşme seçicisinin yanında, RAG Chat'te **Kayıtlı görüşmeleriniz** bölümünde **Bu görüşmeyi sil** ve **Tüm görüşmelerimi sil**. **Tüm görüşmelerimi sil**, kullanıcının tüm Workspace'lerdeki görüşmelerini siler. Her ikisi de onay ister ve denetim günlüğüne yazılır (`assistant_conversation_deleted`, `assistant_conversations_deleted`). Kullanıcı başkasının görüşmesini silemez.
  - Yönetici: kişinin satırında **Görüşmelerini sil** (bkz. Talepler) ya da `DELETE /admin/users/{id}/conversations` (`user_conversations_deleted`).
  - Döküm: kişisel veri dökümü tüm soru ve yanıtları zamanlarıyla içerir.

## 5. Yanıtlanamayan sorular

- **Ne:** modAI'ın belgelerden yanıtlayamadığı sorunun metni (en fazla 2.000 karakter), aranan bilgi tabanları, neden ve zaman. Ayrıca Workspace başına günlük soru sayısı tutulur.
- **Nerede:** PostgreSQL, `unanswered_questions` ve `question_daily_counts` tabloları.
- **Neden:** eksik belgeleri bulmak.
- **Kişiyle bağ:** **kullanıcı kimliği saklanmaz.** Bir kayıt bir kişiye bağlanamaz, bu yüzden kişisel veri dökümünde yer almaz. Ancak çalışan soru metnine kendisi ya da başkası hakkında bilgi yazmış olabilir. Aynı soru, sesli asistanda ya da modAI Assistant'ta sorulduysa kişinin görüşmesinde de durur; görüşmeyi silmek bu kaydı silmez.
- **Ne kadar:** `UNANSWERED_RETENTION_DAYS` (varsayılan 90 gün). `UNANSWERED_REPORT_ENABLED=false` iken hiçbir şey kaydedilmez.
- **Silme ve döküm:** **Yönetim → Yanıtlanamayan sorular**: **Çözüldü** soruyu siler. **Tümünü sil** yalnızca admin'e açıktır ve Workspace'in tüm kayıtlarını siler. **CSV indir** raporu dışa aktarır.

**Yanıt geri bildirimleri (👍/👎):**

- **Ne:** 👍 için yalnızca Workspace, aranan bilgi tabanları ve zaman. 👎 için ayrıca soru (en fazla 2.000 karakter), modAI'ın yanıtı (en fazla 4.000 karakter), kaynak belge adları, seçilen neden ve çalışanın isteğe bağlı notu (en fazla 500 karakter).
- **Nerede:** PostgreSQL, `answer_feedback` tablosu (`app/services/answer_feedback.py`).
- **Neden:** yanlış ya da eski belgeyi bulup düzeltmek ve kalite sorularını genişletmek.
- **Kişiyle bağ:** **kullanıcı kimliği saklanmaz**; kayıt kişisel veri dökümünde yer almaz. Soru, yanıt ve not kişisel bilgi içerebilir. Kullanıcı başına dakikada 30 geri bildirim sınırı Redis'te kullanıcı kimliğiyle 60 saniye tutulur.
- **Ne kadar:** `UNANSWERED_RETENTION_DAYS` (varsayılan 90 gün).
- **Silme:** **Yönetim → Yanıtlanamayan sorular → Yanlış bulunan yanıtlar**: **Çözüldü** kaydı siler; **Kalite sorusu yap** soruyu bir Kalite sorusuna çevirir ve kaydı siler. İkisi de denetim günlüğüne metin olmadan yazılır (`answer_feedback_resolved`, `answer_feedback_to_quality_check`).

## 5b. Yanıt izi

- **Ne:** her tamamlanan yanıt için zaman, Organization, Workspace, aranan bilgi tabanları, soruyu soran kullanıcının kimliği, sonuç (yanıtlandı, belge bulunamadı, belgede yok dedi) ve kaynak olarak kullanılan **belge sürümleri** (belge kimliği, sürüm, dosya adı, kullanılan parça sayısı, en iyi benzerlik puanı).
  - **Soru, yanıt ve parça metni saklanmaz.**
- **Nerede:** PostgreSQL, `answer_traces` ve `answer_trace_sources` tabloları (`app/services/answer_traces.py`).
- **Neden:** hesap verebilirlik: bir belgenin yanlış olduğu anlaşıldığında hangi yanıtların ona dayandığını bulmak; hiç kullanılmayan belgeleri görmek.
- **Ne kadar:** `ANSWER_TRACE_RETENTION_DAYS` gün (varsayılan 180, 6 ay); worker günde bir kez eski kayıtları siler. `0` hiç kayıt tutmaz.
- **Kim görür:**
  - Workspace yöneticileri: belge başına kullanım sayısı ve izler, **kullanıcı olmadan** (**Belgeler → Yanıtlarda** sütunu).
  - Platform yöneticisi: **Yönetim → Denetim günlüğü → Yanıt izi**, kullanıcının e-postasıyla.
- **Silme:** **Hesabı sil** izlerdeki kullanıcı bağını kaldırır; izler belge bilgisiyle kalır.

## 6. Kalite kontrolü yanıtları

- **Ne:**
  - Kalite sorusu: soru metni ve beklentiler, soruyu ekleyen kullanıcının kimliği.
  - Çalıştırma: başlatan kullanıcının kimliği.
  - Sonuç: modelin yanıt metni ve kaynak listesi.
  - Sorular yöneticiler tarafından yazılır; yanıtlar belgelerden üretilir. Belgelerde kişisel veri varsa yanıtlarda da yer alabilir.
  - Güvenlik testleri (istem enjeksiyonu): sabit, uydurma metinlerle modelin yanıtı. Kişisel veri içermez; hiçbir bilgi tabanına eklenmez.
- **Nerede:** PostgreSQL, `quality_checks`, `quality_runs`, `quality_results` ve `quality_security_results` tabloları.
- **Neden:** yanıt kalitesini ölçmek.
- **Ne kadar:** süresiz. Silinen soru arşivlenir; eski sonuçlar sorusuyla birlikte kalır.
- **Silme ve döküm:** arayüzde sonuç silme yoktur. Sonuçlar Kalite sayfasında görünür. Soru ve yanıt metni loglara yazılmaz.

## 6b. Uzman onaylı yanıtlar

- **Ne:** soru ve onaylanan yanıt metni, bilgi tabanları, kaynak belge adları ve sürümleri, onaylayan, oluşturan ve (uzmana atanmışsa) atanan kullanıcının kimliği, tarihler, kullanım sayısı ve sorunun arama modelindeki vektörü.
- **Nerede:** PostgreSQL, `verified_answers` tablosu (`app/services/verified_answers.py`).
- **Neden:** doğruluğu bir uzmanca onaylanmış yanıtı aynı soruyu soranlara tutarlı biçimde vermek.
- **Ne kadar:** arşivlenene kadar. Onay geçerlilik tarihinde (varsayılan 6 ay) ya da kaynak belge değişince düşer; yanıt metni kalır.
- **Kim görür:** onaylı yanıtı, onun bilgi tabanlarında arama yetkisi olan herkes (yanıt olarak; onaylayanın adı gösterilmez). Onaylayan ve atanan kişinin e-postasını yalnızca o çalışma alanının yöneticileri görür.
- **Silme:** **Arşivle** yanıtın verilmesini durdurur, kaydı tutar. Hesap silinince kullanıcı bağları anonim hesaba kalır.

## 7. Yüklenen belgeler

Belgelerin kendisi kişisel veri içerebilir: bordro, özlük dosyası, müşteri listesi. Hangi belgelerin yükleneceğine müşteri karar verir.

- **Ne:**
  - Belge kaydı: dosya adı, belgeden çıkarılan metin, yükleyen kullanıcının kimliği, Organization, Workspace ve bilgi tabanı.
  - Her sürümün dosyası, SHA-256 özeti ve boyutu.
  - Arama dizini: metin parçaları, dosya adı ve yükleyenin kimliği.
  - **Ses ve video kayıtları:** yüklenen dosyanın kendisi (konuşanların sesi ve videodaki görüntüler kişisel veridir) ve otomatik konuşma dökümü. Döküm, belgeden çıkarılan metin olarak saklanır; ayrıca dosyanın yanında `.extracted.txt` olarak tutulur. Taranmış PDF ve görsellerin OCR metni de aynı şekilde saklanır.
  - Döküm ve OCR müşterinin sunucusunda yapılır; kayıt ya da görüntü dışarı gönderilmez.
- **Nerede:**
  - PostgreSQL: `documents` ve `document_versions` tabloları.
  - Dosyalar: `DATA_DIR` (Docker'da `modaidata` volume'u).
  - Qdrant: parça metinleri ve vektörler; BGE-M3 nesli kullanılıyorsa onun koleksiyonu da.
- **Neden:** belgelerden yanıt üretmek ve kaynağı göstermek.
- **Ne kadar:** süresiz.
- **Silme ve döküm:**
  - **Sil** mantıksal silmedir: belge listeden kalkar ve hiçbir yanıtta kullanılmaz.
  - Ancak bu sürümde çıkarılan metin PostgreSQL'de, dosyalar `DATA_DIR`'de, parçalar Qdrant'ta kalır. Değiştirilen belgelerin eski sürüm dosyaları da `DATA_DIR`'de kalır. BGE-M3 neslindeki parçalar nesil yeniden hazırlanınca kaldırılır.
  - Bir belgenin fiziksel olarak silinmesi gerekiyorsa bu bugün elle yapılan bir işlemdir.
  - Kişisel veri dökümü, kişinin yüklediği belgelerin yalnızca adını ve tarihlerini listeler, içeriğini içermez.

- **Toplantı tutanağı taslakları:** **Tutanak çıkar** ile worker belgenin çıkarılmış metninden bir taslak hazırlar. Taslak ve işin durumu Redis'te 24 saat tutulur (`modai:minutes:<belge>`), sonra kendiliğinden silinir. Taslak ancak bir yönetici **Bilgi tabanına kaydet** derse belge olur ve o andan itibaren bu bölümdeki belge kurallarına tabidir. Metin loglara yazılmaz; denetim günlüğünde yalnızca istek (`minutes_request`, belge kimliği ve sürümü) yer alır.

## 8. Ses

- **Sunucuda konuşma tanıma (varsayılan, "Sunucu · Whisper Small"):**
  - Sorunun ses kaydı oturum açmış kullanıcının tarayıcısından şirketin kendi modAI API'sine gönderilir (`POST /voice/transcribe`; 16 kHz, en çok 60 saniye). Üçüncü bir tarafa gitmez.
  - API kaydı bellekte yazıya çevirir (Whisper Small, faster-whisper) ve yanıtı döndürünce bırakır. Kayıt diske, veritabanına, yedeğe ya da loglara yazılmaz; tanınan metin de bu adımda saklanmaz ve loglanmaz. Loglarda yalnızca kaydın süresi, boyutu ve işlem süresi yer alır.
  - Kullanıcı başına dakikada 30 istek sınırı için Valkey'de yalnızca kullanıcı kimliğiyle bir sayaç tutulur (60 saniye).
- **Cihazda konuşma tanıma ("Cihazda · Whisper Tiny/Base"):** konuşma tanıma tarayıcıda çalışır; ses kaydı tarayıcı belleğinde kalır ve sunucuya gönderilmez.
- **Ses sentezi** (EMA Lightning) her iki seçenekte de tarayıcıda çalışır; yanıt metni sunucuya ses olarak geri gönderilmez.
- **Tanınan metin:** kullanıcı soruyu gönderince metin soru olarak işlenir ve görüşmeye kaydedilir (4. bölüm). Yanıtlanamadıysa rapora da eklenir (5. bölüm). Gönderilmeyen (vazgeçilen) metin hiçbir yerde kalmaz.
- **Tarayıcıda kalanlar:**
  - Konuşma ve ses modelleri tarayıcı önbelleğinde tutulur.
  - Hız, dil, konuşma tanıma seçimi ve "soruyu göster" tercihleri `localStorage`'da tutulur.
  - Süre ölçümleri yalnızca `modai.voice.debug` bayrağıyla ve yalnızca sayfa belleğinde tutulur.

## 9. Oturum ve tarayıcı verileri

- **Valkey** (`redis` servisi; her kaydın bir süresi vardır ve süre dolunca silinir):
  - Oturum yenileme kaydı: rastgele bir kimlik ve kullanıcı kimliği. `REFRESH_TOKEN_EXPIRE_DAYS` (varsayılan 7 gün) sonra silinir.
  - WebSocket bileti: kullanıcı kimliği ve rolü, 60 saniye, tek kullanımlık.
  - İstek sınırlama sayaçları: girişte IP adresine, soruda kullanıcı kimliğine göre tutulur ve 60 saniye ile 1 saat arasında silinir.
- **Tarayıcı:**
  - `localStorage`: erişim belirteci (kullanıcı kimliği ve rol, `ACCESS_TOKEN_EXPIRE_MINUTES`, varsayılan 30 dakika), seçili Workspace, tema, maskot konumu ve ses tercihleri.
  - Yenileme belirteci `HttpOnly` çerezde tutulur.
  - Davet bağlantısı yalnızca giriş sırasında `sessionStorage`'da tutulur.

## 10. Uygulama logları

- **Ne:**
  - Production'da (`APP_ENV=production`) API her istek için JSON biçiminde bir satır yazar (`app/main.py`). Satırda kullanıcı kimliği, Workspace kimliği, durum kodu, süre ve istek kimliği bulunur.
  - Uvicorn erişim logu istemci adresini ve sorgu dizesiyle birlikte istek yolunu yazar. Örneğin kullanıcı aramasındaki e-posta adresi sorgu dizesine girer.
  - Arayüzün Nginx'i, imajın varsayılan erişim logunu yazar: IP adresi, istek yolu, tarayıcı bilgisi (user agent) ve `X-Forwarded-For`.
  - Worker logları iş kimliklerini ve sayıları içerir.
  - Soru, yanıt ve belge metni bilinçli olarak loga yazılmaz. Hata kayıtlarının çoğu yalnızca hata türünü içerir; belge yükleme ve silme hatalarında Python hata izi (traceback) de yazılır.
- **Nerede:** kapsayıcıların standart çıktısı (`docker compose logs`).
- **Ne kadar:** en çok 6 ay.
  - Compose dosyaları her hizmetin logunu boyuta göre döndürür: en çok 5 dosya × 10 MB (`docker-compose.yml`, `x-logging`). Eski dosyalar kendiliğinden silinir.
  - Docker logları tarihe göre döndüremez. Kapsayıcı yeniden oluşturulunca logları silinir; her güncelleme bunu yapar.
  - Altı ay içinde güncelleme yapılmadıysa kapsayıcıları yeniden oluşturun: `docker compose up -d --force-recreate`. Bu kısa bir kesinti demektir; [kurulum rehberinin](kurulum-ve-teslim-rehberi.md) bakım takvimine bakın.
- **Silme:** yukarıdaki yeniden oluşturma. Ayar, kapsayıcı bir sonraki oluşturuluşunda geçerli olur.
- Ollama aynı makinede çalışır. Soru, belge parçaları ve son mesajlar ona istem olarak gönderilir. Ollama'nın kendi log ayarı müşterinin kurulumundadır.

## 11. Yedekler

- **Ne:** `scripts/backup_local.sh` PostgreSQL'in tamamını (yukarıdaki tüm tablolar), Qdrant verisini ve `modaidata` dosyalarını bir klasöre kopyalar. Dosya izinleri yalnızca sahibine açıktır (umask 077).
- **Nerede:** komuta verilen klasör.
- **Ne kadar:** varsayılan 180 gün (6 ay).
  - Betik her başarılı yedekten sonra aynı klasördeki, adındaki tarihe göre `BACKUP_RETENTION_DAYS` günden eski `modai-YYYYMMDDTHHMMSS` klasörlerini siler. Başka adlı klasörlere ve dosyalara dokunmaz.
  - `BACKUP_RETENTION_DAYS=0` hepsini tutar.
  - modAI yedek almayı zamanlamaz. Yedeği başka bir diske ya da yere kopyalıyorsanız oradaki kopyaları da aynı süreyle silin.
- **Silme:** silinen görüşmeler ve kayıtlar eski yedeklerde durmaya devam eder.
  - Bir yedekten geri dönülürse, yedek tarihinden sonra yapılmış silmeler yeniden uygulanmalıdır.
  - Geri yükleme denetim günlüğünü de yedek anına döndürür. Bu yüzden silme taleplerinin kaydını yedekten ayrı tutun.

## Talepler

**Erişim talebi (kişi hangi verilerinin tutulduğunu soruyor):**

1. **Yönetim → Kullanıcılar** (platform yöneticisi) ya da **Yönetim → Üyelikler** (tenant yöneticisi) sayfasında kişinin satırında **Kişisel veri dökümü (JSON)**'a basın. API karşılığı `GET /admin/users/{id}/personal-data`'dır.
   - Dosyada hesap, üyelikler, davetler, asistan tercihleri, tüm görüşmeler (soru ve yanıtlar, zamanlarıyla) ve yüklenen belgelerin adları yer alır.
   - Tenant yöneticisinin dökümü yalnızca yönettiği Organization'ların verilerini içerir. Başka bir Organization'ın çalışanı için "bulunamadı" döner.
2. Döküm denetim günlüğüne `personal_data_export` olarak, yalnızca sayılarla yazılır.
3. Dökümde olmayanlar:
   - Denetim kayıtları: gerekirse platform yöneticisi çıkarır (3. bölüm).
   - Yanıtlanamayan sorular: kişiye bağlanamaz (5. bölüm).
   - Loglar ve yedekler.

**Silme talebi:**

1. Görüşmeler: kişi **Tüm görüşmelerimi sil** ile kendisi silebilir. Yönetici kişinin satırında **Görüşmelerini sil**'e basar ya da `DELETE /admin/users/{id}/conversations` çağırır.
   - Tenant yöneticisi yalnızca kendi Organization'ındaki görüşmeleri, platform yöneticisi tüm görüşmeleri siler.
   - Silme kalıcıdır ve `user_conversations_deleted` olarak sayılarla kaydedilir.
2. Yanıtlanamayan sorular: kişi metnini belirtirse rapor sayfasında bulunup **Çözüldü** ile silinir.
3. Üyelikler **Kaldır** ile silinir. Kişinin tüm hesabı için platform yöneticisi **Yönetim → Kullanıcılar → Hesabı sil**'i kullanır (1. bölüm). Belge içeriğinin fiziksel silinmesi bu sürümde elle yapılır (7. bölüm).
4. Yedekler ve loglar için 10. ve 11. bölüme bakın.

Görüşmeler için şirket politikanıza uygun bir saklama süresini `CONVERSATION_RETENTION_DAYS` ile ayarlayın.

Bu belge hukuki görüş değildir.
