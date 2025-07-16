"""
tester.py
Proxy’lerin HTTPS ve LinkedIn erişim testlerini yürüten yardımcı fonksiyonlar.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import List

import aiohttp
import requests
from dbprocess.db_manager import dbManager  # proje‑içi modül

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Yardımcı – Temel Testler
# --------------------------------------------------------------------------- #

def test_proxy(proxy: str,
               test_url: str = "https://www.linkedin.com",
               timeout: int = 5) -> bool:
    """Verilen proxy ile `test_url`’e ulaşılabiliyor mu?"""
    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
    try:
        resp = requests.get(test_url, proxies=proxies,
                            timeout=timeout, verify=False)
        return resp.status_code == 200
    except Exception:
        return False


def filter_ports(proxy_list: List[str]) -> List[str]:
    """Sadece geçerli port numarasına sahip proxy’leri döndürür."""
    filtered: List[str] = []
    for proxy in proxy_list:
        try:
            port = int(proxy.rsplit(":", 1)[-1])
            if 1 <= port <= 65_535:
                filtered.append(proxy)
        except Exception:
            continue
    logger.info("%d proxy port filtresinden geçti.", len(filtered))
    return filtered


# --------------------------------------------------------------------------- #
# HTTPS – Senkron/Asenkron Testler
# --------------------------------------------------------------------------- #

def fast_https_test(proxy: str, timeout: int = 3) -> bool:
    proxies = {"http": f"http://{proxy}", "https": f"http://{proxy}"}
    try:
        resp = requests.get("https://httpbin.org/ip",
                            proxies=proxies, timeout=timeout, verify=False)
        return resp.status_code == 200
    except Exception:
        return False


def batch_fast_https_test(proxy_list: List[str],
                          timeout: int = 3,
                          print_every: int = 1_000) -> List[str]:
    """Thread havuzu ile çoklu proxy’yi HTTPS için test eder."""
    working: List[str] = []
    total = len(proxy_list)
    with ThreadPoolExecutor(max_workers=100) as pool:
        futures = {pool.submit(fast_https_test, p, timeout): p
                   for p in proxy_list}
        checked = success = 0
        for future in as_completed(futures):
            proxy = futures[future]
            checked += 1
            if future.result():
                working.append(proxy)
                success += 1
            if checked % print_every == 0 or checked == total:
                logger.info("[HTTPS TEST] %d/%d test edildi, başarılı: %d",
                            checked, total, success)
    return working


async def async_fast_https_test(proxy: str, timeout: int = 3) -> bool:
    url = "https://httpbin.org/ip"
    proxy_url = f"http://{proxy}"
    conn = aiohttp.TCPConnector(ssl=False)
    try:
        async with aiohttp.ClientSession(connector=conn) as session:
            async with session.get(url, proxy=proxy_url,
                                   timeout=timeout) as resp:
                return resp.status == 200
    except Exception:
        return False


async def async_batch_https_test_db(proxy_list: List[str],
                                    db: dbManager,
                                    timeout: int = 3,
                                    print_every: int = 1_000,
                                    test_existing: bool = False) -> List[str]:
    """
    HTTPS testini asenkron yürütür; başarılı proxy’leri `successhttps`
    koleksiyonunda saklar veya günceller.
    """
    if test_existing:
        docs = await db.FindMany("successhttps", {}, lim=1_000)
        if not docs:
            logger.info("[DB] Test edilecek HTTPS proxy kalmadı.")
            return []
        proxy_list = [d["proxy"] for d in docs]

    working: List[str] = []
    total = len(proxy_list)
    sem = asyncio.Semaphore(200)
    checked = success = 0
    batch: List[dict] = []
    failed: List[str] = []

    async def _work(proxy: str):
        nonlocal checked, success, batch, failed
        async with sem:
            if await async_fast_https_test(proxy, timeout):
                working.append(proxy)
                if test_existing:
                    await db.UpdateProxyTs("successhttps", proxy)
                else:
                    batch.append({"proxy": proxy,
                                  "added_at": datetime.now()})
                success += 1
            elif test_existing:
                failed.append(proxy)
            checked += 1

            if checked % print_every == 0 or checked == total:
                logger.info("[HTTPS ASYNC] %d/%d test edildi, başarılı: %d",
                            checked, total, success)
                if batch and not test_existing:
                    await db.InsertMany("successhttps", batch)
                    logger.info("[DB] %d proxy eklendi.", len(batch))
                    batch.clear()

    await asyncio.gather(*[_work(p) for p in proxy_list])

    if batch and not test_existing:
        await db.InsertMany("successhttps", batch)
    if test_existing and failed:
        await db.DeleteMany("successhttps", {"proxy": {"$in": failed}})
        logger.info("[DB] %d başarısız proxy silindi.", len(failed))
    return working


# --------------------------------------------------------------------------- #
# LinkedIn – Asenkron Testler
# --------------------------------------------------------------------------- #

async def async_linkedin_test(proxy: str, timeout: int = 5) -> bool:
    url = "https://www.linkedin.com"
    proxy_url = f"http://{proxy}"
    conn = aiohttp.TCPConnector(ssl=False)
    try:
        async with aiohttp.ClientSession(connector=conn) as session:
            async with session.get(url, proxy=proxy_url,
                                   timeout=timeout) as resp:
                return resp.status == 200
    except Exception:
        return False


async def async_batch_linkedin_test_db(db: dbManager,
                                       batch_size: int = 1_000,
                                       timeout: int = 5,
                                       print_every: int = 500,
                                       test_existing: bool = False) -> None:
    """
    successhttps → successlinkedin geçişini yönetir ve/veya mevcut
    successlinkedin kayıtlarını periyodik olarak doğrular.
    """
    if test_existing:
        docs = await db.FindMany("successlinkedin", {}, lim=batch_size)
        if not docs:
            logger.info("[DB] Test edilecek LinkedIn proxy kalmadı.")
            return
        proxy_list = [d["proxy"] for d in docs]
        failed: list[str] = []
        sem = asyncio.Semaphore(200)
        checked = success = 0

        async def _work(proxy: str):
            nonlocal checked, success, failed
            async with sem:
                if await async_linkedin_test(proxy, timeout):
                    await db.UpdateProxyTs("successlinkedin", proxy)
                    success += 1
                else:
                    failed.append(proxy)
                checked += 1
                if checked % print_every == 0 or checked == len(proxy_list):
                    logger.info("[LINKEDIN EXIST] %d/%d test edildi, başarılı: %d",
                                checked, len(proxy_list), success)

        await asyncio.gather(*[_work(p) for p in proxy_list])
        if failed:
            await db.DeleteMany("successlinkedin",
                                {"proxy": {"$in": failed}})
            logger.info("[DB] %d başarısız proxy silindi.", len(failed))
        return

    # --- successhttps koleksiyonunu LinkedIn için tarıyoruz ---
    while True:
        docs = await db.FindMany("successhttps", {}, lim=batch_size)
        if not docs:
            logger.info("[DB] İşlenecek HTTPS proxy kalmadı.")
            break
        proxy_list = [d["proxy"] for d in docs]
        sem = asyncio.Semaphore(200)
        checked = success = 0

        async def _work(proxy: str, proxy_doc: dict):
            nonlocal checked, success
            async with sem:
                result = await async_linkedin_test(proxy, timeout)
                checked += 1
                await db.DeleteOne("successhttps", {"proxy": proxy})
                if result:
                    proxy_doc.pop("_id", None)
                    proxy_doc["added_at"] = datetime.now()
                    await db.db["successlinkedin"].update_one(
                        {"proxy": proxy_doc["proxy"]},
                        {"$set": proxy_doc},
                        upsert=True
                    )
                    success += 1
                if checked % print_every == 0 or checked == len(proxy_list):
                    logger.info("[LINKEDIN ASYNC] %d/%d test edildi, başarılı: %d",
                                checked, len(proxy_list), success)

        await asyncio.gather(*[_work(p, docs[i])
                               for i, p in enumerate(proxy_list)])
