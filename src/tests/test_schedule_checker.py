"""
Tests for schedule_checker.py

These tests cover various scenarios:
1. First time schedule appears
2. Schedule changes (time, count)
3. Schedule cancellation
4. Empty schedule ([])
5. New date appears (tomorrow)
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta

# Import after conftest.py sets up the path
from src.services.schedule_checker import ScheduleChecker
from aiogram import Bot


def get_today_str():
    """Get today's date in format DD.MM.YYYY"""
    return datetime.now().strftime("%d.%m.%Y")


def get_tomorrow_str():
    """Get tomorrow's date in format DD.MM.YYYY"""
    return (datetime.now() + timedelta(days=1)).strftime("%d.%m.%Y")


def get_yesterday_str():
    """Get yesterday's date in format DD.MM.YYYY"""
    return (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")


def get_today_datetime():
    """Get today's datetime"""
    return datetime.now()


@pytest.fixture
def mock_bot():
    """Create a mock bot instance"""
    bot = MagicMock(spec=Bot)
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def schedule_checker(mock_bot):
    """Create ScheduleChecker instance with mocked bot"""
    return ScheduleChecker(mock_bot)


class TestNormalizeSchedule:
    """Test schedule normalization"""
    
    def test_normalize_schedule_with_shutdowns(self, schedule_checker):
        """Test normalizing schedule with shutdowns"""
        today = get_today_str()
        yesterday = get_yesterday_str()
        
        schedule_data = [
            {
                "eventDate": today,
                "queues": {
                    "4.2": [
                        {
                            "shutdownHours": "00:00-02:30",
                            "from": "00:00",
                            "to": "02:30",
                            "status": 1
                        },
                        {
                            "shutdownHours": "15:00-16:00",
                            "from": "15:00",
                            "to": "16:00",
                            "status": 1
                        }
                    ]
                },
                "createdAt": f"{yesterday} 19:53",
                "scheduleApprovedSince": f"{today} 00:05"
            }
        ]
        
        result = schedule_checker._normalize_schedule(schedule_data, "4.2")
        
        assert today in result
        assert len(result[today]["shutdowns"]) == 2
        assert result[today]["shutdowns"][0]["from"] == "00:00"
        assert result[today]["shutdowns"][0]["to"] == "02:30"
    
    def test_normalize_schedule_cancelled(self, schedule_checker):
        """Test normalizing cancelled schedule (empty queues)"""
        today = get_today_str()
        yesterday = get_yesterday_str()
        
        schedule_data = [
            {
                "eventDate": today,
                "queues": {
                    "4.2": []
                },
                "createdAt": f"{yesterday} 19:53",
                "scheduleApprovedSince": f"{today} 00:05"
            }
        ]
        
        result = schedule_checker._normalize_schedule(schedule_data, "4.2")
        
        assert today in result
        assert len(result[today]["shutdowns"]) == 0  # Empty shutdowns
    
    def test_normalize_schedule_multiple_dates(self, schedule_checker):
        """Test normalizing schedule with multiple dates"""
        today = get_today_str()
        tomorrow = get_tomorrow_str()
        yesterday = get_yesterday_str()
        
        schedule_data = [
            {
                "eventDate": today,
                "queues": {
                    "4.2": [
                        {
                            "shutdownHours": "00:00-02:30",
                            "from": "00:00",
                            "to": "02:30",
                            "status": 1
                        }
                    ]
                },
                "createdAt": f"{yesterday} 19:53",
                "scheduleApprovedSince": f"{today} 00:05"
            },
            {
                "eventDate": tomorrow,
                "queues": {
                    "4.2": [
                        {
                            "shutdownHours": "10:00-12:00",
                            "from": "10:00",
                            "to": "12:00",
                            "status": 1
                        }
                    ]
                },
                "createdAt": f"{today} 20:00",
                "scheduleApprovedSince": f"{today} 20:00"
            }
        ]
        
        result = schedule_checker._normalize_schedule(schedule_data, "4.2")
        
        assert len(result) == 2
        assert today in result
        assert tomorrow in result


class TestHasChanges:
    """Test change detection logic"""
    
    @pytest.mark.asyncio
    async def test_first_time_with_shutdowns(self, schedule_checker):
        """Test first time schedule appears with shutdowns - should notify"""
        today = get_today_str()
        yesterday = get_yesterday_str()
        
        old_schedule = None
        new_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ],
                "createdAt": f"{yesterday} 19:53",
                "scheduleApprovedSince": f"{today} 00:05"
            }
        }
        
        with patch.object(schedule_checker, '_get_shown_dates_today', return_value=set()):
            has_changes, new_date, cancelled = await schedule_checker._has_changes("4.2", old_schedule, new_schedule)
            
            assert has_changes is True
            assert new_date == today
            assert len(cancelled) == 0
    
    @pytest.mark.asyncio
    async def test_first_time_empty(self, schedule_checker):
        """Test first time with empty schedule - should not notify"""
        old_schedule = None
        new_schedule = {}
        
        has_changes, new_date, cancelled = await schedule_checker._has_changes("4.2", old_schedule, new_schedule)
        
        assert has_changes is False
        assert new_date is None
        assert len(cancelled) == 0
    
    @pytest.mark.asyncio
    async def test_schedule_changes_time(self, schedule_checker):
        """Test when shutdown times change"""
        today = get_today_str()
        
        old_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            }
        }
        new_schedule = {
            today: {
                "shutdowns": [
                    {"from": "01:00", "to": "03:00", "shutdownHours": "01:00-03:00"}
                ]
            }
        }
        
        has_changes, new_date, cancelled = await schedule_checker._has_changes("4.2", old_schedule, new_schedule)
        
        assert has_changes is True
        assert new_date is None
        assert len(cancelled) == 0
    
    @pytest.mark.asyncio
    async def test_schedule_cancelled(self, schedule_checker):
        """Test when schedule is cancelled (had shutdowns, now empty)"""
        today = get_today_str()
        
        old_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            }
        }
        new_schedule = {
            today: {
                "shutdowns": []
            }
        }
        
        has_changes, new_date, cancelled = await schedule_checker._has_changes("4.2", old_schedule, new_schedule)
        
        assert has_changes is True
        assert new_date is None
        assert today in cancelled
    
    @pytest.mark.asyncio
    async def test_empty_array_from_api(self, schedule_checker):
        """Test when API returns [] - should not notify"""
        today = get_today_str()
        
        old_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            }
        }
        new_schedule = {}  # Empty dict from []
        
        has_changes, new_date, cancelled = await schedule_checker._has_changes("4.2", old_schedule, new_schedule)
        
        assert has_changes is False  # Should not notify for []
        assert new_date is None
        assert len(cancelled) == 0
    
    @pytest.mark.asyncio
    async def test_new_date_appears(self, schedule_checker):
        """Test when tomorrow's schedule appears"""
        today = get_today_str()
        tomorrow = get_tomorrow_str()
        
        old_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            }
        }
        new_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            },
            tomorrow: {
                "shutdowns": [
                    {"from": "10:00", "to": "12:00", "shutdownHours": "10:00-12:00"}
                ]
            }
        }
        
        with patch.object(schedule_checker, '_get_shown_dates_today', return_value=set()):
            has_changes, new_date, cancelled = await schedule_checker._has_changes("4.2", old_schedule, new_schedule)
            
            assert has_changes is True
            assert new_date == tomorrow
            assert len(cancelled) == 0
    
    @pytest.mark.asyncio
    async def test_new_date_already_shown_today(self, schedule_checker):
        """Test when new date already shown today - should not notify again"""
        today = get_today_str()
        tomorrow = get_tomorrow_str()
        
        old_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            }
        }
        new_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            },
            tomorrow: {
                "shutdowns": [
                    {"from": "10:00", "to": "12:00", "shutdownHours": "10:00-12:00"}
                ]
            }
        }
        
        # Simulate that tomorrow was already shown today
        with patch.object(schedule_checker, '_get_shown_dates_today', return_value={tomorrow}):
            has_changes, new_date, cancelled = await schedule_checker._has_changes("4.2", old_schedule, new_schedule)
            
            assert has_changes is False  # Should not notify if already shown
            assert new_date is None
            assert len(cancelled) == 0


