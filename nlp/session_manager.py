import json
import requests
import re
from typing import Optional, Dict
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class mistralSessionManager:
  def __init__(self):
    self.session = requests.Session()
    self.access_token = None
    self.session_token = None
    self.user_agent = (
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    self.base_url = "https://chat.openai.com"
    self.api_url = "https://chat.openai.com/backend-api"
    self.session.headers.update({
      "User-Agent": self.user_agent,
      "Accept": "application/json, text/plain, */*",
      "Accept-Language": "en-US,en;q=0.9",
      "Accept-Encoding": "gzip, deflate, br",
      "DNT": "1",
      "Connection": "keep-alive",
      "Upgrade-Insecure-Requests": "1",
    })

  def ExtractTokensFromCookies(self, cookie_string: str) -> Dict[str, str]:
    tokens = {}
    cookies = {}
    for cookie in cookie_string.split(';'):
      if '=' in cookie:
        name, value = cookie.strip().split('=', 1)
        cookies[name] = value
    if '__Secure-next-auth.session-token' in cookies:
      tokens['session_token'] = cookies['__Secure-next-auth.session-token']
    if '__Secure-next-auth.csrf-token' in cookies:
      tokens['csrf_token'] = cookies['__Secure-next-auth.csrf-token']
    return tokens

  def ExtractAccessTokenFromBrowser(self, browser_cookies: str) -> Optional[str]:
    try:
      session_token_match = re.search(
        r'__Secure-next-auth\.session-token=([^;]+)', browser_cookies
      )
      if session_token_match:
        session_token = session_token_match.group(1)
        return self._GetAccessTokenFromSession(session_token)
    except Exception as exc:
      logger.error(f"Erişim tokenı çıkarma hatası: {exc}")
    return None

  def _GetAccessTokenFromSession(self, session_token: str) -> Optional[str]:
    try:
      auth_url = f"{self.api_url}/auth/session"
      headers = {
        "Cookie": f"__Secure-next-auth.session-token={session_token}",
        "User-Agent": self.user_agent,
        "Accept": "application/json",
      }
      response = self.session.get(auth_url, headers = headers)
      if response.status_code == 200:
        data = response.json()
        if 'accessToken' in data:
          return data['accessToken']
    except Exception as exc:
      logger.error(f"Session'dan erişim tokenı hatası: {exc}")
    return None

  def GetAccessTokenFromFile(self, file_path: str) -> Optional[str]:
    try:
      with open(file_path, 'r') as f:
        return f.read().strip()
    except Exception as exc:
      logger.error(f"Token dosyası okuma hatası: {exc}")
      return None

  def SaveAccessTokenToFile(self, access_token: str, file_path: str = "mistral_token.txt"):
    try:
      with open(file_path, 'w') as f:
        f.write(access_token)
      logger.info(f"Erişim tokenı {file_path} dosyasına kaydedildi")
    except Exception as exc:
      logger.error(f"Token kaydetme hatası: {exc}")

  def ValidateAccessToken(self, access_token: str) -> bool:
    try:
      user_url = f"{self.api_url}/user"
      headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": self.user_agent,
        "Accept": "application/json",
      }
      response = self.session.get(user_url, headers = headers)
      if response.status_code == 200:
        logger.info("Erişim tokenı geçerli")
        return True
      else:
        logger.warning(f"Erişim tokenı geçersiz: {response.status_code}")
        return False
    except Exception as exc:
      logger.error(f"Token doğrulama hatası: {exc}")
      return False

  def GetUserInfo(self, access_token: str) -> Optional[Dict]:
    try:
      user_url = f"{self.api_url}/user"
      headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": self.user_agent,
        "Accept": "application/json",
      }
      response = self.session.get(user_url, headers = headers)
      if response.status_code == 200:
        return response.json()
      else:
        logger.error(f"Kullanıcı bilgisi alınamadı: {response.status_code}")
        return None
    except Exception as exc:
      logger.error(f"Kullanıcı bilgisi alınamadı: {exc}")
      return None

  def GetConversations(self, access_token: str, limit: int = 20) -> Optional[Dict]:
    try:
      conversations_url = f"{self.api_url}/conversations?limit={limit}"
      headers = {
        "Authorization": f"Bearer {access_token}",
        "User-Agent": self.user_agent,
        "Accept": "application/json",
      }
      response = self.session.get(conversations_url, headers = headers)
      if response.status_code == 200:
        return response.json()
      else:
        logger.error(f"Konuşma listesi alınamadı: {response.status_code}")
        return None
    except Exception as exc:
      logger.error(f"Konuşma listesi alınamadı: {exc}")
      return None

def Main():
  session_manager = mistralSessionManager()
  access_token = session_manager.GetAccessTokenFromFile("mistral_token.txt")
  if access_token:
    if session_manager.ValidateAccessToken(access_token):
      print("Erişim tokenı geçerli!")
      user_info = session_manager.GetUserInfo(access_token)
      if user_info:
        print(f"Kullanıcı: {user_info.get('name', 'Bilinmiyor')}")
        print(f"Email: {user_info.get('email', 'Bilinmiyor')}")
    else:
      print("Erişim tokenı geçersiz!")
  else:
    print("Token dosyası bulunamadı!")
    print("\nTarayıcı çerezlerinizi buraya yapıştırın:")
    browser_cookies = input("Çerez stringi: ")
    if browser_cookies:
      access_token = session_manager.ExtractAccessTokenFromBrowser(browser_cookies)
      if access_token:
        session_manager.SaveAccessTokenToFile(access_token)
        print("Erişim tokenı başarıyla kaydedildi!")
      else:
        print("Erişim tokenı çıkarılamadı!")

if __name__ == "__main__":
  Main() 