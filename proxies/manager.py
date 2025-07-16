"""
manager.py
Proxy toplama, HTTPS testi ve LinkedIn testi döngülerini yöneten yüksek seviye
denetleyici.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime
from typing import Dict

from dbprocess.db_manager import db
from .fetcher import async_fetch_proxies
from .tester import (async_batch_https_test_db,
                     async_batch_linkedin_test_db)

logger = logging.getLogger(__name__)


class ProxyManager:
    def __init__(self,
                 fetch_interval_min: int = 15,
                 linkedin_interval_min: int = 5):
        self.fetch_interval = fetch_interval_min * 60
        self.linkedin_interval = linkedin_interval_min * 60
        self._is_running = False
        self._stats: Dict[str, int | datetime | None] = {
            "total_fetches": 0,
            "total_linkedin_tests": 0,
            "successful_https": 0,
            "successful_linkedin": 0,
            "last_fetch": None,
            "last_linkedin": None,
        }

    # --------------------------------------------------------------------- #
    # Çekme + HTTPS Testi
    # --------------------------------------------------------------------- #
    async def _fetch_and_https_test(self):
        logger.info("[%s] Proxy çekme + HTTPS testi başlıyor…",
                    datetime.now().strftime("%F %T"))
        proxies = await async_fetch_proxies(limit=5_000)
        await async_batch_https_test_db(proxies, db,
                                        timeout=3, print_every=1_000)

        self._stats["total_fetches"] += 1
        self._stats["last_fetch"] = datetime.now()
        self._stats["successful_https"] = (
            await db.GetColCount("successhttps")
        )

        logger.info("HTTPS testi tamamlandı. Çalışan HTTPS proxy: %d",
                    self._stats["successful_https"])

    # --------------------------------------------------------------------- #
    # LinkedIn Testi
    # --------------------------------------------------------------------- #
    async def _linkedin_test_cycle(self):
        logger.info("[%s] LinkedIn testi başlıyor…",
                    datetime.now().strftime("%F %T"))
        await async_batch_linkedin_test_db(db,
                                           batch_size=500,
                                           timeout=5,
                                           print_every=100)

        self._stats["total_linkedin_tests"] += 1
        self._stats["last_linkedin"] = datetime.now()
        self._stats["successful_linkedin"] = (
            await db.GetColCount("successlinkedin")
        )

        logger.info("LinkedIn testi tamamlandı. "
                    "LinkedIn proxy: %d  |  HTTPS proxy: %d",
                    self._stats["successful_linkedin"],
                    self._stats["successful_https"])

    # --------------------------------------------------------------------- #
    # Sürekli Döngüler
    # --------------------------------------------------------------------- #
    async def _run_fetch_loop(self):
        logger.info("Proxy çekme döngüsü başladı (%.0f sn aralık)…",
                    self.fetch_interval)
        while self._is_running:
            try:
                await self._fetch_and_https_test()
            except Exception as exc:
                logger.error("Fetch döngüsü hatası: %s", exc)
            await asyncio.sleep(self.fetch_interval)

    async def _run_linkedin_loop(self):
        logger.info("LinkedIn döngüsü başladı (%.0f sn aralık)…",
                    self.linkedin_interval)
        while self._is_running:
            try:
                await self._linkedin_test_cycle()
            except Exception as exc:
                logger.error("LinkedIn döngüsü hatası: %s", exc)
            await asyncio.sleep(self.linkedin_interval)

    # --------------------------------------------------------------------- #
    # Dış API
    # --------------------------------------------------------------------- #
    def show_stats(self):
        logger.info("---- PROXY YÖNETİM İSTATİSTİKLERİ ----")
        for k, v in self._stats.items():
            logger.info("  %-20s : %s", k, v)

    async def start_monitoring(self):
        self._is_running = True
        logger.info("Proxy izleme sistemi başlatıldı.")
        tasks = [asyncio.create_task(self._run_fetch_loop()),
                 asyncio.create_task(self._run_linkedin_loop())]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            pass
        finally:
            self._is_running = False
            logger.info("Proxy izleme sistemi durduruldu.")

    # --------------------------------------------------------------------- #
    # Tek Seferlik Pipeline
    # --------------------------------------------------------------------- #
    @staticmethod
    def run_full_pipeline(limit: int = 10_000,
                          https_timeout: int = 3,
                          linkedin_timeout: int = 5):
        async def _pipeline():
            proxies = await async_fetch_proxies(limit=limit)
            await async_batch_https_test_db(proxies, db,
                                            timeout=https_timeout)
            await async_batch_linkedin_test_db(db,
                                               batch_size=1_000,
                                               timeout=linkedin_timeout)
        asyncio.run(_pipeline())


# --------------------------------------------------------------------------- #
# Komut Satırı Arayüzü
# --------------------------------------------------------------------------- #

def _cli():
    parser = argparse.ArgumentParser(
        description="Proxy modül yönetimi ve dinamik kontrol sistemi."
    )
    parser.add_argument("--full-pipeline", action="store_true",
                        help="Tüm pipeline'ı bir kez çalıştır.")
    parser.add_argument("--monitor", action="store_true",
                        help="Dinamik proxy izleme sistemi başlat.")
    parser.add_argument("--fetch-interval", type=int, default=15,
                        help="Proxy çekme aralığı (dakika)")
    parser.add_argument("--linkedin-interval", type=int, default=5,
                        help="LinkedIn test aralığı (dakika)")
    parser.add_argument("--limit", type=int, default=10_000,
                        help="Proxy toplama limiti")
    parser.add_argument("--https-timeout", type=int, default=3)
    parser.add_argument("--linkedin-timeout", type=int, default=5)
    args = parser.parse_args()

    if args.full_pipeline:
        ProxyManager.run_full_pipeline(limit=args.limit,
                                       https_timeout=args.https_timeout,
                                       linkedin_timeout=args.linkedin_timeout)
        return

    if args.monitor:
        manager = ProxyManager(fetch_interval_min=args.fetch_interval,
                               linkedin_interval_min=args.linkedin_interval)
        asyncio.run(manager.start_monitoring())
        return

    parser.print_help()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s: %(message)s")
    _cli()