class TestIsShutdownPast:
    """Test shutdown past detection"""
    
    def test_shutdown_not_past(self, schedule_checker):
        """Test shutdown that hasn't ended yet"""
        today = get_today_str()
        today_dt = get_today_datetime()
        
        # Current time: 15:01, shutdown: 15:00-16:00
        with patch('src.services.schedule_checker.datetime') as mock_datetime:
            mock_now = datetime(today_dt.year, today_dt.month, today_dt.day, 15, 1)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime
            mock_datetime.combine = datetime.combine
            
            is_past = schedule_checker._is_shutdown_past(today, "15:00", "16:00")
            
            assert is_past is False  # Should not be past at 15:01
    
    def test_shutdown_past(self, schedule_checker):
        """Test shutdown that has ended"""
        today = get_today_str()
        today_dt = get_today_datetime()
        
        # Current time: 16:01, shutdown: 15:00-16:00
        with patch('src.services.schedule_checker.datetime') as mock_datetime:
            mock_now = datetime(today_dt.year, today_dt.month, today_dt.day, 16, 1)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime
            mock_datetime.combine = datetime.combine
            
            is_past = schedule_checker._is_shutdown_past(today, "15:00", "16:00")
            
            assert is_past is True  # Should be past at 16:01
    
    def test_shutdown_midnight(self, schedule_checker):
        """Test shutdown ending at midnight (00:00)"""
        yesterday = get_yesterday_str()
        today_dt = get_today_datetime()
        
        with patch('src.services.schedule_checker.datetime') as mock_datetime:
            mock_now = datetime(today_dt.year, today_dt.month, today_dt.day, 0, 30)
            mock_datetime.now.return_value = mock_now
            mock_datetime.strptime = datetime.strptime
            mock_datetime.combine = datetime.combine
            mock_datetime.timedelta = timedelta
            
            is_past = schedule_checker._is_shutdown_past(yesterday, "22:00", "00:00")
            
            # At 00:30, shutdown from 22:00-00:00 (previous day) should be past
            assert is_past is True


