import os
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()  # loads .env from current folder

uri = os.getenv("MONGO_URI")
db_name = os.getenv("MONGO_DB", "spaceweather")

if not uri:
    raise SystemExit("MONGO_URI is empty. Put it in backend\\.env")

client = MongoClient(uri)
db = client[db_name]

print(" Connected to DB:", db.name)
print("Collections:", db.list_collection_names())
