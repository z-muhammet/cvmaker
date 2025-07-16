# Proxy Modülü Kullanım Kılavuzu

Bu modül, ücretsiz proxyleri **asenkron** olarak toplar, ip:port formatı ve başında http(s):// olan proxyleri normalize eder, port ve HTTPS filtresi uygular, LinkedIn ile son testten geçirir ve çalışan proxyleri dosyada saklar. Proxy havuzu otomatik olarak güncellenebilir ve başarısız proxyler otomatik olarak havuzdan silinir.

## Temel Özellikler
- Proxyleri farklı kaynaklardan **asenkron** toplar
- Kaynaklar kolayca değiştirilebilir (fetcher.py'deki PROXY_SOURCES)
- ip:port formatı ve başında http(s):// olan proxyler normalize edilip kullanılır
- Port ve HTTPS filtresi uygular
- LinkedIn ile asenkron son test yapar
- Çalışan proxyleri dosyada saklar (`final_linkedin_proxies.txt` veya istediğin dosya)
- Loglama: Tüm işlemler `proxy_pool.log` dosyasına ve ekrana yazılır
- Thread-safe dosya yönetimi (sync havuz fonksiyonları için)
- API fonksiyonları ile kolay kullanım

---

## Kurulum

Gerekli bağımlılıklar için ana dizindeki `requirements.txt` dosyasını kullanın:

```bash
pip install -r requirements.txt
```

---

## Proxy Kaynakları

Proxy kaynakları `fetcher.py` dosyasındaki `PROXY_SOURCES` listesinde tutulur. Dilediğiniz gibi güncelleyebilirsiniz. Örnek:

```python
PROXY_SOURCES = [
    "https://cdn.jsdelivr.net/gh/proxifly/free-proxy-list@main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/r00tee/Proxy-List/main/Https.txt",
    "https://raw.githubusercontent.com/databay-labs/free-proxy-list/main/http.txt",
    "https://cdn.jsdelivr.net/gh/databay-labs/free-proxy-list/https.txt"
]
```

---

## Format Filtresi ve Normalizasyon

Toplanan proxyler, ip:port formatına uygunluğu kontrol edilerek ve başında `http://` veya `https://` varsa otomatik olarak temizlenip normalize edilir. Böylece tüm kullanılabilir proxyler testlere dahil edilir.

---

## Tam Otomatik Asenkron Proxy Toplama ve Kaydetme

```python
import asyncio
from proxies.fetcher import async_fetch_and_save_final_proxies

# Tüm kaynaklardan proxyleri topla, filtrele, LinkedIn ile test et ve dosyaya kaydet
asyncio.run(async_fetch_and_save_final_proxies(limit=300000, output_file="final_linkedin_proxies.txt"))
```
- Sonuçlar `final_linkedin_proxies.txt` dosyasına kaydedilir.
- Bu dosyadaki proxyler scraperda doğrudan kullanılabilir.

---

## Adım Adım Asenkron Kullanım

```python
import asyncio
from proxies.fetcher import async_fetch_proxies
from proxies.tester import async_batch_linkedin_test

# 1. Proxyleri topla ve port/https filtresi uygula
proxies = asyncio.run(async_fetch_proxies(limit=300000))

# 2. LinkedIn ile son test
final_proxies = asyncio.run(async_batch_linkedin_test(proxies, timeout=5, print_every=500))

# 3. Sonuçları dosyaya kaydet
with open("final_linkedin_proxies.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(final_proxies))
```

---

## Sync API Kullanımı (Havuz Yönetimi)

```python
from proxies.pool import get_random_proxy, remove_proxy
from proxies.manager import refresh_pool, start_auto_refresh, retest_proxy_pool

proxy = get_random_proxy()  # Havuzdan rastgele bir proxy al
remove_proxy(proxy)         # Proxy başarısızsa havuzdan sil
refresh_pool()              # Havuzu manuel güncelle
start_auto_refresh(600)     # Havuzu arka planda otomatik güncelle (örn. 10 dakikada bir)
retest_proxy_pool()         # Havuzdaki proxyleri yeniden test et, başarısızları sil
```

---

## Loglama
Tüm önemli işlemler hem ekrana hem de `proxy_pool.log` dosyasına yazılır.

---

---
## "python -m proxies.manager --monitor --linkedin-interval 1"
---

## Dosya Yapısı
- `fetcher.py`: Proxyleri asenkron toplar, format ve port filtresi uygular, LinkedIn ile test eder ve dosyaya kaydeder
- `tester.py`: Port/HTTPS/LinkedIn test fonksiyonları (hem sync hem async)
- `pool.py`: Proxy havuzunu yönetir (okuma, yazma, silme, rastgele çekme)
- `manager.py`: Sync havuzun güncellenmesi, yeniden test edilmesi ve API fonksiyonları 