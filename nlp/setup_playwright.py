#!/usr/bin/env python3
import subprocess
import sys
import os
import logging

logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)

def RunCommand(command: str, description: str) -> bool:
  try:
    logger.info(f"🔄 {description}...")
    result = subprocess.run(
      command,
      shell = True,
      check = True,
      capture_output = True,
      text = True
    )
    logger.info(f"✅ {description} tamamlandı")
    return True
  except subprocess.CalledProcessError as e:
    logger.error(f"❌ {description} hatası: {e}")
    logger.error(f"Stderr: {e.stderr}")
    return False

def InstallPlaywright():
  logger.info("🚀 Playwright kurulumu başlatıldı...")

  if not RunCommand(
    f"{sys.executable} -m pip install playwright",
    "Playwright pip ile kuruluyor"
  ):
    return False

  if not RunCommand(
    f"{sys.executable} -m playwright install chromium",
    "Chromium tarayıcısı kuruluyor"
  ):
    return False

  browsers = ["firefox", "webkit"]
  for browser in browsers:
    if not RunCommand(
      f"{sys.executable} -m playwright install {browser}",
      f"{browser.capitalize()} tarayıcısı kuruluyor"
    ):
      logger.warning(f"{browser} kurulumu başarısız, devam ediliyor...")

  if not RunCommand(
    f"{sys.executable} -m playwright --version",
    "Playwright versiyonu kontrol ediliyor"
  ):
    return False

  logger.info("🎉 Playwright kurulumu tamamlandı!")
  return True

def InstallDependencies():
  logger.info("📦 Bağımlılıklar yükleniyor...")

  dependencies = [
    "fake-useragent",
    "prometheus-client",
    "websockets",
    "python-dotenv",
    "requests"
  ]

  for dep in dependencies:
    if not RunCommand(
      f"{sys.executable} -m pip install {dep}",
      f"{dep} yükleniyor"
    ):
      logger.warning(f"{dep} yüklenemedi, devam ediliyor...")

  logger.info("✅ Bağımlılıklar yüklendi!")

def TestPlaywright():
  logger.info("🧪 Playwright test ediliyor...")

  test_script = """
import asyncio
from playwright.async_api import async_playwright

async def test_playwright():
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.goto('https://example.com')
        title = await page.title()
        await browser.close()
        await playwright.stop()
        print(f"Playwright testi başarılı! Sayfa başlığı: {title}")
        return True
    except Exception as e:
        print(f"Playwright test hatası: {e}")
        return False

asyncio.run(test_playwright())
"""

  test_file = "test_playwright.py"
  try:
    with open(test_file, 'w', encoding = 'utf-8') as f:
      f.write(test_script)

    if RunCommand(
      f"{sys.executable} {test_file}",
      "Playwright test ediliyor"
    ):
      logger.info("✅ Playwright testi başarılı!")
      return True
    else:
      logger.error("❌ Playwright testi başarısız!")
      return False

  finally:
    if os.path.exists(test_file):
      os.remove(test_file)

def Main():
  logger.info("🔧 ChatGPT WebSocket Bot Kurulumu")
  logger.info("=" * 50)

  InstallDependencies()

  if not InstallPlaywright():
    logger.error("❌ Playwright kurulumu başarısız!")
    sys.exit(1)

  if not TestPlaywright():
    logger.error("❌ Playwright testi başarısız!")
    sys.exit(1)

  logger.info("🎉 Kurulum tamamlandı!")
  logger.info("")
  logger.info("📝 Kullanım:")
  logger.info("1. .env dosyanıza CHATGPT_USERNAME ve CHATGPT_PASSWORD ekleyin")
  logger.info("2. python -m nlp.job_analyzer --use-browser --job-text 'test'")
  logger.info("3. python -m nlp.performance_monitor (metrikleri görmek için)")

if __name__ == "__main__":
  Main() 