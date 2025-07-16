# NLP Modülü - Gelişmiş ChatGPT WebSocket Bot Sistemi

Bu modül, ChatGPT'nin web arayüzünün kullandığı WebSocket bağlantısını taklit eden gelişmiş bir bot sistemini içerir. Playwright browser automation, proxy rotasyonu, anti-bot önlemleri ve performans izleme özellikleri ile donatılmıştır.

## 🚀 Yeni Özellikler

- **Playwright Browser Automation**: Gerçek tarayıcı otomasyonu ile ChatGPT'ye giriş
- **Proxy Rotasyonu**: MongoDB'den proxy listesi ile otomatik proxy değiştirme
- **Anti-bot Önlemleri**: İnsan benzeri davranış simülasyonu ve Cloudflare bypass
- **Performans İzleme**: Prometheus metrikleri ile detaylı performans analizi
- **Hata Yönetimi**: Otomatik kurtarma ve proxy rotasyonu
- **Session Yönetimi**: Oturum sürekliliği ve token yenileme

## 📦 Kurulum

### 1. Otomatik Kurulum
```bash
# Playwright ve tüm bağımlılıkları otomatik kur
python nlp/setup_playwright.py
```

### 2. Manuel Kurulum
```bash
# Gerekli paketleri kur
pip install playwright fake-useragent prometheus-client websockets

# Playwright browser'larını kur
playwright install chromium
```

## 🔧 Konfigürasyon

### Environment Variables (.env)
```bash
# ChatGPT kullanıcı bilgileri (browser otomasyonu için)
CHATGPT_USERNAME=your_email@example.com
CHATGPT_PASSWORD=your_password

# Opsiyonel: Access token (manuel giriş için)
CHATGPT_ACCESS_TOKEN=your_access_token

# MongoDB bağlantısı (proxy rotasyonu için)
MONGODB_URI=mongodb://localhost:27017
```

## 🎯 Kullanım

### 1. Browser ile Otomatik Giriş

#### CLI ile:
```bash
# Browser ile otomatik giriş yaparak iş ilanı analizi
python -m nlp.job_analyzer --use-browser --job-text "Senior Python Developer aranıyor..." --metrics

# Dosyadan iş ilanı analizi
python -m nlp.job_analyzer --use-browser --job-file job_description.txt --output analysis.json

# CV önerileri ile birlikte
python -m nlp.job_analyzer --use-browser --job-file job.txt --cv-file current_cv.txt --suggestions --metrics
```

#### Python API ile:
```python
import asyncio
from nlp.job_analyzer import JobAnalyzer

async def main():
    # Browser ile otomatik giriş
    analyzer = JobAnalyzer(use_browser=True)
    
    # İş ilanı analizi
    job_description = """
    Senior Python Developer aranıyor.
    Gereksinimler:
    - 5+ yıl Python deneyimi
    - Django, Flask framework bilgisi
    - MongoDB, PostgreSQL deneyimi
    """
    
    analysis = await analyzer.analyze_job_description(job_description)
    print(analysis)
    
    # Performans istatistikleri
    stats = analyzer.get_performance_stats()
    print(f"Başarı oranı: {stats['success_rate']:.2f}%")
    
    await analyzer.close()

asyncio.run(main())
```

### 2. Manuel Token ile Giriş

```python
import asyncio
from nlp.job_analyzer import JobAnalyzer

async def main():
    # Manuel token ile giriş
    analyzer = JobAnalyzer(access_token="your_token", use_browser=False)
    
    # İş ilanı analizi
    analysis = await analyzer.analyze_job_description(job_description)
    print(analysis)
    
    await analyzer.close()

asyncio.run(main())
```

### 3. Performans İzleme

```python
from nlp.performance_monitor import performance_monitor, ProxyRotator

# Metrikleri görüntüle
metrics = performance_monitor.get_metrics()
print(metrics)

# Proxy rotasyonu
proxy_rotator = ProxyRotator(performance_monitor)
best_proxy = proxy_rotator.get_best_proxy(proxy_list)
```

## 🔍 Performans Metrikleri

### Prometheus Metrikleri
- `chatgpt_requests_total`: Toplam request sayısı
- `chatgpt_response_time_seconds`: Response time histogramı
- `proxy_performance_score`: Proxy performans skorları
- `browser_sessions_total`: Browser session sayısı
- `chatgpt_errors_total`: Hata sayıları

### CLI ile Metrik Görüntüleme
```bash
# Performans metriklerini göster
python -m nlp.job_analyzer --use-browser --job-text "test" --metrics
```

