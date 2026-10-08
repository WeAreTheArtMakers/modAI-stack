# Atlasnova demo bilgi paketi (modAI Voice)

**Tamamen kurgusal** bir şirkete ait 14 Markdown belgesi. modAI Voice ve RAG Chat'i müşteriye gösterirken kullanılır. Gerçek bir şirkete, kişiye, müşteriye veya kimlik bilgisine ait içerik yoktur. E-posta adresleri `.example` alan adını kullanır. Politikalar hukuki ya da mevzuat gerekliliği olarak sunulmaz.

## İçerik

| Grup | Belge | Dil | Durum |
|---|---|---|---|
| İnsan Kaynakları | `ik/yillik-izin-ve-devamsizlik-politikasi-v3.md` (IK-POL-001) | TR | Güncel |
| İnsan Kaynakları | `ik/uzaktan-ve-hibrit-calisma-politikasi-v2.md` (IK-POL-004) | TR | Güncel |
| İnsan Kaynakları | `ik/calisan-yan-haklari-ve-onaylar.md` (IK-PRS-007) | TR | Güncel |
| BT | `bt/vpn-and-remote-access-troubleshooting.md` (IT-KB-012) | EN | Güncel |
| BT | `bt/parola-ve-cihaz-guvenligi-politikasi.md` (BG-POL-002) | TR | Güncel |
| BT | `bt/bt-destek-ve-eskalasyon-proseduru.md` (BT-PRS-005) | TR | Güncel |
| Finans ve Operasyon | `finans/seyahat-ve-harcama-politikasi-2026.md` (FIN-POL-003) | TR | Güncel |
| Finans ve Operasyon | `finans/ESKI-seyahat-ve-harcama-politikasi-2025.md` (FIN-POL-003 v2025.2) | TR | **Eski — yürürlükten kalktı** |
| Finans ve Operasyon | `finans/satin-alma-ve-onay-limitleri.md` (FIN-PRS-010) | TR | Güncel |
| Finans ve Operasyon | `finans/masraf-iade-proseduru.md` (FIN-PRS-012) | TR | Güncel |
| Ürün ve Müşteri Desteği | `destek/customer-support-sla.md` (CS-SLA-001) | EN | Güncel |
| Ürün ve Müşteri Desteği | `destek/incident-escalation-guidelines.md` (CS-PRS-004) | EN | Güncel |
| Ürün ve Müşteri Desteği | `destek/atlasdesk-urun-destek-talimatlari-v3.md` (DST-TLM-003 v3.0) | TR | Güncel |
| Ürün ve Müşteri Desteği | `destek/ESKI-atlasdesk-urun-destek-talimatlari-v2.md` (DST-TLM-003 v2.0) | TR | **Eski — geçersiz** |

On iki konu belgesi güncel. İki eski sürüm sürüm seçimini sınamak için **bilerek** eklendi ve hem dosya adında hem belge başında açıkça etiketlendi. Benzer ifadeler de bilerek kullanıldı ve farklı yanıtlara karşılık geliyor:
- şirket içi BT "P1" ile müşteri "Severity 1";
- 5.000 TL'lik eğitim onayı ile 5.000 TL'lik masraf onayı;
- izin için "10 iş günü önce" ile yurt dışından çalışma için "15 iş günü önce".

- `questions.md` / `questions.json`: 36 soru (12 basit, 8 çok belgeli, 6 zor, 4 diller arası, 6 yanıtlanmaması gereken). Her soru için beklenen kaynak, bölüm ve yanıt verilir.
- `voice-demo-guide.md`: sunum için önerilen 10 soru ve akış. Ayrıca mevcut MiniLM gömme modeliyle hangi soruların doğru belgeyi bulamadığını ölçülmüş olarak listeler (özellikle Türkçe soru / İngilizce belge).

Her belge 175–370 kelimedir. Varsayılan 700 kelimelik parçalamada her belge tek parça olarak indekslenir; kaynak kartında belgenin tamamı görünür.

## Güvenli içe aktarma

Bu paket otomatik olarak hiçbir yere yüklenmez. Yalnızca bu amaçla yetkilendirilmiş, müşteri veya üretim verisi içermeyen ayrı bir demo alanına yükleyin.

1. **Ayrı bir demo alanı kullanın.** Platform yöneticisi olarak, gerekiyorsa yalnızca demo için bir Organization ve Workspace oluşturun (örneğin "Demo — Atlasnova (kurgusal)"). Gerçek müşteri veya şirket belgeleri içeren bir Workspace'e **yüklemeyin**.
2. **Knowledge Base oluşturun.** Workspace içinde "Atlasnova Demo" adlı yeni bir Knowledge Base açın.
3. **Belgeleri yükleyin.** Knowledge Base sayfasında `ik/`, `bt/`, `finans/` ve `destek/` klasörlerindeki 14 `.md` dosyasını sürükleyip bırakın. `README.md`, `questions.md`, `questions.json` ve `voice-demo-guide.md` dosyalarını **yüklemeyin**; bunlar yanıtları içerir.
4. **İndekslemeyi bekleyin.** Tüm belgeler **Hazır** olana kadar bekleyin.
5. **Deneyin.** `/voice` sayfasında yalnızca "Atlasnova Demo" Knowledge Base'ini seçin ve `voice-demo-guide.md`'deki soruları deneyin.
6. **Yalnızca güncel belgeler isterseniz** iki `ESKI-` dosyasını yüklemeyin. D01–D04 soruları o zaman eski sürüm tuzağını sınamaz.
7. **Kaldırma.** Demo bittiğinde Knowledge Base'i veya demo Workspace'ini silin.

Embedding modeli, Qdrant koleksiyonu, parçalama ayarları ve veritabanı şeması bu paket için değiştirilmez; belgeler normal yükleme akışıyla indekslenir.
