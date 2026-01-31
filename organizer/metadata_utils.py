import sys
import subprocess
import json
import re
import os

# Assuming gallery-dl is installed and available via python -m gallery_dl
GALLERY_DL_CMD = [sys.executable, "-m", "gallery_dl"]

def extract_id_from_filename(filename):
    """
    Extracts the numeric gallery ID from a filename string.
    Expected format: "... (ID).cbz" or similar.
    """
    # Pattern: Look for digits in parentheses at the end of the filename (ignoring extension)
    # e.g. "Title (12345).cbz" -> 12345
    base = os.path.splitext(filename)[0]
    match = re.search(r'\((\d+)\)$', base)
    if match:
        return int(match.group(1))
    
    # Fallback: Just look for last sequence of digits
    # "Title 12345.cbz" -> 12345
    matches = re.findall(r'(\d+)', base)
    if matches:
        return int(matches[-1])
        
    return None

def fetch_metadata(gallery_id):
    """
    Fetches metadata for a given gallery ID using gallery-dl.
    Returns a dictionary of cleaned metadata.
    """
    url = f"https://hitomi.la/galleries/{gallery_id}.html"
    
    cmd = GALLERY_DL_CMD + ["-j", url]
    
    try:
        # Run gallery-dl in JSON mode
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=True
        )
        
        # Parse output
        # gallery-dl -j output can be multiple JSON lines or a single JSON list.
        # We handle both.
        data = None
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Try line by line, take the first one usually
            lines = result.stdout.strip().split('\n')
            for line in lines:
                if line.strip():
                    data = json.loads(line)
                    break 
                    
        if not data:
            return None

        # Extract info from first item (gallery-dl structure handling)
        info = {}
        if isinstance(data, list):
            # [index, metadata_dict] or [metadata_dict, ...]
            # Hitomi usually returns [index, dict] where index can be -1 on error
            if len(data) >= 2 and isinstance(data[1], dict):
                 # Check for valid structure
                 if isinstance(data[0], int):
                      info = data[1]
                 else:
                      # Maybe list of images?
                      info = data[0] if isinstance(data[0], dict) else {}
            elif len(data) > 0 and isinstance(data[0], dict):
                info = data[0]
        elif isinstance(data, dict):
            info = data
            
        return parse_metadata(info, gallery_id)

    except subprocess.CalledProcessError as e:
        print(f"Error executing gallery-dl for {gallery_id}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error fetching metadata for {gallery_id}: {e}")
        return None

def parse_metadata(info, gallery_id):
    """
    Cleans up and normalizes the raw metadata dictionary.
    """
    if not info:
        return None

    def format_field(value):
        if isinstance(value, list):
            return ", ".join(value)
        return value

    # Author (Artist or Group)
    # Prioritize Artist, then Group
    artist = info.get('artist')
    group = info.get('group')
    
    author = "N_A"
    if artist:
        author = format_field(artist)
    elif group:
        author = format_field(group)
        
    # Title
    # Prefer Japanese Title if available? 
    # Spec didn't explicitly say for DB, but hitomi_dl logic preferred JPN.
    # Let's save standard title as 'title', maybe save original in separate field if needed.
    # Let's stick to 'title' field from JSON which is usually the main title.
    title = info.get('title')
    jpn_title = info.get('title_jpn')
    if jpn_title:
        title = jpn_title # Use JPN title as primary display title if available

    # Series (Parody)
    series = format_field(info.get('parody'))
    if not series:
         series = format_field(info.get('series'))

    # Tags
    tags_list = info.get('tags', [])
    tags_str = json.dumps(tags_list, ensure_ascii=False)

    return {
        "id": gallery_id,
        "title": title,
        "author": author,
        "category": info.get('type', 'Unknown'), # Default category from Metadata
        "series": series,
        "tags": tags_str,
        "language": info.get('language')
    }
