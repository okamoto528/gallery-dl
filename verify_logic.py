import os
import shutil
import unittest
from unittest.mock import MagicMock, patch
from organizer.db_manager import DBManager
from organizer.file_organizer import FileOrganizer

# Test Config
TEST_DB = "test_organizer.db"
TEST_BASE_DIR = "test_downloads"
TEST_SOURCE_DIR = "test_source"

class TestOrganizerLogic(unittest.TestCase):
    def setUp(self):
        # Clean up previous runs
        if os.path.exists(TEST_DB):
            os.remove(TEST_DB)
        if os.path.exists(TEST_BASE_DIR):
            shutil.rmtree(TEST_BASE_DIR)
        if os.path.exists(TEST_SOURCE_DIR):
            shutil.rmtree(TEST_SOURCE_DIR)
            
        os.makedirs(TEST_BASE_DIR, exist_ok=True)
        os.makedirs(TEST_SOURCE_DIR, exist_ok=True)
        
        self.db = DBManager(TEST_DB)
        self.organizer = FileOrganizer(self.db)

    def tearDown(self):
        self.db = None
        # Cleanup is useful but let's keep it if we want to inspect results manually if failed
        # shutil.rmtree(TEST_BASE_DIR)
        # shutil.rmtree(TEST_SOURCE_DIR)
        # os.remove(TEST_DB)
        pass

    @patch('organizer.file_organizer.fetch_metadata')
    def test_basic_organize(self, mock_fetch):
        # Setup Mock Metadata
        mock_fetch.return_value = {
            "id": 12345,
            "title": "Test Title",
            "author": "Test Author",
            "series": "Original",
            "tags": "[]",
            "language": "japanese"
        }
        
        # Create Dummy File
        filename = "[Test Author] Test Title (12345).cbz"
        file_path = os.path.join(TEST_SOURCE_DIR, filename)
        with open(file_path, 'w') as f:
            f.write("content")
            
        # Run Organize
        target_cat = "Doujinshi"
        success, msg = self.organizer.organize_file(file_path, target_cat, TEST_BASE_DIR)
        
        self.assertTrue(success, f"Organize failed: {msg}")
        
        # Check File Location
        expected_path = os.path.join(TEST_BASE_DIR, "Doujinshi", "Test Author", filename)
        self.assertTrue(os.path.exists(expected_path), "File not moved to expected path")
        
        # Check DB
        row = self.db.get_gallery_by_id(12345)
        self.assertIsNotNone(row)
        self.assertEqual(row[5], target_cat) # Category
        
        # Check Author Setting
        saved_cat = self.db.get_author_category("Test Author")
        self.assertEqual(saved_cat, target_cat)

    @patch('organizer.file_organizer.fetch_metadata')
    def test_alias_resolution(self, mock_fetch):
        # Setup Alias
        self.db.add_alias("Alias Name", "Primary Name")
        
        # Setup Mock Metadata (returning the ALIAS as author)
        mock_fetch.return_value = {
            "id": 67890,
            "title": "Alias Title",
            "author": "Alias Name",
            "series": None,
            "tags": "[]",
            "language": "japanese"
        }
        
        filename = "[Alias Name] Alias Title (67890).cbz"
        file_path = os.path.join(TEST_SOURCE_DIR, filename)
        with open(file_path, 'w') as f:
            f.write("content")
            
        success, msg = self.organizer.organize_file(file_path, "Manga", TEST_BASE_DIR)
        
        self.assertTrue(success)
        
        # Expect move to PRIMARY Name folder
        expected_path = os.path.join(TEST_BASE_DIR, "Manga", "Primary Name", filename)
        self.assertTrue(os.path.exists(expected_path), f"File should be in Primary Name folder, found in: {msg}")

if __name__ == '__main__':
    unittest.main()
