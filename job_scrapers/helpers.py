import asyncio  
import random
from typing import Callable, Any  
from dbprocess.db_manager import db

RND_MIN = 150  
RANDOM_MAX_DEFAULT = 450  


def RandomInt( mn : int, mx : int ) -> int:
  return random.randint( mn, mx )  


async def RandomPause( mn : int = RND_MIN, mx : int = RANDOM_MAX_DEFAULT ) -> None:
  await asyncio.sleep( RandomInt( mn, mx ) / 1000 )  


async def Retry( fnc : Callable[..., Any], att : int = 3, *a : Any, **kw : Any ) -> Any:
  lastEx : Exception | None = None  
  for _ in range( att ):
    try:
      return await fnc( *a, **kw )  
    except Exception as ex:  
      lastEx = ex  
      await RandomPause()  
  raise lastEx if( lastEx ) else RuntimeError( "retry failed" )  


async def Stealthify( pg ) -> None:
  try:
    from playwright_stealth import stealth_async    
  except ImportError:
    return  
  await stealth_async( pg )  


async def GetAndDeleteSLinkedinProxy( ) -> str | None:
  pxs = await db.FindMany( "successlinkedin", {}, lim = 1 )  
  if not pxs:  
    return None  
  px = pxs[0][ "proxy" ]  
  await db.DeleteOne( "successlinkedin", { "proxy": px } )  
  return px  
