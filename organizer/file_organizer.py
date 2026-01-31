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
                return False, f"Failed to fetch metadata for ID {gallery_id}"

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
        # We record the Category used for the ORIGINAL author name (so if they pick the specific alias again, it works)
        # AND the Primary Name? Usually mapping is per Author Name entity.
        # Let's save for Primary Author for consistency, but if the user has split personalities? 
        # Spec said "Corresponding Author". Primary is safe.
        self.db.update_author_category(primary_author, target_category)

        return True, f"Moved to {safe_category}/{safe_author}"

    def get_default_category_for_file(self, file_path):
        """
        Predicts the default category for a file based on Author history or Metadata.
        """
        gallery_id = extract_id_from_filename(os.path.basename(file_path))
        if not gallery_id:
            return None

        # Try DB logic for existing file?
        # Or just Fetch metadata solely for prediction?
        # Fetching metadata is slow. 
        # If we just draged and dropped, we might not want to wait for network.
        # BUT we need the local DB lookup.
        
        # 1. DB Lookup (Gallery)
        db_data = self.db.get_gallery_by_id(gallery_id)
        if db_data:
            # If already exists, maybe return its current category?
            return db_data[5] # category column
        
        # 2. What if we don't have gallery info BUT we have author info?
        # We don't know the author without fetching metadata! 
        # So we can't predict WITHOUT fetching metadata unless we parse the filename (which is [Artist] Title...)
        # Hitomi naming convention: [Artist] Title.
        
        filename = os.path.basename(file_path)
        # Try to extract [Author] from filename
        import re
        match = re.match(r'^\[(.*?)\]', filename)
        if match:
            potential_author = match.group(1)
            # Check DB for this author's default category
            # Need to handle Alias here too?
            primary = self.db.get_primary_author(potential_author)
            saved_cat = self.db.get_author_category(primary)
            if saved_cat:
                return saved_cat
        
        return None
