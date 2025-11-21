import aiohttp
import asyncio
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.constants import API_BASE_URL, QUEUES

logger = logging.getLogger(__name__)


class ScheduleAPI:
    """Client for fetching schedule data from the API"""
    
    def __init__(self, base_url: str = API_BASE_URL):
        self.base_url = base_url
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def fetch_schedule(self, queue: str) -> Optional[List[Dict[str, Any]]]:
        """
        Fetch schedule for a specific queue
        
        Args:
            queue: Queue number (e.g., "4.2")
            
        Returns:
            List of schedule items or None if error
        """
        url = f"{self.base_url}?queue={queue}"
        
        try:
            session = await self._get_session()
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        logger.info(f"Successfully fetched schedule for queue {queue}")
                        return data
                    except Exception as e:
                        logger.error(f"Error parsing JSON for queue {queue}: {e}")
                        return None
                else:
                    logger.warning(f"Failed to fetch schedule for {queue}: HTTP {response.status}")
                    return None
        except aiohttp.ClientError as e:
            logger.error(f"Error fetching schedule for {queue}: {e}")
            return None
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching schedule for {queue}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error fetching schedule for {queue}: {e}")
            return None
    
    async def fetch_all_queues(self) -> Dict[str, Optional[List[Dict[str, Any]]]]:
        """
        Fetch schedules for all queues
        
        Returns:
            Dictionary mapping queue to its schedule data
        """
        results = {}
        
        for queue in QUEUES:
            schedule = await self.fetch_schedule(queue)
            results[queue] = schedule
            # Small delay to avoid overwhelming the API
            await asyncio.sleep(0.1)
        
        return results



