import asyncio
import datetime
import json
import logging
import os
import random
import re
import sys
from pathlib import Path
from typing import Final

from dotenv import load_dotenv
from fake_useragent import UserAgent
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError, Error as PWError
from faker import Faker

from .helpers import GetAndDeleteSLinkedinProxy, RandomInt, RandomPause, Retry, Stealthify
from dbprocess.db_manager import dbManager

MAX_PROXY_ATTEMPTS = 20

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "jobscrapper")
dbmanager = dbManager(MONGODB_URI, MONGODB_DB)

def SetLogging( ):
  logging.basicConfig( level = logging.INFO )


async def CheckProxyAvail( ):
  try:
    cnt = await dbmanager.GetColCount( "successlinkedin" )
    return cnt > 0
  except Exception as e:
    logging.warning( f"Proxy kontrol hatası: {e}" )
    return False


async def TestProxyWithTheirStack( prx: str ) -> bool:
  try:
    import aiohttp
    import asyncio
    timeout = aiohttp.ClientTimeout( total = 6 )
    conn = aiohttp.TCPConnector( ssl = False )
    async with aiohttp.ClientSession( timeout = timeout, connector = conn ) as sess:
      async with sess.get( "https://theirstack.com/en", proxy = f"http://{prx}", headers = { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" } ) as resp:
        if( resp.status==200 ):
          logging.info( f"Proxy test başarılı: {prx}" )
          return True
        else:
          logging.warning( f"Proxy test başarısız (status {resp.status}): {prx}" )
          return False
  except asyncio.TimeoutError:
    logging.warning( f"Proxy test timeout (6s): {prx}" )
    return False
  except Exception as e:
    logging.warning( f"Proxy test hatası: {prx} | Hata: {e}" )
    return False


async def SetProxyEnvWithRetry( ):
  SetLogging( )
  hasPrx = await CheckProxyAvail( )
  if not hasPrx:
    logging.warning( "successlinkedin koleksiyonu boş, proxy kullanmadan çalıştırılıyor." )
    if( "HTTP_PROXY" in os.environ ):
      del os.environ[ "HTTP_PROXY" ]
    return True
  for att in range( 1, MAX_PROXY_ATTEMPTS + 1 ):
    prx = await GetAndDeleteSLinkedinProxy( )
    if not prx:
      logging.warning( "Proxy bulunamadı, proxy olmadan çalıştırılıyor." )
      if( "HTTP_PROXY" in os.environ ):
        del os.environ[ "HTTP_PROXY" ]
      return True
    logging.info( f"[{att}. deneme] Proxy test ediliyor: {prx}" )
    if await TestProxyWithTheirStack( prx ):
      os.environ[ "HTTP_PROXY" ] = prx
      logging.info( f"Proxy başarılı ve ayarlandı: {prx}" )
      return True
    else:
      logging.warning( f"Proxy test başarısız, silindi: {prx}" )
      continue
  logging.warning( f"{MAX_PROXY_ATTEMPTS} denemede de çalışan proxy bulunamadı, proxy olmadan çalıştırılıyor." )
  if( "HTTP_PROXY" in os.environ ):
    del os.environ[ "HTTP_PROXY" ]
  return True

if not asyncio.run( SetProxyEnvWithRetry( ) ):
  import sys
  sys.exit( 1 )

TIMEOUT_MS: Final[int] = 60_000
SHOTS_DIR: Final[Path] = Path( "./shots" ).resolve( )

TIMEZONES: Final[list[str]] = [
  "Europe/Istanbul",
  "Europe/Berlin",
  "America/New_York",
  "Asia/Tokyo",
  "Europe/Paris",
]

LOCALES: Final[list[str]] = [ "tr-TR", "en-US", "de-DE", "fr-FR", "es-ES" ]

EMAIL_REGEX: Final[re.Pattern[str]] = re.compile( r"^[\w\.-]+@[\w\.-]+\.\w+$" )
OTP_REGEX: Final[re.Pattern[str]] = re.compile( r"\b\d{6}\b" )

logger = logging.getLogger( "pino" )
logger.setLevel( logging.INFO )
handler = logging.StreamHandler( sys.stderr )
handler.setFormatter( logging.Formatter( "%(message)s" ) )
logger.handlers = [ handler ]
logger.propagate = False


async def SaveScreenshot( pg, stp: str ) -> None:
  SHOTS_DIR.mkdir( parents = True, exist_ok = True )
  tstamp = datetime.datetime.now( ).strftime( "%Y%m%d-%H%M%S" )
  pth = SHOTS_DIR / f"{tstamp}-{stp}.png"
  await pg.screenshot( path = pth )
  logger.info( f"[screenshot] {pth}" )


async def WaitVisible( pg, sel: str ):
  await Retry( pg.wait_for_selector, selector = sel, timeout = TIMEOUT_MS, state = "visible" )


async def Click( pg, sel: str ) -> None:
  await WaitVisible( pg, sel )
  await RandomPause( )
  await pg.click( sel )
  await RandomPause( )


async def HoverAndType( pg, sel: str, txt: str ) -> None:
  await WaitVisible( pg, sel )
  bx = await pg.locator( sel ).bounding_box( )
  if( bx ):
    await pg.mouse.move( bx[ "x" ] + 2, bx[ "y" ] + 2 )
  await RandomPause( )
  await pg.type( sel, txt, delay = RandomInt( 80, 150 ) )
  await RandomPause( )


async def Main( ) -> dict[str, str]:
  load_dotenv( )
  hdless = os.getenv( "HEADLESS", "false" ).lower( ) == "true"
  prxSrv = os.getenv( "HTTP_PROXY" )
  if prxSrv:
    logger.info( "proxy configured" )
  ua = UserAgent( ).random
  vport = { "width": RandomInt( 1280, 1920 ), "height": RandomInt( 720, 1080 ) }
  tzid = random.choice( TIMEZONES )
  loc = random.choice( LOCALES )
  hwc = RandomInt( 4, 16 )
  logger.info( "launching browser" )
  async with async_playwright( ) as pw:
    brw = await pw.chromium.launch( headless = hdless, slow_mo = RandomInt( 20, 60 ), args = [ "--disable-blink-features=AutomationControlled" ] )
    ctx = await brw.new_context( user_agent = ua, locale = loc, timezone_id = tzid, viewport = vport, proxy = { "server": prxSrv } if prxSrv else None, permissions = [ "clipboard-read", "clipboard-write" ] )
    await ctx.add_init_script( f"Object.defineProperty(navigator, 'hardwareConcurrency', {{get: () => {hwc}}});" )
    pg = await ctx.new_page( )
    await Stealthify( pg )
    theirpg = None
    try:
      logger.info( "[1] Open tempmail1.com/delete" )
      await pg.goto( "https://www.tempmail1.com/delete", timeout = TIMEOUT_MS )
      await RandomPause( 1000, 2000 )
      logger.info( "[2] Copy email" )
      await Click( pg, 'button[data-clipboard-target="#trsh_mail"]' )
      eml: str = await pg.evaluate( "navigator.clipboard.readText()" )
      if not EMAIL_REGEX.match( eml ):
        raise ValueError( "invalid email copied" )
      logger.info( f"[email] {eml}" )
      await RandomPause( 500, 1000 )
      logger.info( "[3] Open TheirStack landing page" )
      theirpg = await ctx.new_page( )
      await Stealthify( theirpg )
      try:
        await theirpg.goto( "https://theirstack.com/en", timeout = TIMEOUT_MS )
      except Exception as navErr:
        logger.warning( f"TheirStack sayfasına gitme hatası: {navErr}" )
        raise navErr
      await RandomPause( 1000, 2000 )
      logger.info( "[4] Click sign up for free" )
      await Click( theirpg, 'a[href="https://app.theirstack.com/signup"]' )
      logger.info( "[5] Fill first name" )
      fk = Faker( )
      fname = fk.first_name( )
      await HoverAndType( theirpg, '#sign_up_sign_in_credentials_p_first_name', fname )
      logger.info( "[6] Fill last name" )
      lname = fk.last_name( )
      await HoverAndType( theirpg, '#sign_up_sign_in_credentials_p_last_name', lname )
      logger.info( "[7] Fill email" )
      await HoverAndType( theirpg, '#sign_up_sign_in_credentials_p_email', eml )
      logger.info( "[8] Click sign up" )
      await Click( theirpg, 'button[type="submit"].kinde-button-variant-primary' )
    except Exception as exc:
      await SaveScreenshot( pg, "failure-signup" )
      logger.error( f"[signup error] {exc}" )
      try:
        await brw.close( )
      except:
        pass
      raise exc
    try:
      logger.info( "[9] Switch to tempmail tab and refresh inbox" )
      await pg.bring_to_front( )
      await Click( pg, 'a.btn.btn-1' )
      logger.info( "[10] Wait for verification email" )
      await asyncio.sleep( 6 )
      await pg.reload( )
      await pg.wait_for_selector( 'a.sender_email:has-text("TheirStack")', timeout = 90_000 )
      await Click( pg, 'a.view_email' )
      frameElem = await pg.wait_for_selector( "iframe", timeout = TIMEOUT_MS )
      mailFrm = await frameElem.content_frame( )
      await WaitVisible( mailFrm, '[data-testid="email-confirmation-code"]' )
      rawHtml = await mailFrm.inner_text( '[data-testid="email-confirmation-code"]' )
      mtch = OTP_REGEX.search( rawHtml )
      if not mtch:
        raise TimeoutError( "OTP code not found in email content" )
      cde = mtch.group( 0 )
      logger.info( f"[otp] {cde}" )
      await theirpg.bring_to_front( )
      logger.info( "[14] Enter OTP code" )
      await HoverAndType( theirpg, '#otp_code_p_confirmation_code', cde )
      await Click( theirpg, 'button:has(span[data-kinde-button-text="true"]:has-text("Continue"))' )
      await theirpg.wait_for_url( re.compile( r"https://app\.theirstack\.com/home" ), timeout = TIMEOUT_MS )
      await asyncio.sleep( 4 )
    except PlaywrightTimeoutError as e:
      await SaveScreenshot( pg, "failure-otp-timeout" )
      logger.error( f"[otp timeout] {e}" )
      try:
        await brw.close( )
      except:
        pass
      raise e
    except PWError as e:
      await SaveScreenshot( pg, "failure-otp-pwerror" )
      logger.error( f"[otp playwright error] {e}" )
      try:
        await brw.close( )
      except:
        pass
      raise e
    except Exception as exc:
      await SaveScreenshot( pg, "failure-otp" )
      logger.error( f"[otp error] {exc}" )
      try:
        await brw.close( )
      except:
        pass
      raise exc
    try:
      logger.info( "[15] Go to API key page" )
      await theirpg.goto( "https://app.theirstack.com/settings/api-key", timeout = TIMEOUT_MS )
      await RandomPause( 1000, 2000 )
      logger.info( "[16] Refresh API key" )
      await Click( theirpg, 'button:has(svg.lucide-refresh-ccw)' )
      await asyncio.sleep( 4 )
      logger.info( "[17] Copy API key" )
      await Click( theirpg, 'button:has(svg.lucide-copy)' )
      await asyncio.sleep( 4 )
      apikey: str = await theirpg.evaluate( "navigator.clipboard.readText()" )
      if not apikey or len( apikey ) < 10:
        raise ValueError( "API key copy failed" )
      logger.info( f"[api_key] {apikey}" )
    except Exception as exc:
      await SaveScreenshot( theirpg, "failure-apikey" )
      logger.error( f"[apikey error] {exc}" )
      try:
        await brw.close( )
      except:
        pass
      raise exc
    result = { "email": eml, "api_key": apikey }
    try:
      MONGODB_URI = os.getenv( "MONGODB_URI", "mongodb://localhost:27017" )
      MONGODB_DB = os.getenv( "MONGODB_DB", "jobscrapper" )
      tdb = dbManager( MONGODB_URI, MONGODB_DB )
      doc = { "key": apikey, "token_limit": 200, "tokens_used": 0, "created_at": datetime.datetime.utcnow() }
      await tdb.InsertOne( "jobscraper", doc )
      logger.info( "[db] API key başarıyla veritabanına kaydedildi." )
    except Exception as e:
      logger.error( f"[db error] API key veritabanına kaydedilemedi: {e}" )
    print( json.dumps( result, ensure_ascii = False ), file = sys.stdout )
    sys.stdout.flush( )
    await brw.close( )
    return result


async def MainWithProxyRetry( ) -> dict[str, str]:
  for att in range( 1, MAX_PROXY_ATTEMPTS + 1 ):
    try:
      logging.info( f"[{att}. deneme] Scraping başlatılıyor..." )
      return await Main( )
    except Exception as e:
      errMsg = str( e ).lower( )
      prxErrKw = [ 'timeout', 'connection', 'tunnel', 'proxy', 'network', 'net::err_connection_refused', 'net::err_connection_timed_out', 'net::err_connection_reset', 'net::err_connection_aborted', 'net::err_name_not_resolved', 'net::err_address_unreachable', 'page.goto: timeout', 'navigation timeout', 'timeout 20000ms exceeded', 'timeout 60000ms exceeded', 'timeout exceeded', 'net::err_connection_closed' ]
      if any( kw in errMsg for kw in prxErrKw ):
        logging.warning( f"[{att}. deneme] Proxy hatası tespit edildi: {e}" )
        try:
          prx = await GetAndDeleteSLinkedinProxy( )
          if prx:
            logging.info( f"Yeni proxy test ediliyor: {prx}" )
            if await TestProxyWithTheirStack( prx ):
              os.environ[ "HTTP_PROXY" ] = prx
              logging.info( f"Yeni proxy başarılı ve ayarlandı: {prx}" )
              continue
            else:
              logging.warning( f"Yeni proxy test başarısız: {prx}" )
              continue
          else:
            logging.error( "Denenecek başka proxy yok." )
            raise
        except Exception as dbErr:
          logging.error( f"Proxy alma hatası: {dbErr}" )
          logging.warning( "Proxy olmadan çalıştırılıyor." )
          if( "HTTP_PROXY" in os.environ ):
            del os.environ[ "HTTP_PROXY" ]
          continue
      else:
        logging.error( f"[{att}. deneme] Proxy dışı hata: {e}" )
        raise
  logging.error( f"{MAX_PROXY_ATTEMPTS} denemede de başarısız oldu." )
  raise RuntimeError( "Tüm proxy denemeleri başarısız" )

if __name__ == "__main__":
  asyncio.run( MainWithProxyRetry( ) )
