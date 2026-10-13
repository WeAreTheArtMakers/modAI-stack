# Sesli asistan — kabul listesi

Bu liste, sesli asistanın (`/voice`) bir kurulumda teslime hazır olduğunu doğrulamak içindir: ilk kurulumdan sonra, her güncellemeden sonra ve müşteriye gösterimden önce. Sürümden bağımsızdır. Kurulum, güncelleme ve geri alma adımları [kurulum ve teslim rehberindedir](kurulum-ve-teslim-rehberi.md); sürüme özel notlar [sürüm notlarındadır](../../CHANGELOG.md). Sonuçlar [teslim ve kabul formuna](../sales/teslim-ve-kabul.md) yazılır.

## 1. Ön koşullar

- [ ] Uygulama HTTPS üzerinden ya da aynı makinede `http://localhost` ile açılır. Mikrofon başka türlü açılmaz; `/voice`'ta "Mikrofon yalnızca güvenli bağlantıda çalışır" uyarısı görünmemelidir.
- [ ] Tarayıcı güncel masaüstü Chrome ya da Edge'dir.
- [ ] `python3 scripts/fetch_voice_models.py --check` hatasız biter (Türkçe ses modeli ve cihazda tanıma modelleri). Whisper Base de sunulacaksa modeller `--include-optional` ile indirilmiştir.
- [ ] `python3 scripts/fetch_transcription_models.py --check` hatasız biter. Sunucuda konuşma tanıma, ses ve video belgelerinin dökümüyle aynı modeli (Whisper Small) kullanır.
- [ ] Oturum açıkken `GET /api/voice/config` yanıtında `"server_transcription": true` vardır. Oturumsuz istek 401 alır.
- [ ] API konteynerinin belleğinde Whisper Small için yer vardır: model yüklüyken API süreci yaklaşık 0,65–0,9 GB daha fazla kullanır ([kapasite ve donanım](kapasite-ve-donanim.md)).
- [ ] Denemeler yalnızca kurgusal belgelerle (`demo/voice-knowledge-pack/`) ya da müşterinin yazılı onay verdiği belgelerle yapılır. Doğrulanmış örnek sorular ve sunum akışı aynı klasördeki `voice-demo-guide.md` dosyasındadır.

## 2. İlk açılış

- [ ] `/voice` açılır. **Konuşma tanıma** seçiminde "Sunucu · Whisper Small (önerilen)" seçilidir (bu tarayıcıda daha önce başka bir seçenek seçilmediyse; seçim tarayıcıda hatırlanır).
- [ ] Sayfanın altındaki not şunu söyler: "Ses kaydınız şirketinizin modAI sunucusunda yazıya çevrilir; saklanmaz ve kaydedilmez."
- [ ] **Ses modelini hazırla** yalnızca Türkçe ses modelini indirir (ilk kullanımda yaklaşık 63 MB) ve ilerlemeyi gösterir; Whisper indirilmez. Ardından rozetlerde "Konuşma tanıma · Sunucu · Whisper Small" ve "Nöral Türkçe ses" görünür.
- [ ] Sayfa kapatılıp yeniden açıldığında ses modeli önbellekten gelir; yeniden indirilmez.
- [ ] Sayfada İngilizce metin, geliştirici ölçümü ya da "deneme" etiketi görünmez.

## 3. Konuşma tanıma

