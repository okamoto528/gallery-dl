import os
import re
import argparse
import subprocess
import shutil
import sys
from collections import defaultdict

class DuplicateCleaner:
    def __init__(self, target_dir, keyword, dry_run, delete_mode):
        self.target_dir = target_dir
        self.keyword = keyword
        self.dry_run = dry_run
        self.delete_mode = delete_mode
        # Updated regex to match (digits).cbz explicitly at the end
        self.id_pattern = re.compile(r'\((\d+)\)\.cbz$')
        self.processed_count = 0
        self.moved_count = 0

    def get_id_from_name(self, filename):
        """Extract ID from filename. Target is .cbz files only."""
        if not filename.lower().endswith('.cbz'):
            return None
            
        match = self.id_pattern.search(filename)
        if match:
            return match.group(1)
        return None

    def calculate_score(self, filename):
        """Calculate score to determine priority. Higher is better."""
        # Count [] and () pairs
        bracket_score = filename.count('[') + filename.count('(')
        # Length score
        length_score = len(filename)
        
        # Priority: Tag count * 10 + Length
        return bracket_score * 10 + length_score

    def search_everything(self, keyword):
        """Search using 'es' command for .cbz files."""
        # Append .cbz to keyword to filter by extension in Everything
        query = f"{keyword} .cbz"
        print(f"Searching Everything for: {query}")
        try:
            # -r used for regex in some versions, but keyword might be simple. 
            # We want full paths. es output is full paths by default.
            # IMPORTANT: Pass keyword and extension as separate arguments.
            # es matches ALL arguments (AND logic).
            cmd = ['es', keyword, '*.cbz']
            
            # Windows 'es' usually outputs in system encoding (cp932/Shift-JIS on Japanese Windows).
            # Forcing utf-8 causes decode errors.
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='cp932', errors='replace')
            
            if result.returncode != 0:
                print(f"Error executing es: {result.stderr}")
                return []
            
            if not result.stdout:
                return []
                
            lines = result.stdout.strip().split('\n')
            return [line.strip() for line in lines if line.strip() and line.strip().lower().endswith('.cbz')]
        except FileNotFoundError:
            print("Error: 'es' command not found. Please ensure Everything CLI is installed and in your PATH.")
            sys.exit(1)
        except Exception as e:
            print(f"Error searching Everything: {e}")
            import traceback
            traceback.print_exc()
            return []

    def scan_directory(self, directory):
        """Recursively scan directory for .cbz files."""
        print(f"Scanning directory: {directory}")
        files = []
        for root, dirs, filenames in os.walk(directory):
            # Only add .cbz files
            for f in filenames:
                if f.lower().endswith('.cbz'):
                    files.append(os.path.join(root, f))
        return files

    def load_config(self):
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'clean_duplicates.json')
        if os.path.exists(config_path):
            try:
                import json
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
        return {}

    def move_to_trash(self, path):
        """Move path to _trash directory."""
        config = self.load_config()
        trash_config = config.get('trash_dir')

        if trash_config:
            # Use configured trash directory
            # Expand user path (~) and make absolute if needed, or relative to CWD
            # For simplicity, if it's relative, let's treat it relative to CWD or Script?
            # Usually Config relative paths are relative to the config file or CWD.
            # Let's assume CWD or Absolute.
            trash_dir = os.path.abspath(trash_config)
        else:
            # Default: _trash in parent directory
            parent_dir = os.path.dirname(path)
            trash_dir = os.path.join(parent_dir, '_trash')
        
        basename = os.path.basename(path)
        
        if self.dry_run:
            print(f"[Dry-Run] Move to: {os.path.join(trash_dir, basename)}")
            return True

        if not os.path.exists(trash_dir):
            try:
                os.makedirs(trash_dir)
            except OSError as e:
                print(f"Error creating trash dir {trash_dir}: {e}")
                return False

        dest_path = os.path.join(trash_dir, basename)
        
        # Handle collision
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(basename)
            import time
            timestamp = int(time.time())
            new_name = f"{base}_{timestamp}{ext}"
            dest_path = os.path.join(trash_dir, new_name)

        try:
            shutil.move(path, dest_path)
            print(f"Moved: {basename} -> {trash_dir}")
            
            if self.delete_mode:
                if os.path.exists(dest_path):
                    if os.path.isdir(dest_path):
                        shutil.rmtree(dest_path)
                    else:
                        os.remove(dest_path)
                    print(f"Deleted: {dest_path}")
            return True
        except Exception as e:
            print(f"Error moving {path}: {e}")
            return False

    def run(self):
        candidates = []
        if self.keyword:
            candidates = self.search_everything(self.keyword)
        elif self.target_dir:
            candidates = self.scan_directory(self.target_dir)
        else:
            print("Error: Either --dir or --keyword must be specified.")
            return

        # Group by ID
        # key: ID, value: list of (path, score)
        grouped = defaultdict(list)
        
        for path in candidates:
            if not os.path.exists(path):
                continue
            
            # Skip _trash directories themselves to avoid re-scanning trash
            if '_trash' in path.split(os.sep):
                continue

            basename = os.path.basename(path)
            file_id = self.get_id_from_name(basename)
            
            if file_id:
                score = self.calculate_score(basename)
                grouped[file_id].append({'path': path, 'score': score, 'name': basename})

        # Process duplicates
        for file_id, items in grouped.items():
            if len(items) > 1:
                # excessive items, find winner
                items.sort(key=lambda x: x['score'], reverse=True)
                
                winner = items[0]
                losers = items[1:]
                
                print(f"\nDuplicate ID detected: {file_id}")
                print(f"  Winner: {winner['name']} (Score: {winner['score']})")
                
                for loser in losers:
                    print(f"  Loser : {loser['name']} (Score: {loser['score']})")
                    self.move_to_trash(loser['path'])
                    self.moved_count += 1
            self.processed_count += 1
            
        print(f"\nDone. Processed groups: {self.processed_count}, Moved files: {self.moved_count}")

def main():
    parser = argparse.ArgumentParser(description='Clean duplicate gallery files based on ID.')
    parser.add_argument('--dir', help='Target directory to scan')
    parser.add_argument('--keyword', help='Keyword to search using Everything')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--delete', action='store_true', help='Delete files after moving to trash')

    args = parser.parse_args()

    if not args.dir and not args.keyword:
        # Default to current dir if nothing specified? Or strict? 
        # Spec says "Target directory specified", let's restrict or default to cwd.
        # Let's default to cwd if nothing is passed, but maybe safer to require one.
        # "Target directory specified" -> Argument is expected.
        # Let's try to be friendly.
        # But specification interface said: `python clean_duplicates.py [ディレクトリ or オプション]`
        # If user passes a positional arg, argparse handles it if we defined it, but we used named args --dir.
        # Let's just check args.
        pass

    cleaner = DuplicateCleaner(args.dir, args.keyword, args.dry_run, args.delete)
    cleaner.run()

if __name__ == '__main__':
    main()
