# CV Maker - İş İlanı Analizi ve CV Optimizasyon Sistemi

Bu proje, iş ilanlarını otomatik olarak toplayan, analiz eden ve ATS (Applicant Tracking System) uyumlu CV'ler oluşturan kapsamlı bir Python sistemidir.

## 🚀 Özellikler

- **Otomatik İş İlanı Toplama**: Son 24 saatteki iş ilanlarını API üzerinden çeker
- **AI Destekli İlan Analizi**: NLP API ve Playwright ile ilan analizi
- **ATS Uyumlu CV Üretimi**: İlan gereksinimlerine göre optimize edilmiş LaTeX CV'ler
- **Proxy Yönetimi**: Otomatik proxy toplama ve test etme
- **Token Yönetimi**: API token'larının otomatik yenilenmesi ve kullanım takibi
- **Zamanlanmış Görevler**: APScheduler ile otomatik çalışan görevler
- **REST API**: FastAPI ile modern web arayüzü

## 📁 Proje Yapısı

```
cvmaker/
├── job_scrapers/          # İş ilanı toplama modülleri
│   ├── token_requester.py # Son 24 saatlik işleri çeker
│   └── signup.py         # Token oluşturma ve yenileme
├── nlp/                   # Doğal dil işleme modülleri
│   ├── job_processor.py  # Raw job'ları analiz eder
│   ├── job_analyzer.py   # Web tabanlı ilan analizi
│   ├── nlpApi.py         # API tabanlı ilan analizi
│   └── mistral_websocket.py # Mistral AI entegrasyonu
├── proxies/               # Proxy yönetimi
│   ├── manager.py        # Proxy izleme ve test
│   ├── fetcher.py        # Proxy toplama
│   └── tester.py         # Proxy test etme
├── cv_generator/          # CV üretimi
│   └── generate_ats_cv.py # ATS uyumlu CV oluşturma
├── guestscheduler/        # Zamanlanmış görevler
│   └── main_scheduler.py # APScheduler konfigürasyonu
├── dbprocess/            # Veritabanı işlemleri
├── rest_api.py           # FastAPI ana uygulaması
└── requirements.txt      # Python bağımlılıkları
```

## 🛠️ Kurulum

### 1. Gereksinimler

- Python 3.8+
- MongoDB
- Node.js (Playwright için)

### 2. Bağımlılıkları Yükle

```bash
pip install -r requirements.txt
```

### 3. Playwright Kurulumu

```bash
playwright install
```

### 4. Ortam Değişkenleri

`.env` dosyası oluşturun:

```env
OPENAI_API_KEY=your_openai_key
LINKEDIN_EMAIL=your_linkedin_email
LINKEDIN_PASSWORD=your_linkedin_password
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB=jobscrapper
MISTRAL_API_KEY=your_mistral_key
CHATGPT_USERNAME=your_chatgpt_username
CHATGPT_PASSWORD=your_chatgpt_password
```

## 🚀 Kullanım

### API Başlatma

```bash
python rest_api.py
```

API `http://localhost:8000` adresinde çalışacaktır.

### Scheduler Başlatma

```bash
curl -X POST "http://localhost:8000/start" \
     -H "Content-Type: application/json" \
     -d '{"command": "system on start"}'
```

### Manuel Komutlar

#### 1. Son 24 Saatlik İşleri Çek
```bash
python -m job_scrapers.token_requester
```

#### 2. Raw Job'ları Analiz Et
```bash
python -m nlp.job_processor --batch-size 5 --max-retries 2
```

#### 3. AI Web Analizi
```bash
python -m nlp.job_analyzer --use-browser --job-text "Senior Python Developer aranıyor. Gereksinimler: Python, Django, MongoDB deneyimi. 3+ yıl deneyim gerekli." --metrics
```

#### 4. API Analizi
```bash
python -m nlp.nlpApi --job-text "Senior Python Developer aranıyor. Gereksinimler: ..."
```

#### 5. Proxy Sorgu (Sürekli Açık)
```bash
python -m proxies.manager --monitor --linkedin-interval 1
```

