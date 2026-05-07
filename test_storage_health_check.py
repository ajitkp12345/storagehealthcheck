#!/usr/bin/env python3
"""
Test script for storage health check functionality.
Tests the health check logic without requiring actual API connections.
"""

import json
import unittest
from unittest.mock import Mock, patch
import sys
import os
import requests

# Add the current directory to path so we can import the main module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from storage_health_check import StorageHealthCheck

class TestStorageHealthCheck(unittest.TestCase):
    def setUp(self):
        self.checker = StorageHealthCheck()

    @patch('requests.Session')
    def test_pure_storage_check_success(self, mock_session_class):
        """Test Pure Storage health check with successful API responses."""
        # Mock session and responses
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock array response
        mock_array_response = Mock()
        mock_array_response.json.return_value = {
            'status': 'ready',
            'capacity': 1000000,
            'total': 200000
        }
        mock_array_response.raise_for_status.return_value = None

        # Mock hardware response
        mock_hw_response = Mock()
        mock_hw_response.status_code = 200
        mock_hw_response.json.return_value = [
            {'name': 'Controller A', 'status': 'healthy'},
            {'name': 'Controller B', 'status': 'healthy'}
        ]

        # Configure session.get to return different responses
        mock_session.get.side_effect = [mock_array_response, mock_hw_response]

        # Run the check
        results = self.checker.check_pure_storage('192.168.1.1', 'user', 'pass', 'password')

        # Verify results: array status, capacity, 2 hardware = 4 total
        self.assertEqual(len(results), 4)

        # Check array status
        array_check = results[0]
        self.assertEqual(array_check['platform'], 'Pure Storage')
        self.assertEqual(array_check['component'], 'Array')
        self.assertEqual(array_check['status'], 'OK')

        # Check capacity
        capacity_check = results[1]
        self.assertEqual(capacity_check['component'], 'Capacity')
        self.assertEqual(capacity_check['value'], '20.0%')

        # Check hardware
        hw_checks = results[2:]
        self.assertEqual(len(hw_checks), 2)
        for hw_check in hw_checks:
            self.assertEqual(hw_check['component'], 'Hardware')
            self.assertEqual(hw_check['status'], 'OK')

    @patch('requests.Session')
    def test_pure_storage_api_failure(self, mock_session_class):
        """Test Pure Storage health check with API failure."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock failed response using requests exception
        mock_session.get.side_effect = requests.exceptions.RequestException("Connection failed")

        results = self.checker.check_pure_storage('192.168.1.1', 'user', 'pass', 'password')

        self.assertEqual(len(results), 1)
        failure_check = results[0]
        self.assertEqual(failure_check['status'], 'CRITICAL')
        self.assertIn('Connection failed', failure_check['value'])

    @patch('requests.Session')
    def test_netapp_ontap_check_success(self, mock_session_class):
        """Test NetApp ONTAP health check with successful API responses."""
        mock_session = Mock()
        mock_session_class.return_value = mock_session

        # Mock responses
        mock_cluster_response = Mock()
        mock_cluster_response.json.return_value = {'health': {'status': 'ok'}}
        mock_cluster_response.raise_for_status.return_value = None

        mock_nodes_response = Mock()
        mock_nodes_response.status_code = 200
        mock_nodes_response.json.return_value = {
            'records': [
                {'name': 'node1', 'health': 'ok'},
                {'name': 'node2', 'health': 'ok'}
            ]
        }

        mock_agg_response = Mock()
        mock_agg_response.status_code = 200
        mock_agg_response.json.return_value = {
            'records': [
                {'name': 'aggr1', 'state': 'online'}
            ]
        }

        mock_vol_response = Mock()
        mock_vol_response.status_code = 200
        mock_vol_response.json.return_value = {
            'records': [
                {'name': 'vol1', 'state': 'online'}
            ]
        }

        mock_session.get.side_effect = [
            mock_cluster_response, mock_nodes_response,
            mock_agg_response, mock_vol_response
        ]

        results = self.checker.check_netapp_ontap('192.168.1.1', 'user', 'pass')

        # Should have cluster, 2 nodes, 1 aggregate, 1 volume = 5 checks
        self.assertEqual(len(results), 5)

        # Check cluster
        cluster_check = results[0]
        self.assertEqual(cluster_check['component'], 'Cluster')
        self.assertEqual(cluster_check['status'], 'OK')

    def test_display_results(self):
        """Test that results display doesn't crash."""
        test_checks = [
            {
                'platform': 'Test Platform',
                'component': 'Test Component',
                'check_name': 'Test Check',
                'value': 'Test Value',
                'status': 'OK',
                'recommended_action': 'None'
            }
        ]

        # This should not raise an exception
        try:
            self.checker.display_results(test_checks)
        except Exception as e:
            self.fail(f"display_results raised an exception: {e}")

if __name__ == '__main__':
    unittest.main()