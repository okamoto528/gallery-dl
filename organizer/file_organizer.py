import os
import shutil
import logging
from .db_manager import DBManager
from .metadata_utils import extract_id_from_filename, fetch_metadata

class FileOrganizer:
    def __init__(self, db_manager: DBManager):
        self.db = db_manager
        self.logger = logging.getLogger("Organizer")

    def organize_file(self, file_path, target_category, base_dir):
        """
        Organizes a single .cbz file.
        Returns: (Success: bool, Message: str)
        """
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"

        filename = os.path.basename(file_path)
        gallery_id = extract_id_from_filename(filename)

        if not gallery_id:
            return False, f"Could not extract ID from filename: {filename}"

        # 1. Resolve Metadata
        # Try DB first
        metadata = None
        db_data = self.db.get_gallery_by_id(gallery_id)
        
        if db_data:
            # Map DB row to dict (simple mapping based on schema order)
            # id, title, original_filename, current_path, author, category, series, tags, language, imported_at
            metadata = {
                "id": db_data[0],
                "title": db_data[1],
                "author": db_data[4],
                "category": db_data[5], # This might be old, but we use it for other fields if needed
                "series": db_data[6],
                "tags": db_data[7],
                "language": db_data[8]
            }
        else:
            # Fetch from Web
            self.logger.info(f"Fetching metadata for ID {gallery_id}...")
            metadata = fetch_metadata(gallery_id)
            if not metadata:
                # Fallback: Attempt to proceed without online metadata
                # We need at least Author to organize.
                fallback_author = self.extract_author_from_filename(filename)
                if not fallback_author:
                    fallback_author = "N_A"
                
                metadata = {
                    "id": gallery_id,
                    "title": filename, # Use filename as title if metadata fails
                    "author": fallback_author,
                    "category": target_category,
                    "series": None,
                    "tags": "[]",
                    "language": "unknown"
                }
                self.logger.warning(f"Metadata fetch failed for {gallery_id}. Using fallback data.")

        # 2. Resolve Author (Alias Check)
        original_author = metadata.get("author", "N_A")
        primary_author = self.db.get_primary_author(original_author)

        # 3. Determine Target Path
        # Structure: Base / Category / PrimaryAuthor / Filename
        
        # Sanitize folder names
        def sanitize(name):
            return "".join([c for c in name if c.isalnum() or c in (' ', '.', '-', '_')]).strip()

        safe_category = sanitize(target_category)
        safe_author = sanitize(primary_author)
        
        target_dir = os.path.join(base_dir, safe_category, safe_author)
        target_path = os.path.join(target_dir, filename)

        # 4. Move File
        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)

        if os.path.abspath(file_path) == os.path.abspath(target_path):
            return True, "File already in target location."

        if os.path.exists(target_path):
            # Collision handling: Skip for now as per plan
            return False, f"Target file already exists: {target_path}"

        try:
            shutil.move(file_path, target_path)
        except Exception as e:
            return False, f"Error moving file: {e}"

        # 5. Update Database
        # Save metadata with the NEW category (user selected) and Current Path
        metadata['category'] = target_category
        metadata['current_path'] = target_path
        metadata['original_filename'] = filename
        
        self.db.upsert_gallery(metadata)
        
        # Update Author Settings (Last used category)
        self.db.update_author_category(primary_author, target_category)

        return True, f"Moved to {safe_category}/{safe_author}"

    def extract_author_from_filename(self, filename):
        import re
        # Match matches from beginning of string
        # Capture first bracket and optional second bracket
        match = re.match(r'^\[([^\]]+)\](?:\[([^\]]+)\])?', filename)
        
        if match:
            first = match.group(1)
            second = match.group(2)
            
            # Check for N_A or N／A (Case insensitive just in case, though user specified precise cases)
            if first.upper() in ("N_A", "N／A"):
                if second:
                    return second
                return first # Return N_A if no group found
            
            return first
            
        return None

    def get_default_category_for_file(self, file_path):
        """
        Predicts the default category for a file based on Author history or Metadata.
        Returns: (Category, AuthorName) tuple or (None, AuthorName)
        """
        filename = os.path.basename(file_path)
        gallery_id = extract_id_from_filename(filename)
        
        author_from_file = self.extract_author_from_filename(filename)
        potential_cat = None

        # 1. DB Lookup (Gallery)
        if gallery_id:
            db_data = self.db.get_gallery_by_id(gallery_id)
            if db_data:
                # Return existing category AND author
                return db_data[5], db_data[4] 
        
        # 2. Author History
        if author_from_file:
            primary = self.db.get_primary_author(author_from_file)
            saved_cat = self.db.get_author_category(primary)
            if saved_cat:
                potential_cat = saved_cat
        
        return potential_cat, author_from_file
