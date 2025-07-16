import time
import logging
from typing import Dict, Optional
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import asyncio
from flask import Flask, Response

logger = logging.getLogger(__name__)

class performanceMonitor:
  def __init__(self):
    self.requests_counter = Counter(
      'mistral_requests_total',
      'Toplam Mistral istekleri',
      ['status', 'method']
    )
    self.response_time_histogram = Histogram(
      'mistral_response_time_seconds',
      'Mistral istekleri için yanıt süresi',
      buckets = [0.1, 0.5, 1, 2, 5, 10, 30, 60]
    )
    self.proxy_performance_gauge = Gauge(
      'proxy_performance_score',
      'Proxylerin performans skoru',
      ['proxy']
    )
    self.proxy_requests_counter = Counter(
      'proxy_requests_total',
      'Proxy başına toplam istek',
      ['proxy', 'status']
    )
    self.browser_session_counter = Counter(
      'browser_sessions_total',
      'Toplam tarayıcı oturumu',
      ['status']
    )
    self.login_duration_histogram = Histogram(
      'login_duration_seconds',
      'Mistral giriş süresi',
      buckets = [5, 10, 20, 30, 60, 120]
    )
    self.error_counter = Counter(
      'mistral_errors_total',
      'Toplam hata',
      ['error_type']
    )
    self.websocket_connections = Gauge(
      'websocket_connections_active',
      'Aktif WebSocket bağlantıları'
    )
    self.browser_instances = Gauge(
      'browser_instances_active',
      'Aktif tarayıcı instance sayısı'
    )

  def TrackRequest(self, success: bool, method: str = "websocket"):
    status = "success" if success else "failed"
    self.requests_counter.labels(status = status, method = method).inc()

  def TrackResponseTime(self, duration: float):
    self.response_time_histogram.observe(duration)

  def UpdateProxyScore(self, proxy: str, score: float):
    self.proxy_performance_gauge.labels(proxy = proxy).set(score)

  def TrackProxyRequest(self, proxy: str, success: bool):
    status = "success" if success else "failed"
    self.proxy_requests_counter.labels(proxy = proxy, status = status).inc()

  def TrackBrowserSession(self, success: bool):
    status = "success" if success else "failed"
    self.browser_session_counter.labels(status = status).inc()

  def TrackLoginDuration(self, duration: float):
    self.login_duration_histogram.observe(duration)

  def TrackError(self, error_type: str):
    self.error_counter.labels(error_type = error_type).inc()

  def SetWebsocketConnections(self, count: int):
    self.websocket_connections.set(count)

  def SetBrowserInstances(self, count: int):
    self.browser_instances.set(count)

  def GetMetrics(self) -> str:
    return generate_latest().decode('utf-8')

class requestTimer:
  def __init__(self, monitor: performanceMonitor, method: str = "websocket", min_duration: float = 0.01):
    self.monitor = monitor
    self.method = method
    self.start_time = None
    self.min_duration = min_duration
  async def __aenter__(self):
    self.start_time = time.time()
    return self
  async def __aexit__(self, exc_type, exc_val, exc_tb):
    duration = time.time() - self.start_time
    success = exc_type is None
    self.monitor.TrackRequest(success, self.method)
    self.monitor.TrackResponseTime(duration)
    if duration < self.min_duration:
      logger.warning(f"İstek süresi çok kısa: {duration*1000:.2f} ms (yöntem: {self.method})")
    if not success:
      error_type = exc_type.__name__ if exc_type else "bilinmiyor"
      self.monitor.TrackError(error_type)

class proxyRotator:
  def __init__(self, monitor: performanceMonitor, cooldown_seconds: int = 120):
    self.monitor = monitor
    self.proxy_scores: Dict[str, float] = {}
    self.proxy_failures: Dict[str, int] = {}
    self.proxy_cooldowns: Dict[str, float] = {}
    self.max_failures = 3
    self.cooldown_seconds = cooldown_seconds
  def UpdateProxyScore(self, proxy: str, success: bool, response_time: float):
    if proxy not in self.proxy_scores:
      self.proxy_scores[proxy] = 1.0
    if success:
      self.proxy_scores[proxy] = min(1.0, self.proxy_scores[proxy] + 0.1)
      self.proxy_failures[proxy] = 0
      self.proxy_cooldowns.pop(proxy, None)
    else:
      self.proxy_scores[proxy] = max(0.0, self.proxy_scores[proxy] - 0.2)
      self.proxy_failures[proxy] = self.proxy_failures.get(proxy, 0) + 1
      self.proxy_cooldowns[proxy] = time.time()
    if response_time < 1.0:
      self.proxy_scores[proxy] += 0.05
    elif response_time > 5.0:
      self.proxy_scores[proxy] -= 0.05
    self.proxy_scores[proxy] = max(0.0, min(1.0, self.proxy_scores[proxy]))
    self.monitor.UpdateProxyScore(proxy, self.proxy_scores[proxy])
  def GetBestProxy(self, proxy_list: list) -> Optional[str]:
    if not proxy_list:
      return None
    now = time.time()
    available_proxies = [
      proxy for proxy in proxy_list
      if self.proxy_failures.get(proxy, 0) < self.max_failures and
         (proxy not in self.proxy_cooldowns or now - self.proxy_cooldowns[proxy] > self.cooldown_seconds)
    ]
    if not available_proxies:
      self.proxy_failures.clear()
      self.proxy_cooldowns.clear()
      available_proxies = proxy_list
    scored_proxies = [
      (proxy, self.proxy_scores.get(proxy, 0.5))
      for proxy in available_proxies
    ]
    scored_proxies.sort(key = lambda x: x[1], reverse = True)
    top_proxies = scored_proxies[:3]
    if top_proxies:
      return top_proxies[0][0]
    return None
  def MarkProxyFailed(self, proxy: str):
    self.proxy_failures[proxy] = self.proxy_failures.get(proxy, 0) + 1
    self.proxy_cooldowns[proxy] = time.time()
    logger.warning(f"Proxy {proxy} başarısız olarak işaretlendi (cooldown başlatıldı)")

performance_monitor = performanceMonitor()

async def ExampleUsage():
  async with requestTimer(performance_monitor) as timer:
    await asyncio.sleep(2)
    performance_monitor.TrackRequest(True)
  proxy_rotator = proxyRotator(performance_monitor)
  proxy_list = ["proxy1:8080", "proxy2:8080", "proxy3:8080"]
  best_proxy = proxy_rotator.GetBestProxy(proxy_list)
  print(f"En iyi proxy: {best_proxy}")
  proxy_rotator.UpdateProxyScore("proxy1:8080", True, 1.5)
  proxy_rotator.UpdateProxyScore("proxy2:8080", False, 5.0)
  metrics = performance_monitor.GetMetrics()
  print("Prometheus Metrikleri:")
  print(metrics)

if __name__ == "__main__":
  import argparse
  parser = argparse.ArgumentParser(description = "Prometheus metrik sunucusu")
  parser.add_argument('--port', type = int, default = 8000, help = 'Dinlenecek port')
  args = parser.parse_args()
  app = Flask(__name__)
  @app.route('/metrics')
  def metrics():
    return Response(performance_monitor.GetMetrics(), mimetype = 'text/plain')
  app.run(host = '0.0.0.0', port = args.port) 