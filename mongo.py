from pymongo import MongoClient
from collections import Counter

# MongoDB bağlantısı
client = MongoClient("mongodb://localhost:27017/")  # kendi bağlantı stringini kullan
db = client["jobscrapper"]  # veritabanı adı
collection = db["raw_jobs"]  # koleksiyon adı

# Tüm _id değerlerini çek
ids = collection.find({}, {"_id": 1})
id_list = [doc["_id"] for doc in ids]

# Aynı olanları bul
counter = Counter(id_list)
duplicates = [item for item, count in counter.items() if count > 1]

if duplicates:
    print("Aynı olan _id'ler bulundu:")
    for dup in duplicates:
        print(dup)
else:
    print("Tüm _id'ler benzersiz.")
