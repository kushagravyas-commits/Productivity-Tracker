import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
from dotenv import load_dotenv

# Load .env — check PyInstaller bundle dir first, then normal paths
if getattr(sys, "frozen", False):
    env_path = Path(sys._MEIPASS) / ".env"
else:
    env_path = Path(__file__).parent.parent / ".env"

if env_path.exists():
    load_dotenv(env_path)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "tracker")

class MongoDB:
    client: AsyncIOMotorClient = None
    db = None

    @classmethod
    async def connect(cls):
        if cls.client is None:
            cls.client = AsyncIOMotorClient(
                MONGODB_URI,
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=15000,
                maxPoolSize=50,
            )
            cls.db = cls.client[MONGODB_DB]
            masked_uri = MONGODB_URI.split("@")[-1] if "@" in MONGODB_URI else MONGODB_URI
            print(f"Connected to MongoDB: {MONGODB_DB} (Server: {masked_uri})")

    @classmethod
    async def ensure_indexes(cls):
        """Create indexes for fast queries on all collections.
        Primary query pattern: {device_id: X, started_at/captured_at: {$gte, $lte}}
        The compound index covers both filtered and unfiltered date-range queries."""
        try:
            # Users
            await cls.db.users.create_index("email", unique=True)
            await cls.db.users.create_index("registration_token")

            # Devices
            await cls.db.devices.create_index("machine_guid", unique=True)
            await cls.db.devices.create_index("email")

            # Events — compound index for (device_id + date range) queries
            await cls.db.events.create_index([("device_id", 1), ("started_at", 1)])

            # Idle periods
            await cls.db.idle_periods.create_index([("device_id", 1), ("started_at", 1)])

            # Editor context
            await cls.db.editor_context.create_index([("device_id", 1), ("captured_at", 1)])

            # Browser context
            await cls.db.browser_context.create_index([("device_id", 1), ("captured_at", 1)])

            # App context
            await cls.db.app_context.create_index([("device_id", 1), ("captured_at", 1)])

            print("MongoDB indexes ensured.")
        except Exception as e:
            print(f"Warning: Could not create indexes: {e}")

    @classmethod
    async def close(cls):
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.db = None
            print("MongoDB connection closed")

mongodb = MongoDB()
