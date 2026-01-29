import argparse
import subprocess
import json
import os
import shutil
import zipfile
import sys
from concurrent.futures import ThreadPoolExecutor
from PIL import Image

# Configuration
GALLERY_DL_CMD = [sys.executable, "-m", "gallery_dl"]
TEMP_DIR = "temp_download"
OUTPUT_DIR = "downloads"

def get_metadata(gallery_id):
    """Fetches metadata using gallery-dl -j"""
    url = f"https://hitomi.la/galleries/{gallery_id}.html"
    try:
        # Check if gallery-dl is available
        cmd = GALLERY_DL_CMD + ["-j", url]
        
        # Inject config if available (this might be checking only global config loaded in main? 
        # But get_metadata is called from main loop, maybe we should pass config or handle it globally?)
        # Let's assume we handle config file creation in main loop or globally.
        # But to be clean, let's look for the temp file.
        if os.path.exists("gd_config_temp.json"):
            cmd += ["--config", "gd_config_temp.json"]
            
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        # gallery-dl returns a list of dictionaries, usually one per image, or a structure containing album info.
        # For hitomi, it usually outputs a list of JSON objects (one per file) or a single structure.
        # We need to parse the output carefully.
        # Often gallery-dl -j outputs multiple JSON objects separated by newlines or in a list.
        # Let's try to parse the whole output as JSON first, or split lines.
        
        try:
             data = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Try line by line
            data = []
            for line in result.stdout.strip().split('\n'):
                if line.strip():
                     data.append(json.loads(line))
        
        # We extract gallery info from the first item usually
        if isinstance(data, list) and len(data) > 0:
            return data
        return None

    except subprocess.CalledProcessError as e:
        print(f"Error fetching metadata for ID {gallery_id}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error for ID {gallery_id}: {e}")
        return None

def filter_gallery(metadata, target_lang, exclude_tags, exclude_artists):
    """
    Checks if gallery matches criteria.
    metadata: List of image objects from gallery-dl.
             We assume common fields are shared or available in the first entry.
    """
    if not metadata:
        return False
    
    # Extract info from first image/entry
    if not metadata:
        return False
        
    # Extract info from first image/entry
    if not metadata:
        return False
        
    first_item = metadata[0]
    info = {}
    
    # Handle [index, dict] structure (common in gallery-dl for hitomi)
    if isinstance(first_item, list) and len(first_item) >= 2 and isinstance(first_item[1], dict):
        index = first_item[0]
        data_dict = first_item[1]
        
        # Check for error code
        if index == -1:
            print(f"Skipping: Gallery error ({data_dict.get('message', 'Unknown error')})")
            return False
            
        info = data_dict
    elif isinstance(first_item, dict):
        # unexpected but handle just in case it's a direct dict
        info = first_item
    else:
        print(f"Skipping: Unexpected metadata structure (first item is {type(first_item)}: {first_item})")
        return False

    # 1. Language Check
    # hitomi.la/gallery-dl usually provides 'language' field
    # If target_lang is specified, we skip if it doesn't match.
    # Note: Sometimes language might be missing or different.
    current_lang = info.get('language', '').lower()
    if target_lang and current_lang != target_lang.lower():
        # Ensure target_lang is not empty string
        if target_lang:
             print(f"Skipping: Language '{current_lang}' does not match target '{target_lang}'")
             return False

    # 2. Exclude Tags
    # Tags usually come as a list in 'tags' field
    tags = info.get('tags', [])
    if exclude_tags:
        for tag in tags:
            if tag in exclude_tags:
                print(f"Skipping: Contains excluded tag '{tag}'")
                return False

    # 3. Exclude Artists
    # Artist can be in 'artist' field (single or list?)
    artist = info.get('artist')
    artists = []
    if isinstance(artist, list):
        artists = artist
    elif isinstance(artist, str):
        artists = [artist]
    
    if exclude_artists:
        for a in artists:
            if a in exclude_artists:
                print(f"Skipping: Contains excluded artist '{a}'")
                return False

    return True

def download_gallery(gallery_id):
    """Downloads gallery using gallery-dl to a temp folder"""
    url = f"https://hitomi.la/galleries/{gallery_id}.html"
    download_path = os.path.join(TEMP_DIR, str(gallery_id))
    
    # Ensure temp dir exists
    if not os.path.exists(download_path):
        os.makedirs(download_path)

    print(f"Downloading ID {gallery_id}...")
    try:
        cmd = GALLERY_DL_CMD + ["-d", download_path, url]
        if os.path.exists("gd_config_temp.json"):
             cmd += ["--config", "gd_config_temp.json"]
             
        subprocess.run(
            cmd,
            check=True
        )
        return download_path
    except subprocess.CalledProcessError as e:
        print(f"Error downloading ID {gallery_id}: {e}")
        return None

def process_images(directory):
    """Resizes and converts images in the directory"""
    print(f"Processing images in {directory}...")
    
    processed_files = []

    for root, dirs, files in os.walk(directory):
        files.sort()
        for filename in files:
            filepath = os.path.join(root, filename)
            # Skip non-image files if any? gallery-dl usually only DLs images/videos.
            # Check extension or try-except
            try:
                with Image.open(filepath) as img:
                    # Convert to RGB if necessary (e.g. for PNG with transparency being saved as JPG)
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")

                    # Resize logic: max 1920x1920
                    max_w = 1920
                    max_h = 1920
                    
                    original_w, original_h = img.size
                    ratio = min(max_w / original_w, max_h / original_h)
                    
                    # Only resize if larger
                    if ratio < 1.0:
                        new_w = int(original_w * ratio)
                        new_h = int(original_h * ratio)
                        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    
                    # Save as JPG (overwriting or new file? Previous was new file + delete old)
                    # Let's save as .jpg
                    new_filename = os.path.splitext(filename)[0] + ".jpg"
                    new_filepath = os.path.join(root, new_filename)
                    
                    img.save(new_filepath, "JPEG", quality=90)
                    processed_files.append(new_filename)
                    
                    # If we created a new file, remove the old one to avoid duplicates in zip
                    if filename != new_filename:
                        os.remove(filepath)
                        
            except Exception as e:
                # Not an image or error, skip
                # print(f"Skipping processing for {filename}: {e}")
                pass
    
    return processed_files

def create_cbz(source_dir, gallery_info, gallery_id):
    """Creates CBZ file with specific naming convention"""
    # Naming: [artist][group] title(Series) (id).cbz
    # Fields: artist, group, title, series, id
    
    info = {}
    first_item = gallery_info[0]
    
    if isinstance(first_item, list) and len(first_item) >= 2 and isinstance(first_item[1], dict):
        info = first_item[1]
    elif isinstance(first_item, dict):
        info = first_item
        
    artist = info.get('artist')
    if isinstance(artist, list):
        artist = ",".join(artist) # Join if multiple ? simple approach
    if not artist:
        artist = "N_A"

    group = info.get('group')
    if isinstance(group, list):
         group = ",".join(group)
    if not group:
         group = "" # Empty if missing as per typical conventions, or "N_A"
    
    # Prefer Japanese title, fall back to default title
    title = info.get('title_jpn')
    if not title:
        title = info.get('title', 'No Title')
    
    series = info.get('series')
    if isinstance(series, list):
        series = ",".join(series)
    
    # Construct filename parts
    # [artist]
    name_str = f"[{artist}]"
    
    # [group] - only if exists? User said "[artist][group]..."
    if group:
        name_str += f"[{group}]"
    
    # title
    name_str += f" {title}"
    
    # (Series) - only if exists?
    if series:
        name_str += f"({series})"
        
    # (id)
    name_str += f" ({gallery_id})"
    
    # sanitize filename
    valid_chars = "-_.()[] abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    # A bit strict, let's just replace bad chars
    # Windows forbidden: < > : " / \ | ? *
    forbidden = '<>:"/\\|?*'
    for char in forbidden:
        name_str = name_str.replace(char, '_')
    
    filename = name_str + ".cbz"
    filepath = os.path.join(OUTPUT_DIR, filename)

    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    print(f"Creating CBZ: {filename}")
    
    with zipfile.ZipFile(filepath, 'w') as cbz:
        for root, dirs, files in os.walk(source_dir):
            files.sort()
            for f in files:
                full_path = os.path.join(root, f)
                # Add to zip, flattening the structure (placing files at root of zip)
                # This assumes unique filenames, which is typical for hitomi
                cbz.write(full_path, arcname=f)

    return filepath

