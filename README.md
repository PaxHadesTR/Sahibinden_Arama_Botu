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

1. **3 Güçlü Alarm Kurma Yöntemi**:
   - **Yöntem 1 (`/alarm-hizli`):** Tek satırda kategori, özellik/birim (DDR, Kapasite, Vites, 3+1 vb.), marka/model ve bütçe ile saniyeler içinde alarm kurma.
   - **Yöntem 2 (`/alarm-ara`):** Kategori seçmeden tüm Sahibinden genelinde anahtar kelime, bütçe aralığı ve şehir filtresiyle serbest arama başlatma.
   - **Yöntem 3 (`/alarm-url`):** Sahibinden web sitesinde seçtiğiniz 20+ detaylı filtreli arama URL'sini doğrudan takibe alma. (Mobil URL'leri masaüstüne çevirir, sayfalama parametrelerini sıfırlar, `sorting=date_desc` zorlar).
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
Kategori, özellik/birim ve bütçe kriterlerini tek satırda yazarak saniyeler içinde alarm kurun (Tüm kategorilerle uyumlu evrensel parametreler):
```
# Vasıta / Otomobil Alarmı
/alarm-hizli kategori: otomobil marka_veya_model: Civic ozellik: Otomatik sehir: Ankara max_fiyat: 950000

# Emlak / Satılık Daire Alarmı
/alarm-hizli kategori: satilik-daire marka_veya_model: Kadıköy ozellik: 3+1 sehir: İstanbul max_fiyat: 7500000

# RAM Donanım Alarmı (MB, GB, TB, Dual-Kit)
/alarm-hizli kategori: ram ozellik: 16 GB DDR4 marka_veya_model: Corsair max_fiyat: 2500
/alarm-hizli kategori: ram ozellik: 512 MB DDR2 max_fiyat: 300
/alarm-hizli kategori: ram ozellik: 2x 16 GB DDR5 marka_veya_model: G.Skill

# SSD & Ekran Kartı (VRAM)
/alarm-hizli kategori: ssd ozellik: 1 TB kelime: NVMe max_fiyat: 3500
/alarm-hizli kategori: gpu ozellik: 12 GB marka_veya_model: Nvidia kelime: RTX 4070 max_fiyat: 22000

# Tarım / Traktör, Bisiklet & Ev Aletleri
/alarm-hizli kategori: traktor marka_veya_model: New Holland ozellik: 4x4 max_fiyat: 1200000
/alarm-hizli kategori: bisiklet marka_veya_model: Carraro ozellik: 28 Jant max_fiyat: 15000
/alarm-hizli kategori: klima marka_veya_model: Mitsubishi ozellik: 12000 BTU max_fiyat: 35000
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
/alarm-url url: https://www.sahibinden.com/otomobil?sorting=date_desc&price_max=950000 alarm_adi: Civic Arama
```

---

### 5. Yönetim Komutları

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
- Coolify depoyu çeker, `warp` sidecar ve `sahibinden-bot` konteynerlerini ayağa kaldırır.
- Discord bağlantısı `socks5://warp:1080` üzerinden gerçekleşir.
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

**S: Coolify'da her 'Deploy' veya 'Redeploy' yaptığımda botun alarmları ve geçmişi siliniyor, neden?**  
C: Docker konteynerleri doğası gereği geçicidir (stateless). Eğer Coolify üzerinde Persistent Storage tanımlanmazsa, her deploy işleminde eski konteyner yok edilip sıfırdan oluşturulur; bu da `/app/data/sahibinden_bot.db` dosyasını siler. Çözüm: Coolify panelinde uygulamanızın **Storages** sekmesine gidip **Destination Path** olarak `/app/data` kalıcı depolamasını ekleyin ve ardından Redeploy yapın. Artık alarmlarınız hiçbir deployda silinmeyecektir.

---

## 📜 Lisans

Bu proje [MIT Lisansı](LICENSE) altında lisanslanmıştır. Açık kaynaklıdır ve özgürce kullanılabilir, geliştirilebilir ve dağıtılabilir.
