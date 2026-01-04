import os
import time
import requests
import yaml
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# --- CONFIGURATION ---
CONFIG_FILE = "stations.yaml"
BERLIN_TZ = ZoneInfo("Europe/Berlin")

def extract_apple_music_link(link):
    """Cleans an Apple Music link to keep only the song ID."""
    if not link or "music.apple.com" not in link:
        return None
    try:
        parsed = urlparse(link)
        query_params = parse_qs(parsed.query)
        if 'i' in query_params:
            new_query = urlencode({'i': query_params['i'][0]})
            return urlunparse((
                parsed.scheme, parsed.netloc, parsed.path, 
                parsed.params, new_query, parsed.fragment
            ))
        return link.split('?')[0]
    except:
        return None

def fetch_entries(config, start_dt, end_dt):
    """Helper to perform the actual API request and return the raw entry list."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": config['referer'],
        "Origin": config['referer'].rstrip('/'),
        "Accept": "application/json"
    }
    
    params = {
        "station": config['station_id'],
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat()
    }

    try:
        # Short sleep to be polite if looping
        if config.get('chunk_hours'):
            time.sleep(0.5)
            
        print(f"   Querying {start_dt.strftime('%H:%M')} -> {end_dt.strftime('%H:%M')}...")
        response = requests.get(config['api_url'], params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data.get("result", {}).get("entry", [])
    except Exception as e:
        print(f"   Error fetching range: {e}")
        return []

def process_station(config):
    print(f"--- Processing: {config['name']} ---")
    
    # --- TIME CALCULATION ---
    days_back = int(os.environ.get("DAYS_BACK", 0))
    now_berlin = datetime.now(BERLIN_TZ)
    target_date = now_berlin - timedelta(days=days_back)
    
    # Define Global Start/End (08:00 - 18:00/Now)
    global_start = target_date.replace(hour=8, minute=0, second=0, microsecond=0)
    
    if days_back > 0 or target_date.hour >= 18:
        global_end = target_date.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        global_end = target_date.replace(minute=0, second=0, microsecond=0)

    print(f"Target Window: {global_start.strftime('%Y-%m-%d %H:%M')} to {global_end.strftime('%H:%M')}")

    # --- FETCHING STRATEGY ---
    chunk_size = config.get('chunk_hours', 0) # 0 means single request
    
    all_entries = []

    if chunk_size > 0:
        # HOURLY LOOP
        current_ptr = global_start
        while current_ptr < global_end:
            # Calculate chunk end (e.g. current + 1 hour, but dont exceed global_end)
            chunk_end = min(current_ptr + timedelta(hours=chunk_size), global_end)
            
            # If start == end (reached current time exactly), stop
            if current_ptr >= chunk_end:
                break

            entries = fetch_entries(config, current_ptr, chunk_end)
            
            # API returns Newest -> Oldest. 
            # We insert at the BEGINNING of our master list to keep chronological order correct
            # or we collect all raw chunks and process them later. 
            # Strategy: Reverse the chunk immediately to get Chronological, then append.
            if entries:
                all_entries.extend(reversed(entries))
            
            current_ptr = chunk_end
    else:
        # SINGLE REQUEST
        entries = fetch_entries(config, global_start, global_end)
        if entries:
            all_entries.extend(reversed(entries))

    if not all_entries:
        print("No songs found.")
        return

    # --- PARSING & DEDUPLICATION ---
    ordered_data = [] 
    seen_identifiers = set() 

    for entry in all_entries:
        song_data = entry.get("song", {})
        song_entries = song_data.get("entry", [])
        
        if song_entries:
            info = song_entries[0]
            
            # Metadata
            title = info.get("title", "").strip()
            artist_list = info.get("artist", {}).get("entry", [])
            artist = artist_list[0].get("name", "").strip() if artist_list else ""
            
            if not title or not artist:
                continue

            formatted_name = f"{artist} - {title}"
            
            # Link
            clean_link = None
            if 'links' in config['outputs']:
                raw_link = info.get("affiliate_url")
                clean_link = extract_apple_music_link(raw_link)

            # Deduplication Key (Artist - Title)
            dedup_key = formatted_name.lower()

            if dedup_key not in seen_identifiers:
                seen_identifiers.add(dedup_key)
                ordered_data.append({
                    "name": formatted_name,
                    "link": clean_link
                })

    print(f"Found {len(ordered_data)} unique songs.")

    # --- WRITE OUTPUTS ---
    if 'links' in config['outputs']:
        out_path = config['outputs']['links']
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            count = 0
            for item in ordered_data:
                if item['link']:
                    f.write(item['link'] + "\n")
                    count += 1
            print(f"Saved {count} links to {out_path}")

    if 'artist_title' in config['outputs']:
        out_path = config['outputs']['artist_title']
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            for item in ordered_data:
                f.write(item['name'] + "\n")
            print(f"Saved {len(ordered_data)} titles to {out_path}")

def run():
    if not os.path.exists(CONFIG_FILE):
        print(f"Configuration file {CONFIG_FILE} not found.")
        exit(1)

    with open(CONFIG_FILE, 'r') as f:
        stations = yaml.safe_load(f)

    for station_config in stations:
        process_station(station_config)
        print("") # formatting newline

if __name__ == "__main__":
    run()
