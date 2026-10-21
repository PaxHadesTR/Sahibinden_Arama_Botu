# Sahibinden Discord Arama & Bildirim Botu

Sahibinden.com üzerinde **tüm kategorilerde** (Donanım/RAM/GPU/CPU, Vasıta/Otomobil/Motosiklet, Emlak/Satılık-Kiralık Daire, Cep Telefonu ve genel aramalar) kriter ve filtrelere göre alarm kuran; **alarmın kurulduğu andan itibaren eklenen yeni ilanları** ve **mevcut ilanlardaki fiyat düşüşlerini** anında Discord kanalınıza zengin Embed kartlarıyla bildiren gelişmiş Discord botu.

---

## 🚀 Özellikler

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

---

## 🛠️ Kurulum

### 1. Gereksinimler
- Python 3.10+ (Python 3.15 test edildi)
- Microsoft Edge veya Google Chrome (Windows üzerinde yüklü olması yeterlidir)

### 2. Bağımlılıkları Yükleme
```powershell
pip install -r requirements.txt
playwright install chromium
```

### 3. Yapılandırma (`.env`)
Proje kök dizinindeki `.env` dosyasını açıp Discord Bot tokeninizi ekleyin:

```env
DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN_HERE
CHECK_INTERVAL_SECONDS=90
BROWSER_CHANNEL=msedge
HEADLESS=False
# PROXY_URL=http://user:pass@host:port
```

> **Not:** Discord Developer Portal'dan botunuzu oluştururken `bot` ve `applications.commands` (Slash Commands) yetkilerini vermeyi unutmayın.

---

## 🎮 Discord Komutları

| Komut | Açıklama |
|---|---|
| `/alarm-ara kelime:"honda civic" min_fiyat:500000 max_fiyat:800000 sehir:ankara` | Tüm Sahibinden genelinde kategori bağımsız evrensel alarm kurar. |
| `/alarm-kur [kategori]` | Görsel kategori seçici ve RAM/Donanım filtre sihirbazı ile interaktif alarm kurar. |
| `/alarm-hizli kategori:ram ddr:ddr4 kapasite:16gb marka:corsair max_fiyat:2500` | Tek satırda kategori, DDR, kapasite, marka/chipset, fiyat ve şehir ile alarm açar. |
| `/alarm-url url:<sahibinden_linki> alarm_adi:<isim>` | Sahibinden'de filtrelediğiniz herhangi bir kategorideki hazır linki doğrudan takibe alır. |
| `/alarmlarim` | Tanımladığınız tüm alarmları, filtre özetlerini ve aktif/duraklatılmış durumlarını listeler. |
| `/alarm-durum alarm_id:<id> aktif:<True/False>` | Mevcut bir alarmı silmeden geçici olarak duraklatır veya yeniden aktifleştirir. |
| `/alarm-sil [alarm_id]` | Seçtiğiniz bir alarmı ve geçmiş kayıtlarını siler. |
| `/alarm-test alarm_id:<id>` | İlgili alarmın arama sonucunu anında test edip en güncel ilanı önizler. |

---

## 🧪 Testleri Çalıştırma
```powershell
python -m pytest -v
```
