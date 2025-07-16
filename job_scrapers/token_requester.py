import asyncio
import logging
import math
import os
import secrets
import sys
import time
from datetime import datetime, timedelta, UTC
from typing import Dict, List, Optional

import aiohttp
from pymongo import ReturnDocument
from dbprocess.db_manager import db

ORDER_BY = [
  {"field": "date_posted",   "desc": False},
  {"field": "discovered_at", "desc": False},
  {"field": "job_title",     "desc": False},
]

TURKEY_JOB_FILTER = {
  "location": {
    "country": ["Turkey", "Türkiye", "TR"]
  }
}

class InsufficientCreditsError(Exception):
  pass

class InvalidTokenError(Exception):
  """API anahtarının geçersiz/expired olduğunu belirtir."""
  pass

class jobScraper:
  def __init__( self ):
    self.tokCol = os.getenv("TOKEN_COLLECTION", "jobscraper")
    self.rawCol = os.getenv("RAW_JOB_COLLECTION", "raw_jobs")
    self.apiBase = "https://api.theirstack.com/v1/jobs/search"
    self.SetupLogging()
    self.stTm = None
    self.totJ = 0
    self.totP = 0
    self.failP = 0

  def SetupLogging( self ):
    logging.basicConfig(
      level = logging.INFO,
      format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
      handlers = [
        logging.StreamHandler(),
        logging.FileHandler("job_scraper.log")
      ]
    )
    self.lgr = logging.getLogger(__name__)
    self.lgr.info("=== Job Scraper Started ===")
    self.lgr.info(f"Token Collection: {self.tokCol}")
    self.lgr.info(f"Raw Job Collection: {self.rawCol}")
    self.lgr.info(f"API Base URL: {self.apiBase}")

  def GetDateFilter( self ) -> str:
    d48 = datetime.now(UTC) - timedelta(hours = 48)
    dStr = d48.strftime("%Y-%m-%d")
    self.lgr.info(f"Date filter set to: {dStr} (48 hours ago)")
    return dStr

  async def MakeApiRequest( self, session: aiohttp.ClientSession, tkn: str, pld: Dict, timeout: aiohttp.ClientTimeout = None, reqType: str = "unknown" ) -> Dict:
    if(timeout==None):
      timeout = aiohttp.ClientTimeout(connect = 15, total = 30)
    fTkn = tkn.strip()
    hdrs = {
      "Content-Type": "application/json",
      "Authorization": f"Bearer {fTkn}"
    }
    self.lgr.debug(f"Using token: {fTkn[:8]}… ({len(fTkn)} chars)")
    self.lgr.info(f"Making {reqType} API request with payload: {pld}")
    reqSt = time.time()
    for att in range(3):
      try:
        self.lgr.debug(f"API request attempt {att + 1}/3")
        async with session.post(
          self.apiBase,
          json = pld,
          headers = hdrs,
          timeout = timeout
        ) as resp:
          respTm = time.time() - reqSt
          if ( resp.status == 200 ):
            respDat = await resp.json()
            self.lgr.info(
              f"{reqType} API request successful in {respTm:.2f}s"
            )
            self.lgr.debug(f"Response keys: {list(respDat.keys())}")
            return respDat
          elif( resp.status in (402, 403) ):
            raise InsufficientCreditsError(f"Credits exhausted: {resp.status}")
          elif resp.status==401:
            errTxt = await resp.text()
            self.lgr.error(
              f"{reqType} API request failed: Unauthorized (401) - "
              f"Invalid or expired token after {respTm:.2f}s"
            )
            raise InvalidTokenError("Invalid or expired token")
          elif (resp.status==429):
            errTxt = await resp.text()
            self.lgr.warning(
              f"{reqType} API request failed: Rate limited (429) - "
              f"Too many requests after {respTm:.2f}s"
            )
            await asyncio.sleep(5 * (2 ** att))
            continue
          else:
            errTxt = await resp.text()
            self.lgr.warning(
              f"{reqType} API request failed with status {resp.status} "
              f"after {respTm:.2f}s: {errTxt}"
            )
            if (resp.status >= 500):
              raise aiohttp.ClientError(f"Server error: {resp.status}")
            else:
              raise aiohttp.ClientError(f"Client error: {resp.status}")
      except InsufficientCreditsError:
        # 402/403 durumunda retry yapılmayacak, hemen dışarı çıkılacak
        raise
      except InvalidTokenError:
        # 401 durumunda retry yapılmayacak, hemen dışarı çıkılacak
        raise
      except asyncio.TimeoutError:
        respTm = time.time() - reqSt
        self.lgr.warning(
          f"{reqType} request timeout on attempt {att + 1} "
          f"after {respTm:.2f}s"
        )
        if att==2:
          raise
      except Exception as e:
        respTm = time.time() - reqSt
        self.lgr.warning(
          f"{reqType} request failed on attempt {att + 1} "
          f"after {respTm:.2f}s: {e}"
        )
        if att==2:
          raise
      if att<2:
        wTm = 0.5 * (2 ** (att + 1))
        self.lgr.debug(f"Waiting {wTm}s before retry")
        await asyncio.sleep(wTm)
    raise Exception(f"All retry attempts failed for {reqType} request")

  async def PickTokenWithQuota( self ) -> tuple[Optional[dict], int]:
    flt = {"$expr": {"$lt": ["$tokens_used", "$token_limit"]}}
    srt = [("tokens_used", 1)]
    d = await db.FindOne(self.tokCol, flt, srt)
    if not d:
      return None, 0
    rem = d["token_limit"] - d.get("tokens_used", 0)
    return d, rem

  async def MarkTokenUsage( self, tId, usd ):
    if(usd>0):
      await db.UpdateOne(
        self.tokCol,
        {"_id": tId},
        {"$inc": {"tokens_used": usd}}
      )

  async def MarkTokenExhausted( self, tId ):
    t = await db.FindOne(self.tokCol, {"_id": tId})
    if t:
      await db.UpdateOne(
        self.tokCol,
        {"_id": tId},
        {"$set": {"tokens_used": t["token_limit"]}}
      )

  async def UpsertJobsAtomic( self, js: List[Dict] ):
    if not js:
      self.lgr.warning("No jobs to upsert")
      return
    self.lgr.info(f"Starting atomic upsert of {len(js)} jobs")
    upSt = time.time()
    try:
      ups = 0
      mod = 0
      for j in js:
        res = await db.UpdateOne(
          self.rawCol,
          {"_id": j["id"]},
          {"$setOnInsert": j},
          upsert = True
        )
        if hasattr(res, 'upserted_id') and res.upserted_id:
          ups += 1
        elif hasattr(res, 'modified_count') and res.modified_count:
          mod += 1
      upTm = time.time() - upSt
      self.lgr.info(
        f"Upserted: {ups} yeni, {mod} mevcut, elapsed: {upTm:.2f}s"
      )
      self.totJ += len(js)
    except Exception as e:
      self.lgr.error(f"Error upserting jobs: {e}")
      raise

  async def ProcessPage( self, session: aiohttp.ClientSession, off: int, lim: int, dFil: str, pNum: int, tPgs: int ) -> bool:
    self.lgr.info(f"=== Processing page {pNum + 1}/{tPgs} ===")
    self.lgr.info(f"Offset: {off}, Limit: {lim}")
    pSt = time.time()
    pld = {
      "offset": off,
      "limit": lim,
      "blur_company_data": False,
      "include_total_results": False,
      "order_by": ORDER_BY,
      "posted_at_max_age_days": 1,
      "job_country_code_or": ["TR"]
    }
    rLeft = 3
    while rLeft:
      tDoc, rem = await self.PickTokenWithQuota()
      if not tDoc:
        self.lgr.error("No token with remaining quota")
        self.failP += 1
        return False
      effLim = min(lim, rem)
      pld["limit"] = effLim
      try:
        resp = await self.MakeApiRequest(
          session, tDoc["key"], pld, reqType = f"page_{pNum + 1}"
        )
        js = resp.get("data", [])
        await self.UpsertJobsAtomic(js)
        await self.MarkTokenUsage(tDoc["_id"], len(js))
        pTm = time.time() - pSt
        self.lgr.info(
          f"Page {pNum + 1} completed in {pTm:.2f}s: "
          f"{len(js)} jobs processed"
        )
        self.totP += 1
        return True
      except InsufficientCreditsError:
        await self.MarkTokenExhausted(tDoc["_id"])
        rLeft -= 1
        self.lgr.warning("Token exhausted, switching to next one...")
      except InvalidTokenError:
        await self.MarkTokenExhausted(tDoc["_id"])
        rLeft -= 1
        self.lgr.warning("Invalid token, switching to next one...")
      except Exception as e:
        pTm = time.time() - pSt
        self.lgr.error(
          f"Error processing page {pNum + 1} after {pTm:.2f}s: {e}"
        )
        self.failP += 1
        return False
    self.lgr.error("All tokens exhausted or invalid")
    self.failP += 1
    return False

  async def TestConnection( self, session: aiohttp.ClientSession ) -> bool:
    self.lgr.info("=== Testing API Connection ===")
    try:
      self.lgr.info("Fetching available tokens for connection test")
      allT = await db.FindMany(self.tokCol, {}, lim = 1)
      if not allT:
        self.lgr.error("No tokens available for connection test")
        return False
      tDoc = allT[0]
      self.lgr.info(f"Using token: {tDoc['_id']} for connection test")
      pld = {
        "limit": 1,
        "blur_company_data": True,
        "include_total_results": True,
        "order_by": ORDER_BY,
        "posted_at_max_age_days": 1,
        "job_country_code_or": ["TR"]
      }
      resp = await self.MakeApiRequest(
        session, tDoc["key"], pld, reqType = "connection_test"
      )
      if ("metadata" in resp and "total_results" in resp["metadata"]):
        totRes = resp["metadata"]["total_results"]
        self.lgr.info(f"Connection test successful! Total jobs available: {totRes}")
        self.lgr.info("=== Connection Test Completed ===")
        return True
      else:
        self.lgr.error("Connection test failed: Invalid response structure")
        return False
    except Exception as e:
      self.lgr.error(f"Connection test failed: {e}")
      return False

  async def GetTotalJobsCount( self, session: aiohttp.ClientSession ) -> int:
    self.lgr.info("=== Starting metadata probe ===")
    pld = {
      "limit": 1,
      "blur_company_data": True,
      "include_total_results": True,
      "order_by": ORDER_BY,
      "posted_at_max_age_days": 1,
      "job_country_code_or": ["TR"]
    }
    try:
      self.lgr.info("Fetching available tokens for metadata request")
      allT = await db.FindMany(self.tokCol, {}, lim = 1)
      if not allT:
        raise Exception("No tokens available for metadata request")
      tDoc = allT[0]
      self.lgr.info(f"Using token: {tDoc['_id']} for metadata request")
      resp = await self.MakeApiRequest(
        session, tDoc["key"], pld, reqType = "metadata"
      )
      totRes = resp.get("metadata", {}).get("total_results", 0)
      self.lgr.info(f"=== Metadata probe completed ===")
      self.lgr.info(f"Total jobs found: {totRes}")
      return totRes
    except Exception as e:
      self.lgr.error(f"Failed to get total jobs count: {e}")
      raise

  async def ResetOldTokens(self):
    """Kayıt tarihi 30 günden eski olan tokenların tokens_used alanını 0 yapar."""
    now = datetime.now(UTC)
    one_month_ago = now - timedelta(days=30)
    flt = {"created_at": {"$lt": one_month_ago}}
    old_tokens = await db.FindMany(self.tokCol, flt)
    for t in old_tokens:
      await db.UpdateOne(self.tokCol, {"_id": t["_id"]}, {"$set": {"tokens_used": 0, "created_at": now}})
    if old_tokens:
      self.lgr.info(f"{len(old_tokens)} eski token sıfırlandı.")

  async def RunScraper( self ):
    self.stTm = time.time()
    self.lgr.info("=== Starting Job Scraper ===")
    try:
      await self.ResetOldTokens()
      async with aiohttp.ClientSession() as sess:
        self.lgr.info("Created aiohttp session")
        connOk = await self.TestConnection(sess)
        if not connOk:
          self.lgr.error("Connection test failed, aborting")
          return
        totJ = await self.GetTotalJobsCount(sess)
        if totJ == 0:
          self.lgr.info("No jobs found in the specified date range")
          return
        remJ = totJ
        pNum = 0
        pCnt = math.ceil(totJ / 200)
        self.lgr.info(f"Calculated pagination: {pCnt} pages")
        dFil = self.GetDateFilter()
        self.lgr.info("=== Starting page processing ===")
        while remJ > 0:
          off = totJ - remJ
          lim = min(200, remJ)
          self.lgr.info(
            f"Processing page {pNum + 1}/{pCnt} "
            f"(offset: {off}, limit: {lim})"
          )
          ok = await self.ProcessPage(
            sess, off, lim, dFil, pNum, pCnt
          )
          if not ok:
            break
          remJ -= lim
          pNum += 1
        totTm = time.time() - self.stTm
        self.lgr.info("=== Job Scraper Completed ===")
        self.lgr.info(f"Total execution time: {totTm:.2f}s")
        self.lgr.info(f"Total pages processed: {self.totP}")
        self.lgr.info(f"Total jobs processed: {self.totJ}")
        self.lgr.info(f"Failed pages: {self.failP}")
        self.lgr.info(f"Average time per page: {totTm/max(1, self.totP):.2f}s")
    except Exception as e:
      totTm = time.time() - self.stTm
      self.lgr.error(f"Fatal error in scraper after {totTm:.2f}s: {e}")
      sys.exit(1)


async def Main():
  scr = jobScraper()
  await scr.RunScraper()


if __name__ == "__main__":
  asyncio.run(Main()) 