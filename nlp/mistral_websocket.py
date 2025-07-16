import asyncio
import json
import websockets
import uuid
import time
import random
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
import os
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Browser, Page
from fake_useragent import UserAgent
import aiohttp
import textwrap
import datetime

try:
  from playwright_stealth import stealth
except ImportError:
  stealth = None
  logging.warning("playwright_stealth mevcut değil, basic stealth kullanılacak")

logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MistralMessage:
  role: str
  content: str
  id: Optional[str] = None
  def to_dict(self) -> Dict:
    return {
      "role": self.role,
      "content": self.content,
      "id": self.id or str(uuid.uuid4())
    }

class humanBehaviorSimulator:
  @staticmethod
  async def HumanType(page: Page, element, text: str):
    selectors = [
      'textarea[placeholder*="Ask Le Chat"]',
      'textarea[name="message.text"]',
      'textarea[placeholder*="anything"]',
      'textarea[placeholder*="message"]',
      'textarea[placeholder*="chat"]',
      'textarea[data-testid*="input"]',
      'textarea[class*="input"]',
      'textarea'
    ]
    for att in range(3):
      try:
        await element.click()
        await element.fill("")
        for char in text:
          if( char == "\n" ):
            continue
          await element.type(char, delay = random.uniform(5, 30))
          if random.random() < 0.1:
            await element.press("Backspace")
            await asyncio.sleep(random.uniform(0.01, 0.05))
            await element.type(char, delay = random.uniform(5, 30))
        return
      except Exception as exc:
        logging.warning(f"Textarea yazma hatası: {exc}, tekrar deneniyor ({att+1}/3)...")
        element = None
        for selector in selectors:
          try:
            element = await page.query_selector(selector)
            if element:
              is_attached = await element.is_visible()
              if is_attached:
                break
              else:
                element = None
          except Exception:
            continue
        if not element:
          raise Exception("Textarea tekrar bulunamadı!")
    raise Exception("Textarea'ya yazılamadı, 3 deneme başarısız!")

  @staticmethod
  async def HumanLikeMouseMove(page: Page, start: tuple, end: tuple):
    control_points = [
      (start[0] + random.randint(-50, 50), start[1] + random.randint(-50, 50)),
      (end[0] + random.randint(-50, 50), end[1] + random.randint(-50, 50))
    ]
    steps = random.randint(20, 40)
    for i in range(steps):
      t = i / steps
      x = (
        (1-t)**3*start[0] + 3*(1-t)**2*t*control_points[0][0] +
        3*(1-t)*t**2*control_points[1][0] + t**3*end[0]
      )
      y = (
        (1-t)**3*start[1] + 3*(1-t)**2*t*control_points[0][1] +
        3*(1-t)*t**2*control_points[1][1] + t**3*end[1]
      )
      await page.mouse.move(x, y)
      await asyncio.sleep(0.01 + 0.05 * (1 - abs(0.5 - t)))

  @staticmethod
  async def RandomMouseMovement(page: Page, start: tuple = None, end: tuple = None, steps: int = None):
    viewport = page.viewport_size
    if not viewport:
      return
    width, height = viewport['width'], viewport['height']
    if start is None:
      start = (random.randint(0, width), random.randint(0, height))
    if end is None:
      end = (random.randint(0, width), random.randint(0, height))
    if steps is None:
      steps = random.randint(20, 60)
    ctrl1 = (random.randint(0, width), random.randint(0, height))
    ctrl2 = (random.randint(0, width), random.randint(0, height))
    def bezier(t, p0, p1, p2, p3):
      return (
        (1-t)**3 * p0[0] + 3*(1-t)**2*t*p1[0] + 3*(1-t)*t**2*p2[0] + t**3*p3[0],
        (1-t)**3 * p0[1] + 3*(1-t)**2*t*p1[1] + 3*(1-t)*t**2*p2[1] + t**3*p3[1]
      )
    await page.mouse.move(start[0], start[1])
    await asyncio.sleep(random.uniform(0.05, 0.2))
    for i in range(steps + 1):
      t = i / steps
      x, y = bezier(t, start, ctrl1, ctrl2, end)
      x += random.uniform(-2, 2)
      y += random.uniform(-2, 2)
      await page.mouse.move(x, y)
      base_delay = 0.01 + 0.04 * (1 - abs(0.5 - t) * 2)
      await asyncio.sleep(base_delay + random.uniform(0, 0.02))
      if random.random() < 0.07:
        await asyncio.sleep(random.uniform(0.05, 0.2))
    await asyncio.sleep(random.uniform(0.1, 0.3))

  @staticmethod
  async def RandomScroll(page: Page):
    scroll_amount = random.randint(200, 800)
    if random.random() < 0.5:
      scroll_amount *= -1
    await page.evaluate(f"window.scrollBy(0, {scroll_amount})")
    await asyncio.sleep(random.uniform(0.5, 2))

