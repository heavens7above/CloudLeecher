import unittest
from unittest.mock import MagicMock, patch
import os
import json
import sys

# Add backend to path if needed, though we are in root
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set env before importing app
os.environ['CLOUDLEECHER_API_KEY'] = 'test-secret-key'

# Import app. Since app.py is in backend/, and we are running from root or backend
# If we run from root, it is backend.app
try:
    from backend.app import app
except ImportError:
    from app import app

class BackendTestCase(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True

    def test_health_check(self):
        response = self.app.get('/health')
        self.assertEqual(response.status_code, 200)

    def test_auth_missing(self):
        # /api/status requires auth
        response = self.app.get('/api/status')
        # Should be 401 because x-api-key is missing
        self.assertEqual(response.status_code, 401)

    @patch('xmlrpc.client.ServerProxy')
    def test_auth_success(self, mock_server_proxy):
        # Patch the global 's' object in app
        # Since 's' is already instantiated in app.py, we need to patch it there.
        # But patching imports is tricky.
        # Instead, we just patch the rpc calls if they happen.

        with patch('backend.app.s') as mock_s:
            mock_s.aria2.tellActive.return_value = []
            mock_s.aria2.tellWaiting.return_value = []
            mock_s.aria2.tellStopped.return_value = []

            response = self.app.get('/api/status', headers={'x-api-key': 'test-secret-key'})
            self.assertEqual(response.status_code, 200)

if __name__ == '__main__':
    unittest.main()
