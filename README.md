# Sahibinden Discord Arama & Bildirim Botu

Sahibinden.com üzerinde belirli kriter ve filtrelere (örnek: RAM Bellek, DDR tipi, Kapasite, Fiyat, Şehir vb.) göre alarm kuran ve **alarmın kurulduğu andan itibaren eklenen yeni ilanları** anında Discord kanalınıza zengin Embed kartlarıyla bildiren gelişmiş Discord botu.

---

## 🚀 Özellikler

1. **Akıllı Alias & Kategori Eşleme**:
   - `ram`, `bellek`, `ekran kartı`, `gpu`, `işlemci` gibi kısaltmaları otomatik olarak Sahibinden kategorilerine dönüştürür.
2. **Kriter & Filtre Desteği (Arama Seçenekleri)**:
   - **Bellek Tipi:** DDR, DDR2, DDR3, DDR3L, DDR4, DDR5
   - **Kapasite:** 4 GB, 8 GB, 16 GB, 32 GB, 64 GB, 2x 8 GB vb.
   - **Fiyat:** Min TL ve Max TL filtreleri
   - **Şehir:** İstanbul, Ankara, İzmir vb. il bazlı filtreleme
   - **Arama Kelimesi:** Özel anahtar kelime arama (`query_text`)
3. **Doğrudan URL Desteği (`/alarm-url`)**:
   - İsterseniz Sahibinden web sitesinde istediğiniz tüm filtreleri seçip linki doğrudan bota verebilirsiniz. Bot bu linke `sorting=date_desc` ekleyerek en yeni ilanları otomatik izler.
4. **Sıfır Spam & Kesin Deduplication**:
   - Alarm ilk kurulduğunda o anda yayında olan mevcut ilanlar baseline olarak taranır ve kaydedilir.
   - Yalnızca alarm başladıktan sonra eklenen **gerçekten yeni** ilanlar için Discord bildirimi gönderilir.
   - Her ilan sadece 1 kez bildirilir.
5. **Anti-Bot & Cloudflare Evasion**:
   - Sahibinden'in Cloudflare/Akamai Turnstile korumalarını aşmak için optimize edilmiş persistent browser oturumu ve jitter gecikmeleri kullanır.

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
```

> **Not:** Discord Developer Portal'dan botunuzu oluştururken `bot` ve `applications.commands` (Slash Commands) yetkilerini vermeyi unutmayın.

---

## 🎮 Discord Komutları

| Komut | Açıklama |
|---|---|
| `/alarm-ara kelime:"honda civic" min_fiyat:500000 max_fiyat:800000` | Tüm Sahibinden genelinde (Vasıta, Emlak, İkinci El vb.) kategori bağımsız evrensel alarm kurar. |
| `/alarm-kur kategori:ram` | İnteraktif sihirbaz ile DDR nesli, kapasite ve fiyat modalı üzerinden alarm kurar. |
| `/alarm-hizli kategori:araba min_fiyat:400000 max_fiyat:750000 sehir:ankara` | Tek satırda kategori ve parametrelerle hızlı alarm açar. |
| `/alarm-url url:<sahibinden_linki> alarm_adi:<isim>` | Sahibinden'de filtrelediğiniz herhangi bir kategorideki hazır linki doğrudan takibe alır. |
| `/alarmlarim` | Tanımladığınız tüm aktif alarmları ve hedef linklerini listeler. |
| `/alarm-sil [alarm_id]` | Seçtiğiniz bir alarmı ve veritabanı kayıtlarını siler. |
| `/alarm-test alarm_id:<id>` | İlgili alarmın arama sonucunu anında test edip en güncel ilanı önizler. |

---

## 🧪 Testleri Çalıştırma
```powershell
pytest -v
```
