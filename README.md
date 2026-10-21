# Sahibinden Discord Arama & Bildirim Botu

Sahibinden.com üzerinde **tüm kategorilerde** (Donanım/RAM/GPU/CPU, Vasıta/Otomobil/Motosiklet, Emlak/Satılık-Kiralık Daire, Cep Telefonu ve genel aramalar) kriter ve filtrelere göre alarm kuran; **alarmın kurulduğu andan itibaren eklenen yeni ilanları** ve **mevcut ilanlardaki fiyat düşüşlerini** anında Discord kanalınıza zengin Embed kartlarıyla bildiren gelişmiş Discord botu.

---

## 🚀 Öne Çıkan Özellikler

1. **3 Evrensel Alarm Kurma Yöntemi**:
   - **Yöntem 1 (`/alarm-ara`):** Kategori seçmeden tüm Sahibinden genelinde kelime, fiyat ve il filtreli arama (otomatik kategori çıkarımı ve yönlendirme koruması ile).
   - **Yöntem 2 (`/alarm-url`):** Sahibinden web sitesinde seçtiğiniz 20+ detaylı filtreyi içeren hazır arama linkini doğrudan takibe alma (mobil link dönüştürme, sayfalama sıfırlama ve `sorting=date_desc` garantisi ile).
   - **Yöntem 3 (`/alarm-kur` & `/alarm-hizli`):** Discord Autocomplete destekli görsel kategori seçici, RAM DDR/Kapasite sihirbazı ve tek satırda hızlı kurulum.
2. **Akıllı Alias & Donanım Filtreleri**:
   - **Bellek (Masaüstü & Laptop SODIMM):** DDR, DDR2, DDR3, DDR3L, DDR4, DDR5 ve 4 GB'dan 2x 32 GB'a kadar kapasite ve marka (`Corsair`, `Kingston`, `G.Skill` vb.) filtreleri.
   - **Ekran Kartı (GPU) & İşlemci (CPU):** Chipset (`Nvidia`, `AMD`, `Intel`) ve VRAM (`6 GB` - `24 GB`) filtreleri.
   - **81 İl Desteği:** Türkiye'nin 81 ilinin tamamı için Türkçe karakter duyarlı şehir filtreleme.
3. **Sıfır Spam, Ertelenmiş Baseline Priming & Kesin Deduplication**:
   - Alarm ilk kurulduğunda yayındaki mevcut ilanlar `seen_listings` tablosuna baseline olarak kaydedilir (`is_primed = 1`).
   - İlk kurulum anında bağlantı/WAF gecikmesi yaşansa dahi arka plan izleyicisi ilk döngüde geçmiş ilanları sessizce arşivler; **asla geçmiş ilan spam'i yapmaz**.
   - Defense-in-depth fiyat doğrulaması sayesinde reklam (`nativeAd`) veya bütçe dışı ilanlar elenir.
4. **Otomatik Fiyat Düşüşü Bildirimi (`📉 Fiyat Düştü!`)**:
   - Takip edilen bir aramada daha önce görülen bir ilanın fiyatı satıcı tarafından düşürüldüğünde, eski ve yeni fiyatı indirim oranıyla birlikte karşılaştırmalı olarak bildirir.
5. **Anti-Bot & Self-Healing Scraper**:
   - Cloudflare Turnstile (`checkLoading`) geçişlerini otomatik çözer, tarayıcı kapanması durumunda oturumu kendi kendine onarır ve opsiyonel `PROXY_URL` destekler.
6. **Türkiye (BTK Ban) & Cloudflare WARP Desteği (İzole Trafik)**:
   - Discord'un Türkiye'de engelli olması sorununu Cloudflare WARP SOCKS5 proxy'si ile çözer.
   - **Önemli Trafik İzolasyonu**: Discord API/Gateway trafiği WARP tünelinden geçerken, Sahibinden tarama istekleri doğrudan yerel Türk IP'nizden (veya Türk residential proxy'den) çıkar; böylece Sahibinden yabancı/datacenter IP bloku koymaz.
7. **Docker, WSL & Coolify Desteği (Xvfb Virtual Display)**:
   - Linux konteynerlerinde Cloudflare Turnstile korumasını aşmak için arka planda sanal X11 ekranı (`Xvfb :99`) çalıştırır.

---

## 🛡️ Türkiye'de Kullanım & Cloudflare WARP Entegrasyonu

Türkiye'de Discord servisleri BTK tarafından erişime engellendiğinde, botun Discord Gateway'ine bağlanabilmesi için SOCKS5 proxy desteği entegre edilmiştir.

### Trafik Ayrımı Mantığı (Traffic Isolation)
- **Discord Trafiği (API + Gateway):** `USE_WARP=true` ayarlandığında `socks5://127.0.0.1:40000` (veya Coolify sidecar `socks5://warp:1080`) üzerinden akar ve Discord'a kesintisiz bağlanır.
- **Sahibinden Kazıma Trafiği:** Asla WARP üzerinden gönderilmez! Sahibinden yabancı veya veri merkezi (WARP) IP'lerini anında blokladığı için, web istekleri doğrudan WSL / sunucunuzun Türk IP adresinden gerçekleştirilir.

