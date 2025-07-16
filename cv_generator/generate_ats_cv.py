import asyncio
import os
from dbprocess.db_manager import dbManager
from nlp.mistral_websocket import mistralWebSocketClient
from nlp.nlpApi import ExtractJobData, GenerateLatexCv
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "jobscrapper")

async def GenerateAtsCv(rawCV: str, jbId: int, tgtLang: str, hpth: str = "heb.txt"):
  db = dbManager(MONGODB_URI, MONGODB_DB)

  jbDc = await db.FindOne(
    "job_analysis_results",
    { "job_id": jbId }
  )

  if( not jbDc or "analysis_result" not in jbDc ):
    raise ValueError( f"job_id={jbId} için analiz kaydı bulunamadı!" )  

  anlys = jbDc[ "analysis_result" ]

  jbTtl = anlys.get("job_title", "")
  smry = anlys.get("summary", "")
  kywds = anlys.get("keywords", [])
  rsps = anlys.get("responsibilities", [])
  rqrmnts = anlys.get("requirements", {})
  bnfts = anlys.get("benefits", [])

  systemPrompt = (
    "Sen kıdemli bir “ATS Resume Optimizer” yapay zekâsısın.\n"
    "Girdi JSON’unda üç alan bulunur:\n"
    "* \"analysis_result\"  → İLAN ANALİZİ\n"
    "* \"raw_cv\"           → ADAYIN CV’Sİ\n"
    "* \"target_lang\"      → TR veya EN\n\n"
    "**AMAÇ**\n"
    "• CV’yi, ilanın gerektirdiği beceri ve sorumlulukları açıkça vurgulayacak şekilde yeniden düzenle.\n"
    "• Çıktı yalnızca geçerli, **ATS uyumlu, derlenebilir düz LaTeX CV kodu** olmalı. **Başka hiçbir metin, JSON, markdown çiti veya yorum üretme.**\n"
    "• **Kesinlikle yalan bilgi ekleme.** Sadece adayın CV’sinde zaten bulunan becerileri veya bunların **doğrudan eş, üst veya alt kavramlarını** kullanabilirsin.\n"
    "• ATS botlarının okumasını zorlaştıracak hiçbir tasarım unsuru (renk, tablo, çizgi, ikon, grafik vb.) kullanma.\n"
    "• Çıktıda yalnızca sade LaTeX paketlerini (ör. `article`, `geometry`, `enumitem`) kullan. `xcolor`, `fancyhdr`, `tabularx`, `tikz` gibi görsellik paketleri yasaktır.\n"
    "**YAPISAL KURALLAR**\n"
    "• Başlıklar şu sırayla ve İngilizce/Türkçe çevirisine uygun olmalı: \n"
    "  1. İletişim Bilgileri (Contact Information)\n"
    "  2. Özet (Summary)\n"
    "  3. Yetenekler (Skills)\n"
    "  4. Çalışma Deneyimi (Work Experience)\n"
    "  5. Eğitim (Education)\n"
    "• Eğer \"target_lang\":\"TR\" ise LaTeX içeriğinin tamamı Türkçe olacak; özel isimler (ör. şirket adları) hariç İngilizce kullanma.\n"
    "• Eğer \"target_lang\":\"EN\" ise LaTeX içeriği yalnızca İngilizce olacak; özel isimler hariç Türkçe kullanma.\n"
    "**ADIMLAR**\n"
    "1 **İlanı Ayrıştır**\n"
    "   - `requirements` ve `analysis_result` içindeki tüm anahtar terimleri topla ve normalize et.\n"
    "2 **CV’yi Ayrıştır**\n"
    "   - Standart bölümleri (Özet, Deneyim, Eğitim, Yetenekler vb.) tespit et ve normalize et.\n"
    "3 **Eşleme & Genişletme**\n"
    "   - CV’deki terimler için eş/üst/alt kavram haritası uygula.\n"
    "   - İlan terimlerinden sadece CV’de karşılığı olanları veya kavramsal eşleşenleri ekle.\n"
    "4 **LaTeX Üretimi**\n"
    "   - Maksimum iki sayfa olacak şekilde gereksiz detayları çıkar.\n"
    "   - Sadece dolu bölümlerle sade, ATS uyumlu bir LaTeX şablonu üret.\n"
    "5 **SONUÇ**\n"
    "   - Yalnızca LaTeX kodunu TEK BLOK olarak döndür; başında veya sonunda hiçbir ekstra karakter, boş satır veya yorum olmasın.\n"
  )

  userPrompt = {
    "analysis_result": {
      "job_title": jbTtl,
      "summary": smry,
      "keywords": kywds,
      "responsibilities": rsps,
      "requirements": rqrmnts,
      "benefits": bnfts
    },
    "raw_cv": rawCV,
    "target_lang": tgtLang
  }
  userPromptStr = json.dumps(userPrompt, ensure_ascii=False)
  fullPrompt = f"SİSTEM:\n{systemPrompt}\n\nKULLANICI:\n{userPromptStr}"

  apiSuccess = False
  latexCV = None

  for attmpt in range(3):
    try:
      logger.info(f"[API] Mistral API denemesi {attmpt + 1}/3...")
      rawResult = await GenerateLatexCv(fullPrompt, retries=0)  
      try:
        cleanedResult = CleanLatexOutput(rawResult)  
        latexCV = cleanedResult
        apiSuccess = True
        logger.info("[API] Başarılı ve temizlenmiş LaTeX dökümanı alındı.")
        break
      except ValueError as ve:  
        logger.warning(f"[API] Geçersiz LaTeX çıktı: {ve}")
    except Exception as e:
      logger.warning(f"[API] Hata: {e}")

    await asyncio.sleep(1)  

  if not apiSuccess:
    logger.info("[BROWSER] API başarısız, tarayıcı ile Mistral'a geçiliyor...")
    client = mistralWebSocketClient(use_browser = True)
    await client.connect()
    latexCV = await client.send_message(fullPrompt)
    await client.disconnect()

  with open(hpth, "w", encoding="utf-8") as f:
    f.write(latexCV)  
  logger.info(f"LaTeX CV {hpth} dosyasına kaydedildi.")
  return latexCV


def CleanLatexOutput(rawOutput: str) -> str:
  cleaned = rawOutput.strip()  
  if( cleaned.startswith("```") and cleaned.endswith("```") ):
    cleaned = cleaned.strip("`").strip()  
  lines = cleaned.splitlines()
  for i, line in enumerate(lines):
    if ( line.strip().startswith("\\documentclass") ):
      return "\n".join(lines[i:]).strip()  
  raise ValueError("Geçerli bir LaTeX dökümanı bulunamadı.")


def Main():
  import argparse
  parser = argparse.ArgumentParser(description = "ATS Resume Optimizer")
  parser.add_argument("--raw-cv", type = str, required = True, help = "Ham CV metni")
  parser.add_argument("--job-id", type = int, required = True, help = "İş ilanı ID")
  parser.add_argument("--target-lang", type = str, choices = ["TR", "EN"], required = True, help = "Hedef dil (TR veya EN)")
  parser.add_argument("--heb-path", type = str, default = "heb.txt", help = "Çıktı dosyası")
  args = parser.parse_args()
  asyncio.run(GenerateAtsCv(args.raw_cv, args.job_id, args.target_lang, args.heb_path))

if( __name__ == "__main__" ):
  Main() 