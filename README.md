# 🤖 Sahibinden Discord Arama & Bildirim Botu

[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.15-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.7+-5865F2.svg?logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Playwright](https://img.shields.io/badge/Playwright-Chromium-45ba4b.svg?logo=playwright&logoColor=white)](https://playwright.dev/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![Coolify](https://img.shields.io/badge/Coolify-Supported-6B46C1.svg)](https://coolify.io/)
[![Cloudflare WARP](https://img.shields.io/badge/Cloudflare-WARP%20SOCKS5-F38020.svg?logo=cloudflare&logoColor=white)](https://developers.cloudflare.com/warp-client/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Sahibinden.com üzerinde **tüm kategorilerde** (Donanım/RAM/GPU/CPU, Vasıta/Otomobil/Motosiklet, Emlak/Daire, Cep Telefonu ve genel aramalar) dinamik filtrelerle alarm kuran; **alarm başladığı andan itibaren eklenen yeni ilanları** ve **mevcut ilanlardaki fiyat indirimlerini** anında Discord kanalınıza zengin Embed kartlarıyla ileten yüksek anti-bot korumalı Discord botu.

---

## 📋 İçindekiler
- [Öne Çıkan Özellikler](#-öne-çıkan-özellikler)
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
  Eğer veritabanını Docker hacmi yerine doğrudan WSL/sunucunuzdaki sabit bir klasöre (örn: `/data/sahibinden_data`) bağlamak isterseniz, `docker-compose.yml` dosyasındaki satırı `- /data/sahibinden_data:/app/data` şeklinde değiştirmeniz yeterlidir.

---

## 🛑 Maksimum Alarm Sınırı & Performans Mimarisi

Aynı anda binlerce alarmın Sahibinden sunucularını tararken IP adresinizin Cloudflare tarafından bloklanmasını veya tarama döngüsünün saatler sürmesini önlemek amacıyla çift katmanlı limit ve URL tekilleştirme mimarisi entegre edilmiştir:

1. **Sistem Genel Alarm Sınırı (`MAX_ALARMS_TOTAL=1000` - 10.000 Destekli):**
   - **Disk & Bellek Analizi:** 10.000 alarm ve 500.000 görülen ilan kaydı SQLite B-Tree dosyasında sadece **~100-150 MB** disk alanı ve sorgu anında ~20 MB RAM tüketir. Dolayısıyla depolama veya bellek açısından hiçbir darboğaz yoktur.
   - **Asıl Kısıt (Tarama Gecikmesi & IP Sağlığı):** Sahibinden'in Cloudflare Turnstile korumasına takılmamak için her arama arasında 3-5 saniye beklenir. Tek bir IP üzerinden 10.000 bağımsız URL taranırsa bir döngü ~19 saat sürer. Bu nedenle tek IP için **optimum varsayılan değer 1000** olarak ayarlanmıştır. İsterseniz `.env` dosyasından doğrudan `MAX_ALARMS_TOTAL=10000` yapabilirsiniz.
   - **URL Gruplama (Batching Optimization):** Farklı kullanıcılar aynı aramayı veya kategoriyi takip ediyorsa bot o sayfayı döngü başına yalnızca **1 kez** tarar ve tüm kullanıcılara tek seferde dağıtır.
2. **Kullanıcı Başı Alarm Sınırı (`MAX_ALARMS_PER_USER=100`):**
   - Tek bir Discord kullanıcısı için **100 alarm** hakkı tanınır.
   - Kullanıcı 100 alarm sınırına ulaştığında Discord'da `/alarm-sil` ile eski alarmlarını temizlemesi gerektiği bildirilir.

Bu değerler `.env` dosyasından veya Coolify Environment Variables sekmesinden dilediğiniz sayıya ayarlanabilir (`MAX_ALARMS_TOTAL=10000`, `MAX_ALARMS_PER_USER=100`).

---

## 🚀 Öne Çıkan Özellikler

1. **3 Evrensel Alarm Kurma Yöntemi**:
   - **Yöntem 1 (`/alarm-ara`):** Kategori seçmeden tüm Sahibinden genelinde anahtar kelime, fiyat ve il filtreli arama. (Arka planda otomatik kategori çıkarımı ve redirect koruması yapar).
   - **Yöntem 2 (`/alarm-url`):** Sahibinden web sitesinde seçtiğiniz 20+ detaylı filtreli arama URL'sini doğrudan takibe alma. (Mobil URL'leri masaüstüne çevirir, sayfalama parametrelerini sıfırlar, `sorting=date_desc` zorlar).
   - **Yöntem 3 (`/alarm-kur` & `/alarm-hizli`):** Discord Autocomplete destekli kategori seçici, RAM DDR/Kapasite sihirbazı ve tek satırda spesifik donanım alarmı açma.
2. **Akıllı Donanım & Alias Desteği**:
   - **RAM (Masaüstü & Laptop SODIMM):** `ram` dendiğinde otomatik anlaşılır; DDR, DDR2, DDR3, DDR3L, DDR4, DDR5 ve 4 GB'dan 2x 32 GB'a kadar kapasite/marka (`Corsair`, `Kingston`, `G.Skill` vb.) filtrelerini eksiksiz URL parametrelerine dönüştürür.
   - **Ekran Kartı (GPU) & İşlemci (CPU):** Chipset (`Nvidia`, `AMD`, `Intel`) ve VRAM (`6 GB` - `24 GB`) filtreleri.
   - **81 İl Desteği:** Türkiye'nin tüm 81 ili için Türkçe karakter duyarlı şehir filtreleme.
3. **Sıfır Spam & Ertelenmiş Baseline Priming**:
   - Alarm ilk kurulduğunda yayındaki mevcut ilanları `seen_listings` tablosuna arşivler (`is_primed = 1`).
   - İlk kurulum anında ağ gecikmesi veya Cloudflare challenge olsa dahi bot ilk döngüde geçmiş ilanları sessizce hafızaya alır; **asla yüzlerce eski ilanı kanala spam yapmaz**.
4. **Otomatik Fiyat Düşüşü Bildirimi (`📉 Fiyat Düştü!`)**:
   - Takip edilen bir aramada mevcut bir ilanın fiyatı satıcı tarafından düşürüldüğünde, eski ve yeni fiyatı indirim oranıyla birlikte karşılaştırmalı olarak bildirir.
5. **Anti-Bot & Sanal Ekran (Xvfb)**:
   - Linux konteynerlerinde Cloudflare Turnstile bot tespitini aşmak için RAM üzerinde sanal monitör (`Xvfb :99`) çalıştırır. Chromium bu sanal ekranda gerçek bir kullanıcı gibi sayfaları açar.

---

## 🛡️ Trafik İzolasyonu & Cloudflare WARP (Türkiye BTK Banı Çözümü)

Türkiye'de Discord servisleri BTK tarafından erişime engellendiğinde, botun Discord Gateway'ine bağlanabilmesi için SOCKS5 proxy desteği entegre edilmiştir.

### Trafik Ayrımı Mantığı (Traffic Isolation)
> [!IMPORTANT]
> **Sahibinden.com, WARP ve yabancı veri merkezi IP'lerini anında engeller (Cloudflare 403 Forbidden).**
> Bu bot **çift kanallı izole ağ mimarisi** kullanır:
> - **Discord API & Gateway Trafiği:** Cloudflare WARP SOCKS5 tüneli üzerinden (`socks5://127.0.0.1:40000`) yönlendirilir ve BTK engeli aşılır.
> - **Sahibinden Kazıma Trafiği:** WARP proxy'sine **asla** girmez; doğrudan WSL / sunucunuzun yerel Türk IP'sinden çıkar.

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

### 1. `/alarm-ara` (Evrensel Serbest Arama)
Kategori belirtmeden tüm Sahibinden genelinde anahtar kelime, bütçe aralığı ve şehir filtresiyle arama başlatır.

```
/alarm-ara kelime: honda civic min_fiyat: 600000 max_fiyat: 900000 sehir: Ankara
/alarm-ara kelime: iphone 15 pro max_fiyat: 65000
/alarm-ara kelime: rtx 4070 ti sehir: İstanbul
```
- **Özellik:** Sahibinden'in kelime aramasını kategoriye yönlendirirken filtreleri sıfırlamasını engeller; parametreleri otomatik olarak hedefe enjekte eder.

---

### 2. `/alarm-url` (Detaylı Sahibinden Linki Takibi)
Sahibinden web sitesinde istediğiniz kadar detaylı filtre (Örn: Hasar kayıtsız, boyasız, ilk sahibinden, belirli kasa tipi, vb.) seçip arama linkini bota verebilirsiniz.

```
/alarm-url url: https://www.sahibinden.com/otomobil/ankara-cankaya?sorting=date_desc&price_max=850000 alarm_adi: Çankaya Uygun Araçlar
```
- **Özellik:** 
  - Mobilden kopyalanan `m.sahibinden.com` linklerini otomatik masaüstü formatına dönüştürür.
  - Sayfalama parametrelerini (`pagingOffset`) sıfırlar, böylece ilk sayfadaki en güncel ilanlar taranır.
  - `sorting=date_desc` parametresini otomatik ekleyerek en yeni ilanların en üstte gelmesini garanti eder.

---

### 3. `/alarm-hizli` & `/alarm-kur` (Donanım & Kategori Sihirbazı)
Bilgisayar donanımı (RAM, Ekran Kartı, İşlemci) veya hazır kategorilerde hızlı alarm oluşturur.

```
/alarm-hizli kategori: ram ddr: ddr4 kapasite: 16gb marka: corsair max_fiyat: 2500
/alarm-hizli kategori: ekran-karti chipset: nvidia vram: 12gb max_fiyat: 20000
/alarm-hizli kategori: laptop-ram ddr: ddr5 kapasite: 32gb
```
- `/alarm-kur`: Kategori açılır menüsü (Select Menu) ve ardından RAM DDR/Kapasite seçebileceğiniz görsel bir modal pencere açar.

---

### 4. Yönetim Komutları

| Komut | Parametreler | Açıklama |
|---|---|---|
| `/alarmlarim` | `-` | Kurduğunuz tüm alarmları, ID numaralarını, filtre detaylarını ve aktif/duraklatılmış durumlarını listeler. |
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
- **Build Pack:** Coolify otomatik olarak **Docker Compose** veya **Dockerfile** tespit edecektir. (Varsayılan `Docker Compose` seçilidir).

### Adım 3: Ortam Değişkenlerini (Environment Variables) Tanımlayın
Coolify'daki uygulamanızın **Environment Variables** sekmesine gidin ve aşağıdaki değerleri ekleyin:

```env
DISCORD_BOT_TOKEN=buraya_discord_bot_tokeninizi_yazin
USE_WARP=true
WARP_HOST=127.0.0.1
WARP_PORT=40000
MAX_ALARMS_TOTAL=1000
MAX_ALARMS_PER_USER=100
CHECK_INTERVAL_SECONDS=90
BROWSER_CHANNEL=
HEADLESS=false
```

### Adım 4: WSL Hostunda Cloudflare WARP'ı Başlatın
WSL terminalinizde Cloudflare WARP'ın proxy modunda çalıştığından emin olun:
```bash
# WARP'ı proxy moduna ayarlayın ve bağlanın
warp-cli set-mode proxy
warp-cli connect

# Bağlantıyı doğrulayın
curl -x socks5://127.0.0.1:40000 https://discord.com
```

### Adım 5: Dağıtımı Başlatın (Deploy)
Coolify panelinde sağ üstteki **Deploy** butonuna tıklayın.
- Coolify depoyu çeker, Chromium ve Xvfb sanal ekranını barındıran Docker imajını derler.
- `network_mode: "host"` sayesinde WSL hostunuzdaki WARP proxy'sine doğrudan bağlanır.
- SQLite veritabanı `bot_data` Docker hacminde kalıcı olarak saklanır.

---

## 🐳 WSL / Docker Compose ile Dağıtım

Eğer Coolify kullanmadan doğrudan WSL terminalinde Docker Compose ile çalıştırmak isterseniz:

```bash
# 1. Repoyu klonlayın
git clone https://github.com/<kullanici_adiniz>/Sahibinden_Arama_Botu.git
cd Sahibinden_Arama_Botu

# 2. .env dosyasını oluşturup tokeninizi yazın
cp .env.example .env
nano .env

# 3. WSL üzerinde WARP'ı başlatın
warp-cli set-mode proxy
warp-cli connect

# 4. Konteyneri derleyip arka planda başlatın
docker compose up -d --build

# 5. Logları canlı izleyin
docker compose logs -f sahibinden-bot
```

---

## 💻 Yerel (Windows) Geliştirici Kurulumu

Windows üzerinde doğrudan Python ile çalıştırmak isterseniz:

```powershell
# 1. Bağımlılıkları yükleyin
pip install -r requirements.txt
playwright install chromium

# 2. .env dosyasını yapılandırın
cp .env.example .env
# .env içinde DISCORD_BOT_TOKEN değerini girin
# Windows Desktop WARP kullanıyorsanız USE_WARP=false bırakabilirsiniz

# 3. Botu başlatın
python src/main.py
```

---

## ⚙️ Ortam Değişkenleri (.env) Referansı

| Değişken | Varsayılan | Açıklama |
|---|---|---|
| `DISCORD_BOT_TOKEN` | *Zorunlu* | Discord Developer Portal'dan alınan Bot Token. |
| `DISCORD_GUILD_ID` | `None` | İsteğe bağlı. Belirli bir sunucu ID'si verilirse slash komutları 1 saat beklemeden anında yüklenir. |
| `USE_WARP` | `true` | Discord trafiğinin Cloudflare WARP SOCKS5 proxy üzerinden geçmesini sağlar (Türkiye için önerilir). |
| `WARP_HOST` | `127.0.0.1` | WARP SOCKS5 proxy sunucu adresi (Host network için `127.0.0.1`). |
| `WARP_PORT` | `40000` | Cloudflare WARP varsayılan SOCKS5 portu (`40000`). |
| `DISCORD_PROXY_URL` | `None` | Özel proxy bağlantı adresi (Belirtilirse `USE_WARP` ayarını ezer). |
| `MAX_ALARMS_TOTAL` | `1000` | Bot genelinde oluşturulabilecek maksimum aktif alarm sayısı (Optimum değer; istenirse 10000 yapılabilir). |
| `MAX_ALARMS_PER_USER` | `100` | Kullanıcı başına oluşturulabilecek maksimum alarm sayısı. |
| `CHECK_INTERVAL_SECONDS` | `90` | Alarmların kaç saniyede bir taranacağı periyot (Tavsiye: 60 - 180 sn). |
| `SCRAPER_TIMEOUT_SECONDS` | `35` | Her bir sayfa yüklemesi için maksimum zaman aşımı süresi. |
| `BROWSER_CHANNEL` | `""` | Docker/Linux üzerinde standart Chromium için boş bırakılır; Windows'ta `msedge` veya `chrome`. |
| `HEADLESS` | `false` | Linux konteynerinde sanal ekran (`Xvfb :99`) üzerinde Cloudflare Turnstile'ı aşmak için `false` kalmalıdır. |
| `PROXY_URL` | `None` | Sadece Sahibinden kazıma istekleri için opsiyonel Türk residential proxy adresi. |

---

## ❓ Sıkça Sorulan Sorular (SSS)

#### 1. Neden sanal ekran (Xvfb) ve tarayıcı kullanılıyor?
Sahibinden.com, standart HTTP istemcilerini (`requests`, `curl`) ve standart başsız (`headless=True`) tarayıcıları Cloudflare Turnstile ile anında bloklar. Bot, Linux sunucunun RAM belleğinde sanal bir monitör (`Xvfb`) oluşturur ve tarayıcıyı fiziksel ekranda açılmış gibi çalıştırarak bot algılama testlerinden başarıyla geçer.

#### 2. Alarm kurduğumda mevcut 50 ilan Discord'a düşecek mi?
**Hayır.** Bot "Ertelenmiş Baseline Priming" kullanır. Alarm açıldığında yayındaki mevcut tüm ilanlar veritabanına "görüldü" olarak işlenir. Yalnızca alarm kurulduktan sonra sisteme düşen **yeni ilanlar** kanala iletilir.

#### 3. İlan sahibi fiyat düşürdüğünde ne olur?
Daha önce bildirilen bir ilanın fiyatı indirildiğinde bot bunu fark eder, eski ve yeni fiyatı indirim oranıyla hesaplayarak kanala `📉 Fiyat Düştü!` başlığıyla özel bir indirim embed kartı gönderir.

#### 4. Testleri nasıl çalıştırırım?
Proje 34 adet kapsamlı birim, entegrasyon, limit ve proxy testine sahiptir:
```bash
python -m pytest -v
```

---

## 📄 Lisans

Bu proje [MIT Lisansı](LICENSE) altında açık kaynak olarak sunulmaktadır.