def load_config():
    """Loads configuration from config.json in the script's directory"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "config.json")
    
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config.json from {config_path}: {e}")
    else:
        # Fallback to CWD just in case
        config_path = "config.json"
        if os.path.exists(config_path):
             try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
             except:
                 pass
    return {}

def process_gallery(gid, lang, exclude_tags, exclude_artists):
    """Processes a single gallery ID: metadata -> filtering -> download -> processing -> CBZ -> cleanup"""
    print(f"Processing ID: {gid}")
    
    # 1. Get Metadata
    metadata = get_metadata(gid)
    if not metadata:
        print(f"ID {gid}: No metadata found or error. Skipping.")
        return
        
    # 2. Filter
    if not filter_gallery(metadata, lang, exclude_tags, exclude_artists):
        return
        
    # 3. Download
    dl_path = download_gallery(gid)
    if not dl_path:
        return
        
    # 4. Process Images
    process_images(dl_path)

    # 5. Create CBZ
    create_cbz(dl_path, metadata, gid)
    
    # 6. Cleanup
    try:
        shutil.rmtree(dl_path)
    except Exception as e:
        print(f"Error cleaning up {dl_path}: {e}")

def main():
    global OUTPUT_DIR
    global TEMP_DIR

    parser = argparse.ArgumentParser(description="Download and process hitomi.la galleries.")
    parser.add_argument("start_id", type=int, help="Start Gallery ID")
    parser.add_argument("end_id", type=int, help="End Gallery ID")
    parser.add_argument("--lang", type=str, default="japanese", help="Target Language (default: japanese)")
    parser.add_argument("--exclude_tags", nargs='+', help="Tags to exclude (overrides config)")
    parser.add_argument("--exclude_artists", nargs='+', help="Artists to exclude (overrides config)")
    parser.add_argument("--output_dir", type=str, help="Output directory (overrides config)")
    parser.add_argument("--temp_dir", type=str, help="Temporary directory (overrides config)")
    parser.add_argument("--workers", type=int, help="Number of parallel workers (overrides config)")

    args = parser.parse_args()
    config = load_config()

    # Apply configuration with CLI overrides
    if args.output_dir:
        OUTPUT_DIR = args.output_dir
    elif config.get("output_dir"):
        OUTPUT_DIR = config.get("output_dir")

    # Temp Dir
    if args.temp_dir:
        TEMP_DIR = args.temp_dir
    elif config.get("temp_dir"):
        TEMP_DIR = config.get("temp_dir")
    
    # Exclude Tags
    exclude_tags = config.get("exclude_tags", [])
    if args.exclude_tags is not None:
        exclude_tags = args.exclude_tags

    # Exclude Artists
    exclude_artists = config.get("exclude_artists", [])
    if args.exclude_artists is not None:
        exclude_artists = args.exclude_artists

    # Workers
    max_workers = config.get("max_workers", 3)
    if args.workers is not None:
        max_workers = args.workers

    # Ensure absolute paths for clarity
    OUTPUT_DIR = os.path.abspath(OUTPUT_DIR)
    TEMP_DIR = os.path.abspath(TEMP_DIR)

    print(f"Output Directory: {OUTPUT_DIR}")
    print(f"Temporary Directory: {TEMP_DIR}")

    start = args.start_id
    end = args.end_id
    
    # Handle downloader config
    downloader_config = config.get("downloader")
    if downloader_config:
        try:
            # Wrap in "downloader" key for gallery-dl
            gd_conf = {"downloader": downloader_config}
            with open("gd_config_temp.json", "w") as f:
                json.dump(gd_conf, f, indent=4)
        except Exception as e:
            print(f"Warning: Failed to create temp config for gallery-dl: {e}")

    # Handle range
    if start > end:
        start, end = end, start
    
    ids = list(range(start, end + 1))
    
    print(f"Starting parallel processing with {max_workers} workers for {len(ids)} galleries...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_gallery, gid, args.lang, exclude_tags, exclude_artists): gid for gid in ids}
        for future in futures:
            gid = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"ID {gid}: An error occurred during processing: {e}")
                import traceback
                traceback.print_exc()

    # Final cleanup of temp root
    try:
        if os.path.exists(TEMP_DIR):
            shutil.rmtree(TEMP_DIR)
    except:
        pass

    if os.path.exists("gd_config_temp.json"):
        try:
            os.remove("gd_config_temp.json")
        except:
            pass

if __name__ == "__main__":
    main()
