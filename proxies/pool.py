import random
from pathlib import Path
from typing import Set, Optional
import threading
import datetime
import logging

PROXY_POOL_FILE = "working_proxies.txt"
PROXY_LOG_FILE = "proxy_pool.log"
_poolLock = threading.Lock()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Proxy işlemlerini günlüğe kaydeder

def LogProxyAction( action: str, proxy: Optional[str] = None ):
  timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
  msg = f"[{timestamp}] {action}"
  if( proxy ):
    msg += f": {proxy}"
  logger.info( msg )
  with open( PROXY_LOG_FILE, "a", encoding="utf-8" ) as file:
    file.write( msg + "\n" )


# Proxy havuzunu dosyadan yükler

def LoadProxyPool( ) -> Set[str]:
  with _poolLock:
    path = Path( PROXY_POOL_FILE )
    if ( not path.exists() ):
      return set()
    return set(
      line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    )


# Proxy havuzunu dosyaya kaydeder

def SaveProxyPool( proxies: Set[str] ):
  with _poolLock:
    Path( PROXY_POOL_FILE ).write_text( "\n".join( proxies ), encoding="utf-8" )


# Havuzdan rastgele bir proxy döndürür

def GetRandomProxy( ) -> Optional[str]:
  proxies = list( LoadProxyPool() )
  if not proxies:
    return None
  return random.choice( proxies )


# Proxy'yi havuzdan çıkarır

def RemoveProxy( proxy: str ):
  with _poolLock:
    proxies = LoadProxyPool()
    if proxy in proxies:
      proxies.remove( proxy )
      SaveProxyPool( proxies )
      LogProxyAction( "KALDIRILDI", proxy ) 