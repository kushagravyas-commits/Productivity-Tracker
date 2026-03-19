import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

async def test_mongo():
    load_dotenv("x:\\Varahe Analtics\\Productivity-Tracker\\backend\\.env")
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "tracker")
    print(f"Connecting to {uri} / {db_name}")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=5000)
    try:
        await client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
        db = client[db_name]
        collections = await db.list_collection_names()
        print(f"Collections: {collections}")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_mongo())