## 🛡️ Anti-bot Önlemleri

### İnsan Benzeri Davranış
- Rastgele mouse hareketleri
- İnsan benzeri yazma simülasyonu
- Rastgele scroll davranışı
- Gecikme ve duraklamalar

### Cloudflare Bypass
- JavaScript challenge çözme
- Otomatik yeniden deneme
- Proxy rotasyonu ile IP değiştirme

### Proxy Yönetimi
- MongoDB'den proxy listesi alma
- Performans skoruna göre proxy seçimi
- Başarısız proxy'leri otomatik filtreleme

## 📊 Çıktı Formatları

### İş İlanı Analizi
```json
{
  "pozisyon": "Senior Python Developer",
  "sirket": "Tech Company",
  "gerekli_yetenekler": ["Python", "Django", "MongoDB"],
  "tercih_edilen_yetenekler": ["Docker", "Kubernetes"],
  "deneyim_seviyesi": "Senior",
  "egitim_seviyesi": "Lisans",
  "sorumluluklar": ["Kod yazma", "Code review"],
  "sartlar": ["5+ yıl deneyim"],
  "ozet": "Senior Python Developer pozisyonu"
}
```

### Performans İstatistikleri
```json
{
  "total_requests": 10,
  "successful_requests": 8,
  "failed_requests": 2,
  "success_rate": 80.0,
  "prometheus_metrics": "# HELP chatgpt_requests_total..."
}
```

## 🗂️ Dosya Yapısı

```
nlp/
├── chatgpt_websocket.py      # Gelişmiş WebSocket client
├── session_manager.py         # Token yönetimi
├── job_analyzer.py           # İş ilanı analizi
├── performance_monitor.py    # Performans izleme
├── setup_playwright.py       # Kurulum script'i
└── README.md                # Bu dosya
```

## 🔧 Gelişmiş Özellikler

### Proxy Rotasyonu
```python
from nlp.performance_monitor import ProxyRotator

proxy_rotator = ProxyRotator(performance_monitor)

# Proxy performansını güncelle
proxy_rotator.update_proxy_score("proxy1:8080", True, 1.5)
proxy_rotator.update_proxy_score("proxy2:8080", False, 5.0)

# En iyi proxy'yi seç
best_proxy = proxy_rotator.get_best_proxy(proxy_list)
```

### Hata Yönetimi
```python
from nlp.chatgpt_websocket import ErrorHandler

# Cloudflare challenge'ını çöz
await ErrorHandler.handle_cloudflare_block(page)

# Rate limit'i kontrol et
await ErrorHandler.handle_rate_limit(page)
```

### İnsan Benzeri Davranış
```python
from nlp.chatgpt_websocket import HumanBehaviorSimulator

# İnsan benzeri yazma
await HumanBehaviorSimulator.human_type(page, element, "text")

# Rastgele mouse hareketleri
await HumanBehaviorSimulator.random_mouse_movement(page)

# Rastgele scroll
await HumanBehaviorSimulator.random_scroll(page)
```

## 🚨 Hata Yönetimi

### Yaygın Hatalar ve Çözümleri

1. **Cloudflare Challenge**
   - Otomatik olarak çözülür
   - Proxy rotasyonu ile IP değiştirilir

2. **Rate Limit**
   - Proxy değiştirilir
   - Bekleme süresi eklenir

3. **Browser Başlatma Hatası**
   - Playwright'ı yeniden kurun
   - `python nlp/setup_playwright.py` çalıştırın

4. **Token Geçersiz**
   - Browser ile yeniden giriş yapın
   - Token'ı manuel olarak güncelleyin

## 🔒 Güvenlik

- Access token'ları güvenli şekilde saklayın
- .env dosyasını .gitignore'a ekleyin
- Proxy bilgilerini şifreleyin
- Rate limit'lere dikkat edin

## 📈 Performans Optimizasyonu

### Proxy Yönetimi
- En iyi performans gösteren proxy'leri önceliklendirin
- Başarısız proxy'leri otomatik filtreleyin
- Proxy rotasyonu ile yük dağıtımı yapın

### Browser Optimizasyonu
- Headless mod kullanın (production'da)
- Browser instance'larını paylaşın
- Session'ları yeniden kullanın

### Metrik İzleme
- Prometheus metriklerini izleyin
- Başarı oranlarını takip edin
- Response time'ları optimize edin

## 🤝 Katkı

Pull request ve issue açabilirsiniz. Her türlü öneri için teşekkürler!

## 📝 Lisans

Bu proje MIT lisansı altında lisanslanmıştır. 