import re
import json
import logging


def SafeExtractJsonFromResponse(response_text: str):
  try:
    parsed = json.loads(response_text)
    logging.info("json.loads ile doğrudan ayrıştırıldı.")
    return parsed
  except Exception as exc:
    logging.info(f"Doğrudan json.loads başarısız: {exc}")

  html_match = re.search(r'<p[^>]*>(\{.*?\})</p>', response_text, re.DOTALL)
  if not html_match:
    html_match = re.search(r'<pre[^>]*>(\{.*?\})</pre>', response_text, re.DOTALL)
  if html_match:
    json_str = html_match.group(1)
    try:
      return json.loads(json_str)
    except Exception as exc:
      logging.error(f"HTML içinden JSON ayrıştırılamadı: {exc}\nHam: {json_str[:200]}")

  if '```json' in response_text:
    response_text = response_text.split('```json', 1)[-1]
  if '```' in response_text:
    response_text = response_text.split('```', 1)[0]

  match = re.search(r'({.*})', response_text, re.DOTALL)
  if match:
    json_str = match.group(1)
    try:
      return json.loads(json_str)
    except Exception as exc:
      logging.error(
        f"JSON ayrıştırılamadı: {exc}\nHam: {json_str[:200]}\nTüm string: {json_str}"
      )
      return None
  logging.error(
    "Yanıtta JSON bulunamadı! Ham: %s\nTüm string: %s", response_text[:200], response_text
  )
  return None 