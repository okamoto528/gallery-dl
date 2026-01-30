import json
try:
    with open('debug_metadata.json', 'r', encoding='utf-16') as f:
        content = f.read()
    
    # gallery-dl -j often outputs multiple JSON objects (one per line or list)
    # But usually for hitomi valid gallery it might return a list of images.
    # The first item often contains gallery metadata.
    
    try:
        data = json.loads(content)
    except:
        # try line by line
        data = []
        for line in content.strip().split('\n'):
            if line.strip():
                try:
                    data.append(json.loads(line))
                except:
                    pass
    
    if isinstance(data, list) and len(data) > 0:
        first = data[0]
        # Check structure [index, dict]
        if isinstance(first, list) and len(first) >= 2:
            info = first[1]
            print("Found keys in info:")
            print(list(info.keys()))
            if 'parody' in info:
                print(f"parody: {info['parody']}")
            if 'series' in info:
                print(f"series: {info['series']}")
        elif isinstance(first, dict):
             print("Found keys in first dict:")
             print(list(first.keys()))
             if 'parody' in first:
                print(f"parody: {first['parody']}")
             if 'series' in first:
                print(f"series: {first['series']}")
    else:
        print("No valid data list found")

except Exception as e:
    print(f"Error: {e}")
