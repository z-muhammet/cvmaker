# Job Scrapers Modülü - TheirStack API Token Alma

Bu modül, TheirStack platformunda otomatik hesap oluşturup API anahtarı alan basit bir web scraping script'idir.

## 📁 Modül Yapısı

```
job_scrapers/
├── __init__.py                    # Boş modül dosyası
├── signup.py                      # Ana scraping script'i
├── job_scraper_add_token.py       # Token'ı DB'ye ekleme
└── helpers.py                     # Basit yardımcı fonksiyonlar
```

## 🔧 Ne Yapar?

### `signup.py` - Ana Script
1. **Temp Mail Alır**: tempmail1.com'dan geçici e-posta alır
2. **TheirStack'te Kayıt Olur**: Sahte isimle hesap oluşturur
3. **E-posta Doğrular**: Gelen kodu otomatik alır
4. **API Key Alır**: API anahtarını kopyalar
5. **JSON Çıktısı Verir**: `{"email": "...", "api_key": "..."}`

### `job_scraper_add_token.py` - DB Entegrasyonu
- API key'i MongoDB'ye kaydeder
- Aynı key varsa eklemez
- Basit token limit takibi yapar

### `helpers.py` - Yardımcı Fonksiyonlar
- `random_int()`: Rastgele sayı
- `random_pause()`: Rastgele bekleme
- `retry()`: 3 kez deneme
- `stealthify()`: Basit anti-detection (opsiyonel)

## 🛠️ Kurulum

```bash
# Gerekli paketler
pip install playwright fake-useragent faker python-dotenv motor

# Playwright browser kur
playwright install chromium

# MongoDB başlat
mongod --dbpath /path/to/data/db
```

## 🎯 Kullanım

### Basit Kullanım
```bash
# Sadece token al
python job_scrapers/signup.py
# Çıktı: {"email": "temp@...", "api_key": "sk-..."}

# Token'ı DB'ye ekle
python job_scrapers/job_scraper_add_token.py
```

### Environment Variables
```bash
# .env dosyası
HEADLESS=false                    # Browser görünürlüğü
HTTP_PROXY=proxy:port            # Proxy (opsiyonel)
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=jobscrapper
```

## ⚠️ Sınırlamalar

- **Basit Anti-Detection**: Sadece temel önlemler
- **Tek Site**: Sadece TheirStack
- **Manuel Hata Yönetimi**: Hata durumunda screenshot alır
- **Proxy Desteği**: Sadece basit HTTP proxy
- **Rate Limiting**: Manuel bekleme süreleri

## 🚨 Bilinen Sorunlar

1. **Temp Mail Erişim**: Bazen tempmail1.com erişilemez
2. **TheirStack Değişiklikleri**: Site yapısı değişirse script bozulur
3. **Captcha**: Captcha varsa script çalışmaz
4. **Rate Limiting**: Çok sık çalıştırırsan ban yiyebilirsin

## 🔧 Basit Konfigürasyon

```python
# signup.py içinde değiştirilebilir
TIMEOUT_MS = 20_000              # Sayfa yükleme süresi
TIMEZONES = ["Europe/Istanbul"]   # Zaman dilimi
LOCALES = ["tr-TR"]              # Dil ayarı
```

## 📝 Örnek Çıktı

```json
{
  "email": "temp123@tempmail1.com",
  "api_key": "sk-theirstack-abc123..."
}
```

## 🆘 Sorun Giderme

### Yaygın Hatalar

1. **"invalid email copied"**
   - Temp mail sitesi değişmiş olabilir
   - Proxy kullanmayı dene

2. **"OTP code not found"**
   - E-posta gelmemiş olabilir
   - Daha uzun bekle

3. **"API key copy failed"**
   - TheirStack sitesi değişmiş olabilir
   - Selector'ları güncelle

### Debug İçin
```bash
# Screenshot'ları kontrol et
ls shots/

# Log'ları detaylı gör
python job_scrapers/signup.py 2>&1 | tee debug.log
```

## 💡 İpuçları

- **Proxy Kullan**: IP ban'ından kaçın
- **Bekleme Süreleri**: Rate limiting için yeterli bekle
- **Screenshot'ları Kontrol Et**: Hata durumunda ne olduğunu gör
- **Selector'ları Güncelle**: Site değişirse güncelle

---

**Not**: Bu script TheirStack'in kullanım şartlarına uygun kullanılmalıdır. Çok sık çalıştırmayın. 