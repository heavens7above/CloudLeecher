import unittest
from unittest.mock import MagicMock, patch
import os
import json
import sys

# Add backend to path to import app
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestBackend(unittest.TestCase):
    def setUp(self):
        # Set API Key env var
        os.environ['CLOUDLEECHER_API_KEY'] = 'test-key'

        # Patch external dependencies
        self.xmlrpc_patcher = patch('xmlrpc.client.ServerProxy')
        self.mock_server = self.xmlrpc_patcher.start()
        self.mock_aria2 = MagicMock()
        self.mock_server.return_value.aria2 = self.mock_aria2

        self.shutil_patcher = patch('shutil.move')
        self.mock_move = self.shutil_patcher.start()

        # Import app after patching
        from app import app
        self.app = app
        self.client = self.app.test_client()

    def tearDown(self):
        self.xmlrpc_patcher.stop()
        self.shutil_patcher.stop()

    def test_health_check(self):
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)

    def test_api_key_required(self):
        # Without key
        response = self.client.get('/api/status')
        self.assertEqual(response.status_code, 401)

        # With wrong key
        response = self.client.get('/api/status', headers={'x-api-key': 'wrong-key'})
        self.assertEqual(response.status_code, 401)

        # With correct key
        # Mock aria2 responses
        self.mock_aria2.tellActive.return_value = []
        self.mock_aria2.tellWaiting.return_value = []
        self.mock_aria2.tellStopped.return_value = []

        response = self.client.get('/api/status', headers={'x-api-key': 'test-key'})
        self.assertEqual(response.status_code, 200)

    def test_add_magnet(self):
        self.mock_aria2.tellActive.return_value = []
        self.mock_aria2.tellWaiting.return_value = []
        self.mock_aria2.addUri.return_value = "gid123"

        payload = {"magnet": "magnet:?xt=urn:btih:..."}
        response = self.client.post('/api/download/magnet',
                                  headers={'x-api-key': 'test-key'},
                                  json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['gid'], "gid123")

        # Verify temp dir used
        args, kwargs = self.mock_aria2.addUri.call_args
        self.assertEqual(args[1]['dir'], "/content/temp_downloads")

if __name__ == '__main__':
    unittest.main()
