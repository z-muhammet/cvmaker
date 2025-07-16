# fetcher.py  (v2 – dayanıklı)

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import re
import sys
import time
import warnings
from pathlib import Path
from typing import List, Set, Tuple, Callable

import aiohttp
from bs4 import BeautifulSoup

from .tester import filter_ports

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

warnings.filterwarnings("ignore", category=ResourceWarning)
logging.getLogger("asyncio").setLevel(logging.ERROR)
logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Kaynaklar (tam liste, hiçbirini kaldırmadık)
# --------------------------------------------------------------------------- #

PROXY_SOURCES: list[str] = [
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
    "https://raw.githubusercontent.com/GoekhanDev/free-proxy-list/refs/heads/main/http.txt",
    "https://raw.githubusercontent.com/GoekhanDev/free-proxy-list/refs/heads/main/socks5.txt",
    "https://raw.githubusercontent.com/GoekhanDev/free-proxy-list/refs/heads/main/socks4.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/http.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks4.txt",
    "https://raw.githubusercontent.com/themiralay/Proxy-List-World/master/data.txt",
    "https://raw.githubusercontent.com/FifzzSENZE/Master-Proxy/master/proxies/all.txt",
    "https://raw.githubusercontent.com/shiftytr/proxy-list/master/proxy.txt",
    "https://api.proxyscrape.com/?request=getproxies&proxytype=http",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all&skip=0&limit=2000",
    "https://www.proxy-list.download/api/v1/get?type=http",
    "https://www.proxy-list.download/api/v1/get?type=https",
]

HTML_SOURCES: list[str] = [
    "https://www.sslproxies.org/",
    "https://free-proxy-list.net/",
    "https://www.us-proxy.org/",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/115.0 Safari/537.36"
    )
}

# --------------------------------------------------------------------------- #
# Yardımcı – Biçim Kontrolü
# --------------------------------------------------------------------------- #

def _filter_ip_port_format(lines: List[str]) -> List[str]:
    pat = re.compile(r"^(?:http[s]?://)?((?:\d{1,3}\.){3}\d{1,3}:\d{2,5})$")
    return [m.group(1) for l in lines if (m := pat.match(l))]


# --------------------------------------------------------------------------- #
# İndirme İşlevleri (retry’li)
# --------------------------------------------------------------------------- #

async def _get_with_retry(session: aiohttp.ClientSession,
                          url: str,
                          retries: int = 3,
                          base_timeout: int = 5) -> str | None:
    for attempt in range(1, retries + 1):
        timeout_cfg = aiohttp.ClientTimeout(total=base_timeout * attempt * 2)
        try:
            async with session.get(url, timeout=timeout_cfg,
                                   ssl=False, headers=HEADERS) as resp:
                if resp.status == 200:
                    return await resp.text()
                logger.warning("[%s] HTTP %s (deneme %d/%d)",
                               url, resp.status, attempt, retries)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            logger.warning("[%s] %s (deneme %d/%d)",
                           url, type(exc).__name__, attempt, retries)
        await asyncio.sleep(0.5 * attempt)  # kademeli bekleme
    return None


async def _fetch_text(session: aiohttp.ClientSession,
                      url: str) -> List[str]:
    text = await _get_with_retry(session, url)
    if not text:
        return []
    return [l.strip() for l in text.splitlines() if ":" in l]


async def _fetch_html(session: aiohttp.ClientSession,
                      url: str) -> List[str]:
    html = await _get_with_retry(session, url)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    proxies = [
        f"{tds[0].get_text(strip=True)}:{tds[1].get_text(strip=True)}"
        for row in soup.select("table tbody tr")
        if (tds := row.find_all("td")) and len(tds) >= 2
    ]
    return proxies


# --------------------------------------------------------------------------- #
# Batch Çalıştırıcı (aynı kaldı)
# --------------------------------------------------------------------------- #

FetchTask = Tuple[Callable[..., asyncio.Future], str]  # (func, url)

async def _run_batch(batch: List[FetchTask]) -> List[str]:
    async with aiohttp.ClientSession() as session:
        futures = [func(session, url) for func, url in batch]
        results = await asyncio.gather(*futures, return_exceptions=True)
    merged: List[str] = []
    for res in results:
        if isinstance(res, Exception):
            logger.error("Batch içi hata: %s", res)
        else:
            merged.extend(res)
    return merged

def _threaded_batch(batch: List[FetchTask]) -> List[str]:
    return asyncio.run(_run_batch(batch))


# --------------------------------------------------------------------------- #
# Ana Toplayıcı API
# --------------------------------------------------------------------------- #

async def async_fetch_proxies(limit: int = 10_000) -> List[str]:
    all_tasks: List[FetchTask] = (
        [(_fetch_text, u) for u in PROXY_SOURCES] +
        [(_fetch_html, u) for u in HTML_SOURCES]
    )

    batch_size = 4
    batches = [all_tasks[i:i + batch_size]
               for i in range(0, len(all_tasks), batch_size)]
    logger.info("%d batch oluşturuldu (%d görev/batch).",
                len(batches), batch_size)

    collected: Set[str] = set()
    start = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(batches)) as exe:
        futures = [exe.submit(_threaded_batch, b) for b in batches]
        for f in concurrent.futures.as_completed(futures):
            try:
                collected.update(f.result())
                logger.info("Ara toplam: %d proxy", len(collected))
                if len(collected) >= limit:
                    logger.info("Limit (%d) doldu, durduruluyor.", limit)
                    break
            except Exception as exc:
                logger.error("Thread hatası: %s", exc)

    duration = time.perf_counter() - start
    logger.info("Ham toplama bitti (%.1f s).", duration)

    cleaned = filter_ports(_filter_ip_port_format(list(collected)))
    logger.info("Sonuç: %d temiz proxy.", len(cleaned))
    return cleaned


async def async_fetch_and_save_final_proxies(limit: int = 10_000,
                                             output_file: str = "final_linkedin_proxies.txt") -> None:
    proxies = await async_fetch_proxies(limit=limit)
    Path(output_file).write_text("\n".join(proxies), encoding="utf-8")
    logger.info("%d proxy → %s", len(proxies), output_file)
