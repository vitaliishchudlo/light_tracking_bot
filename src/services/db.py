from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
import os
import logging

logger = logging.getLogger(__name__)

# Sync client for subscriptions (used in handlers)
mongodb_url = os.getenv('MONGODB_URL', 'mongodb://localhost:27017/')
sync_client = MongoClient(mongodb_url)
sync_db = sync_client['light_tracker_db']
subscriptions_collection = sync_db['subscriptions']

# Create indexes for subscriptions (with background=True to avoid blocking)
try:
    subscriptions_collection.create_index([("id_telegram", 1), ("queue", 1)], unique=True, background=True)
except Exception:
    pass  # Index might already exist
try:
    subscriptions_collection.create_index([("id_telegram", 1), ("group_number", 1)], background=True)
except Exception:
    pass  # Index might already exist

# Async client for background tasks
async_client: AsyncIOMotorClient = None
async_db = None

# Collections
schedules_collection = None  # Will store last known schedule state
notifications_collection = None  # Will store notification history


def get_schedules_collection():
    """Get schedules collection - returns None if not initialized"""
    return schedules_collection


async def init_db():
    """Initialize async MongoDB connection"""
    global async_client, async_db, schedules_collection, notifications_collection
    
    try:
        logger.info(f"Connecting to MongoDB at {mongodb_url}")
        async_client = AsyncIOMotorClient(mongodb_url, serverSelectionTimeoutMS=5000)
        
        # Test connection
        await async_client.admin.command('ping')
        logger.info("MongoDB connection successful")
        
        async_db = async_client['light_tracker_db']
        
        schedules_collection = async_db['schedules']
        notifications_collection = async_db['notifications']
        
        # Create indexes
        await schedules_collection.create_index([("queue", 1)], unique=True)
        logger.info("MongoDB initialized successfully - schedules_collection ready")
    except Exception as e:
        logger.error(f"Failed to initialize MongoDB: {e}")
        raise


async def close_db():
    """Close async MongoDB connection"""
    global async_client
    if async_client:
        async_client.close()
    if sync_client:
        sync_client.close()