class errorHandler:
  @staticmethod
  async def BypassCloudflare(page: Page):
    try:
      await page.wait_for_selector('#challenge-form', timeout = 10000)
      await page.evaluate('''() => {
        const form = document.querySelector('#challenge-form');
        const input = form.querySelector('input[type="text"]');
        if (input) {
          input.value = '1';
          form.submit();
        }
      }''')
      await page.wait_for_navigation(timeout = 30000)
      logger.info("Cloudflare doğrulaması başarıyla çözüldü")
      return True
    except Exception as exc:
      logger.error(f"Cloudflare atlatma hatası: {exc}")
      return False

  @staticmethod
  async def HandleCloudflareBlock(page: Page):
    try:
      current_url = page.url.lower()
      if "challenge" in current_url or "cloudflare" in current_url:
        logger.warning("Cloudflare doğrulaması algılandı")
        if await errorHandler.BypassCloudflare(page):
          return True
        await page.evaluate("""
          window.__cf_chl_opt={cType: 'non-interactive'};
        """)
        await asyncio.sleep(5)
        await page.reload()
        await asyncio.sleep(10)
        return True
    except Exception as exc:
      logger.error(f"Cloudflare handle hatası: {exc}")
    return False

  @staticmethod
  async def HandleRateLimit(page: Page):
    try:
      error_elements = await page.query_selector_all("text=rate limit")
      if error_elements:
        logger.warning("Rate limit algılandı")
        return True
    except Exception as exc:
      logger.error(f"Rate limit handle hatası: {exc}")
    return False

class sessionManager:
  def __init__(self):
    self.sessions = {}
    self.lock = asyncio.Lock()
    self._last_request_time = 0
    self.min_interval = 1.2

  async def RotateSession(self):
    async with self.lock:
      now = time.time()
      self.sessions = {k: v for k, v in self.sessions.items() if v['expiry'] > now}
      session_id = str(uuid.uuid4())
      self.sessions[session_id] = {
        'expiry': now + 3600,
        'cookies': await self._GetFreshCookies(),
        'tokens': await self._GetFreshTokens()
      }
      return session_id

  async def _GetFreshCookies(self):
    return {}

  async def _GetFreshTokens(self):
    return None

  async def SendMessageWithRateLimit(self, message: str):
    elapsed = time.time() - self._last_request_time
    if elapsed < self.min_interval:
      delay = self.min_interval - elapsed + random.uniform(0, 0.5)
      await asyncio.sleep(delay)
    try:
      response = await self.SendMessage(message)
      self._last_request_time = time.time()
      return response
    except Exception as exc:
      if "rate limit" in str(exc).lower():
        logger.warning("Rate limit algılandı, oturum değiştiriliyor...")
        await self.RotateSession()
        return await self.SendMessageWithRateLimit(message)
      raise exc

class RateLimitError(Exception):
  pass

