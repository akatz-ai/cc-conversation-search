#!/usr/bin/env python3
"""Tests for date utility functions"""

import pytest
from datetime import datetime, timedelta, time
from conversation_search.core.date_utils import parse_date, build_date_filter


class TestParseDate:
    """Test date parsing functionality"""

    def test_parse_yesterday(self):
        """Should parse 'yesterday' to previous calendar day"""
        result = parse_date('yesterday')
        expected = datetime.combine(
            (datetime.now().date() - timedelta(days=1)),
            time.min
        )
        assert result == expected
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0

    def test_parse_today(self):
        """Should parse 'today' to current calendar day at midnight"""
        result = parse_date('today')
        expected = datetime.combine(datetime.now().date(), time.min)
        assert result == expected
        assert result.hour == 0
        assert result.minute == 0

    def test_parse_iso_date(self):
        """Should parse ISO format dates (YYYY-MM-DD)"""
        result = parse_date('2025-11-13')
        expected = datetime(2025, 11, 13, 0, 0, 0)
        assert result == expected

    def test_parse_iso_with_time_strips_time(self):
        """Should strip time component if provided"""
        result = parse_date('2025-11-13T14:30:00')
        expected = datetime(2025, 11, 13, 0, 0, 0)
        assert result == expected

    def test_case_insensitive(self):
        """Should handle case-insensitive relative dates"""
        assert parse_date('Yesterday') == parse_date('yesterday')
        assert parse_date('TODAY') == parse_date('today')
        assert parse_date('ToDay') == parse_date('today')

    def test_whitespace_handling(self):
        """Should strip whitespace"""
        assert parse_date('  yesterday  ') == parse_date('yesterday')
        assert parse_date('\ttoday\n') == parse_date('today')

    def test_invalid_format_raises(self):
        """Should raise ValueError for invalid formats"""
        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date('tomorrow')

        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date('last week')

        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date('2025-13-01')  # Invalid month

        with pytest.raises(ValueError, match="Invalid date format"):
            parse_date('not a date')


class TestBuildDateFilter:
    """Test SQL date filter building"""

    def test_single_date_filter(self):
        """Should build filter for a specific date"""
        sql, params = build_date_filter(date='2025-11-13')

        assert sql == "timestamp >= ? AND timestamp < ?"
        assert len(params) == 2
        assert params[0] == '2025-11-13T00:00:00'
        assert params[1] == '2025-11-14T00:00:00'  # Next day

    def test_date_filter_with_yesterday(self):
        """Should handle 'yesterday' keyword"""
        sql, params = build_date_filter(date='yesterday')

        yesterday = datetime.combine(
            (datetime.now().date() - timedelta(days=1)),
            time.min
        )
        tomorrow_from_yesterday = yesterday + timedelta(days=1)

        assert sql == "timestamp >= ? AND timestamp < ?"
        assert params[0] == yesterday.isoformat()
        assert params[1] == tomorrow_from_yesterday.isoformat()

    def test_since_filter_only(self):
        """Should build filter with only start date"""
        sql, params = build_date_filter(since='2025-11-10')

        assert sql == "timestamp >= ?"
        assert len(params) == 1
        assert params[0] == '2025-11-10T00:00:00'

    def test_until_filter_only(self):
        """Should build filter with only end date (inclusive)"""
        sql, params = build_date_filter(until='2025-11-13')

        assert sql == "timestamp < ?"
        assert len(params) == 1
        # Until is inclusive, so we add one day
        assert params[0] == '2025-11-14T00:00:00'

    def test_since_and_until_range(self):
        """Should build filter for date range"""
        sql, params = build_date_filter(since='2025-11-10', until='2025-11-13')

        assert sql == "timestamp >= ? AND timestamp < ?"
        assert len(params) == 2
        assert params[0] == '2025-11-10T00:00:00'
        assert params[1] == '2025-11-14T00:00:00'  # Until is inclusive

    def test_since_and_until_with_keywords(self):
        """Should handle keyword dates in ranges"""
        sql, params = build_date_filter(since='yesterday', until='today')

        yesterday = datetime.combine(
            (datetime.now().date() - timedelta(days=1)),
            time.min
        )
        tomorrow = datetime.combine(
            (datetime.now().date() + timedelta(days=1)),
            time.min
        )

        assert sql == "timestamp >= ? AND timestamp < ?"
        assert params[0] == yesterday.isoformat()
        assert params[1] == tomorrow.isoformat()

    def test_no_filters_returns_empty(self):
        """Should return empty filter when no dates provided"""
        sql, params = build_date_filter()

        assert sql == ""
        assert params == []

    def test_date_overrides_since_until(self):
        """When date is provided, since/until are ignored"""
        sql, params = build_date_filter(
            date='2025-11-13',
            since='2025-11-10',
            until='2025-11-15'
        )

        # Should only use 'date' parameter
        assert sql == "timestamp >= ? AND timestamp < ?"
        assert params[0] == '2025-11-13T00:00:00'
        assert params[1] == '2025-11-14T00:00:00'


class TestDateFilterEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_same_day_range(self):
        """Should handle since==until (single day)"""
        sql, params = build_date_filter(since='2025-11-13', until='2025-11-13')

        # Since is inclusive start, until adds a day for exclusive end
        assert params[0] == '2025-11-13T00:00:00'
        assert params[1] == '2025-11-14T00:00:00'

    def test_reverse_date_range_allowed(self):
        """Should allow reverse ranges (caller's responsibility to validate)"""
        # This is a logic error but we don't validate - SQL will return no results
        sql, params = build_date_filter(since='2025-11-15', until='2025-11-10')

        assert sql == "timestamp >= ? AND timestamp < ?"
        assert params[0] == '2025-11-15T00:00:00'
        assert params[1] == '2025-11-11T00:00:00'

    def test_leap_year_handling(self):
        """Should correctly handle leap year dates"""
        sql, params = build_date_filter(date='2024-02-29')

        assert params[0] == '2024-02-29T00:00:00'
        assert params[1] == '2024-03-01T00:00:00'

    def test_year_boundary(self):
        """Should handle year boundaries correctly"""
        sql, params = build_date_filter(since='2024-12-31', until='2025-01-01')

        assert params[0] == '2024-12-31T00:00:00'
        assert params[1] == '2025-01-02T00:00:00'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
