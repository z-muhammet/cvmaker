import asyncio
import json
import logging
import os
import queue
import re
import threading
import time
import warnings
from pathlib import Path
from typing import Dict, Optional

from dotenv import load_dotenv

from .mistral_websocket import mistralWebSocketClient
from .performance_monitor import performance_monitor, requestTimer, proxyRotator
from .session_manager import mistralSessionManager
from dbprocess.db_manager import db

warnings.filterwarnings("ignore", category=ResourceWarning)

MAX_JOB_DESC_LEN = 40000
MAX_CV_LEN = 40000

logging.basicConfig(level = logging.INFO)
logger = logging.getLogger(__name__)

def ExtractJsonFromText(txt: str) -> str:
  txt = txt.strip()
  txt = re.sub(r'^(Copy|json|JSON|```json|```)', '', txt, flags = re.IGNORECASE).strip()
  txt = re.sub(r'(```)+$', '', txt).strip()
  mtchs = list(re.finditer(r'({.*?})', txt, re.DOTALL))
  if mtchs:
    js = [m.group(1) for m in mtchs]
    js.sort(key = len, reverse = True)
    return js[0]
  return txt

class jobAnalyzer:
  def __init__( self, accTkn: Optional[str] = None, useBr: bool = True ):
    self.useBr = useBr
    self.cli = None
    self.sessMgr = mistralSessionManager()
    self.prxRot = proxyRotator(performance_monitor)
    self.reqCnt = 0
    self.succCnt = 0
    self.errCnt = 0
    self.accTkn = accTkn or self._GetAccessToken()

  def _TimedInput( self, prmpt: str, timeout: int = 30 ) -> str:
    q = queue.Queue()
    def ask():
      try:
        q.put(input(prmpt))
      except Exception:
        q.put(None)
    t = threading.Thread(target = ask)
    t.daemon = True
    t.start()
    try:
      return q.get(timeout = timeout)
    except queue.Empty:
      raise TimeoutError(f"Kullanıcı girişi {timeout} saniye içinde alınamadı.")

  def _GetAccessToken( self ) -> Optional[str]:
    load_dotenv()
    tkn = os.getenv("MISTRAL_ACCESS_TOKEN")
    if tkn:
      return tkn
    tkn = self.sessMgr.get_access_token_from_file("mistral_token.txt")
    if tkn:
      return tkn
    self.useBr = True
    return None

  async def InitializeClient( self ) -> bool:
    try:
      stTm = time.time()
      performance_monitor.set_browser_instances(1)
      self.cli = mistralWebSocketClient(
        access_token = self.accTkn,
        use_browser = self.useBr
      )
      self.cli.proxy_list = await self.cli.load_proxies()
      if await self.cli.connect():
        loginDur = time.time() - stTm
        performance_monitor.track_login_duration(loginDur)
        performance_monitor.track_browser_session(True)
        performance_monitor.set_websocket_connections(1)
        logger.info("Mistral AI istemcisi başarıyla başlatıldı.")
        return True
      performance_monitor.track_browser_session(False)
      performance_monitor.track_error("connection_failed")
      logger.error("Mistral AI'ya bağlanılamadı.")
      return False
    except Exception as exc:
      performance_monitor.track_error("initialization_failed")
      logger.error(f"İstemci başlatma hatası: {exc}")
      return False

  async def AnalyzeJobDescription( self, jobDesc: str ) -> Dict:
    if len(jobDesc) > MAX_JOB_DESC_LEN:
      logger.error(
        f"İş ilanı açıklaması çok uzun! ({len(jobDesc)} karakter, sınır: {MAX_JOB_DESC_LEN})"
      )
      return {"error": f"İş ilanı açıklaması çok uzun! ({len(jobDesc)} karakter, sınır: {MAX_JOB_DESC_LEN})"}
    if not self.cli:
      if not await self.InitializeClient():
        return {"error": "İstemci başlatılamadı"}
    try:
      async with requestTimer(performance_monitor, "job_analysis"):
        resp = await self.cli.analyze_job_description(jobDesc)
        self._SaveRawResponse(resp)
        return self._ParseJsonResponse(resp, "analysis_failed")
    except Exception as exc:
      self.errCnt += 1
      performance_monitor.track_error("analysis_failed")
      logger.error(f"İş analizi hatası: {exc}")
      return {"error": str(exc)}
    finally:
      self.reqCnt += 1

  async def GenerateCvSuggestions( self, jobAn: Dict, currCv: str ) -> Dict:
    if len(currCv) > MAX_CV_LEN:
      logger.error(
        f"CV metni çok uzun! ({len(currCv)} karakter, sınır: {MAX_CV_LEN})"
      )
      return {"error": f"CV metni çok uzun! ({len(currCv)} karakter, sınır: {MAX_CV_LEN})"}
    if not self.cli:
      if not await self.InitializeClient():
        return {"error": "İstemci başlatılamadı"}
    try:
      async with requestTimer(performance_monitor, "cv_suggestions"):
        jobAnStr = json.dumps(jobAn, ensure_ascii = False, indent = 2)
        resp = await self.cli.generate_cv_suggestions(jobAnStr, currCv)
        resp = ExtractJsonFromText(resp)
        return self._ParseJsonResponse(resp, "suggestions_failed")
    except Exception as exc:
      self.errCnt += 1
      performance_monitor.track_error("suggestions_failed")
      logger.error(f"CV öneri hatası: {exc}")
      return {"error": str(exc)}
    finally:
      self.reqCnt += 1

  async def AnalyzeJobFromFile( self, jobFile: str ) -> Dict:
    try:
      with open(jobFile, 'r', encoding = 'utf-8') as f:
        jobDesc = f.read()
      return await self.AnalyzeJobDescription(jobDesc)
    except Exception as exc:
      performance_monitor.track_error("file_read_error")
      logger.error(f"Dosya okuma hatası: {exc}")
      return {"error": str(exc)}

  async def SaveAnalysisToFile( self, an: Dict, outFile: str ):
    try:
      with open(outFile, 'w', encoding = 'utf-8') as f:
        json.dump(an, f, ensure_ascii = False, indent = 2)
      logger.info(f"Analiz {outFile} dosyasına kaydedildi")
    except Exception as exc:
      performance_monitor.track_error("file_write_error")
      logger.error(f"Dosyaya yazma hatası: {exc}")

  def GetPerformanceStats( self ) -> Dict:
    return {
      "total_requests": self.reqCnt,
      "successful_requests": self.succCnt,
      "failed_requests": self.errCnt,
      "success_rate": (self.succCnt / self.reqCnt * 100) if self.reqCnt > 0 else 0,
      "prometheus_metrics": performance_monitor.get_metrics()
    }

  async def Close( self ):
    if self.cli:
      await self.cli.disconnect()
      performance_monitor.set_websocket_connections(0)
      performance_monitor.set_browser_instances(0)

  def _SaveRawResponse( self, resp: str ):
    try:
      with open("raw_response.json", "w", encoding = "utf-8") as f:
        f.write(resp)
      logger.info("Ham yanıt raw_response.json dosyasına kaydedildi.")
    except Exception as exc:
      logger.error(f"Ham yanıt kaydedilemedi: {exc}")

  def _ParseJsonResponse( self, resp: str, errType: str ) -> Dict:
    try:
      parsed = json.loads(resp)
      self.succCnt += 1
      return parsed
    except json.JSONDecodeError as exc:
      self.errCnt += 1
      performance_monitor.track_error("json_parse_error")
      logger.error(
        f"JSON ayrıştırma hatası. Ham yanıt (ilk 200 karakter): {resp[:200]}\nHata: {exc}"
      )
      return {
        "raw_response": resp,
        "error": f"JSON ayrıştırılamadı: {exc}"
      }

