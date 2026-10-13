# modAI Kutusu: kurulu gelen cihaz

modAI Kutusu, modAI kurulmuş olarak teslim edilen ayrı bir bilgisayardır. Müşteri cihazı şirket ağına takar, tarayıcıda açar ve etiketteki kurulum koduyla ilk yöneticiyi oluşturur. BT ekibinin Docker, model ya da sunucu kurmasına gerek kalmaz.

## Neden cihaz?

- **Satın alma kolaylaşır.** "Sunucu ayırın, Docker kurun, modeli indirin" yerine "kutuyu prize ve ağa takın" denir. Küçük ve orta şirketlerde BT ekibi çoğu zaman tek kişidir.
- **Veri şirketin içinde kalır.** Belgeler, arama dizini, modeller ve yedekler kutunun diskindedir. İnternet bağlantısı gerekmez. Güncellemeler çevrimdışı paketle gelir.
- **Bilinen donanımla bilinen performans elde edilir.** Kapasite tablosu bu donanım için ölçülür ve teslimde yük testiyle doğrulanır.

## Modeller (SKU)

Kapasite rakamları [kapasite ve donanım rehberinden](../guides/kapasite-ve-donanim.md) alınmıştır. **Ölçülen** ve **tahmin** olanlar ayrı belirtilir. Fiyatlar donanım tedarikine göre ayrıca verilir.

| Model | Donanım | Çalışan | Varsayılan model | Dayanak |
|---|---|---|---|---|
| **Kutu S** | Mac mini (Apple M4, 16 GB, 512 GB SSD) ya da eşdeğeri x86 mini PC (8 çekirdek, 16 GB) | 250'ye kadar rahat, 500'e kadar güvenli | gemma3:4b | 16 GB Apple silicon üzerinde **ölçüldü** (M1 Pro referansı); M4 aynı ya da daha hızlıdır, teslimde ölçülür |
| **Kutu M** | Mac mini (M4 Pro, 48 GB, 1 TB SSD) ya da x86 ve 16 GB NVIDIA ekran kartı, 32 GB bellek | 250–1.000 | gemma3:4b; qwen3.5:9b sınanırsa | **Tahmin**: satıştan önce yük testi |
| **Kutu L** | 64 GB bellek ve 24 GB NVIDIA ekran kartı (RTX 4090 / L4), 2 TB SSD, raf tipi | 1.000–3.000 | qwen3.5:9b | **Tahmin**: satıştan önce yük testi |

Bütün modellerde:

- bir ikinci disk ya da ağ klasörüne gece yedeği kopyası (`BACKUP_MIRROR_DIR`);
- kesintisiz güç kaynağı (UPS) önerilir. Kutu, elektrik gidip gelince kendiliğinden açılır (`pmset autorestart` ya da BIOS ayarı).

## Kutuda neler var?

- modAI'nin teslim edilen sürümü (çevrimdışı paket). Admin'in seçebileceği bütün yerel modeller kutuda kurulu gelir.
- Çok dilli arama modeli (BGE-M3) ve ses modelleri (Whisper).
- **Ağ adı:** `http://modai.local:5173`. DNS kaydı gerekmez. HTTPS ve şirket adı için kurulum rehberi bölüm 8'e bakın.
- **İlk kurulum sayfası:** kodla ilk yönetici, şirket ve ilk workspace oluşturulur. Bir yönetici oluşunca sayfa kalıcı olarak kapanır.
- **Bekçi:** 5 dakikada bir sağlık kontrolü yapar. Durmuş servisi başlatır, takılanı yeniden başlatır ve disk dolmadan uyarır (`data/logs/watchdog.log`).
- **Gece yedeği:** her gece 03:15'te alınır. Yedekler katmanlı tutulur: 14 günlük, 8 haftalık, 6 aylık.
- **Active Directory ile giriş, SSO (Entra ID, Okta, Google), SCIM.** Ağ klasörü ve SharePoint eşitlemesi, kurulum rehberindeki ayarlarla açılır.

## Hazırlama (bizim tarafımızda)

1. Donanım: işletim sistemi güncel, disk şifrelemesi açık (FileVault ya da LUKS).
2. Docker ve Ollama kurulu. Paket klasörü kutuya kopyalanmış.
3. `sh scripts/appliance_setup.sh` çalıştırılır. Ağ adı, güç ayarları, modAI kurulumu, kurulum kodu, bekçi ve gece yedeği kurulur. Betik etiket metnini ve elle yapılacakların listesini yazar. Önce `--dry-run` ile adımlar gözden geçirilir.
4. Yük testi yapılır: `docker compose exec -T api python -m app.tools.load_test --workspace-id <id>`. Sonuç teslim tutanağına yazılır. Test, geçici bir workspace'te ve kurulum kodu girilmeden önce bootstrap yöneticisiyle **yapılmaz**. Ölçüm, aynı donanımdaki bir referans kutuda yapılır.
5. Etiket: adres, kurulum kodu, sürüm ve destek iletişimi.
6. Elektrik kesintisi denemesi yapılır: fiş çekilip takılır ve kutunun birkaç dakika içinde açıldığı görülür.

Kurulum kodu kaybolursa yeni kod üretilir: `sh scripts/appliance_setup.sh --new-code`. Bunun için kutuya yerel erişim gerekir. Eski kod geçersiz olur.

## Teslim (müşteri tarafında)

1. Kutu ağa ve prize takılır.
2. Bir bilgisayardan `http://modai.local:5173` açılır. Kurulum sayfası gelir.
3. Etiketteki kod, şirket adı, ilk workspace ve yönetici e-postası ile şifresi girilir. Konsol açılır.
4. Kurulum rehberi "teslim ve kabul" listesi uygulanır: [teslim-ve-kabul.md](teslim-ve-kabul.md).

## Sınırlar (dürüstçe)

- **Tek kutu yerine iki kutu:** ikinci bir kutu sıcak beklemede tutulabilir (`standby_sync.sh`). Bu kutu her gece ana kutunun yedeğiyle güncellenir ve arızada ad yönlendirilerek dakikalar içinde devralır. Otomatik devralma yoktur. Yedeklerin geri yüklenebildiği `restore_drill.sh` ile kanıtlanır; üretim yedeğinde veri kısmı 12 saniye sürdü.
- **Bağımsız sızma testi henüz yapılmadı.** İç kontroller (her uç için otomatik yetki taraması, bağımlılık taraması, SBOM) her sürümde çalışır. Güvenlik mimarisi [guvenlik-mimarisi.md](../guides/guvenlik-mimarisi.md) belgesinde anlatılır. Bağımsız test, satıştan önce planlanan bir sahip işidir.
- Kutu M ve L için kapasite rakamları tahmindir. Satıştan önce o donanımda yük testi yapılır.

İletişim: info@wearetheartmakers.com · +90 505 314 9360 · güvenlik bildirimleri: admin@wearetheartmakers.com