#### 6. Token Yarat ve DB'ye Kaydet
```bash
python -m job_scrapers.signup
```

#### 7. İlan CV Yarat
```bash
python -m cv_generator.generate_ats_cv --raw-cv "CV metni" --job-id 123 --target-lang TR
```

## ⏰ Zamanlanmış Görevler

Sistem aşağıdaki görevleri otomatik olarak çalıştırır:

| Görev | Sıklık | Açıklama |
|-------|--------|----------|
| `token_requester` | 24 saat | Son 24 saatlik işleri çeker |
| `job_processor` | token_requester sonrası | Raw job'ları analiz eder |
| `signup` | 6 saat | Yeni token'lar oluşturur |
| `proxy_monitor` | 5 dakika | Proxy'leri test eder |
| `cleanup_old_proxies` | 1 saat | Eski proxy'leri temizler |

## 🔧 API Endpoints

### CV Üretimi

#### POST `/generate-cv`
ATS uyumlu CV oluşturur.

**Request:**
```json
{
  "raw_cv": "CV metni",
  "job_id": 123,
  "target_lang": "TR"
}
```

**Response:**
```json
{
  "latex_cv": "\\documentclass{article}..."
}
```

#### POST `/generate-raw-cv`
LaTeX ham metnini döndürür.

#### POST `/start`
Scheduler'ı başlatır ve tüm görevleri tetikler.

**Request:**
```json
{
  "command": "system on start"
}
```

## 🔄 İş Akışı

1. **Token Requester** (24 saatte bir)
   - Son 24 saatteki iş ilanlarını API'den çeker
   - MongoDB'ye `raw_jobs` koleksiyonuna kaydeder

2. **Job Processor** (token_requester sonrası)
   - İşlenmemiş job'ları alır
   - NLP API ile analiz eder (başarısız olursa Playwright kullanır)
   - Sonuçları `job_analysis_results` koleksiyonuna kaydeder

3. **CV Generator** (manuel veya API ile)
   - İlan analizi ve ham CV'yi alır
   - ATS uyumlu LaTeX CV üretir

## 🛡️ Proxy Yönetimi

Sistem otomatik olarak:
- Proxy'leri toplar ve test eder
- HTTPS ve LinkedIn uyumluluğunu kontrol eder
- Çalışan proxy'leri `successhttps` ve `successlinkedin` koleksiyonlarında saklar
- Eski proxy'leri temizler

## 📊 Veritabanı Koleksiyonları

- `raw_jobs`: Ham iş ilanları
- `job_analysis_results`: Analiz edilmiş iş ilanları
- `jobscraper`: API token'ları
- `successhttps`: HTTPS çalışan proxy'ler
- `successlinkedin`: LinkedIn çalışan proxy'ler
- `apscheduler_jobs`: Zamanlanmış görevler

## 🐛 Hata Ayıklama

### Log Dosyaları
- `job_scraper.log`: Ana log dosyası
- `heb.txt`: Üretilen LaTeX CV'ler

### Yaygın Sorunlar

1. **MongoDB Bağlantı Hatası**
   - MongoDB'nin çalıştığından emin olun
   - `MONGODB_URI` değişkenini kontrol edin

2. **API Token Hatası**
   - Token'ların geçerli olduğunu kontrol edin
   - `signup.py` ile yeni token oluşturun

3. **Proxy Hatası**
   - Proxy testlerini manuel çalıştırın
   - Proxy kaynaklarını kontrol edin

## 🤝 Katkıda Bulunma

1. Fork yapın
2. Feature branch oluşturun (`git checkout -b feature/amazing-feature`)
3. Commit yapın (`git commit -m 'Add amazing feature'`)
4. Push yapın (`git push origin feature/amazing-feature`)
5. Pull Request oluşturun

## 📄 Lisans

Bu proje MIT lisansı altında lisanslanmıştır. Detaylar için `LICENSE` dosyasına bakın.

## 📞 İletişim

Sorularınız için issue açabilir veya pull request gönderebilirsiniz.

