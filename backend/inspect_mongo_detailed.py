import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, date
from dotenv import load_dotenv
import json

async def inspect_data():
    load_dotenv("x:\\Varahe Analtics\\Productivity-Tracker\\backend\\.env")
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "tracker")
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    today = date(2026, 3, 19)
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())
    
    query = {"captured_at": {"$gte": start_dt, "$lte": end_dt}}
    
    docs = await db.browser_context.find(query).limit(5).to_list(None)
    print(f"Found {len(docs)} docs for today")
    for doc in docs:
        print(f"Doc: {doc.get('_id')}")
        for k, v in doc.items():
            print(f"  {k}: {type(v).__name__} = {v}")
        print("-" * 40)
        
    # Also check if any recent docs have a different device_id format
    recent_docs = await db.browser_context.find().sort("captured_at", -1).limit(5).to_list(None)
    print("Most recent 5 docs overall:")
    for doc in recent_docs:
        print(f"  captured_at: {doc.get('captured_at')}, device_id: {doc.get('device_id')}")

    client.close()

if __name__ == "__main__":
    asyncio.run(inspect_data())
