import asyncio
import json
import logging
import os
import sys
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv

from .nlpApi import ExtractJobData
from .job_analyzer import jobAnalyzer
from dbprocess.db_manager import db

import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from dbprocess.db_manager import dbManager
import os
from dotenv import load_dotenv

load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "jobscrapper")

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class jobProcessor:
  def __init__( self, batch_size: int = 10, max_retries: int = 3 ):
    self.batch_size = batch_size
    self.max_retries = max_retries
    self.processed_count = 0
    self.success_count = 0
    self.error_count = 0
    self.skipped_count = 0
    self.job_analyzer = None
    load_dotenv()

  async def InitializeJobAnalyzer( self ):
    try:
      self.job_analyzer = jobAnalyzer(use_browser = True)
      await self.job_analyzer.initialize_client()
      logger.info("✅ jobAnalyzer başarıyla başlatıldı")
      return True
    except Exception as e:
      logger.error(f"❌ jobAnalyzer başlatılamadı: {e}")
      return False

  async def IsJobAlreadyAnalyzed( self, job_id ) -> bool:
    try:
      existing = await db.FindOne(
        "job_analysis_results",
        {"job_id": job_id}
      )
      return existing is not None
    except Exception as e:
      logger.error(f"❌ Çift kontrol hatası (job {job_id}): {e}")
      return False

  def CombineJobText( self, job_data: Dict ) -> str:
    try:
      description = job_data.get('description', '')
      location = job_data.get('location', '')
      long_location = job_data.get('long_location', '')
      combined_location = location
      if( long_location and long_location != location ):
        combined_location = f"{location} - {long_location}" if location else long_location
      combined_text = description
      if ( combined_location ):
        combined_text = f"Location: {combined_location}\n\n{description}"
      logger.info(f"Birleştirilmiş metin uzunluğu: {len(combined_text)} karakter")
      return combined_text
    except Exception as e:
      logger.error(f"İş metni birleştirme hatası: {e}")
      return job_data.get('description', '')

  async def ProcessJobWithNlpApi( self, job_text: str, job_id: str ) -> Optional[Dict]:
    for att in range(self.max_retries):
      try:
        logger.info(f"Job {job_id} NLP API ile işleniyor (deneme {att + 1}/{self.max_retries})")
        result = await ExtractJobData(job_text)
        if result and isinstance(result, dict):
          logger.info(f"✅ Job {job_id} NLP API ile başarıyla işlendi")
          return result
        else:
          logger.warning(f"⚠️ NLP API job {job_id} için geçersiz sonuç döndürdü")
      except Exception as e:
        logger.error(f"❌ NLP API hatası job {job_id} (deneme {att + 1}): {e}")
        if att < self.max_retries - 1:
          await asyncio.sleep(2 ** att)
    return None

  async def ProcessJobWithPlaywright( self, job_text: str, job_id: str ) -> Optional[Dict]:
    try:
      if not self.job_analyzer:
        if not await self.InitializeJobAnalyzer():
          return None
      logger.info(f"Job {job_id} Playwright sistemi ile işleniyor")
      result = await self.job_analyzer.analyze_job_description(job_text)
      if result and not result.get('error'):
        logger.info(f"✅ Job {job_id} Playwright ile başarıyla işlendi")
        return result
      else:
        logger.warning(f"⚠️ Playwright job {job_id} için hata döndürdü: {result.get('error', 'Bilinmeyen hata')}")
        return None
    except Exception as e:
      logger.error(f"❌ Playwright hatası job {job_id}: {e}")
      return None

  async def SaveAnalysisResult( self, job_id: str, analysis_result: Dict, original_job: Dict ):
    try:
      source_url = original_job.get('source_url', original_job.get('url', ''))
      if source_url:
        analysis_result['source_url'] = source_url
      analysis_doc = {
        "job_id": job_id,
        "analysis_result": analysis_result,
        "processed_at": datetime.now(),
        "processor_version": "1.0"
      }
      await db.InsertOne("job_analysis_results", analysis_doc)
      logger.info(f"✅ Analiz sonucu kaydedildi job {job_id} (source_url: {source_url[:50] if source_url else 'YOK'}...)")
    except Exception as e:
      logger.error(f"❌ Analiz sonucu kaydedilemedi job {job_id}: {e}")
      raise

  async def MarkJobAsProcessed( self, job_id ):
    try:
      job = await db.FindOne("raw_jobs", {"_id": job_id})
      if not job:
        logger.warning(f"⚠️ Job {job_id} raw_jobs koleksiyonunda bulunamadı")
        return
      await db.UpdateOne(
        "raw_jobs",
        {"_id": job_id},
        {"$set": {"processed": True, "processed_at": datetime.now()}}
      )
      logger.info(f"✅ Job {job_id} işlendi olarak işaretlendi")
    except Exception as e:
      logger.error(f"❌ Job {job_id} işlendi olarak işaretlenemedi: {e}")

  async def GetUnprocessedJobs( self, limit: int = None ) -> List[Dict]:
    try:
      query = {"processed": {"$ne": True}}
      jobs = await db.FindMany("raw_jobs", query, limit or self.batch_size)
      if not jobs:
        logger.info("'processed' alanı olan iş bulunamadı, tüm işler alınıyor...")
        jobs = await db.FindMany("raw_jobs", {}, limit or self.batch_size)
      logger.info(f"📊 {len(jobs)} iş işlenmemiş olarak bulundu")
      return jobs
    except Exception as e:
      logger.error(f"❌ İşlenmemiş işler alınamadı: {e}")
      return []

  async def ProcessSingleJob( self, job_data: Dict ) -> bool:
    job_id = job_data.get('_id')
    try:
      logger.info(f"🔄 Job {job_id} işleniyor")
      if await self.IsJobAlreadyAnalyzed(job_id):
        logger.info(f"⚠️ Job {job_id} zaten analiz edilmiş, atlanıyor")
        await self.MarkJobAsProcessed(job_id)
        self.skipped_count += 1
        return True
      job_text = self.CombineJobText(job_data)
      if not job_text or len(job_text.strip()) < 10:
        logger.warning(f"⚠️ Job {job_id} yeterli metne sahip değil, atlanıyor")
        await self.MarkJobAsProcessed(job_id)
        self.skipped_count += 1
        return True
      analysis_result = await self.ProcessJobWithNlpApi(job_text, job_id)
      if not analysis_result:
        logger.info(f"🔄 NLP API başarısız oldu job {job_id}, Playwright deneniyor...")
        analysis_result = await self.ProcessJobWithPlaywright(job_text, job_id)
      if not analysis_result:
        logger.error(f"❌ Hem NLP API hem Playwright başarısız oldu job {job_id}")
        self.error_count += 1
        return False
      await self.SaveAnalysisResult(job_id, analysis_result, job_data)
      await self.MarkJobAsProcessed(job_id)
      self.success_count += 1
      logger.info(f"✅ Job {job_id} başarıyla işlendi")
      return True
    except Exception as e:
      logger.error(f"❌ Beklenmeyen hata job {job_id} işlenirken: {e}")
      self.error_count += 1
      return False

  async def ProcessAllJobs( self ):
    logger.info("🚀 İş işleme başlatılıyor...")
    total_processed = 0
    consecutive_empty_batches = 0
    max_empty_batches = 3
    while True:
      jobs = await self.GetUnprocessedJobs(self.batch_size)
      if not jobs:
        consecutive_empty_batches += 1
        logger.info(f"📭 İşlenmemiş iş bulunamadı (boş batch {consecutive_empty_batches}/{max_empty_batches})")
        if consecutive_empty_batches >= max_empty_batches:
          logger.info("📭 Maksimum boş batch sayısına ulaşıldı, duruluyor...")
          break
        await asyncio.sleep(5)
        continue
      consecutive_empty_batches = 0
      logger.info(f"📦 {len(jobs)} işten oluşan batch işleniyor")
      for job in jobs:
        success = await self.ProcessSingleJob(job)
        total_processed += 1
        await asyncio.sleep(1)
      logger.info(f"📊 Batch tamamlandı. Toplam işlenen: {total_processed}")
      remaining_jobs = await self.GetUnprocessedJobs(1)
      if not remaining_jobs:
        logger.info("📭 İşlenecek başka iş kalmadı")
        break
    logger.info("=" * 60)
    logger.info("📊 FİNAL İŞLEME İSTATİSTİKLERİ")
    logger.info("=" * 60)
    logger.info(f"Toplam işlenen iş: {total_processed}")
    logger.info(f"Başarıyla analiz edilen: {self.success_count}")
    logger.info(f"Atlanan (zaten analizli): {self.skipped_count}")
    logger.info(f"Başarısız: {self.error_count}")
    if total_processed > 0:
      success_rate = ((self.success_count + self.skipped_count) / total_processed * 100)
      logger.info(f"Genel başarı oranı: {success_rate:.2f}%")
    logger.info("=" * 60)

  async def Cleanup( self ):
    if self.job_analyzer:
      await self.job_analyzer.close()
      logger.info("🧹 Temizlik tamamlandı")

async def Main():
  import argparse
  parser = argparse.ArgumentParser(description = "Veritabanındaki işleri NLP API ile işle")
  parser.add_argument('--batch-size', type = int, default = 10, help = 'İşleme batch boyutu')
  parser.add_argument('--max-retries', type = int, default = 3, help = 'Her iş için maksimum deneme')
  parser.add_argument('--test-single', type = str, help = 'Tek bir iş ID ile test')
  args = parser.parse_args()
  processor = jobProcessor(
    batch_size = args.batch_size,
    max_retries = args.max_retries
  )
  try:
    if args.test_single:
      job = await db.FindOne("raw_jobs", {"_id": args.test_single})
      if job:
        await processor.ProcessSingleJob(job)
      else:
        logger.error(f"Job {args.test_single} bulunamadı")
    else:
      await processor.ProcessAllJobs()
  except KeyboardInterrupt:
    logger.info("⏹️ İşleme kullanıcı tarafından durduruldu")
  except Exception as e:
    logger.error(f"❌ Beklenmeyen hata: {e}")
  finally:
    await processor.Cleanup()

if __name__ == "__main__":
  asyncio.run(Main()) 