class TestCheckQueueScenarios:
    """Test full check_queue scenarios"""
    
    @pytest.mark.asyncio
    async def test_scenario_1_first_schedule(self, schedule_checker, mock_bot):
        """Scenario 1: First time schedule appears"""
        today = get_today_str()
        yesterday = get_yesterday_str()
        
        schedule_data = [
            {
                "eventDate": today,
                "queues": {
                    "4.2": [
                        {
                            "shutdownHours": "00:00-02:30",
                            "from": "00:00",
                            "to": "02:30",
                            "status": 1
                        }
                    ]
                },
                "createdAt": f"{yesterday} 19:53",
                "scheduleApprovedSince": f"{today} 00:05"
            }
        ]
        
        with patch.object(schedule_checker.api_client, 'fetch_schedule', return_value=schedule_data):
            with patch.object(schedule_checker, '_get_stored_schedule', return_value=None):
                with patch.object(schedule_checker, '_save_schedule', new_callable=AsyncMock):
                    with patch.object(schedule_checker, '_get_shown_dates_today', return_value=set()):
                        with patch.object(schedule_checker, '_notify_subscribers', new_callable=AsyncMock) as mock_notify:
                            result = await schedule_checker.check_queue("4.2")
                            
                            # Should notify on first time if schedule has shutdowns
                            assert result is True
                            mock_notify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_scenario_2_empty_array(self, schedule_checker):
        """Scenario 2: API returns [] - should not notify"""
        today = get_today_str()
        
        with patch.object(schedule_checker.api_client, 'fetch_schedule', return_value=[]):
            with patch.object(schedule_checker, '_get_stored_schedule', return_value={
                today: {
                    "shutdowns": [{"from": "00:00", "to": "02:30"}]
                }
            }):
                with patch.object(schedule_checker, '_save_schedule', new_callable=AsyncMock):
                    with patch.object(schedule_checker, '_notify_subscribers', new_callable=AsyncMock) as mock_notify:
                        result = await schedule_checker.check_queue("4.2")
                        
                        # Should not notify for []
                        assert result is False
                        mock_notify.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_scenario_3_schedule_cancelled(self, schedule_checker):
        """Scenario 3: Schedule cancelled (queues: {"4.2": []})"""
        today = get_today_str()
        yesterday = get_yesterday_str()
        
        schedule_data = [
            {
                "eventDate": today,
                "queues": {
                    "4.2": []
                },
                "createdAt": f"{yesterday} 19:53",
                "scheduleApprovedSince": f"{today} 00:05"
            }
        ]
        
        old_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            }
        }
        
        with patch.object(schedule_checker.api_client, 'fetch_schedule', return_value=schedule_data):
            with patch.object(schedule_checker, '_get_stored_schedule', return_value=old_schedule):
                with patch.object(schedule_checker, '_save_schedule', new_callable=AsyncMock):
                    with patch.object(schedule_checker, '_notify_subscribers', new_callable=AsyncMock) as mock_notify:
                        result = await schedule_checker.check_queue("4.2")
                        
                        # Should notify about cancellation
                        assert result is True
                        mock_notify.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_scenario_4_time_changes(self, schedule_checker):
        """Scenario 4: Shutdown times changed"""
        today = get_today_str()
        yesterday = get_yesterday_str()
        
        old_schedule = {
            today: {
                "shutdowns": [
                    {"from": "00:00", "to": "02:30", "shutdownHours": "00:00-02:30"}
                ]
            }
        }
        
        schedule_data = [
            {
                "eventDate": today,
                "queues": {
                    "4.2": [
                        {
                            "shutdownHours": "01:00-03:00",
                            "from": "01:00",
                            "to": "03:00",
                            "status": 1
                        }
                    ]
                },
                "createdAt": f"{yesterday} 19:53",
                "scheduleApprovedSince": f"{today} 00:05"
            }
        ]
        
        with patch.object(schedule_checker.api_client, 'fetch_schedule', return_value=schedule_data):
            with patch.object(schedule_checker, '_get_stored_schedule', return_value=old_schedule):
                with patch.object(schedule_checker, '_save_schedule', new_callable=AsyncMock):
                    with patch.object(schedule_checker, '_notify_subscribers', new_callable=AsyncMock) as mock_notify:
                        result = await schedule_checker.check_queue("4.2")
                        
                        # Should notify about changes
                        assert result is True
                        mock_notify.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

