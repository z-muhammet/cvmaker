import os
import logging
import asyncio
import subprocess
import functools
from datetime import datetime, timedelta

import pymongo
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.mongodb import MongoDBJobStore
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

# Logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB connection
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "jobscrapper")
mongo_client = pymongo.MongoClient(MONGODB_URI)
db = mongo_client[MONGODB_DB]

# Scheduler
jobstores = {
    'default': MongoDBJobStore(database=MONGODB_DB,
                               collection='apscheduler_jobs',
                               host=MONGODB_URI)
}
scheduler = AsyncIOScheduler(jobstores=jobstores, timezone="UTC")

async def run_command_async(cmd: str) -> int:
    logger.info(f"Komut çalıştırılıyor: {cmd}")
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        functools.partial(subprocess.run, cmd, shell=True, check=False, capture_output=True, text=True)
    )
    logger.info(f"Komut bitti (exit={result.returncode}): {result.stdout} {result.stderr}")
    return result.returncode

async def proxy_monitor():
    await run_command_async("python -m proxies.manager --monitor --linkedin-interval 1")

async def token_requester_and_job_processor():
    ret = await run_command_async("python -m job_scrapers.token_requester")
    if ret == 0:
        await run_command_async("python -m nlp.job_processor --batch-size 5 --max-retries 2")
    else:
        logger.error("token_requester başarısız oldu, job_processor çalıştırılmadı.")

async def signup():
    await run_command_async("python -m job_scrapers.signup")

async def cleanup_old_proxies():
    try:
        collection = db['successlinkedin']
        threshold = datetime.utcnow() - timedelta(minutes=30)
        result = collection.delete_many({"added_at": {"$lt": threshold}})
        logger.info(f"{result.deleted_count} adet eski proxy silindi.")
    except Exception as exc:
        logger.error(f"Proxy temizleme hatası: {exc}")

# Job event listener
def job_listener(event):
    if event.exception:
        logger.error(f"Job {event.job_id} hata ile bitti: {event.exception}")
    else:
        logger.info(f"Job {event.job_id} başarıyla çalıştı")

def start_scheduler():
    """
    Job'ları planlayıp scheduler'ı başlatır. ID çakışmalarını önlemek için replace_existing=True kullanır.
    """
    scheduler.add_job(token_requester_and_job_processor,
                      trigger=IntervalTrigger(hours=24),
                      id="token_and_jobproc",
                      replace_existing=True)
    scheduler.add_job(signup,
                      trigger=IntervalTrigger(hours=6),
                      id="signup",
                      replace_existing=True)
    scheduler.add_job(cleanup_old_proxies,
                      trigger=IntervalTrigger(hours=1),
                      id="cleanup_old_proxies",
                      replace_existing=True)
    scheduler.add_job(proxy_monitor,
                      trigger=IntervalTrigger(minutes=5),
                      id="proxy_monitor",
                      replace_existing=True)
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.start()
    logger.info("Scheduler başlatıldı ve iş planları oluşturuldu.")

async def shutdown_scheduler():
    """
    Scheduler'ı düzgün şekilde kapatır.
    """
    try:
        if scheduler.running:
            scheduler.shutdown(wait=False)
            logger.info("Scheduler kapatıldı.")
        else:
            logger.info("Scheduler zaten kapalı.")
    except Exception as e:
        logger.error(f"Scheduler kapatma hatası: {e}")

if __name__ == "__main__":
    start_scheduler()
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        pass
