import os
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, date
from dotenv import load_dotenv

async def inspect_data():
    load_dotenv("x:\\Varahe Analtics\\Productivity-Tracker\\backend\\.env")
    uri = os.getenv("MONGODB_URI")
    db_name = os.getenv("MONGODB_DB", "tracker")
    client = AsyncIOMotorClient(uri)
    db = client[db_name]
    
    # Check browser_context for today
    today = date(2026, 3, 19)
    start_dt = datetime.combine(today, datetime.min.time())
    end_dt = datetime.combine(today, datetime.max.time())
    
    query = {"captured_at": {"$gte": start_dt, "$lte": end_dt}}
    print(f"Query: {query}")
    
    count = await db.browser_context.count_documents(query)
    print(f"Count for browser_context today: {count}")
    
    if count > 0:
        docs = await db.browser_context.find(query).limit(5).to_list(None)
        for doc in docs:
            print(f"Doc ID: {doc['_id']}")
            print(f"Fields: {list(doc.keys())}")
            for k, v in doc.items():
                if k != '_id':
                    print(f"  {k}: {type(v)} = {v}")
            print("-" * 20)
    
    # Check editor_context for today
    count_editor = await db.editor_context.count_documents(query)
    print(f"Count for editor_context today: {count_editor}")

    client.close()

if __name__ == "__main__":
    asyncio.run(inspect_data())