### WARP Kullanım Seçenekleri

#### Seçenek 1: WSL Host Üzerinde WARP (`warp-cli`) (Tavsiye Edilen)
WSL dağıtımınızın terminalinde Cloudflare WARP'ı proxy modunda başlatın:
```bash
# WARP'ı proxy moduna ayarlayın
warp-cli set-mode proxy

# WARP'a bağlanın (Varsayılan SOCKS5 portu: 127.0.0.1:40000)
warp-cli connect

# Bağlantıyı test edin
curl -x socks5://127.0.0.1:40000 https://discord.com
```

Docker Compose kullanıyorsanız, `docker-compose.yml` dosyasında `network_mode: "host"` satırını açın ve `.env` dosyanıza şu değerleri girin:
```env
USE_WARP=true
WARP_HOST=127.0.0.1
WARP_PORT=40000
```

#### Seçenek 2: Coolify / Docker Compose WARP Sidecar (`caomingjun/warp`)
WSL hostunuza hiçbir paket kurmak istemiyorsanız veya Coolify üzerinden tek tıkla izole bir stack kurmak istiyorsanız:
1. `docker-compose.yml` içerisindeki `warp` servisini ve `depends_on: [warp]` bölümünü yorum satırından çıkarın.
2. `.env` dosyanıza şu değerleri girin:
```env
USE_WARP=true
WARP_HOST=warp
WARP_PORT=1080
```
Coolify / Docker her iki konteyneri aynı ağda başlatır ve bot otomatik olarak Discord trafiğini `warp` servisi üzerinden yönlendirir.

---

## 🐳 Docker & Coolify Kurulumu

### 1. Dosyaları Hazırlama
Proje dizininde `.env` dosyasını oluşturun:
```bash
cp .env.example .env
nano .env
```
`.env` dosyanıza `DISCORD_BOT_TOKEN` değerinizi girin.

### 2. Docker Compose ile Başlatma (WSL / Linux)
```bash
docker compose up -d --build
```

Logları incelemek için:
```bash
docker compose logs -f sahibinden-bot
```

Durdurmak için:
```bash
docker compose down
```

### 3. Coolify Üzerinde Dağıtım
1. **Coolify Dashboard**'a girin -> **Projects** -> **Add New Resource** -> **Docker Compose**.
2. GitHub reponuzu bağlayın veya reponun `docker-compose.yml` dosyasını seçin.
3. Coolify Environment Variables sekmesinde `.env` içeriğinizi (özellikle `DISCORD_BOT_TOKEN`, `USE_WARP=true`, vb.) tanımlayın.
4. **Deploy** butonuna basın. Coolify botu ve veritabanı hacmini (`bot_data`) otomatik olarak ayağa kaldıracaktır.

---

## 💻 Yerel (Local) Windows Kurulumu

### 1. Gereksinimler
- Python 3.10+ (Python 3.12 veya 3.15 önerilir)
- Microsoft Edge veya Google Chrome

### 2. Bağımlılıkları Yükleme
```powershell
pip install -r requirements.txt
playwright install chromium
```

### 3. Yapılandırma (`.env`)
```env
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
CHECK_INTERVAL_SECONDS=90
BROWSER_CHANNEL=msedge
HEADLESS=False

# Türkiye'de Windows üzerinde WARP Desktop açıkken proxy gerekmez (WARP tüm sistemi tüneller).
# Eğer sadece socks proxy kullanmak isterseniz:
USE_WARP=false
```

### 4. Botu Başlatma
```powershell
python src/main.py
```

---

## 🎮 Discord Komutları

| Komut | Açıklama |
|---|---|
| `/alarm-ara kelime:"honda civic" min_fiyat:500000 max_fiyat:800000 sehir:ankara` | Tüm Sahibinden genelinde kategori bağımsız evrensel arama alarmı kurar. |
| `/alarm-kur [kategori]` | Görsel kategori seçici ve RAM/Donanım filtre sihirbazı ile interaktif alarm kurar. |
| `/alarm-hizli kategori:ram ddr:ddr4 kapasite:16gb marka:corsair max_fiyat:2500` | Tek satırda kategori, DDR, kapasite, marka/chipset, fiyat ve şehir ile alarm açar. |
| `/alarm-url url:<sahibinden_linki> alarm_adi:<isim>` | Sahibinden'de filtrelediğiniz herhangi bir kategorideki hazır linki doğrudan takibe alır. |
| `/alarmlarim` | Tanımladığınız tüm alarmları, filtre özetlerini ve aktif/duraklatılmış durumlarını listeler. |
| `/alarm-durum alarm_id:<id> aktif:<True/False>` | Mevcut bir alarmı silmeden geçici olarak duraklatır veya yeniden aktifleştirir. |
| `/alarm-sil [alarm_id]` | Seçtiğiniz bir alarmı ve geçmiş kayıtlarını siler. |
| `/alarm-test alarm_id:<id>` | İlgili alarmın arama sonucunu anında test edip en güncel ilanı önizler. |

---

## 🧪 Testleri Çalıştırma
Tüm birim, entegrasyon ve proxy testlerini çalıştırmak için:
```powershell
python -m pytest -v
```
