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

## 4. Chromium Sekme Tutma Yaşam Döngüsü & Sıfır Bellek Sızıntısı (V2 Resource Bounds)
- **Problem**: Persistent context modunda tüm sekmelerin (`page.close()`) kapatılması, Chromium pencere hedefini (window target) yok ederek bir sonraki istekte `BrowserContext.new_page: Protocol error (Target.createTarget): Failed to open a new tab` hatasına yol açıyordu.
- **Çözüm**:
  - Ana sekme (`context.pages[0]`) sürekli canlı tutulur; yalnızca tarama esnasında açılan ikincil açılır pencereler (popuplar) kapatılır.
  - `finally: await context.pages[0].goto("about:blank")` çağrısı ile taranan sitenin tüm DOM düğümleri, zamanlayıcıları ve V8 JavaScript heap belleği tamamen serbest bırakılır. Hem sekme kapanma çökmesi engellenir hem de 24/7 çalıştırmada bellek tüketimi sabit kalır.
  - Boş arama sonuçlarında (`div.noResult`, `div.searchResultsRight`, `div.no-result`) Playwright'ın 10 saniye boş yere tablo beklemesi engellendi; sıfır sonuç anında tespit edilip dönülür.

---

## 5. İzleme Döngüsünde Silinmiş Alarm Güvenliği (V5 Resilience)
- **Problem**: Monitör döngüsü çalışırken bir kullanıcı `/alarm-sil` ile alarmını sildiğinde, o döngüde taranmak üzere hafızaya alınmış grup içinde silinmiş alarm kalabiliyordu.
- **Çözüm**:
  - `AlarmMonitor._run_loop` içinde her alarm taranmadan önce `database.get_alarm(alarm["id"])` ile veritabanından güncel durum teyit edilir. Alarm silinmiş veya pasife alınmışsa tarama anında atlanır.

---

## 6. Ölü Kod Temizliği
- **Temizlik**: Artık kullanılmayan eski `/alarm-kur` modal formları ve kategori seçim görünümleri (`SpecFilterModal`, `UniversalCategorySelectView`, `RamSpecSelectView`, `CategoryGroupSelectView`, `SubCategorySelectView`) kod tabanından tamamen kaldırıldı (660+ satır).

---

## 7. Login Wall Kısa Devresi, Parmak İzi Düzeltmesi & Oturum Isıtma (ADR-035)
- **Problem 1 (Login Wall Parametre Döngüsü)**: Sahibinden oturumsuz istekleri `https://secure.sahibinden.com/giris?return_url=...` adresine yönlendirdiğinde, `merge_dropped_redirect_params` fonksiyonu `/giris` URL'sine eksik arama parametrelerini (`sorting=date_desc&price_max=...`) ekleyip sayfayı tekrar giriş ekranına yönlendiriyor ve tablolar için 10 saniye bekliyordu.
- **Çözüm 1**: `merge_dropped_redirect_params` fonksiyonu `/giris`, `uye-girisi`, `secure.sahibinden.com`, `checkLoading` ve `challenge` URL'lerinde parametre birleştirmeyi derhal durdurup `None` döner. `_wait_for_challenge_and_table` giriş ekranını algıladığı anda 10 saniyelik beklemeden çıkar.
- **Problem 2 (Bot Tespiti)**: Başlatma bayraklarındaki `--start-minimized`, sayfanın gizli (`document.hidden = true`) kalmasına ve Cloudflare Turnstile Proof-of-Work betiklerinin zaman aşımına uğramasına neden oluyordu. Ayrıca Edge User-Agent ile Chromium Client Hints arasındaki uyumsuzluk bot olarak algılanıyordu.
- **Çözüm 2**: `--start-minimized` bayrağı kaldırıldı, User-Agent orijinal Chrome standardına çekildi. Taze tarayıcı profillerinde derin filtrelere girmeden önce anasayfadan temel oturum çerezleri (`vid`, `cdid`, `csss`, `__cf_bm`) otomatik ısıtılır.
- **Testler**: 14 test modülünde 296 testin tamamı (%100) yeşil durumdadır.
