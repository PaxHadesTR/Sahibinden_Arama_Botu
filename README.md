# 🤖 Sahibinden Discord Arama & Bildirim Botu

[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.15-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.7+-5865F2.svg?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-45ba4b.svg?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Coolify](https://img.shields.io/badge/Coolify-Supported-6B46C1.svg)](https://coolify.io/)
[![SpoofDPI + WARP](https://img.shields.io/badge/Turkey%20DPI%20Bypass-SpoofDPI%20%2B%20WARP-F38020.svg?logo=cloudflare&logoColor=white)](https://developers.cloudflare.com/warp-client/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Sahibinden.com üzerinde **tüm kategorilerde** (Vasıta/Otomobil/Motosiklet/SUV/Ticari, Emlak/Daire/Arsa/Villa/İşyeri, Donanım/RAM/SSD/GPU/CPU/Anakart/Monitör, Cep Telefonu/Tablet/Akıllı Saat, Oyun Konsolları ve genel aramalar) dinamik filtreler ve çoklu birimlerle (MB, GB, TB, Dual-Kit) alarm kuran; **alarm başladığı andan itibaren eklenen yeni ilanları** ve **mevcut ilanlardaki fiyat indirimlerini** anında Discord kanalınıza zengin Embed kartlarıyla ileten yüksek anti-bot korumalı Discord botu.

---

## ⚠️ Proje Durumu (Kasım 2026): Askıya Alındı

Proje **aktif kullanımda değil**; kod ve testler (334+) referans olarak korunuyor.

**Neden?** Kasım 2026 itibarıyla sahibinden.com aramaları, geçerli kullanıcı çerezleri yüklü olsa bile `https://www.sahibinden.com/cs/hloading?...` doğrulama ekranına yönlendiriyor. Çerezler giriş duvarını (`/giris`) kaldırdı; ancak bu ekran oturumdan değil, PerimeterX/Cloudflare **bot tespitinden** (tarayıcı parmak izi, TLS imzası, davranış, IP itibarı) kaynaklanıyor. Bu korumayı atlatmaya yönelik yöntemler (stealth tarayıcı yamaları, `_px3` token üretimi, challenge çözücüler, proxy rotasyonu) bilinçli olarak kapsam dışı bırakıldı: sitenin güvenlik kontrollerini aşmaya yöneliktirler, her güncellemede yeniden kırılırlar ve kullanım koşulları otomatik erişimi yasakladığı için hesabı riske atarlar.

**Değerlendirilen meşru alternatifler ve sonuç:**

| Kanal | Sonuç |
|---|---|
| Resmî API | Yalnızca tüzel kişilere açık (vergi no, KEP, EİDS); bireysel kullanım yok |
| RSS | Sunulmuyor |
| Favori Arama e-postası (IMAP → Discord) | Teknik olarak kurulabilir, ancak bildirimler **günde bir kez (≈10:00-11:00) toplu** gönderiliyor ve **90 günde** sona eriyor |
| Favori Arama push'u (Android emülatörü → Discord) | Aynı günlük toplu bildirime bağlı; ek bakım yüküne değmiyor |

Yeni ilanın 1-2 dakika içinde bildirilmesi hedefi meşru kanallarla karşılanamadığı için, ek altyapı (IMAP dinleyici, emülatör, watchdog) kurulmadı. Bunun yerine **sahibinden mobil uygulamasının kendi Favori Arama bildirimleri** kullanılıyor (90 günde bir yeniden etkinleştirilmeli).

**Tekrar çalıştırmak isterseniz:** sahibinden'in bot koruması veya bildirim politikası değişirse aşağıdaki kurulum adımları geçerliliğini korur. Kullanılmayan dağıtımlarda konteyneri durdurun ve `/app/data/sahibinden_cookies.json` dosyasını silin; bu dosya gerçek oturum çerezlerinizi içerir.

---

## 📋 İçindekiler
- [Proje Durumu (Kasım 2026): Askıya Alındı](#️-proje-durumu-kasım-2026-askıya-alındı)
- [Öne Çıkan Özellikler](#-öne-çıkan-özellikler)
- [Desteklenen Kategoriler ve Birim Türleri (MB, GB, TB)](#-desteklenen-kategoriler-ve-birim-türleri-mb-gb-tb)
- [Alarmlar Nereye Kaydediliyor? (Kalıcı Depolama & Coolify)](#-alarmlar-nereye-kaydediliyor-kalıcı-depolama--coolify)
- [Maksimum Alarm Sınırı (Sistem Koruması)](#-maksimum-alarm-sınırı-sistem-koruması)
- [Trafik İzolasyonu & Çift Proxy Failover (SpoofDPI + Cloudflare WARP)](#-trafik-izolasyonu--çift-proxy-failover-spoofdpi--cloudflare-warp)
- [Sahibinden Giriş Duvarı (/giris) & Oturum Çerezi (Cookie) Kurulumu](#-sahibinden-giriş-duvarı-giris--oturum-çerezi-cookie-kurulumu)
- [Discord Botu Oluşturma (Adım Adım)](#-discord-botu-oluşturma-adım-adım)
- [Discord Komutları ve Detaylı Kullanım Kılavuzu](#-discord-komutları-ve-detaylı-kullanım-kılavuzu)
- [Coolify (Public Repository) ile Dağıtım Rehberi](#-coolify-public-repository-ile-dağıtım-rehberi)
- [WSL / Docker Compose ile Dağıtım](#-wsl--docker-compose-ile-dağıtım)
- [Yerel (Windows) Geliştirici Kurulumu](#-yerel-windows-geliştirici-kurulumu)
- [Ortam Değişkenleri (.env) Referansı](#-ortam-değişkenleri-env-referansı)
- [Sıkça Sorulan Sorular (SSS)](#-sıkça-sorulan-sorular-sss)
- [Lisans](#-lisans)

---

## 🚀 Öne Çıkan Özellikler

1. **3 Güçlü Alarm Kurma Yöntemi**:
   - **Yöntem 1 (`/alarm-hizli`):** Tek satırda kategori, özellik/birim (DDR, Kapasite, Vites, 3+1 vb.), marka/model ve bütçe ile saniyeler içinde alarm kurma.
   - **Yöntem 2 (`/alarm-ara`):** Kategori seçmeden tüm Sahibinden genelinde anahtar kelime, bütçe aralığı ve şehir filtresiyle serbest arama başlatma.
   - **Yöntem 3 (`/alarm-url`):** Sahibinden web sitesinde seçtiğiniz 20+ detaylı filtreli arama URL'sini doğrudan takibe alma. (Mobil URL'leri masaüstüne çevirir, sayfalama parametrelerini sıfırlar, `sorting=date_desc` zorlar).
2. **Çoklu Birim Desteği (MB, GB, TB, Dual-Kit)**:
   - **RAM Kapasitesi:** Hem eski/retro nesiller (`512 MB`, `256 MB`, `128 MB`) hem modern nesiller (`4 GB`, `8 GB`, `16 GB`, `32 GB`, `64 GB`) ve Dual-Kit setler (`2x 8 GB`, `2x 16 GB`, `2x 32 GB`) tam desteklenir.
   - **Depolama (SSD/HDD):** Hem GB (`120 GB`, `240 GB`, `500 GB`) hem TB (`1 TB`, `2 TB`, `4 TB`, `8 TB`) birimleri hesaplanır.
   - **Kayıpsız Arama (Non-Lossy Fallback):** Sahibinden'in sayısal parametre kodunda yer almayan özel bir marka veya özellik girildiğinde, parametre asla çöpe atılmaz; otomatik olarak `query_text` kelime filtresine eklenir.
3. **Parametrelerin Yanında Açık Örnekler**:
   - Komut parametrelerinde (`@app_commands.describe`), detaylı seçim menülerinde (`DetailFilterSelectView`) ve otomatik tamamlama menülerinde kullanıcıya nasıl yazması gerektiği örneklerle gösterilir (örn: `'16 GB'`, `'512 MB'`, `'1 TB'`, `'2x 16 GB'`).
   - `/kategoriler` komutuyla tüm kategoriler, birimler ve hazır komut kalıpları tek tıkla listelenir.
4. **Sıfır Spam & Ertelenmiş Baseline Priming**:
   - Alarm ilk kurulduğunda yayındaki mevcut ilanları `seen_listings` tablosuna arşivler (`is_primed = 1`).
   - İlk kurulum anında ağ gecikmesi veya Cloudflare challenge olsa dahi bot ilk döngüde geçmiş ilanları sessizce hafızaya alır; **asla yüzlerce eski ilanı kanala spam yapmaz**.
5. **Otomatik Fiyat Düşüşü Bildirimi (`📉 Fiyat Düştü!`)**:
   - Takip edilen bir aramada mevcut bir ilanın fiyatı satıcı tarafından düşürüldüğünde, eski ve yeni fiyatı indirim oranıyla birlikte karşılaştırmalı olarak bildirir.
6. **Anti-Bot & Sanal Ekran (Xvfb)**:
   - Linux konteynerlerinde Cloudflare Turnstile bot tespitini aşmak için RAM üzerinde sanal monitör (`Xvfb :99`) çalıştırır. Chromium bu sanal ekranda gerçek bir kullanıcı gibi sayfaları açar.

---

## 📐 Desteklenen Tüm Sahibinden Başlıkları ve Birim Türleri

Bot; Sahibinden web sitesindeki **bütün ana kategorileri ve alt başlıkları (75+ kategori)** ve bunlara ait farklı birim türlerini hesaplar:

| Ana Kategori Grubu | Kapsanan Başlıklar | Desteklenen Birim / Özellikler | Nasıl Yazılmalı? (Örnek Formatlar) |
|---|---|---|---|
| **🏠 Emlak & Gayrimenkul** | `Emlak`, `Konut`, `Satılık Daire`, `Kiralık Daire`, `Villa`, `Arsa`, `İş Yeri`, `Konut Projeleri`, `Bina`, `Devre Mülk`, `Turistik Tesis` | Oda Sayısı, Durum, İmar, Isıtma, Lokasyon | `3+1`, `2+1`, `Kombili`, `Sıfır`, `İmarlı Tarla`, `Devren Dükkan`, `Villa Havuzlu` |
| **🚗 Vasıta & Araçlar** | `Vasıta`, `Otomobil`, `Arazi/SUV`, `Elektrikli Araçlar`, `Motosiklet`, `Minivan & Panelvan`, `Ticari`, `Kiralık`, `Deniz Araçları`, `Hasarlı`, `Karavan`, `Klasik` | Yakıt, Vites, Kasa, Boya/Hata, Motor Hacmi, Menzil | `Civic 1.6 Otomatik`, `Tesla Model Y Long Range`, `Yamaha R25 ABS`, `Çekme Karavan 3.90`, `Motoryat` |
| **🔧 Yedek Parça & Tuning** | `Yedek Parça Tümü`, `Otomotiv Ekipmanları`, `Motosiklet Ekipmanları`, `Deniz Aracı Ekipmanları` | Ebat, Parça Türü, Beden, Koruma | `205 55 R16 Kış Lastiği`, `Shoei Kask L Beden`, `15 HP Tekne Motoru`, `Coilover` |
| **💻 Bilgisayar & Donanım** | `Bilgisayar`, `RAM Bellek (Masaüstü & Laptop)`, `Ekran Kartı (GPU)`, `İşlemci (CPU)`, `SSD & Sabit Disk`, `Anakart`, `Monitör`, `Kasa/PSU`, `Laptop`, `Masaüstü PC` | `MB`, `GB`, `TB`, `Dual Kit`, `DDR Nesli`, `VRAM`, `Watt`, `Hz` | `16 GB DDR4`, `512 MB DDR2`, `2x 16 GB DDR5`, `1 TB NVMe SSD`, `RTX 4070 12 GB`, `Ryzen 5 7600`, `144hz 2K` |
| **📱 Telefon, Foto & Elektronik** | `Cep Telefonu & Aksesuar`, `Akıllı Saat`, `Tablet`, `Fotoğraf & Kamera`, `Ev Elektroniği`, `Televizyon`, `Elektrikli Ev Aletleri`, `Teknik Elektronik` | Kapasite (`GB`), Kasa Çapı (`mm`), Ekran (`inç`), Çözünürlük | `iPhone 15 Pro 128 GB`, `Apple Watch 44mm`, `Sony A7 IV 50mm Lens`, `55 inç OLED 4K`, `Dyson V15` |
| **🛍️ İkinci El, Hobi, Yaşam & Diğer** | `Giyim & Aksesuar`, `Saat`, `Anne & Bebek`, `Kişisel Bakım`, `Hobi & Oyuncak`, `Oyunculara Özel`, `Kitap/Film`, `Müzik`, `Spor`, `Takı`, `Koleksiyon`, `Antika`, `Bahçe/Yapı Market`, `İş Makineleri`, `Hizmetler` | Model, Numara, Ayar, Enstrüman, Araç Türü | `Nike 42 Sneaker`, `Seiko Otomatik Saat`, `Fender Elektro Gitar`, `Lego Technic`, `JCB Kepçe`, `Trek Bisiklet` |
| **🌐 Tüm Sahibinden (Genel Arama)** | Kategori bağımsız evrensel serbest arama (`/alarm-ara`) | Serbest anahtar kelime, marka, model | `Playstation 5`, `Deri Ceket`, `Dağ Bisikleti` |

---

## 💾 Alarmlar Nereye Kaydediliyor? (Kalıcı Depolama & Coolify)

Bot, kurulan alarmları ve taranan ilan geçmişini **SQLite (WAL modunda)** dosya tabanlı veritabanında saklar:

- **Veritabanı Dosyası:** `/app/data/sahibinden_bot.db`
- **Tarayıcı Çerez/Oturum Profili:** `/app/data/browser_profile/`

> [!WARNING]
> **Docker Konteynerleri Doğası Gereği Geçicidir (Stateless):**  
> Coolify üzerinde kalıcı depolama (**Persistent Storage / Volume**) tanımlanmazsa, **her "Redeploy" veya güncelleme butonuna bastığınızda** eski konteyner silinir ve sıfır bir konteyner yaratılır. Bu durum `/app/data` dizinindeki veritabanını (`sahibinden_bot.db`) sıfırlar ve botun tüm hafızası silinir.
> 
> **Hafızanın Kalıcı Olması İçin:** Konteyner içindeki `/app/data` dizinini kalıcı bir depolamaya bağlamanız gerekir.

### 🛠️ Coolify Üzerinde Kalıcı Hafıza Ayarı (Adım Adım)

Coolify kontrol panelinde 1 dakikada kalıcı depolama ekleyebilirsiniz:

1. **Coolify Paneline Giriş Yapın:** Uygulamanızın (Application) sayfasına gelin.
2. **Storages Sekmesine Geçin:** Üst veya sol menüdeki **Storages** (veya **Depolama**) sekmesine tıklayın.
3. **+ Add Storage (veya Add Persistent Storage) Butonuna Basın.**
4. **Formu Aşağıdaki Gibi Doldurun:**
   - **Name (İsim):** `bot-data` (veya `sahibinden-data`)
   - **Destination Path (Hedef Dizin):** `/app/data` *(⚠️ En kritik kısım! Tam olarak bu şekilde yazılmalıdır).*
   - **Source Path / Volume Name (Kaynak):** Boş bırakabilirsiniz (Coolify otomatik kalıcı Docker volume atar) ya da sunucuda sabit bir klasör belirtebilirsiniz (örn: `/data/sahibinden_data`).
5. **Save (Kaydet)** butonuna tıklayın.
6. Sağ üstteki **Redeploy** butonuna basarak uygulamayı yeniden dağıtın.

Artık her yeni kod güncellemesinde veya sunucu yeniden başlatıldığında botun tüm alarmları, görülen ilan geçmişi ve Cloudflare çerezleri kalıcı olarak korunur.

### 🐳 Docker Compose ile Çalıştıranlar İçin
Eğer yerel terminalde veya Docker Compose ile ayağa kaldırıyorsanız, `docker-compose.yml` dosyamızda kalıcı volume zaten hazırdır:

```yaml
    volumes:
      - bot_data:/app/data

volumes:
  bot_data:
    name: sahibinden_bot_data
```

- **Linux Sunucunuzdaki Fiziksel Yolu:**  
  Docker bu hacmi host dosya sisteminizde şu dizinde tutar:  
  `/var/lib/docker/volumes/sahibinden_bot_data/_data/sahibinden_bot.db`
- **Yedekleme Kolaylığı:**  
  İstediğiniz zaman bu `.db` dosyasını `sqlite3` veya *DB Browser for SQLite* ile açabilir, alarmlarınızı ve geçmiş ilanlarınızı doğrudan inceleyebilir veya yedekleyebilirsiniz.
- **İsteğe Bağlı Host Bind Mount:**  
  Eğer veritabanını Docker hacmi yerine doğrudan sabit bir klasöre (örn: `/data/sahibinden_data`) bağlamak isterseniz, `docker-compose.yml` dosyasındaki satırı `- /data/sahibinden_data:/app/data` şeklinde değiştirmeniz yeterlidir.

---

## 🛑 Maksimum Alarm Sınırı & Performans Mimarisi

Aynı anda binlerce alarmın Sahibinden sunucularını tararken IP adresinizin Cloudflare tarafından bloklanmasını veya tarama döngüsünün saatler sürmesini önlemek amacıyla çift katmanlı limit ve URL tekilleştirme mimarisi entegre edilmiştir:

1. **Sistem Genel Alarm Sınırı (`MAX_ALARMS_TOTAL=1000` - 10.000 Destekli):**
   - **Disk & Bellek Analizi:** 10.000 alarm ve 500.000 görülen ilan kaydı SQLite B-Tree dosyasında sadece **~100-150 MB** disk alanı ve sorgu anında ~20 MB RAM tüketir. Depolama veya bellek açısından hiçbir darboğaz yoktur.
   - **Asıl Kısıt (Tarama Gecikmesi & IP Sağlığı):** Sahibinden'in Cloudflare Turnstile korumasına takılmamak için her arama arasında 3-5 saniye beklenir. Tek bir IP üzerinden 10.000 bağımsız URL taranırsa bir döngü ~19 saat sürer. Bu nedenle tek IP için **optimum varsayılan değer 1000** olarak ayarlanmıştır. İsterseniz `.env` dosyasından doğrudan `MAX_ALARMS_TOTAL=10000` yapabilirsiniz.
   - **URL Gruplama (Batching Optimization):** Farklı kullanıcılar aynı aramayı veya kategoriyi takip ediyorsa bot o sayfayı döngü başına yalnızca **1 kez** tarar ve tüm kullanıcılara tek seferde dağıtır.
2. **Kullanıcı Başı Alarm Sınırı (`MAX_ALARMS_PER_USER=100`):**
   - Tek bir Discord kullanıcısı için **100 alarm** hakkı tanınır.
   - Kullanıcı 100 alarm sınırına ulaştığında Discord'da `/alarm-sil` ile eski alarmlarını temizlemesi gerektiği bildirilir.

Bu değerler `.env` dosyasından veya Coolify Environment Variables sekmesinden dilediğiniz sayıya ayarlanabilir (`MAX_ALARMS_TOTAL=10000`, `MAX_ALARMS_PER_USER=100`).

---

## 🛡️ Trafik İzolasyonu & Çift Proxy Failover (SpoofDPI + Cloudflare WARP)

Türkiye'de BTK ve mahkeme kararıyla **Discord'a erişim engeli** uygulandığından, Türkiye lokasyonlu sunuculardan (veya yerel WSL/Docker kurulumlarından) `discord.com`'a bağlanmaya çalışıldığında internet servis sağlayıcıların (Superonline, TTNET vb.) DPI engellemesi nedeniyle `SSLCertVerificationError` hatası alınır.

Bu bota tek başına WARP tünel kopmaları yaşamadan 7/24 kesintisiz çalışabilmesi için **Çift Proxy Failover (`SpoofDPI` birincil + sertleştirilmiş `Cloudflare WARP` yedek + `Autoheal` + Dayanıklı Supervisor)** mimarisi entegre edilmiştir:

### Trafik Ayrımı Mantığı (Traffic Isolation)
> [!IMPORTANT]
> **Sahibinden.com, WARP ve yabancı veri merkezi IP'lerini anında engeller (Cloudflare 403 Forbidden).**
> Bu bot **çift kanallı izole ağ mimarisi** kullanır:
> - **Discord API & Gateway Trafiği:** Önce tünelsiz `spoof-dpi` (`http://spoof-dpi:8080`), herhangi bir DPI reset/hata durumunda ise **5 saniye içinde otomatik** sertleştirilmiş `warp` yedeği (`http://warp:1080`) üzerinden yönlendirilir. `autoheal` donan `warp` konteynerini otomatik yeniden başlatır.
> - **Sahibinden Kazıma Trafiği:** Ne `spoof-dpi` ne de `warp` proxy'sine **asla** girmez; doğrudan sunucunuzun yerel Türk IP'sinden çıkar.

### Nasıl Çalışır?
- **Birincil (`spoof-dpi`):** VPN/UDP tüneli kurmaz (~10 MB RAM, düşük ping, tünel kopması sıfır). Yalnızca TLS `ClientHello` paketini parçalayarak BTK SNI/DPI engelini doğrudan geçer.
- **Yedek (`warp` + `autoheal`):** ISS kuralları sıkılaşıp `spoof-dpi` TCP reset / TLS hatası verirse supervisor döngüsü **5 saniye içinde otomatik `http://warp:1080` yedeğine** geçer; `warp` sağlık kontrolü (`cloudflare.com/cdn-cgi/trace` -> `warp=(on|plus)`) bozulursa `autoheal` konteyneri otomatik yeniden başlatır.
- **Sıfır Kurulum (Docker Compose):** `docker-compose.yml` dosyasında `spoof-dpi`, sertleştirilmiş `warp` ve `autoheal` servisleri hazır tanımlıdır. Coolify veya `docker compose up -d --build` ile ayağa kalktığında ek kurulum gerekmeden çift proxy failover otomatik devreye girer.

> [!TIP]
> - **Coolify Standalone (Dockerfile) kurulumunda:** Aynı sunucudaki `coolify` ağına ortak `spoof-dpi`, `warp` ve `autoheal` konteynerlerini kurup Coolify Environment Variables kısmına `DISCORD_PROXY=http://spoof-dpi:8080,http://warp:1080`, `DISCORD_PROXY_FALLBACK_DIRECT=false`, `DISCORD_PROXY_FAILOVER_THRESHOLD=2` yazmanız yeterlidir.
> - **Türkiye Dışı (EU/US) Sunucularda Proxy Kapatma:** `DISCORD_PROXY=direct` yazmanız yeterlidir (bu değer eski `USE_WARP=true` ayarını da devre dışı bırakır).
> - **Proxy Test Komutları:**
>   - SpoofDPI testi (`HTTP/2 200` dönmeli): `docker exec sahibinden-warp curl -sI --max-time 8 -x http://spoof-dpi:8080 https://discord.com/api/v10/gateway | head -n 1`
>   - WARP tünel testi (`warp=on` veya `warp=plus` yazmalı): `docker exec sahibinden-warp curl -s --max-time 8 -x http://127.0.0.1:1080 https://cloudflare.com/cdn-cgi/trace | grep warp=`

---

## 🍪 Sahibinden Giriş Duvarı (`/giris`) & Oturum Çerezi (Cookie) Kurulumu

Sahibinden.com, özellikle filtreli aramalarda veya sunucu/VPS IP'lerinden gelen anonim (giriş yapılmamış) isteklerde sayfaları doğrudan **`https://secure.sahibinden.com/giris?return_url=...`** giriş ekranına yönlendirebilir.

Bot bu durumla karşılaştığında:
- Chromium'u kapatıp tekrar açmaz ve kalan alarmlara boşa istek yağdırmaz (**Circuit Breaker**).
- Otomatik artan soğuma moduna geçer (**5 dk -> 15 dk -> 30 dk**, `LOGIN_WALL_COOLDOWN_SECONDS` ile ayarlanabilir).
- Kendi hesabınızla giriş yaptığınız tarayıcı çerezlerini `/app/data/sahibinden_cookies.json` dosyasına koyduğunuzda **konteyneri yeniden başlatmanıza gerek kalmadan ~5 saniye içinde otomatik algılar**, soğumayı bitirir ve taramaya devam eder.

### Yöntem 1 (En Kolay & Önerilen — 10 Saniyede Doğrudan Discord'dan `/cookie-yukle`)

Coolify başka bir cihazda olsa bile SSH, Terminal veya 3. parti eklenti **gerekmeden** doğrudan Discord içinden çerez yükleyebilirsiniz:

1. Bilgisayarınızdaki normal tarayıcınızda (**Chrome / Edge / Firefox**) [sahibinden.com](https://www.sahibinden.com/) adresine girip **kendi hesabınızla giriş yapın**.
2. **`F12`** -> **Network (Ağ)** -> sayfayı yenileyin (**`F5`**) -> soldan en üstteki **`www.sahibinden.com`** isteğine tıklayın.
3. Sağ tarafta **`Headers`** -> **Request Headers** altında **`cookie:`** satırına sağ tıklayıp **`Copy value`** deyin.
4. Discord'da **`/cookie-yukle`** yazıp Enter'a basın:
   - Açılan özel pencereye (Modal — yalnızca size görünür, kanala yazılmaz) kopyaladığınız `cookie:` değerini **Ctrl+V** ile yapıştırıp gönderin!
   - *(Eğer `cookie:` değeriniz 4000 karakterden uzunsa Not Defteri'ne kaydedip `/cookie-yukle dosya:cookies.txt` şeklinde dosya olarak ekleyin; 512 KB'a kadar desteklenir.)*
5. Bitti! Konteyneri yeniden başlatmanıza gerek yoktur; bot ~5 saniye içinde çerezleri otomatik yükleyip taramaya devam eder. Durumu istediğiniz zaman **`/cookie-durum`** ile kontrol edebilirsiniz.

> [!NOTE]
> **Güvenlik:** `/cookie-yukle` ve `/cookie-durum` komutlarını yalnızca **Bot Sahibi** (Discord Developer Portal'da botu oluşturan hesap, otomatik tanınır) ve isteğe bağlı olarak `.env` içindeki `ADMIN_USER_IDS` kullanıcıları çalıştırabilir.

### Yöntem 2 (Opsiyonel — Çapraz Platform Script: Windows / Linux / macOS)

Tarayıcıda F12 açmak yerine tek komutla JSON çıktısı almak (veya SSH / Coolify Terminal ile yüklemek) isterseniz `scripts/export_sahibinden_cookies.py` aracını kullanabilirsiniz:

```bash
# Windows / Linux / macOS:
python scripts/export_sahibinden_cookies.py
```
Oluşan `sahibinden_cookies.json` dosyasını isterseniz Discord'da **`/cookie-yukle dosya:sahibinden_cookies.json`** ile, isterseniz script içindeki Coolify Terminal / SSH seçenekleriyle yükleyebilirsiniz.

### Oturum Ömrü & Süre Dolumu Bildirimi
- **Uzun Ömürlü Oturum (Rolling Persistence):** Bot, geçici oturum çerezlerini 30 günlük kalıcı TTL ile saklar ve her başarılı taramada Sahibinden'in yenilediği güncel çerezleri periyodik olarak `/app/data/sahibinden_cookies.json` dosyasına geri yazar; böylece konteyner yeniden başlasa veya Redeploy edilse bile en güncel oturum korunur.
- **Otomatik Süre Dolumu Uyarısı:** Çerezin süresi dolup `/giris` yönlendirmesi başladığında, bot üzerinde **herhangi bir slash komutunu** (`/alarmlarim`, `/alarm-hizli`, `/alarm-test` vb.) kullandığınız anda bot size yalnızca sizin görebileceğiniz (ephemeral) bir uyarı kartıyla çerezin süresinin dolduğunu ve `/cookie-yukle` ile yenileme adımını bildirir.

> [!CAUTION]
> **Güvenlik Uyarısı:** `sahibinden_cookies.json` dosyası aktif Sahibinden oturum anahtarlarınızı içerir. Bu dosyayı **asla GitHub'a yüklemeyin** (`.gitignore` içinde engellenmiştir) ve kimseyle paylaşmayın.

### Çalıştığını Doğrulayın
- Konteyneri **yeniden başlatmanız gerekmez**!
- Loglarda ~5 saniye içinde şu satırları göreceksiniz:
```text
Detected updated Sahibinden cookies file ('/app/data/sahibinden_cookies.json'); ending login-wall cooldown early.
Loaded 18 user session cookies for sahibinden.com from '/app/data/sahibinden_cookies.json'.
```
- `/app/data` dizini Coolify Persistent Storage (veya Docker `bot_data` volume) üzerinde olduğu için **Redeploy** yaptığınızda `sahibinden_cookies.json` dosyanız silinmez.

---

## 🔑 Discord Botu Oluşturma (Adım Adım)

1. [Discord Developer Portal](https://discord.com/developers/applications) sayfasına gidin ve giriş yapın.
2. Sağ üstteki **New Application** butonuna tıklayın, botunuza bir isim verin (Örn: `Sahibinden Alarm`).
3. Sol menüden **Bot** sekmesine gelin:
   - **Reset Token** butonuna basarak bot tokeninizi kopyalayın ve güvenli bir yere kaydedin (`DISCORD_BOT_TOKEN`).
   - *(Bot yalnızca Slash Komutları ve `discord.Intents.default()` ile çalıştığından herhangi bir Privileged Gateway Intent açmanız gerekmez.)*
4. Sol menüden **OAuth2** -> **OAuth2 URL Generator** sekmesine gelin:
   - **SCOPES**: `bot` ve `applications.commands` seçeneklerini işaretleyin.
   - **BOT PERMISSIONS**: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History` seçeneklerini işaretleyin.
5. Sayfanın altındaki üretilen URL'yi kopyalayıp tarayıcınızda açarak botu Discord sunucunuza ekleyin.

---

## 🎮 Discord Komutları ve Detaylı Kullanım Kılavuzu

Bot Discord slash komutlarıyla (`/`) çalışır. Yazmaya başladığınızda Discord otomatik tamamlama (autocomplete) ve parametre ipuçları sunar.

### 1. `/alarm-hizli` (Tek Komutta 4 Ana Bölüm ve Parametrik Alarm)
Sahibinden'in 4 ana bölümündeki (Emlak, Vasıta, Yedek Parça, İkinci El & Alışveriş) dilediğiniz kategoriyi seçip aradığınız modeli, özelliği ve bütçenizi girerek saniyeler içinde alarm kurun:

```
# 🚗 1. Vasıta / Otomobil & Araçlar
/alarm-hizli kategori: Otomobil arama: Civic 1.6 ozellik: Otomatik sehir: Ankara min_fiyat: 500000 max_fiyat: 950000
/alarm-hizli kategori: Elektrikli Araçlar arama: Tesla Model Y ozellik: Long Range max_fiyat: 2400000
/alarm-hizli kategori: Motosiklet arama: Yamaha R25 ozellik: ABS max_fiyat: 200000

# 🏠 2. Emlak & Gayrimenkul
/alarm-hizli kategori: Satılık Daire arama: Kadıköy ozellik: 3+1 Kombili sehir: İstanbul max_fiyat: 7500000
/alarm-hizli kategori: Satılık Arsa arama: İmarlı arsa sehir: İzmir max_fiyat: 1500000
/alarm-hizli kategori: Satılık Tarla arama: Zeytinlik ozellik: Müstakil parsel sehir: Balıkesir

# 🛍️ 3. İkinci El ve Sıfır Alışveriş (Donanım, Telefon, Konsol, Bisiklet vb.)
/alarm-hizli kategori: Ekran Kartı (GPU) arama: RTX 4070 ozellik: 12 GB min_fiyat: 15000 max_fiyat: 25000
/alarm-hizli kategori: RAM Bellek (Masaüstü) arama: Corsair ozellik: 16 GB DDR4 max_fiyat: 2500
/alarm-hizli kategori: Sabit Disk (SSD/HDD) arama: NVMe ozellik: 1 TB max_fiyat: 3500
/alarm-hizli kategori: Cep Telefonu arama: iPhone 15 Pro ozellik: 128 GB max_fiyat: 60000
/alarm-hizli kategori: Oyun Konsolları arama: PlayStation 5 ozellik: Slim Digital max_fiyat: 20000
/alarm-hizli kategori: Bisiklet arama: Carraro ozellik: 29 Jant max_fiyat: 15000

# 🔧 4. Yedek Parça & Tuning
/alarm-hizli kategori: Jant & Lastik arama: 205 55 R16 ozellik: Kış Lastiği max_fiyat: 10000
/alarm-hizli kategori: Motosiklet Ekipmanları arama: Shoei kask ozellik: L Beden max_fiyat: 25000

# 🚜 Tarım & İş Makineleri
/alarm-hizli kategori: Traktör arama: New Holland T4.75 ozellik: 4x4 min_fiyat: 750000
```

---

### 2. `/alarm-ara` (Evrensel Serbest Arama)
Kategori seçmeden tüm sitede serbest kelime ve bütçe araması:
```
/alarm-ara kelime: Kadıköy 3+1 satılık daire min_fiyat: 4000000 max_fiyat: 7500000 sehir: İstanbul
/alarm-ara kelime: playstation 5 konsol max_fiyat: 22000
/alarm-ara kelime: 512 mb ddr2 ram
```

---

### 3. `/alarm-url` (Doğrudan Sahibinden Linki Dinleme)
Sahibinden web sitesinde filtrelediğiniz arama linkini doğrudan bota yapıştırın:
```
/alarm-url url: https://www.sahibinden.com/otomobil?sorting=date_desc&price_max=950000 alarm_adi: Civic Arama
```

---

### 4. `/kategoriler` (Kategori ve Birim Rehberi)
Desteklenen tüm kategorileri, RAM (MB/GB), SSD (GB/TB), Ekran Kartı, Vasıta ve Emlak formatlarını gösterir.
```
/kategoriler
```

---

### 5. Alarm Yönetim Komutları

| Komut | Parametreler | Açıklama |
|---|---|---|
| `/alarm-hizli` | `kategori`, `arama`, `ozellik`, `ek_ozellik`, `min_fiyat`, `max_fiyat`, `sehir`, `alarm_adi` | 4 ana bölüm hiyerarşisi, dinamik özellik ve 81 il/plaka/eşanlamlı (İçel, Afyon vb.) otomatik tamamlamasıyla tek komutta hızlı parametrik alarm kurar. |
| `/alarm-ara` | `kelime`, `min_fiyat`, `max_fiyat`, `sehir`, `alarm_adi` | Tüm Sahibinden sitesinde kategori bağımsız serbest arama yapar (81 il, plaka ve eşanlamlı otomatik tamamlamalı). |
| `/alarm-url` | `url`, `alarm_adi` | Doğrudan yapıştırılan Sahibinden arama URL'sini dinler ve alt kategorileri otomatik tespit eder. |
| `/kategoriler` | `-` | Tüm kategorileri, birim türlerini (MB, GB, TB) ve komut örneklerini gösterir. |
| `/alarmlarim` | `-` | Kurduğunuz tüm alarmları, ID numaralarını ve aktiflik durumlarını listeler. |
| `/alarm-durum` | `alarm_id: <ID> aktif: <True/False>` | Bir alarmı geçici olarak duraklatır veya yeniden başlatır (Alarm ID dinamik otomatik tamamlamalı). |
| `/alarm-test` | `alarm_id: <ID>` | Bir alarmın hedef URL'sini anında tarayıp en güncel ilanı kanala test önizlemesi olarak atar (Alarm ID dinamik tamamlamalı). |
| `/alarm-sil` | `alarm_id: <ID>` | İlgili alarmı ve geçmiş ilan veritabanı kayıtlarını kalıcı olarak siler (Alarm ID dinamik tamamlamalı). |

---

## ☁️ Coolify (Public Repository) ile Dağıtım Rehberi

Coolify üzerinde botu **Public Repository** olarak tek tıkla ayağa kaldırmak için aşağıdaki adımları izleyin:

### Adım 1: Coolify'da Yeni Kaynak Ekleyin
1. Coolify kontrol panelinizde **Projects** -> Projeniz -> Ortamınız (**production**) sayfasına gidin.
2. **+ New Resource** butonuna tıklayın.
3. **Applications** altındaki **Git Based** grubundan **Public Repository** seçeneğini seçin.

### Adım 2: Depo Bilgilerini Girin
- **Repository URL:** Bu GitHub reposunun linkini girin (Örn: `https://github.com/<kullanici_adiniz>/Sahibinden_Arama_Botu`).
- **Branch:** `main`
- **Build Pack:** Otomatik olarak **Docker Compose** seçilir.

### Adım 3: Ortam Değişkenlerini (Environment Variables) Tanımlayın
Coolify'daki uygulamanızın **Environment Variables** sekmesine gidin ve aşağıdaki değerleri ekleyin:

```env
DISCORD_BOT_TOKEN=buraya_discord_bot_tokeninizi_yazin
DISCORD_PROXY=http://spoof-dpi:8080,http://warp:1080
DISCORD_PROXY_FALLBACK_DIRECT=false
DISCORD_PROXY_FAILOVER_THRESHOLD=2
MAX_ALARMS_TOTAL=1000
MAX_ALARMS_PER_USER=100
CHECK_INTERVAL_SECONDS=90
HEADLESS=false
```

### Adım 4: Kalıcı Depolama (Persistent Storage / Hafıza) Ekleyin (ÖNEMLİ ⚠️)
Docker konteynerleri doğası gereği geçicidir (stateless). Her yeni deploy yaptığınızda alarmlarınızın ve görülen ilan geçmişinizin **silinmemesi** için Coolify'a bu dizini kalıcı olarak tanıtmalısınız:

1. Uygulama sayfasında **Storages** (veya **Depolama**) sekmesine tıklayın.
2. **+ Add Storage** (veya **Add Persistent Storage**) butonuna basın.
3. Açılan formda:
   - **Name:** `bot-data` (veya `sahibinden-data`)
   - **Destination Path:** `/app/data` *(⚠️ Tam olarak bu şekilde yazılmalıdır).*
   - **Source Path:** Boş bırakabilirsiniz (Coolify otomatik kalıcı Docker volume oluşturur) veya sunucuda sabit bir host dizini belirtebilirsiniz.
4. **Save** butonuna tıklayarak kaydedin.

### Adım 5: Dağıtımı Başlatın (Deploy)
Coolify panelinde sağ üstteki **Deploy** butonuna tıklayın.
- Coolify depoyu çeker; `spoof-dpi` (birincil), sertleştirilmiş `warp` (yedek), `autoheal` ve `sahibinden-bot` konteynerlerini ayağa kaldırır.
- Discord bağlantısı önce `http://spoof-dpi:8080`, herhangi bir DPI/bağlantı hatasında 5 saniyede otomatik `http://warp:1080` üzerinden gerçekleşir.
- Sahibinden aramaları doğrudan sunucunuzun Türk IP'sinden çıkar.
- SQLite veritabanı `/app/data` dizininde kalıcı olarak saklanır ve hiçbir güncellemede silinmez.

---

## 🐳 WSL / Docker Compose ile Dağıtım

Eğer Coolify kullanmadan doğrudan terminalde Docker Compose ile çalıştırmak isterseniz:

```bash
# 1. Depoyu klonlayın
git clone https://github.com/<kullanici_adiniz>/Sahibinden_Arama_Botu.git
cd Sahibinden_Arama_Botu

# 2. .env dosyasını oluşturun
cp .env.example .env
nano .env  # DISCORD_BOT_TOKEN değerini girin

# 3. Konteynerleri arka planda başlatın
docker compose up -d --build

# 4. Logları takip edin
docker compose logs -f sahibinden-bot
```

---

## 💻 Yerel (Windows) Geliştirici Kurulumu

Windows üzerinde doğrudan test etmek isterseniz:

```powershell
# 1. Sanal ortamı oluşturun ve aktifleştirin
python -m venv venv
.\venv\Scripts\Activate.ps1

# 2. Bağımlılıkları ve Playwright Chromium'u yükleyin
pip install -r requirements.txt
playwright install chromium

# 3. .env dosyasını oluşturup tokeni girin
cp .env.example .env

# 4. Testleri çalıştırın
python -m pytest -v

# 5. Botu başlatın
python -m src.main
```

---

## ⚙️ Ortam Değişkenleri (.env) Referansı

| Değişken Adı | Varsayılan | Açıklama |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *Zorunlu* | Discord Developer Portal'dan alınan bot tokeni. |
| `DISCORD_PROXY` | `http://spoof-dpi:8080,http://warp:1080` | Discord çıkış proxy listesi (virgülle ayrılmış HTTP/SOCKS5 failover sırası). Kapatmak için `direct` yazabilirsiniz. Yalnızca Discord trafiği için kullanılır. |
| `DISCORD_PROXY_FALLBACK_DIRECT` | `false` | Tüm proxy'ler ardışık hata verirse direkt bağlantıyı dener (TR sunucularda `false`, engelsiz VPS'te `true` önerilir). |
| `DISCORD_PROXY_FAILOVER_THRESHOLD` | `2` | Direkt fallback öncesi proxy başına ardışık hata eşiği. |
| `DISCORD_PROXY_URL` | *Boş* | İsteğe bağlı açık proxy override (`DISCORD_PROXY` ve `USE_WARP` yerine geçer; virgüllü liste destekler). |
| `USE_WARP` / `WARP_HOST` / `WARP_PORT` | `false` / `warp` / `1080` | Geriye dönük tekli WARP ayarları (yalnızca `DISCORD_PROXY` boşken kullanılır). |
| `SAHIBINDEN_COOKIES_PATH` | `/app/data/sahibinden_cookies.json` | İsteğe bağlı Sahibinden oturum çerezleri dosya yolu (ham F12 DevTools `Cookie:` satırı, `{"cookie_header": "..."}` veya Playwright `storage_state.json`; değiştiğinde hot-reload olur). |
| `LOGIN_WALL_COOLDOWN_SECONDS` | `300` | Sahibinden `/giris` yönlendirmesi geldiğinde temel soğuma süresi (`1x -> 3x -> 6x`, yani 5 dk -> 15 dk -> 30 dk). |
| `MAX_ALARMS_TOTAL` | `1000` | Sistem genelinde kurulabilecek maksimum alarm sayısı (10.000 destekler). |
| `MAX_ALARMS_PER_USER` | `100` | Kullanıcı başına oluşturulabilecek maksimum alarm sayısı. |
| `CHECK_INTERVAL_SECONDS` | `90` | Arama döngüleri arasındaki bekleme süresi (saniye). |
| `DATABASE_PATH` | `/app/data/sahibinden_bot.db` | Kalıcı SQLite veritabanı dosya yolu. |
| `HEADLESS` | `false` | Playwright tarayıcı modu (Xvfb için `false` önerilir). |

---

## ❓ Sıkça Sorulan Sorular (SSS)

**S: Eski model bir RAM için 512 MB alarmı kurabilir miyim?**  
C: Evet! `/alarm-hizli kategori:ram-bellek-masaustu ozellik:512 MB, DDR2` yazmanız yeterlidir. Bot otomatik olarak 512 MB'ı algılar ve Sahibinden'in doğru parametresiyle filtreler.

**S: SSD için 1 TB ve 500 GB filtreleri nasıl yazılır?**  
C: `/alarm-hizli kategori:ssd-dahili-sabit-disk ozellik:1 TB` veya `/alarm-hizli kategori:ssd-dahili-sabit-disk ozellik:500 GB` şeklinde doğrudan yazabilirsiniz.

**S: Özel bir marka veya model yazdığımda kaybolur mu?**  
C: Kesinlikle hayır. Botumuzda **Non-Lossy Fallback (Kayıpsız Arama)** mimarisi bulunur. Sahibinden'in sayısal kodlarında yer almayan özel bir marka, çipset veya model yazdığınızda, filtre silinmez; otomatik olarak kelime arama motoruna (`query_text`) eklenir.

**S: Bot geçmiş ilanları spamlar mı?**  
C: Hayır. Alarm ilk oluşturulduğunda mevcut tüm ilanlar otomatik olarak arşivlenir. Yalnızca alarm açıldıktan sonra gelen yeni ilanlar ve fiyatı düşenler bildirilir.

**S: Coolify'da her 'Deploy' veya 'Redeploy' yaptığımda botun alarmları ve geçmişi siliniyor, neden?**  
C: Docker konteynerleri doğası gereği geçicidir (stateless). Eğer Coolify üzerinde Persistent Storage tanımlanmazsa, her deploy işleminde eski konteyner yok edilip sıfırdan oluşturulur; bu da `/app/data/sahibinden_bot.db` dosyasını siler. Çözüm: Coolify panelinde uygulamanızın **Storages** sekmesine gidip **Destination Path** olarak `/app/data` kalıcı depolamasını ekleyin ve ardından Redeploy yapın. Artık alarmlarınız hiçbir deployda silinmeyecektir.

---

## 📜 Lisans

Bu proje [MIT Lisansı](LICENSE) altında lisanslanmıştır. Açık kaynaklıdır ve özgürce kullanılabilir, geliştirilebilir ve dağıtılabilir.