class mistralWebSocketClient:
  def __init__(self, access_token: Optional[str] = None, use_browser: bool = True, use_proxy: bool = False):
    self.access_token: Optional[str] = access_token
    self.use_browser: bool = use_browser
    self.use_proxy: bool = use_proxy
    self.websocket: Optional[websockets.WebSocketServerProtocol] = None
    self.browser: Optional[Browser] = None
    self.page: Optional[Page] = None
    self.conversation_id: Optional[str] = None
    self.message_id: Optional[str] = None
    self.is_connected: bool = False
    self.message_handlers: List[Callable] = []
    self.proxy_list: List[str] = []
    self.current_proxy: Optional[str] = None
    self.user_agent: str = UserAgent().chrome
    self.mistral_url: str = "https://chat.mistral.ai/chat"
    self.session_cookies: Dict[str, str] = {}
    self.auth_token: Optional[str] = None

  async def LoadProxies(self) -> List[str]:
    try:
      from dbprocess.db_manager import dbManager
      uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
      db_name = os.getenv("MONGODB_DB", "jobscrapper")
      db_manager = dbManager(uri, db_name)
      proxies = await db_manager.FindMany("successlinkedin", {}, limit = 50)
      return [proxy['proxy'] for proxy in proxies]
    except Exception as exc:
      logger.warning(f"Proxy yükleme hatası: {exc}")
      return []

  async def TestProxy(self, proxy: str) -> bool:
    url = "https://chat.mistral.ai/"
    for _ in range(2):
      try:
        async with aiohttp.ClientSession() as session:
          async with session.get(url, proxy = f"http://{proxy}", timeout = 10) as resp:
            if resp.status != 200:
              return False
      except Exception as exc:
        logger.warning(f"Proxy {proxy} testi başarısız: {exc}")
        return False
    return True

  def GetRandomProxy(self) -> Optional[str]:
    if not self.proxy_list:
      return None
    return random.choice(self.proxy_list)

  async def ConfigureBrowser(self) -> Browser:
    playwright = await async_playwright().start()
    browser_args = [
      "--disable-blink-features=AutomationControlled",
      "--disable-web-security",
      "--disable-features=VizDisplayCompositor",
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-dev-shm-usage",
      "--disable-accelerated-2d-canvas",
      "--no-first-run",
      "--no-zygote",
      "--disable-gpu",
      "--disable-background-timer-throttling",
      "--disable-backgrounding-occluded-windows",
      "--disable-renderer-backgrounding",
      "--disable-field-trial-config",
      "--disable-back-forward-cache",
      "--disable-ipc-flooding-protection",
      "--disable-hang-monitor",
      "--disable-prompt-on-repost",
      "--disable-client-side-phishing-detection",
      "--disable-component-extensions-with-background-pages",
      "--disable-default-apps",
      "--disable-extensions",
      "--disable-sync",
      "--disable-translate",
      "--hide-scrollbars",
      "--mute-audio",
      "--no-default-browser-check",
      "--safebrowsing-disable-auto-update",
      "--disable-safebrowsing",
      "--disable-features=TranslateUI",
      "--disable-ipc-flooding-protection",
      "--disable-features=VizDisplayCompositor",
      "--disable-features=TranslateUI",
      "--disable-features=BlinkGenPropertyTrees",
      "--disable-features=CalculateNativeWinOcclusion",
      "--disable-features=GlobalMediaControls",
      "--disable-features=MediaRouter",
      "--disable-features=OptimizationHints",
      "--disable-features=PasswordGeneration",
      "--disable-features=PasswordLeakDetection",
      "--disable-features=PreloadMediaEngagementData",
      "--disable-features=ReadLater",
      "--disable-features=SafeBrowsing",
      "--disable-features=SafeBrowsingEnhanced",
      "--disable-features=SafeBrowsingEnhancedProtection",
      "--disable-features=SafeBrowsingRealTimeUrlLookup",
      "--disable-features=SafeBrowsingRealTimeUrlLookupEnabled",
      "--disable-features=SafeBrowsingRealTimeUrlLookupEnabledForTesting",
      "--disable-features=SafeBrowsingRealTimeUrlLookupForTesting",
      "--disable-features=SafeBrowsingRealTimeUrlLookupForTestingEnabled",
      "--disable-features=SafeBrowsingRealTimeUrlLookupForTestingEnabledForTesting",
      "--disable-features=SafeBrowsingRealTimeUrlLookupForTestingEnabledForTestingForTesting",
      f"--user-agent={self.user_agent}",
      "--start-maximized"
    ]
    if self.use_proxy and self.proxy_list:
      while self.proxy_list:
        self.current_proxy = self.GetRandomProxy()
        if self.current_proxy and await self.TestProxy(self.current_proxy):
          logger.info(f"Proxy kullanılıyor: {self.current_proxy}")
          browser_args.append(f"--proxy-server={self.current_proxy}")
          break
        else:
          logger.warning(f"Proxy başarısız: {self.current_proxy}, listeden çıkarıldı.")
          self.proxy_list.remove(self.current_proxy)
      else:
        logger.error("Geçerli proxy bulunamadı!")
        raise RuntimeError("Geçerli proxy bulunamadı!")
    browser = await playwright.chromium.launch(
      headless = False,
      args = browser_args
    )
    return browser

  async def ConnectToMistral(self):
    try:
      self.browser = await self.ConfigureBrowser()
      self.page = await self.browser.new_page()
      await self.page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        if (window.chrome && window.chrome.runtime) {
          Object.defineProperty(window.chrome, 'runtime', { get: () => undefined });
        }
      """)
      await self.page.set_extra_http_headers({
        "User-Agent": self.user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none"
      })
      logger.info("Mistral AI'ya bağlanılıyor...")
      await asyncio.sleep(random.uniform(2, 4))
      try:
        await self.page.goto(self.mistral_url, wait_until = "domcontentloaded", timeout = 30000)
        logger.info("Mistral AI sayfası yüklendi")
      except Exception as exc:
        logger.error(f"Sayfa yükleme hatası: {exc}")
        raise
      await asyncio.sleep(random.uniform(3, 6))
      await humanBehaviorSimulator.RandomMouseMovement(self.page)
      await asyncio.sleep(random.uniform(1, 2))
      accept_button = None
      accept_selectors = [
        'button:has-text("Accept and continue")',
        'button:has-text("Accept")',
        'button:has-text("Continue")',
        'button[class*="bg-inverted"]',
        'button[class*="primary"]',
        'button[type="button"]',
        '[role="button"]:has-text("Accept")',
        '[role="button"]:has-text("Continue")'
      ]
      for selector in accept_selectors:
        try:
          accept_button = await self.page.wait_for_selector(selector, timeout = 8000)
          if accept_button:
            logger.info(f"Accept butonu bulundu: {selector}")
            break
        except Exception:
          continue
      if accept_button:
        await humanBehaviorSimulator.RandomMouseMovement(self.page)
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await accept_button.click()
        logger.info("Accept and continue butonuna tıklandı")
        await asyncio.sleep(random.uniform(2, 4))
      else:
        logger.warning("Accept butonu bulunamadı, devam ediliyor...")
      textarea = None
      textarea_selectors = [
        'textarea[placeholder*="Ask Le Chat"]',
        'textarea[name="message.text"]',
        'textarea[placeholder*="anything"]',
        'textarea[placeholder*="message"]',
        'textarea[placeholder*="chat"]',
        'textarea[data-testid*="input"]',
        'textarea[class*="input"]',
        'textarea'
      ]
      for selector in textarea_selectors:
        try:
          textarea = await self.page.wait_for_selector(selector, timeout = 15000)
          if textarea:
            logger.info(f"Textarea bulundu: {selector}")
            break
        except Exception:
          continue
      if not textarea:
        page_content = await self.page.content()
        logger.error(f"Textarea bulunamadı. Sayfa içeriği: {page_content[:1000]}...")
        raise Exception("Textarea bulunamadı")
      await textarea.click()
      await asyncio.sleep(random.uniform(0.5, 1))
      self.is_connected = True
      logger.info("Mistral AI'ya başarıyla bağlanıldı")
    except Exception as exc:
      logger.error(f"Mistral AI bağlantı hatası: {exc}")
      raise

  async def _ClickContinueDiscussion(self):
    try:
      btn = await self.page.query_selector(
        'div.m-auto.cursor-pointer.text-center.text-sm.text-subtle.underline'
      )
      if btn:
        await btn.click()
        logger.info("Continue the discussion butonuna tıklandı!")
        await asyncio.sleep(0.5)
    except Exception as exc:
      logger.debug(f"Continue the discussion butonuna tıklanamadı: {exc}")

  async def SendMessageToMistral(self, message: str) -> str:
    try:
      if not self.is_connected:
        await self.ConnectToMistral()
      try:
        await self.page.wait_for_load_state("networkidle", timeout = 5000)
      except Exception:
        logger.warning("Sayfa yüklenme durumu kontrol edilemedi, devam ediliyor...")
      textarea_selectors = [
        'textarea[placeholder*="Ask Le Chat"]',
        'textarea[name="message.text"]',
        'textarea[placeholder*="anything"]',
        'textarea[placeholder*="message"]',
        'textarea[placeholder*="chat"]',
        'textarea[data-testid*="input"]',
        'textarea[class*="input"]',
        'textarea'
      ]
      textarea = None
      for selector in textarea_selectors:
        try:
          textarea = await self.page.wait_for_selector(selector, timeout = 10000)
          if textarea:
            is_attached = await textarea.is_visible()
            if is_attached:
              logger.info(f"Textarea bulundu: {selector}")
              break
            else:
              textarea = None
        except Exception as exc:
          logger.debug(f"Textarea selector {selector} hatası: {exc}")
          continue
      if not textarea:
        logger.warning("Textarea bulunamadı, sayfa yeniden yükleniyor...")
        await self.page.reload()
        await asyncio.sleep(3)
        for selector in textarea_selectors:
          try:
            textarea = await self.page.wait_for_selector(selector, timeout = 10000)
            if textarea:
              is_attached = await textarea.is_visible()
              if is_attached:
                logger.info(f"Textarea tekrar bulundu: {selector}")
                break
          except Exception:
            continue
        if not textarea:
          raise Exception("Textarea bulunamadı")
      await textarea.click()
      await textarea.fill("")
      await textarea.press(" ")
      await asyncio.sleep(random.uniform(0.1, 0.2))
      await textarea.evaluate(
        "(el, value) => { el.value = value; el.dispatchEvent(new Event('input', { bubbles: true })); el.dispatchEvent(new Event('change', { bubbles: true })); }",
        message
      )
      await asyncio.sleep(random.uniform(0.3, 0.8))
      current_value = await textarea.input_value()
      if not current_value.strip():
        logger.warning("Textarea boş, tekrar yazılıyor...")
        await textarea.fill(message)
        await asyncio.sleep(random.uniform(0.5, 1))
      submit_button = None
      submit_selectors = [
        'button[aria-label="Send question"]',
        'button:has(svg.-rotate-90)',
        'button[type="submit"]',
        'button[aria-label*="Send"]',
        'button[aria-label*="send"]',
        'button[class*="submit"]'
      ]
      for selector in submit_selectors:
        try:
          submit_button = await self.page.wait_for_selector(selector, timeout = 5000)
          if submit_button:
            is_enabled = await submit_button.is_enabled()
            if is_enabled:
              logger.info(f"Gönder butonu bulundu: {selector}")
              break
            else:
              logger.warning(f"Gönder butonu bulundu ama aktif değil: {selector}")
              submit_button = None
        except Exception as exc:
          logger.debug(f"Gönder buton selector {selector} hatası: {exc}")
          continue
      if submit_button:
        await submit_button.click()
        logger.info(f"Mesaj gönderildi (buton): {message[:50]}...")
      else:
        logger.warning("Gönder butonu bulunamadı, Enter tuşu kullanılıyor...")
        await textarea.press("Enter")
        logger.info(f"Mesaj gönderildi (Enter): {message[:50]}...")
      logger.info("Yanıt bekleniyor (20 saniye, Continue the discussion kontrolü)...")
      for _ in range(40):
        await self._ClickContinueDiscussion()
        await asyncio.sleep(0.5)
      response = await self._WaitForMistralResponse()
      return response
    except Exception as exc:
      logger.error(f"Mistral AI mesaj gönderme hatası: {exc}")
      return f"Hata: {str(exc)}"

  async def _WaitForMistralResponse(self, timeout: int = 60) -> str:
    start = time.time()
    while time.time() - start < timeout:
      try:
        await self._ClickContinueDiscussion()
        await self.page.wait_for_selector('div[data-message-part-type="answer"]', timeout = 5000)
        answer_divs = await self.page.query_selector_all('div[data-message-part-type="answer"]')
        all_text = ""
        for div in answer_divs:
          p_tags = await div.query_selector_all('p[dir="auto"]')
          for p in p_tags:
            t = await p.text_content()
            if t:
              all_text += t
        if all_text:
          logger.info(f"Yanıt bulundu (tüm p[dir='auto']): {all_text[:3000]}...")
          return all_text.strip()
      except Exception as exc:
        logger.debug(f"Yanıt div parse hatası: {exc}")
      await asyncio.sleep(0.5)
    return "Yanıt alınamadı"

  async def AnalyzeJobDescription(self, job_description: str) -> str:
    prompt = textwrap.dedent(f"""
    You are a senior HR-data extractor.

    —TASK—
    Extract structured data from ANY job posting text and output only a single-line, minified, valid JSON object that matches this exact schema (no extra keys, no comments) RESPONSE TYPE:JSON !:
    {{"company_name":null,"job_title":"","department":null,"employment_type":null,"location":null,"summary":null,"responsibilities":[],"requirements":{{"education":[],"experience_years_min":null,"experience_years_pref":null,"skills_mandatory":[],"skills_optional":[],"certifications":[],"languages":[],"other_requirements":[]}},"benefits":[],"application":{{"apply_url":null,"contact_email":null,"deadline":null}}}}

    —RULES—
    1. Preserve the key order of the schema.
    2. Use null where information is missing, never empty strings except for job_title.
    3. Use empty arrays [] for list-type fields with no data.
    4. Output must be a single line (no linebreaks, no indentation).
    5. Do NOT wrap the JSON in markdown fences or add any extra text.
    6. Normalize dates to ISO 8601 ("YYYY-MM-DD") if deadline is present; otherwise keep as null.
    7. Translate field values to English except the original summary and location.
    8. Trim whitespace inside strings; do not add trailing commas.
    9. If the input contains multiple languages, prioritise English terms; keep Turkish only when no English equivalent exists.
    10. Items appearing under headings such as "Preferred", "Tercih edilen", or preceded by words like "Tercihen" MUST be captured in skills_optional.
    11. Split comma- or slash-separated skill lists into individual elements.
    12. If a skill is both mandatory and preferred, list it in skills_mandatory and ALSO in skills_optional only if explicitly in preferred section.
    13. Use canonical English technology names (e.g., TypeScript, PrimeNG, Angular).

    Failure to comply with any rule is a critical error.
    Job description: {job_description}
    """)
    return await self.SendMessageToMistral(prompt)

  async def GenerateCvSuggestions(self, job_analysis: str, current_cv: str) -> str:
    prompt = f"""
    Job Analysis:
    {job_analysis}

    Current CV:
    {current_cv}

    Generate CV suggestions for this job posting. Update the following sections:
    1. Summary/Objective section
    2. Experience section (according to job posting)
    3. Skills section
    4. Education section

    Return suggestions in JSON format for each section:
    {{
        "summary_suggestion": "New summary text",
        "experience_suggestions": ["suggestion1", "suggestion2", ...],
        "skill_suggestions": ["skill1", "skill2", ...],
        "education_suggestions": ["suggestion1", "suggestion2", ...],
        "general_suggestions": ["suggestion1", "suggestion2", ...]
    }}
    """
    return await self.SendMessageToMistral(prompt)

  async def Connect(self, max_retries: int = 5, retry_delay: float = 3.0) -> bool:
    try:
      await self.ConnectToMistral()
      return True
    except Exception as exc:
      logger.error(f"Mistral AI bağlantı hatası: {exc}")
      return False

  async def Disconnect(self):
    if self.browser:
      await self.browser.close()
      logger.info("Tarayıcı kapatıldı")

  async def SendMessage(self, message: str) -> str:
    return await self.SendMessageToMistral(message)

async def Main():
  load_dotenv()
  access_token = os.getenv("CHATGPT_ACCESS_TOKEN")
  client = mistralWebSocketClient(use_browser = True)
  if await client.Connect():
    job_desc = """
    Senior Python Developer is needed.
    Requirements:
    - 5+ years of Python experience
    - Django, Flask framework knowledge
    - MongoDB, PostgreSQL experience
    - Docker, Kubernetes knowledge
    - Git, CI/CD experience
    """
    analysis_raw = await client.AnalyzeJobDescription(job_desc)
    try:
      analysis = json.loads(analysis_raw)
      print("İş Tanımı Analizi (JSON):", analysis)
    except Exception as exc:
      print("İş Tanımı Analizi (ham yanıt):", analysis_raw)
      print(f"JSON ayrıştırma hatası: {exc}")
      try:
        filename = f"answer_raw_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out_path = os.path.abspath(filename)
        with open(out_path, "w", encoding = "utf-8") as f:
          f.write(analysis_raw)
        print(f"Ham yanıt dosyaya kaydedildi: {out_path}")
      except Exception as exc2:
        print(f"Ham yanıt kaydedilemedi! Hata: {exc2}")
    await client.Disconnect()

if __name__ == "__main__":
  asyncio.run(Main()) 