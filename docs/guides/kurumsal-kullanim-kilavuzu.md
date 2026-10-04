# modAI-stack Kurumsal Kullanım Kılavuzu

Bu kılavuz şirket yöneticileri, ekip yöneticileri ve çalışanlar içindir. Ekran adları mevcut Web Console ile eşleşir.

## modAI-stack nedir?

modAI-stack, şirket belgeleri üzerinde yerel yapay zekâ ile soru-cevap yapmanızı sağlar. Belgeler bilgi tabanlarına yüklenir, indekslenir ve RAG Chat yanıtlarında kaynak kartlarıyla gösterilir. Yanıtları önemli kararlardan önce kaynak belgelerle karşılaştırın.

## Giriş ve bilgi hiyerarşisi

Size verilen hesapla giriş yapın. Sol üstte erişebildiğiniz **Workspace**'i seçin. Hiyerarşi şöyledir:

**Organization → Workspace → Knowledge Base → Belge**

Organization şirket sınırıdır. Workspace ekip/çalışma alanıdır. Knowledge Base aynı konuya ait belgeleri toplar. Yalnızca üyeliğinizin kapsadığı alanları görür ve sorgularsınız.

## Roller

| Rol | Yetki |
| --- | --- |
| Platform Admin | Platform kullanıcılarını ve Organization yapılandırmasını yönetir; tenant belgelerine otomatik erişmez. |
| Organization Admin | Kendi Organization'ındaki üyelikleri ve çalışma alanlarını yönetir; kapsamındaki belgeleri kullanabilir. |
| Manager | Yetkili Workspace'te Knowledge Base ve belgeleri yönetir, RAG kullanır. |
| User | Yetkili Knowledge Base'leri okur ve RAG kullanır; yönetim/yükleme yapmaz. |

## İlk kurulum

1. Platform yöneticisi **Yönetim → Organization'lar** ekranından şirket Organization'ını oluşturur.
2. **Yönetim → Üyelikler** ekranında ilgili Organization'ı seçip **Kendimi Organization Admin yap** düğmesine basar. Bu açık işlem platform rolünü değiştirmez; yalnızca seçili Organization için tenant üyeliği oluşturur veya mevcut Organization üyeliğini yükseltir.
3. **Yönetim → Workspaceler** ekranında Workspace oluşturur. Üyelik güncellenince sol üst Workspace listesi yeniden yüklenir; çıkış/giriş gerekmez.
4. **Knowledge Base'ler → Yeni Knowledge Base** ile ilk bilgi tabanını oluşturur.
5. **Belgeler** veya Knowledge Base ayrıntısından PDF, DOCX, TXT ya da Markdown belgesini yükler.
6. Belge **Hazır** olunca **RAG Chat**'te Knowledge Base'i seçip soru sorar.

Dashboard'daki **Kurumsal alanınızı hazırlayın** kartı eksik adımları gerçek erişim ve belge durumuna göre gösterir.

## Belge indeks durumu

- **Kuyrukta (queued):** Yükleme kabul edildi, işçi bekleniyor.
- **İşleniyor (processing):** Metin çıkarma, parçalama, embedding ve vektör indeksleme sürüyor.
- **Hazır (ready):** Belge RAG sorgularında kullanılabilir.
- **Hatalı (failed):** Yönetici hata ayrıntısını inceler ve uygun ise yeniden indeksler.

Hazır olmayan bir belgeden yanıt beklemeyin.

## RAG Chat ve kaynak kartları

Chat yalnızca seçilen Workspace'teki yetkili Knowledge Base'leri sunar. Birden çok kaynak seçebilirsiniz. Bilgi tabanı ayrıntısındaki **Bu kaynaklarla chat** bağlantısı o bilgi tabanını önceden seçer. Yanıt altında kaynak kartları belge adını, ilgili parça numarasını, skoru ve açılabilir alıntıyı gösterir. Kaynak görünmüyorsa cevabın belgeye dayandığını varsaymayın.

## Çalışan ekleme ve davet kabulü

**Üyelikler → Mevcut hesabı ekle**, yalnızca platformda zaten kayıtlı bir hesaba üyelik verir. Yeni çalışan için **Yeni çalışan davet et** bağlantısıyla **Davetler** ekranını kullanın. Davet e-postasını, rolünü ve gerekiyorsa Workspace kapsamını seçin. Oluşan tek kullanımlık bağlantıyı güvenli bir kanaldan iletin; bağlantı yalnızca oluşturulurken gösterilir.

Davetli kişi bağlantıyı açıp mevcut hesabıyla giriş yapar veya yeni hesap için kendi şifresini belirler. Davet e-postaya bağlıdır, süreli ve tek kullanımlıktır. Davet bağlantısını genel kanallarda paylaşmayın.

## Model ve Sistem ekranları

**Modeller** ekranı yerel üretim ve embedding modelinin durumunu gösterir. Model yönetimi platform yetkisine bağlıdır. **Sistem** ekranı API, PostgreSQL, Redis, Qdrant, Ollama ve embedding hazırlığını gösterir; arama profili burada salt okunurdur.

## Güvenlik notları

Platform yöneticiliği Organization belgelerine örtük erişim vermez. Üyelikleri yalnızca gerekli Organization/Workspace kapsamına verin. Davet bağlantısı bir erişim sırrıdır; kopyalarken dikkatli olun. Şifreleri veya erişim bağlantılarını destek mesajlarına yapıştırmayın.

## Sık karşılaşılan durumlar

**Workspace neden boş?** Hesabınıza henüz Workspace erişimi verilmemiş olabilir. Platform yöneticisiyseniz Organization üyeliğinizi ve Workspace'i hazırlayın; çalışan iseniz Organization yöneticinize başvurun.

**Knowledge Base oluştur butonu neden görünmüyor?** Workspace'te manager/admin rolü gerekir. User rolü yalnızca okuma ve sorgulama içindir.

**RAG Chat neden pasif?** Erişilebilir Workspace veya Knowledge Base olmayabilir. Önce bu alanları hazırlayın ve en az bir belgenin hazır olmasını bekleyin.

**“User not found” ne anlama geliyor?** E-posta ile mevcut hesap bulunamadı. Yeni çalışan için Davetler ekranından davet oluşturun.

**Belgem ne zaman kullanılabilir?** Belgeler ekranında durum **Hazır** olunca. Uzun süre İşleniyor veya Hatalı kalırsa yöneticinize bildirin.
