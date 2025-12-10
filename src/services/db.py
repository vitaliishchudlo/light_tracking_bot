from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
import os
import logging

logger = logging.getLogger(__name__)

# Sync client for subscriptions (used in handlers)
mongodb_url = os.getenv('MONGODB_URL', 'mongodb://localhost:27017/')
sync_client = None
sync_db = None
subscriptions_collection = None
user_settings_collection = None


def _ensure_sync_connection():
    """Ensure sync MongoDB connection is active, reconnect if needed"""
    global sync_client, sync_db, subscriptions_collection, user_settings_collection

    try:
        # Check if client exists and is connected
        if sync_client is None:
            raise ConnectionFailure("Client not initialized")

        # Try to ping the server
        sync_client.admin.command('ping')
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError, AttributeError) as e:
        logger.warning(f"Sync MongoDB connection lost: {e}. Reconnecting...")
        try:
            # Close old connection if exists
            if sync_client:
                try:
                    sync_client.close()
                except:
                    pass

            # Create new connection
            sync_client = MongoClient(
                mongodb_url,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=5000,
                maxPoolSize=10,
                retryWrites=True
            )
            sync_db = sync_client['light_tracker_db']
            subscriptions_collection = sync_db['subscriptions']
            user_settings_collection = sync_db['user_settings']

            # Recreate indexes
            try:
                subscriptions_collection.create_index([("id_telegram", 1), ("queue", 1)], unique=True, background=True)
            except Exception:
                pass
            try:
                subscriptions_collection.create_index([("id_telegram", 1), ("group_number", 1)], background=True)
            except Exception:
                pass
            try:
                user_settings_collection.create_index([("id_telegram", 1)], unique=True, background=True)
            except Exception:
                pass

            logger.info("Sync MongoDB connection reestablished")
            return True
        except Exception as e:
            logger.error(f"Failed to reconnect sync MongoDB: {e}")
            return False


def _init_sync_client():
    """Initialize sync MongoDB client"""
    global sync_client, sync_db, subscriptions_collection, user_settings_collection

    if sync_client is None:
        sync_client = MongoClient(
            mongodb_url,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
            maxPoolSize=10,
            retryWrites=True
        )
        sync_db = sync_client['light_tracker_db']
        subscriptions_collection = sync_db['subscriptions']
        user_settings_collection = sync_db['user_settings']

        # Create indexes for subscriptions (with background=True to avoid blocking)
        try:
            subscriptions_collection.create_index([("id_telegram", 1), ("queue", 1)], unique=True, background=True)
        except Exception:
            pass  # Index might already exist
        try:
            subscriptions_collection.create_index([("id_telegram", 1), ("group_number", 1)], background=True)
        except Exception:
            pass  # Index might already exist
        # Create index for user settings
        try:
            user_settings_collection.create_index([("id_telegram", 1)], unique=True, background=True)
        except Exception:
            pass  # Index might already exist


# Initialize sync client on module import
_init_sync_client()

# Async client for background tasks
async_client: AsyncIOMotorClient = None
async_db = None

# Collections
schedules_collection = None  # Will store last known schedule state
notifications_collection = None  # Will store notification history


def get_schedules_collection():
    """Get schedules collection - returns None if not initialized"""
    return schedules_collection


def get_subscriptions_collection():
    """Get subscriptions collection with connection check"""
    if not _ensure_sync_connection():
        raise ConnectionFailure("Cannot connect to MongoDB")
    return subscriptions_collection


def get_user_settings_collection():
    """Get user settings collection with connection check"""
    if not _ensure_sync_connection():
        raise ConnectionFailure("Cannot connect to MongoDB")
    return user_settings_collection


async def ensure_async_connection():
    """Ensure async MongoDB connection is active, reconnect if needed"""
    global async_client, async_db, schedules_collection, notifications_collection

    try:
        # Check if client exists and is connected
        if async_client is None:
            raise ConnectionFailure("Client not initialized")

        # Try to ping the server
        await async_client.admin.command('ping')
        return True
    except (ConnectionFailure, ServerSelectionTimeoutError, AttributeError) as e:
        logger.warning(f"Async MongoDB connection lost: {e}. Reconnecting...")
        try:
            # Close old connection if exists
            if async_client:
                try:
                    async_client.close()
                except:
                    pass

            # Create new connection
            async_client = AsyncIOMotorClient(
                mongodb_url,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                socketTimeoutMS=5000,
                maxPoolSize=10,
                retryWrites=True
            )

            # Test connection
            await async_client.admin.command('ping')

            async_db = async_client['light_tracker_db']
            schedules_collection = async_db['schedules']
            notifications_collection = async_db['notifications']

            # Recreate indexes
            await schedules_collection.create_index([("queue", 1)], unique=True)
            await schedules_collection.create_index([("queue", 1), ("shownDates.date", 1)])

            logger.info("Async MongoDB connection reestablished")
            return True
        except Exception as e:
            logger.error(f"Failed to reconnect async MongoDB: {e}")
            return False


async def init_db():
    """Initialize async MongoDB connection"""
    global async_client, async_db, schedules_collection, notifications_collection
    
    try:
        logger.info(f"Connecting to MongoDB at {mongodb_url}")
        async_client = AsyncIOMotorClient(
            mongodb_url,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
            maxPoolSize=10,
            retryWrites=True
        )
        
        # Test connection
        await async_client.admin.command('ping')
        logger.info("MongoDB connection successful")
        
        async_db = async_client['light_tracker_db']
        
        schedules_collection = async_db['schedules']
        notifications_collection = async_db['notifications']
        
        # Create indexes
        await schedules_collection.create_index([("queue", 1)], unique=True)
        # Index for tracking shown dates
        await schedules_collection.create_index([("queue", 1), ("shownDates.date", 1)])
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

