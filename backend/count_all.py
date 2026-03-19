import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

async def count_all():
    load_dotenv("x:\\Varahe Analtics\\Productivity-Tracker\\backend\\.env")
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "tracker")
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    collections = await db.list_collection_names()
    for coll in collections:
        count = await db[coll].count_documents({})
        print(f"Collection {coll}: {count} documents")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(count_all())
