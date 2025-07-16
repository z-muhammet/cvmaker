import os
import asyncio
import logging
import subprocess
from datetime import datetime, timedelta
from fastapi.responses import PlainTextResponse
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Literal
import uvicorn
import importlib

# CV generator (sync veya async olabilir)
from cv_generator.generate_ats_cv import GenerateAtsCv

# Scheduler tek bir import: hem scheduler objesini hem de helper fonksiyonları alıyoruz
from guestscheduler.main_scheduler import scheduler, start_scheduler, shutdown_scheduler

# APScheduler durumu sabiti
from apscheduler.schedulers.base import STATE_RUNNING

# Pydantic request modeli
class GenerateCvRequest(BaseModel):
    raw_cv: str
    job_id: int
    target_lang: Literal["TR", "EN"]

class StartCommand(BaseModel):
    command: str

app = FastAPI()

# Logger konfigürasyonu
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/")
async def root():
    return {"message": "CV Maker API çalışıyor", "status": "active"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.post("/generate-cv")
async def generate_cv(req: GenerateCvRequest):
    try:
        # Eğer GenerateAtsCv sync ise executor'da çalıştır
        if not asyncio.iscoroutinefunction(GenerateAtsCv):
            loop = asyncio.get_event_loop()
            latex_cv = await loop.run_in_executor(
                None, GenerateAtsCv, req.raw_cv, req.job_id, req.target_lang
            )
        else:
            latex_cv = await GenerateAtsCv(req.raw_cv, req.job_id, req.target_lang)
        return {"latex_cv": latex_cv}
    except ValueError as ve:
        # İş mantığı hatası → 400
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception("CV oluşturulurken beklenmeyen hata")
        # Sunucu hatası → 500
        raise HTTPException(status_code=500, detail="Sunucu hatası, lütfen daha sonra tekrar deneyin.")

@app.post(
    "/generate-raw-cv",
    response_class=PlainTextResponse,
    summary="LaTeX ham metni döndürür"
)
async def generate_latex_raw(req: GenerateCvRequest) -> PlainTextResponse:
    try:
        if not asyncio.iscoroutinefunction(GenerateAtsCv):
            loop = asyncio.get_event_loop()
            latex = await loop.run_in_executor(
                None,
                GenerateAtsCv,
                req.raw_cv,
                req.job_id,
                req.target_lang
            )
        else:
            latex = await GenerateAtsCv(
                req.raw_cv,
                req.job_id,
                req.target_lang
            )
        return PlainTextResponse(content=latex, media_type="text/plain")
    except ValueError as ve:
        # Mantıksal hata → 400
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as exc:
        logger.exception("LaTeX ham üretimi sırasında beklenmeyen hata")
        # Sunucu hatası → 500
        raise HTTPException(
            status_code=500,
            detail="Sunucu hatası, lütfen daha sonra tekrar deneyin."
        )

async def trigger_all_jobs():
    jobs = scheduler.get_jobs()
    for job in jobs:
        func_ref = getattr(job, 'func_ref', None)
        if func_ref:
            if ':' in func_ref:
                mod_name, func_name = func_ref.split(':')
            else:
                mod_name, func_name = func_ref.rsplit('.', 1)
            mod = importlib.import_module(mod_name)
            func = getattr(mod, func_name)
            if asyncio.iscoroutinefunction(func):
                asyncio.create_task(func())
            else:
                func()

@app.post("/start")
async def start_system(cmd: StartCommand):
    if cmd.command != "system on start":
        raise HTTPException(status_code=400, detail="Geçersiz komut")

    if scheduler.state == STATE_RUNNING:
        return {"status": "already running"}

    start_scheduler()
    logger.info("Scheduler '/start' endpoint ile asenkron başlatıldı.")

    # Tüm işleri anında tetikle
    await trigger_all_jobs()

    return {"status": "scheduler started and all jobs triggered"}

@app.get("/scheduler/status")
async def get_scheduler_status():
    return {
        "state": scheduler.state,
        "running": scheduler.running,
        "job_count": len(scheduler.get_jobs()),
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            }
            for job in scheduler.get_jobs()
        ]
    }

# Scheduler shutdown event
@app.on_event("shutdown")
async def on_shutdown():
    try:
        await shutdown_scheduler()
        logger.info("Scheduler düzgün şekilde kapatıldı (shutdown event içinde).")
    except Exception as e:
        logger.error(f"Scheduler kapatma hatası: {e}")

if __name__ == "__main__":
    uvicorn.run(
        "rest_api:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )
