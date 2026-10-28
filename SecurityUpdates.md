# Security & Architectural Hardening Updates

Bu doküman, Sahibinden Discord Botu projesine uygulanan güvenlik (Security), veri bütünlüğü (Data Integrity), eşzamanlılık (Concurrency) ve kaynak yönetimi (Resource Bounds) sertleştirme adımlarını özetler.

---

## 1. Discord UI Bileşenlerinde Yetkilendirme Kontrolü (V4 Security & Authorization)
- **Problem**: Discord etkileşimli Select Menu ve Button bileşenleri (Dropdown & Butonlar), mesajın gönderildiği kanaldaki diğer yetkisiz kullanıcılar tarafından tetiklenebiliyordu. Yetkisiz bir kullanıcı başka birinin alarmını silebilir veya filtrelerini değiştirebilirdi.
- **Çözüm**:
  - `DeleteAlarmSelect` ve `DeleteAlarmView` sınıflarına `user_id` bağlandı. Menüden seçim yapıldığında `interaction.user.id != self.user_id` kontrolü yapılarak yetkisiz işlemler anında `ephemeral` hata mesajıyla reddedildi.
  - `DetailFilterSelectView` (sayfalama, özellik filtreleri, kaydetme) ve `AlarmQuickActionView` (filtre düzenleme butonu) bileşenlerine katı sahip doğrulama (`user_id == interaction.user.id`) uygulandı.

---

## 2. Merkezi Veritabanı Bağlantı Yöneticisi & Foreign Key Zorunluluğu (V3 Integrity)
- **Problem**: SQLite mimarisinde `PRAGMA foreign_keys = ON;` ayarı bağlantı (connection) bazlıdır ve varsayılan olarak `OFF` gelir. Kod genelindeki dağınık `aiosqlite.connect` çağrılarında foreign key kısıtlamaları ve busy timeout ayarları garanti altına alınamıyordu.
- **Çözüm**:
  - `Database.get_connection()` merkezi asenkron context manager fonksiyonu eklendi.
  - Her bağlantı açılışında `PRAGMA foreign_keys = ON;` ve `PRAGMA busy_timeout = 15000;` zorunlu kılındı.
  - Veritabanı servisindeki 16 farklı sorgu metodunun tamamı doğrudan `self.get_connection()` yapısına geçirildi.

---

## 3. Asenkron Arka Plan Baselining & Kilit Çakışması Önleme (V1 Concurrency & Responsiveness)
- **Problem**: `/alarm-ara`, `/alarm-url` ve `/alarm-hizli` komutları çalıştırıldığında, ilk ilan tablosunu çekmek için `StealthScraper._lock` kilidini senkron olarak bekliyordu. Arka plan monitörü (`AlarmMonitor`) o esnada tarama yapıyorsa, Discord slash komutu 3 saniyelik deferral SLA sınırını aşarak Gateway zaman aşımına düşebiliyordu.
- **Çözüm**:
  - Komut yanıt süresi <100ms seviyesine indirildi.
  - Alarm kaydı veritabanına `is_primed = 0` bayrağıyla anında yazılarak kullanıcıya teyit embed'i verilir.
  - İlk tarama (baseline priming), `_schedule_background_priming` ile arka planda asenkron bir görev olarak çalıştırılır. Olası geçici ağ/tarayıcı hatalarında işlem monitör döngüsüne devredilir ve asla geçmiş ilan spam'i yapılmaz.

---

## 4. İzole Chromium Sayfa Yaşam Döngüsü & Sıfır Bellek Sızıntısı (V2 Resource Bounds)
- **Problem**: Scraper motoru tüm taramalarda tek bir Chromium sekmesini (`context.pages[0]`) sürekli açık tutuyordu. Uzun süreli çalıştırmalarda Chromium renderer süreçlerinde DOM ağacı ve JavaScript heap birikerek Docker konteynerinin bellek tüketimini artırıyordu.
- **Çözüm**:
  - İstek başına izole sekme modeli (`page = await context.new_page()`) devreye alındı.
  - `try...finally: await page.close()` bloğu ile her tarama sonrasında sekme bellekten tamamen tahliye edilir.
  - Boş arama sonuçlarında (`div.noResult`, `div.searchResultsRight`, `div.no-result`) Playwright'ın 10 saniye boş yere tablo beklemesi engellendi; sıfır sonuç anında tespit edilip dönülür.

---

## 5. İzleme Döngüsünde Silinmiş Alarm Güvenliği (V5 Resilience)
- **Problem**: Monitör döngüsü çalışırken bir kullanıcı `/alarm-sil` ile alarmını sildiğinde, o döngüde taranmak üzere hafızaya alınmış grup içinde silinmiş alarm kalabiliyordu.
- **Çözüm**:
  - `AlarmMonitor._run_loop` içinde her alarm taranmadan önce `database.get_alarm(alarm["id"])` ile veritabanından güncel durum teyit edilir. Alarm silinmiş veya pasife alınmışsa tarama anında atlanır.

---

## 6. Ölü Kod Temizliği & Test Bütünlüğü
- **Temizlik**: Artık kullanılmayan eski `/alarm-kur` modal formları ve kategori seçim görünümleri (`SpecFilterModal`, `UniversalCategorySelectView`, `RamSpecSelectView`, `CategoryGroupSelectView`, `SubCategorySelectView`) kod tabanından tamamen kaldırıldı (660+ satır).
- **Testler**: 14 test modülünde 294 testin tamamı (%100) yeşil durumdadır.
