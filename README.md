# 🤖 Sahibinden Discord Arama & Bildirim Botu

[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.15-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.7+-5865F2.svg?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-45ba4b.svg?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Coolify](https://img.shields.io/badge/Coolify-Supported-6B46C1.svg)](https://coolify.io/)
[![Cloudflare WARP](https://img.shields.io/badge/Cloudflare-WARP%20SOCKS5-F38020.svg?logo=cloudflare&logoColor=white)](https://developers.cloudflare.com/warp-client/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Sahibinden.com üzerinde **tüm kategorilerde** (Vasıta/Otomobil/Motosiklet/SUV/Ticari, Emlak/Daire/Arsa/Villa/İşyeri, Donanım/RAM/SSD/GPU/CPU/Anakart/Monitör, Cep Telefonu/Tablet/Akıllı Saat, Oyun Konsolları ve genel aramalar) dinamik filtreler ve çoklu birimlerle (MB, GB, TB, Dual-Kit) alarm kuran; **alarm başladığı andan itibaren eklenen yeni ilanları** ve **mevcut ilanlardaki fiyat indirimlerini** anında Discord kanalınıza zengin Embed kartlarıyla ileten yüksek anti-bot korumalı Discord botu.

---

## 📋 İçindekiler
- [Öne Çıkan Özellikler](#-öne-çıkan-özellikler)
- [Desteklenen Kategoriler ve Birim Türleri (MB, GB, TB)](#-desteklenen-kategoriler-ve-birim-türleri-mb-gb-tb)
- [Alarmlar Nereye Kaydediliyor? (Kalıcı Depolama & Coolify)](#-alarmlar-nereye-kaydediliyor-kalıcı-depolama--coolify)
- [Maksimum Alarm Sınırı (Sistem Koruması)](#-maksimum-alarm-sınırı-sistem-koruması)
- [Trafik İzolasyonu & Cloudflare WARP (Türkiye BTK Banı Çözümü)](#-trafik-izolasyonu--cloudflare-warp-türkiye-btk-banı-çözümü)
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

1. **3 Evrensel Alarm Kurma Yöntemi**:
   - **Yöntem 1 (`/alarm-ara`):** Kategori seçmeden tüm Sahibinden genelinde anahtar kelime, bütçe aralığı ve şehir filtresiyle arama başlatır. (Arka planda otomatik kategori çıkarımı ve redirect koruması yapar).
   - **Yöntem 2 (`/alarm-url`):** Sahibinden web sitesinde seçtiğiniz 20+ detaylı filtreli arama URL'sini doğrudan takibe alma. (Mobil URL'leri masaüstüne çevirir, sayfalama parametrelerini sıfırlar, `sorting=date_desc` zorlar).
   - **Yöntem 3 (`/alarm-kur` & `/alarm-hizli`):** Discord Autocomplete destekli 25 ana kategori seçici, RAM DDR/Kapasite sihirbazı ve tek satırda spesifik donanım alarmı açma.
2. **Çoklu Birim Desteği (MB, GB, TB, Dual-Kit)**:
   - **RAM Kapasitesi:** Hem eski/retro nesiller (`512 MB`, `256 MB`, `128 MB`) hem modern nesiller (`4 GB`, `8 GB`, `16 GB`, `32 GB`, `64 GB`) ve Dual-Kit setler (`2x 8 GB`, `2x 16 GB`, `2x 32 GB`) tam desteklenir.
   - **Depolama (SSD/HDD):** Hem GB (`120 GB`, `240 GB`, `500 GB`) hem TB (`1 TB`, `2 TB`, `4 TB`, `8 TB`) birimleri hesaplanır.
   - **Kayıpsız Arama (Non-Lossy Fallback):** Sahibinden'in sayısal parametre kodunda yer almayan özel bir marka veya özellik girildiğinde, parametre asla çöpe atılmaz; otomatik olarak `query_text` kelime filtresine eklenir.
3. **Parametrelerin Yanında Açık Örnekler**:
   - Komut parametrelerinde (`@app_commands.describe`), modal formlarında (`SpecFilterModal`) ve otomatik tamamlama menülerinde kullanıcıya nasıl yazması gerektiği örneklerle gösterilir (örn: `'16 GB'`, `'512 MB'`, `'1 TB'`, `'2x 16 GB'`).
   - `/kategoriler` komutuyla tüm kategoriler, birimler ve hazır komut kalıpları tek tıkla listelenir.
4. **Sıfır Spam & Ertelenmiş Baseline Priming**:
   - Alarm ilk kurulduğunda yayındaki mevcut ilanları `seen_listings` tablosuna arşivler (`is_primed = 1`).
   - İlk kurulum anında ağ gecikmesi veya Cloudflare challenge olsa dahi bot ilk döngüde geçmiş ilanları sessizce hafızaya alır; **asla yüzlerce eski ilanı kanala spam yapmaz**.
5. **Otomatik Fiyat Düşüşü Bildirimi (`📉 Fiyat Düştü!`)**:
   - Takip edilen bir aramada mevcut bir ilanın fiyatı satıcı tarafından düşürüldüğünde, eski ve yeni fiyatı indirim oranıyla birlikte karşılaştırmalı olarak bildirir.
6. **Anti-Bot & Sanal Ekran (Xvfb)**:
   - Linux konteynerlerinde Cloudflare Turnstile bot tespitini aşmak için RAM üzerinde sanal monitör (`Xvfb :99`) çalıştırır. Chromium bu sanal ekranda gerçek bir kullanıcı gibi sayfaları açar.

---

## 📐 Desteklenen Kategoriler ve Birim Türleri (MB, GB, TB)

Bot; Sahibinden web sitesindeki her ana kategoriyi ve bunlara ait farklı birim türlerini hesaplar:

| Ana Kategori | Desteklenen Birim / Özellik Türleri | Nasıl Yazılmalı? (Örnek Formatlar) |
|---|---|---|
| **RAM Bellek (Masaüstü & Laptop)** | `MB`, `GB`, `Dual Kit`, `DDR Nesli` | `512 MB`, `256 MB`, `16 GB`, `32 GB`, `2x 8 GB`, `2x 16 GB`, `DDR4`, `DDR5`, `DDR2` |
| **SSD & Sabit Disk** | `GB`, `TB`, Form Faktörü | `120 GB`, `250 GB`, `500 GB`, `1 TB`, `2 TB`, `4 TB`, `NVMe`, `SATA` |
| **Ekran Kartı (GPU)** | `VRAM (GB)`, Chipset Üreticisi | `6 GB`, `8 GB`, `12 GB`, `16 GB`, `24 GB`, `Nvidia`, `AMD`, `Intel` |
| **İşlemci (CPU)** | Marka, Soket, Seri | `AMD`, `Intel`, `Ryzen 5`, `Ryzen 7`, `i5`, `i7`, `AM5`, `LGA1700` |
| **Anakart** | Çipset, Soket | `AM4`, `AM5`, `B650`, `Z790`, `B550`, `LGA1700` |
| **Monitör** | Boyut, Yenileme Hızı, Çözünürlük | `144hz`, `165hz`, `240hz`, `27 inç`, `2K`, `IPS` |
| **Kasa & Güç Kaynağı** | Watt Değeri, Sertifika | `750W`, `850W`, `80+ Gold`, `ATX Kasa` |
| **Vasıta (Otomobil, SUV, Motor, Ticari)** | Model, Motor, Yakıt, Vites | `Civic 1.6`, `Otomatik`, `Manuel`, `Benzin`, `Dizel`, `Boyasız` |
| **Emlak (Satılık/Kiralık Daire, Arsa, Villa)** | Oda Sayısı, Durum, Özellik | `3+1`, `2+1`, `1+1`, `Kombili`, `Sıfır`, `Balkonlu`, `Havuzlu` |
| **Mobil (Telefon, Tablet, Akıllı Saat)** | Kapasite, Boyut, Model | `128 GB`, `256 GB`, `512 GB`, `iPhone 15 Pro`, `Apple Watch 44mm` |
| **Oyun & Eğlence (Konsol, TV, Saat)** | Model, Çözünürlük, Mekanizma | `PS5 Konsol`, `Xbox Series X`, `Switch`, `55 inç OLED`, `Otomatik Saat` |
| **Tüm Sahibinden (Genel Arama)** | Serbest anahtar kelime | `Playstation 5`, `Deri Ceket`, `Bisiklet` |

---

## 💾 Alarmlar Nereye Kaydediliyor? (Kalıcı Depolama & Coolify)

Bot, kurulan alarmları ve taranan ilan geçmişini **SQLite (WAL modunda)** dosya tabanlı veritabanında saklar:

- **Veritabanı Dosyası:** `/app/data/sahibinden_bot.db`
- **Tarayıcı Çerez/Oturum Profili:** `/app/data/browser_profile/`

### Coolify & Docker Üzerindeki Kayıt Yeri (Persistent Volume)
Konteynerler geçicidir (stateless), ancak verilerinizin Coolify üzerinde güncelleme (Redeploy) veya sunucu yeniden başlatmalarında **asla silinmemesi** için `docker-compose.yml` içinde kalıcı bir Docker Volume (`bot_data`) tanımlanmıştır:

```yaml
    volumes:
      - bot_data:/app/data

volumes:
  bot_data:
    name: sahibinden_bot_data
```

- **Coolify / Linux Sunucunuzdaki Fiziksel Yolu:**
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

## 🛡️ Trafik İzolasyonu & Cloudflare WARP (Türkiye BTK Banı Çözümü)

Türkiye'de Discord servisleri BTK tarafından erişime engellendiğinde, botun Discord Gateway'ine bağlanabilmesi için SOCKS5 proxy desteği entegre edilmiştir.

### Trafik Ayrımı Mantığı (Traffic Isolation)
> [!IMPORTANT]
> **Sahibinden.com, WARP ve yabancı veri merkezi IP'lerini anında engeller (Cloudflare 403 Forbidden).**
> Bu bot **çift kanallı izole ağ mimarisi** kullanır:
> - **Discord API & Gateway Trafiği:** `docker-compose.yml` içindeki yerleşik `warp` sidecar konteyneri (`socks5://warp:1080`) üzerinden yönlendirilir ve BTK engeli aşılır.
> - **Sahibinden Kazıma Trafiği:** WARP proxy'sine **asla** girmez; doğrudan sunucunuzun yerel Türk IP'sinden çıkar.

### Sıfır Kurulum: Docker Compose Sidecar (Önerilen & Varsayılan)

WSL veya sunucunuza `warp-cli` kurmanıza **kesinlikle gerek yoktur!** `docker-compose.yml` dosyasında `caomingjun/warp` servisi hazır tanımlıdır. Coolify veya Docker Compose ile ayağa kalktığında:

1. `warp` konteyneri arka planda otomatik başlar ve 1080 portunda SOCKS5 proxy sağlar.
2. `sahibinden-bot` konteyneri `socks5://warp:1080` üzerinden Discord'a bağlanır.
3. Sahibinden aramaları ise host makinenizin yerel Türk IP'sinden çıkar.

> [!TIP]
> - **Tak-Çalıştır:** Coolify'da ek hiçbir ayar yapmadan deploy etmeniz yeterlidir.
> - **WARP Kullanmak İstemiyorsanız:** Coolify Environment Variables paneline `USE_WARP=false` yazmanız yeterlidir.
> - **Otomatik Fallback:** `WARP_FALLBACK_TO_DIRECT=true` tanımlarsanız, WARP geçici olarak çevrimdışı olsa bile bot durmaz ve doğrudan Discord'a bağlanır.

---

## 🔑 Discord Botu Oluşturma (Adım Adım)

1. [Discord Developer Portal](https://discord.com/developers/applications) sayfasına gidin ve giriş yapın.
2. Sağ üstteki **New Application** butonuna tıklayın, botunuza bir isim verin (Örn: `Sahibinden Alarm`).
3. Sol menüden **Bot** sekmesine gelin:
   - **Reset Token** butonuna basarak bot tokeninizi kopyalayın ve güvenli bir yere kaydedin (`DISCORD_BOT_TOKEN`).
   - **Privileged Gateway Intents** altında `Message Content Intent` ayarını açın.
4. Sol menüden **OAuth2** -> **OAuth2 URL Generator** sekmesine gelin:
   - **SCOPES**: `bot` ve `applications.commands` seçeneklerini işaretleyin.
   - **BOT PERMISSIONS**: `Send Messages`, `Embed Links`, `Attach Files`, `Read Message History` seçeneklerini işaretleyin.
5. Sayfanın altındaki üretilen URL'yi kopyalayıp tarayıcınızda açarak botu Discord sunucunuza ekleyin.

---

## 🎮 Discord Komutları ve Detaylı Kullanım Kılavuzu

Bot slash komutlarıyla (`/`) çalışır. Yazmaya başladığınızda Discord otomatik tamamlama ve parametre ipuçları sunar.

### 1. `/kategoriler` (Kategori ve Birim Rehberi)
Desteklenen tüm kategorileri, RAM (MB/GB), SSD (GB/TB), Ekran Kartı, Vasıta ve Emlak formatlarını gösterir.
```
/kategoriler
```

---

### 2. `/alarm-hizli` (Tek Satırda Parametrik Alarm)
Kategori, birim ve kriterleri doğrudan yazarak saniyeler içinde alarm kurun:
```
/alarm-hizli kategori: ram ddr: DDR4 kapasite: 16 GB marka: Corsair max_fiyat: 2500
/alarm-hizli kategori: ram ddr: DDR2 kapasite: 512 MB max_fiyat: 300
/alarm-hizli kategori: ram ddr: DDR5 kapasite: 2x 16 GB marka: G.Skill
/alarm-hizli kategori: ssd kapasite: 1 TB kelime: NVMe max_fiyat: 3500
/alarm-hizli kategori: gpu kapasite: 12 GB marka: Nvidia kelime: RTX 4070 max_fiyat: 22000
/alarm-hizli kategori: araba kelime: Civic 1.6 Otomatik sehir: Ankara max_fiyat: 900000
```

---

### 3. `/alarm-ara` (Evrensel Serbest Arama)
Kategori belirtmeden tüm sitede serbest kelime ve bütçe araması:
```
/alarm-ara kelime: Kadıköy 3+1 satılık daire min_fiyat: 4000000 max_fiyat: 7500000 sehir: İstanbul
/alarm-ara kelime: playstation 5 konsol max_fiyat: 22000
/alarm-ara kelime: 512 mb ddr2 ram
```

---

### 4. `/alarm-url` (Detaylı Sahibinden Linki Takibi)
Sahibinden web sitesinde seçtiğiniz arama sonucunun URL'sini doğrudan yapıştırın:
```
/alarm-url url: https://www.sahibinden.com/otomobil/ankara-cankaya?sorting=date_desc&price_max=850000 alarm_adi: Çankaya Araçlar
```

---

### 5. `/alarm-kur` (Görsel Sihirbaz)
Kategori açılır menüsü (Select Menu), RAM DDR/Kapasite seçicisi ve fiyat modal penceresiyle görsel kurulum:
```
/alarm-kur
/alarm-kur kategori: ram
```

---

### 6. Yönetim Komutları

| Komut | Parametreler | Açıklama |
|---|---|---|
| `/kategoriler` | `-` | Tüm kategorileri, birim türlerini (MB, GB, TB) ve komut örneklerini gösterir. |
| `/alarmlarim` | `-` | Kurduğunuz tüm alarmları, ID numaralarını ve aktiflik durumlarını listeler. |
| `/alarm-durum` | `alarm_id: <ID> aktif: <True/False>` | Bir alarmı silmeden geçici olarak duraklatır (`False`) veya yeniden başlatır (`True`). |
| `/alarm-test` | `alarm_id: <ID>` | Bir alarmın hedef URL'sini anında tarayıp en güncel ilanı kanala test önizlemesi olarak atar. |
| `/alarm-sil` | `alarm_id: <ID>` | İlgili alarmı ve geçmiş ilan veritabanı kayıtlarını kalıcı olarak siler. |

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
USE_WARP=true
WARP_HOST=warp
WARP_PORT=1080
WARP_FALLBACK_TO_DIRECT=false
MAX_ALARMS_TOTAL=1000
MAX_ALARMS_PER_USER=100
CHECK_INTERVAL_SECONDS=90
HEADLESS=false
```

### Adım 4: Dağıtımı Başlatın (Deploy)
Coolify panelinde sağ üstteki **Deploy** butonuna tıklayın.
- Coolify depoyu çeker, `warp` sidecar ve `sahibinden-bot` konteynerlerini ayağa kaldırır.
- Discord bağlantısı `socks5://warp:1080` üzerinden gerçekleşir.
- Sahibinden aramaları doğrudan sunucunuzun Türk IP'sinden çıkar.
- SQLite veritabanı `bot_data` Docker hacminde kalıcı olarak saklanır.

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
| `USE_WARP` | `true` | Discord bağlantısı için SOCKS5 WARP proxy kullanımını açar. |
| `WARP_HOST` | `warp` | WARP proxy hostu (Docker Compose'da `warp`, hostta `127.0.0.1`). |
| `WARP_PORT` | `1080` | WARP SOCKS5 portu (Sidecar'da `1080`, warp-cli'da `40000`). |
| `WARP_FALLBACK_TO_DIRECT` | `false` | WARP ulaşılamazsa doğrudan internete bağlanmayı dener. |
| `MAX_ALARMS_TOTAL` | `1000` | Sistem genelinde kurulabilecek maksimum alarm sayısı (10.000 destekler). |
| `MAX_ALARMS_PER_USER` | `100` | Kullanıcı başına oluşturulabilecek maksimum alarm sayısı. |
| `CHECK_INTERVAL_SECONDS` | `90` | Arama döngüleri arasındaki bekleme süresi (saniye). |
| `DATABASE_PATH` | `/app/data/sahibinden_bot.db` | Kalıcı SQLite veritabanı dosya yolu. |
| `HEADLESS` | `false` | Playwright tarayıcı modu (Xvfb için `false` önerilir). |

---

## ❓ Sıkça Sorulan Sorular (SSS)

**S: Eski model bir RAM için 512 MB alarmı kurabilir miyim?**  
C: Evet! `/alarm-hizli kategori:ram ddr:DDR2 kapasite:512 MB` yazmanız yeterlidir. Bot otomatik olarak 512 MB'ı algılar ve Sahibinden'in doğru parametresiyle filtreler.

**S: SSD için 1 TB ve 500 GB filtreleri nasıl yazılır?**  
C: `/alarm-hizli kategori:ssd kapasite:1 TB` veya `/alarm-hizli kategori:ssd kapasite:500 GB` şeklinde doğrudan yazabilirsiniz.

**S: Özel bir marka veya model yazdığımda kaybolur mu?**  
C: Kesinlikle hayır. Botumuzda **Non-Lossy Fallback (Kayıpsız Arama)** mimarisi bulunur. Sahibinden'in sayısal kodlarında yer almayan özel bir marka, çipset veya model yazdığınızda, filtre silinmez; otomatik olarak kelime arama motoruna (`query_text`) eklenir.

**S: Bot geçmiş ilanları spamlar mı?**  
C: Hayır. Alarm ilk oluşturulduğunda mevcut tüm ilanlar otomatik olarak arşivlenir. Yalnızca alarm açıldıktan sonra gelen yeni ilanlar ve fiyatı düşenler bildirilir.

---

## 📜 Lisans

Bu proje [MIT Lisansı](LICENSE) altında lisanslanmıştır. Açık kaynaklıdır ve özgürce kullanılabilir, geliştirilebilir ve dağıtılabilir.