- [ ] Basılı tut, konuş, bırak; ayrıca dokun, konuş, tekrar dokun. İkisi de çalışır. Kayıt sırasında "Mikrofon kaydediyor" görünür; kayıt 30 saniyede kendiliğinden biter.
- [ ] Müşteriyle seçilen 10 Türkçe soru sesli sorulur. "Göndermeden önce soruyu göster" açıkken anlaşılan soru gösterilir, yanlış kelime düzeltilip gönderilir. Kaç sorunun düzeltme gerektirdiği forma yazılır.
- [ ] Aynı sorulardan birkaçı "Cihazda · Whisper Tiny" ile tekrarlanır. Seçim sayfa yenilenince korunur; geri "Sunucu"ya alınabilir.
- [ ] Sessiz ya da çok kısa bir kayıt "Konuşma anlaşılamadı" der ve soru gönderilmez.
- [ ] (Staging'de) sunucu modeli bağlı değilken (`TRANSCRIPTION_MODEL_ROOT` boş bir klasörü gösterir) **Konuşma tanıma** seçiminde Sunucu seçeneği yoktur ve Whisper Tiny seçilidir. Sayfa açıkken model kaldırılırsa sesli soru Türkçe bir hata ve **Cihazda tanımaya geç (Whisper Tiny)** düğmesi gösterir.

## 4. Yanıt ve ses

- [ ] Yanıt kaynak kartlarıyla gelir. Ses yanıtın tamamı beklenmeden başlar. **Durdur** sesi ve üretimi hemen keser.
- [ ] "Yanıt dili" Türkçe'dir (varsayılan). İngilizce belgeye dayanan yanıt da Türkçe gelir; Türkçe olmayan cümle sesle okunmaz ve bu yanıtın altında belirtilir.
- [ ] Selamlaşma ("Merhaba") belgelerde aranmadan yanıtlanır ve görüşmeye kaydedilmez.
- [ ] Bir talep türüne uyan soruda (ör. "Gelecek pazartesiden itibaren 3 gün izin almak istiyorum") yanıtın altında "modAI bu işi sizin için başlatabilir" önerisi çıkar; bağlantı formu sorudan doldurulmuş açar.
- [ ] Hız seçimi (1,00×–1,15×) ve sesli yanıtı kapatma çalışır. Nöral ses başlatılamazsa "Sistem sesi (yedek)" etiketi görünür.

## 5. Görüşmeler ve gizlilik

- [ ] Tamamlanan yanıtlar görüşmeye kaydedilir; `/voice`'a dönüldüğünde son görüşme otomatik çalmadan geri yüklenir. Durdurulan yanıtların kaydedilmediği ekranda yazar.
- [ ] **Bu görüşmeyi sil** ve **Tüm görüşmelerimi sil** onay ister ve görüşmeleri siler.
- [ ] Sesli bir sorudan sonra API logunda (`docker compose logs api`) yalnızca "Voice question transcribed: … ms of audio, … bytes, … ms on the server" gibi sayılar vardır; sorunun metni ve ses yoktur. Veri klasöründe ses dosyası oluşmaz.
- [ ] 10 dakika sesli soru gelmediğinde API logunda "Voice transcription model released …" satırı görülür (bellek geri verilir); sonraki soru modeli birkaç saniyede yeniden yükler.

## 6. Telefon ve tablet

- [ ] Telefonda (390 px genişlik) ve tablette sayfa yana kaymaz; seçimler, düğmeler ve yanıtlar ekrana sığar.
- [ ] Telefonda sunucuda tanımayla bir soru sorulur ve yanıt dinlenir (HTTPS gerekir).

## 7. Kanıt

- [ ] Ölçüm gerekirse tarayıcıda `localStorage["modai.voice.debug"] = "1"` yapılır. Her yanıtın altında süreler görünür; **Test ölçümlerini kopyala** sonuçları panoya alır. Çıktı forma eklenir, sonra bayrak kaldırılır (`localStorage.removeItem("modai.voice.debug")`).

## Müşteriye söylenecek sınırlamalar

- **Ses tanıma hatasız değildir.** Whisper Small özel adları, kısaltmaları ve gürültülü kayıtları yanlış duyabilir. Bu yüzden soru göndermeden önce gösterilir ve düzeltilebilir; kelimeler sessizce değiştirilmez.
- **Kaynak kontrolü:** model zaman zaman yanlış satırı ya da belgeyi seçebilir; önemli kararlardan önce kaynak kartı açılmalıdır.
- **Sürüm seçimi:** eski ve güncel politika birlikte yanıtlara açıksa sistem hangisinin geçerli olduğunu bilemez; eski sürüm arşivlenmelidir.
- **Desteklenmeyenler:** hesaplama soruları (toplamlar), PDF ya da birleşik hücreli tablolar.
- **Diller arası arama:** çok dilli arama profili (BGE-M3) etkin değilse Türkçe soruyla İngilizce belge bulunmaz.
- **Gecikme donanıma bağlıdır:** ilk ses, dil modelinin bellekte olup olmamasına ve makinenin yüküne göre değişir. `/voice` açıldığında ve kayıt başladığında model önceden ısıtılır. Ölçümler [kapasite ve donanım](kapasite-ve-donanim.md) belgesindedir.

## Bellek

- **API:** Whisper Small yüklüyken yaklaşık 0,65–0,9 GB ek (10 dakika soru gelmezse bırakılır). Çok dilli arama (BGE-M3) etkinken API ve worker'ın her biri yaklaşık 2 GiB daha kullanır.
- **Dil modeli:** gemma3:4b yüklüyken Ollama yaklaşık 4,6 GB kullanır.
- **Tarayıcı sekmesi:** cihazda tanımada Whisper Tiny ile yaklaşık 1,3 GB, Base ile yaklaşık 1,8 GB. Sunucuda tanımada sekmede yalnızca ses modeli çalışır.
- [ ] Gösterim makinesinde yalnızca bir yığın çalışır (production ya da staging, ikisi birden değil); ağır uygulamalar kapatılır. 16 GB'lık makinede tek yığın, 250'den fazla çalışan için 32 GB önerilir.
