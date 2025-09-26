"""
Test profile utilities
"""

import unittest
from unittest.mock import Mock, patch

from samcli.lib.utils.profile import list_available_profiles


class TestProfile(unittest.TestCase):
    @patch("samcli.lib.utils.profile.Session")
    def test_list_available_profiles(self, mock_session):
        """Test that list_available_profiles returns available profiles from boto session"""
        # Arrange
        expected_profiles = ["default", "test-profile", "prod-profile"]
        mock_session_instance = Mock()
        mock_session_instance.available_profiles = expected_profiles
        mock_session.return_value = mock_session_instance

        # Act
        result = list_available_profiles()

        # Assert
        self.assertEqual(result, expected_profiles)
        mock_session.assert_called_once()
