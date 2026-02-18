import sys
import os
import unittest
import time
from unittest.mock import MagicMock, patch

# Mock env vars
os.environ["CLOUDLEECHER_API_KEY"] = "test-key"

# We need to mock xmlrpc.client BEFORE importing app because it initializes the connection at module level
patcher = patch('xmlrpc.client.ServerProxy')
mock_proxy_class = patcher.start()
mock_aria2 = MagicMock()
mock_proxy_class.return_value.aria2 = mock_aria2

# Also mock os.makedirs to avoid permission errors
patcher_makedirs = patch('os.makedirs')
patcher_makedirs.start()

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

# Import app
import app as backend_module
from app import app as flask_app, BackgroundMover, DOWNLOAD_DIR, FINAL_DIR

# Stop the real background thread that started on import
backend_module.mover_thread.running = False

class TestBackend(unittest.TestCase):
    def setUp(self):
        self.client = flask_app.test_client()
        self.client.testing = True

        # Reset mocks
        mock_aria2.reset_mock()

        # Ensure we use the mocked aria2 from the module
        backend_module.s.aria2 = mock_aria2

    def test_auth_required(self):
        # Test without key
        response = self.client.get('/api/status')
        self.assertEqual(response.status_code, 401)

        # Test with wrong key
        response = self.client.get('/api/status', headers={'x-api-key': 'wrong'})
        self.assertEqual(response.status_code, 401)

        # Test with correct key
        # Mock return values to avoid AttributeError when accessing results
        mock_aria2.tellActive.return_value = []
        mock_aria2.tellWaiting.return_value = []
        mock_aria2.tellStopped.return_value = []

        response = self.client.get('/api/status', headers={'x-api-key': 'test-key'})
        self.assertEqual(response.status_code, 200)

    @patch('shutil.move')
    @patch('os.path.exists')
    @patch('os.path.relpath')
    def test_background_mover(self, mock_relpath, mock_exists, mock_move):
        # Create instance but don't start thread
        mover = BackgroundMover()

        # Mock aria2.tellStopped to return a completed task
        # Task that downloaded /content/temp_downloads/MyMovie/movie.mkv
        task = {
            'gid': 'gid1',
            'status': 'complete',
            'files': [{'path': f'{DOWNLOAD_DIR}/MyMovie/movie.mkv'}]
        }
        mock_aria2.tellStopped.return_value = [task]

        # Mock file system checks
        # We need to ensure os.path.exists returns True for source, but False for destination
        def exists_side_effect(path):
            if path.startswith(DOWNLOAD_DIR): return True
            return False

        mock_exists.side_effect = exists_side_effect

        # Mock relpath to return 'MyMovie/movie.mkv'
        # app.py: rel_path = os.path.relpath(source_path, DOWNLOAD_DIR)
        mock_relpath.return_value = 'MyMovie/movie.mkv'

        # Execute check
        mover.check_and_move_files()

        # Verify move called
        # Should move DOWNLOAD_DIR/MyMovie to FINAL_DIR/MyMovie
        expected_src = os.path.join(DOWNLOAD_DIR, 'MyMovie')
        expected_dst = os.path.join(FINAL_DIR, 'MyMovie')

        mock_move.assert_called_with(expected_src, expected_dst)

        # Verify cleanup called
        mock_aria2.removeDownloadResult.assert_called_with('gid1')

    @patch('shutil.move')
    @patch('os.path.exists')
    @patch('os.path.relpath')
    def test_background_mover_collision(self, mock_relpath, mock_exists, mock_move):
        mover = BackgroundMover()

        task = {
            'gid': 'gid2',
            'status': 'complete',
            'files': [{'path': f'{DOWNLOAD_DIR}/MyMovie/movie.mkv'}]
        }
        mock_aria2.tellStopped.return_value = [task]

        mock_relpath.return_value = 'MyMovie/movie.mkv'

        # Mock exists to return True for source AND destination
        def exists_side_effect(path):
            return True

        mock_exists.side_effect = exists_side_effect

        mover.check_and_move_files()

        # Should detect collision and rename
        args, _ = mock_move.call_args
        src, dst = args

        self.assertEqual(src, os.path.join(DOWNLOAD_DIR, 'MyMovie'))
        self.assertTrue('MyMovie_' in dst)
        self.assertNotEqual(dst, os.path.join(FINAL_DIR, 'MyMovie'))

if __name__ == '__main__':
    unittest.main()