async def Main():
  import argparse
  parser = argparse.ArgumentParser(
    description = "Mistral AI ile gelişmiş iş ilanı analizi ve CV önerileri"
  )
  parser.add_argument("--job-file", help = "İş ilanı dosyası")
  parser.add_argument("--job-text", help = "İş ilanı metni")
  parser.add_argument("--cv-file", help = "Mevcut CV dosyası")
  parser.add_argument("--output", default = "job_analysis.json", help = "Çıktı dosyası")
  parser.add_argument("--suggestions", action = "store_true", help = "CV önerileri üret")
  parser.add_argument("--use-browser", action = "store_true", help = "Mistral AI girişi için tarayıcı kullan")
  parser.add_argument("--metrics", action = "store_true", help = "Performans metriklerini göster")
  parser.add_argument("--proxy", action = "store_true", help = "Proxy kullan")
  args = parser.parse_args()
  useBr = args.use_browser or True
  analyzer = jobAnalyzer(useBr = useBr)
  try:
    jobDesc = ""
    if args.job_file:
      with open(args.job_file, 'r', encoding = 'utf-8') as f:
        jobDesc = f.read()
    elif args.job_text:
      jobDesc = args.job_text
    else:
      print("İş ilanı açıklamasını girin (Ctrl+D ile bitirin):")
      jobDesc = input()
    print("İş ilanı Mistral AI ile analiz ediliyor...")
    an = await analyzer.AnalyzeJobDescription(jobDesc)
    if "error" not in an:
      print("İş analizi başarıyla tamamlandı!")
      print(json.dumps(an, ensure_ascii = False, indent = 2))
      await analyzer.SaveAnalysisToFile(an, args.output)
      try:
        await db.InsertOne("JobAnalysis", an)
        print("Analiz JobAnalysis koleksiyonuna kaydedildi.")
      except Exception as exc:
        print(f"Analiz veritabanına kaydedilemedi: {exc}")
      if args.suggestions:
        currCv = ""
        if args.cv_file:
          with open(args.cv_file, 'r', encoding = 'utf-8') as f:
            currCv = f.read()
        else:
          print("Mevcut CV'nizi girin:")
          currCv = input()
        print("CV önerileri üretiliyor...")
        sugg = await analyzer.GenerateCvSuggestions(an, currCv)
        if "error" not in sugg:
          print("CV önerileri başarıyla oluşturuldu!")
          print(json.dumps(sugg, ensure_ascii = False, indent = 2))
          suggFile = args.output.replace('.json', '_suggestions.json')
          await analyzer.SaveAnalysisToFile(sugg, suggFile)
        else:
          print(f"CV öneri hatası: {sugg['error']}")
    else:
      print(f"Analiz hatası: {an['error']}")
    if args.metrics:
      stats = analyzer.GetPerformanceStats()
      print("\nPerformans İstatistikleri:")
      print(f"Toplam İstek: {stats['total_requests']}")
      print(f"Başarılı: {stats['successful_requests']}")
      print(f"Başarısız: {stats['failed_requests']}")
      print(f"Başarı Oranı: {stats['success_rate']:.2f}%")
  finally:
    await analyzer.Close()

if __name__ == "__main__":
  asyncio.run(Main()) 