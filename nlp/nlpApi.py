import asyncio
import os
import aiohttp
import json
import time
import logging
from dotenv import load_dotenv

from dbprocess.db_manager import dbManager

load_dotenv()
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "jobscrapper")
dbmanager = dbManager(MONGODB_URI, MONGODB_DB)

async def GenerateLatexCv(prompt: str, retries: int = 3, retry_delay: float = 1.0) -> str:
  api_key = os.getenv("MISTRAL_API_KEY")
  if not api_key:
    raise EnvironmentError("MISTRAL_API_KEY .env dosyasında bulunamadı!")
  url = "https://api.mistral.ai/v1/chat/completions"
  headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {api_key}"
  }
  payload = {
    "model": "codestral-2405",
    "temperature": 0.1,
    "max_tokens": 32768,
    "messages": [
      {"role": "system", "content": "You are an ATS Resume Optimizer AI.\nOutput ONLY valid LaTeX code."},
      {"role": "user", "content": prompt}
    ]
  }

  attempt = 0
  while attempt <= retries:
    try:
      async with aiohttp.ClientSession() as session:
        async with session.post(url, headers = headers, json = payload) as response:
          if response.status == 200:
            data = await response.json()
            latex_result = data['choices'][0]['message']['content']
            return latex_result
          else:
            logging.warning(f"Yanıt {response.status}: {await response.text()}")
    except aiohttp.ClientError as exc:
      logging.error(f"İstek hatası: {exc}")
    attempt += 1
    if attempt <= retries:
      logging.info(f"Tekrar deneniyor ({attempt}/{retries})...")
      await asyncio.sleep(retry_delay)
  raise Exception("API yanıtı alınamadı veya tekrar limiti aşıldı.")

async def ExtractJobData(job_description: str, retries: int = 5, retry_delay: float = 1.0) -> dict:
  api_key = os.getenv("MISTRAL_API_KEY")
  if not api_key:
    raise EnvironmentError("MISTRAL_API_KEY .env dosyasında bulunamadı!")
  url = "https://api.mistral.ai/v1/chat/completions"
  headers = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "Authorization": f"Bearer {api_key}"
  }
  payload = {
    "model": "codestral-2405",
    "temperature": 0.1,
    "max_tokens": 32768,
    "response_format": {"type": "json_object"},
    "messages": [
      {
        "role": "system",
        "content": (
          "You are a senior HR-data extractor.\n\n"
          "—TASK—\n"
          "Extract structured data from ANY job posting text and output only a single-line, minified, valid JSON object "
          "that matches this exact schema (no extra keys, no comments):\n"
          '{"company_name":null,"job_title":"","department":null,"employment_type":null,"location":null,'
          '"summary":null,"keywords":[],"responsibilities":[],'
          '"requirements":{"education":[],"experience_years_min":null,"experience_years_pref":null,'
          '"skills_mandatory":[],"skills_optional":[],"certifications":[],"languages":[],"other_requirements":[]},'
          '"benefits":[],"application":{"apply_url":null,"contact_email":null,"deadline":null}}\n\n'
          "—RULES—\n"
          "1. Preserve the key order of the schema.\n"
          "2. Use null where information is missing, never empty strings except for job_title.\n"
          "3. Use empty arrays [] for list-type fields with no data.\n"
          "4. Output must be a single line (no linebreaks, no indentation).\n"
          "5. Do NOT wrap the JSON in markdown fences or add any extra text.\n"
          "6. Normalize dates to ISO 8601 (\"YYYY-MM-DD\") if deadline is present; otherwise keep as null.\n"
          "7. Translate field values to English except the original summary and location.\n"
          "8. Trim whitespace inside strings; do not add trailing commas.\n"
          "9. If the input contains multiple languages, prioritise English terms; keep Turkish only when no English equivalent exists.\n"
          "10. Items appearing under headings such as \"Preferred\", \"Tercih edilen\", or preceded by words like \"Tercihen\" MUST be captured in skills_optional.\n"
          "11. Split comma- or slash-separated skill lists into individual elements.\n"
          "12. If a skill is both mandatory and preferred, list it in skills_mandatory and ALSO in skills_optional only if explicitly in preferred section.\n"
          "13. Use canonical English technology names (e.g., TypeScript, PrimeNG, Angular).\n"
          "14. **keywords** must be an array of up to 15 distinct, lower-case English keywords or key phrases that best represent the role (e.g., technologies, methodologies, domain terms).  \n    • Derive them from any section of the posting.  \n    • Remove duplicates and synonyms; keep concise.  \n    • Maintain original casing only for proper technology names (e.g., \"Spring Boot\").  \n    • Avoid generic words like \"team\", \"company\", \"work\".  \n"
          "15. Output ALL fields in English, even if the original job posting is in Turkish. Only the summary and location fields may remain in Turkish if no English equivalent exists.\n"
          "\nFailure to comply with any rule is a critical error."
        )
      },
      {
        "role": "user",
        "content": job_description
      }
    ]
  }
  attempt = 0
  while attempt <= retries:
    try:
      async with aiohttp.ClientSession() as session:
        async with session.post(url, headers = headers, json = payload) as response:
          if response.status == 200:
            data = await response.json()
            extracted_content = data['choices'][0]['message']['content']
            structured_json = json.loads(extracted_content)
            return structured_json
          else:
            logging.warning(f"Yanıt {response.status}: {await response.text()}")
    except aiohttp.ClientError as exc:
      logging.error(f"İstek hatası: {exc}")
    except (KeyError, json.JSONDecodeError) as exc:
      logging.error(f"Yanıt ayrıştırılamadı: {exc}")
    attempt += 1
    if attempt <= retries:
      logging.info(f"Tekrar deneniyor ({attempt}/{retries})...")
      await asyncio.sleep(retry_delay)
  raise Exception("API yanıtı alınamadı veya tekrar limiti aşıldı.")

async def SaveToDb(document: dict):
  try:
    await dbmanager.InsertOne("JobAnalysis", document)
    print("Analiz JobAnalysis koleksiyonuna kaydedildi.")
  except Exception as db_exc:
    print(f"Analiz veritabanına kaydedilemedi: {db_exc}")
    logging.error(f"Veritabanı hatası: {db_exc}")

def Main():
  import sys
  import argparse
  parser = argparse.ArgumentParser(description = "Mistral API ile iş ilanı metninden yapısal veri çıkar.")
  parser.add_argument('--job-text', type = str, help = 'İş ilanı metni (string)')
  parser.add_argument('--job-file', type = str, help = 'İş ilanı metni dosya yolu')
  args = parser.parse_args()

  if args.job_text:
    job_desc = args.job_text
  elif args.job_file:
    try:
      with open(args.job_file, 'r', encoding = 'utf-8') as f:
        job_desc = f.read()
    except Exception as exc:
      print(f"Dosya okunamadı: {exc}")
      sys.exit(1)
  else:
    print("Lütfen --job-text veya --job-file argümanı verin.")
    sys.exit(1)

  async def run():
    try:
      result = await ExtractJobData(job_desc)
      print(json.dumps(result, ensure_ascii = False, indent = 2))
      await SaveToDb(result)
    except Exception as exc:
      print(f"Hata: {exc}")
      logging.error(f"Ana çalışma hatası: {exc}")

  asyncio.run(run())

if __name__ == "__main__":
  Main() 