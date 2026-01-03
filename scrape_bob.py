import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# --- CONFIGURATION ---
API_URL = "https://iris-bob.loverad.io/search.json"
OUTPUT_FILE_LINKS = "docs/bob.txt"
OUTPUT_FILE_NAMES = "docs/bob_at.txt"
STATION_ID = 69  # "Livestream National"

# Timezone setup
BERLIN_TZ = ZoneInfo("Europe/Berlin")

def run_scrape():
    # Headers to mimic a real browser to avoid being blocked
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.radiobob.de/",
        "Origin": "https://www.radiobob.de",
        "Accept": "application/json"
    }

    # --- CALCULATE TIME RANGE ---
    now_berlin = datetime.now(BERLIN_TZ)
    
    # Start: Today at 08:00:00
    start_time = now_berlin.replace(hour=8, minute=0, second=0, microsecond=0)
    
    # End: Today at 18:00:00 (or 'now' if the script runs early)
    if now_berlin.hour < 18:
        end_time = now_berlin
    else:
        end_time = now_berlin.replace(hour=18, minute=0, second=0, microsecond=0)

    print(f"Fetching playlist from {start_time.strftime('%H:%M')} to {end_time.strftime('%H:%M')}...")

    # Single Request Parameters
    params = {
        "station": STATION_ID,
        "start": start_time.isoformat(),
        "end": end_time.isoformat()
    }

    try:
        response = requests.get(API_URL, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Parse structure
        entries = data.get("result", {}).get("entry", [])
        
        if not entries:
            print("No songs found for this time range.")
            return

        # Prepare lists
        ordered_songs = []
        seen_links = set()

        # IMPORTANT: The API usually returns [Newest ... Oldest].
        # We REVERSE it to get [08:00 ... 18:00].
        for entry in reversed(entries):
            
            song_data = entry.get("song", {})
            song_entries = song_data.get("entry", [])
            
            if song_entries:
                song_info = song_entries[0]
                link = song_info.get("affiliate_url")
                
                if link and "music.apple.com" in link:
                    # --- CLEAN URL ---
                    try:
                        parsed = urlparse(link)
                        query_params = parse_qs(parsed.query)
                        
                        # Keep only 'i' parameter
                        if 'i' in query_params:
                            new_query = urlencode({'i': query_params['i'][0]})
                            clean_link = urlunparse((
                                parsed.scheme, parsed.netloc, parsed.path, 
                                parsed.params, new_query, parsed.fragment
                            ))
                        else:
                            clean_link = link.split('?')[0]

                        # --- EXTRACT METADATA ---
                        if clean_link not in seen_links:
                            title = song_info.get("title", "Unknown Title")
                            
                            # Artist is often nested: artist -> entry -> [0] -> name
                            artist_list = song_info.get("artist", {}).get("entry", [])
                            artist = artist_list[0].get("name", "Unknown Artist") if artist_list else "Unknown Artist"
                            
                            formatted_name = f"{artist} - {title}"

                            # Add to list
                            seen_links.add(clean_link)
                            ordered_songs.append({
                                "link": clean_link,
                                "name": formatted_name
                            })
                            
                    except Exception as e:
                        print(f"Skipping error entry: {e}")

        # --- SAVE FILES ---
        print(f"Found {len(ordered_songs)} unique songs.")
        
        os.makedirs(os.path.dirname(OUTPUT_FILE_LINKS), exist_ok=True)

        # 1. Links File
        with open(OUTPUT_FILE_LINKS, "w", encoding="utf-8") as f:
            for song in ordered_songs:
                f.write(song['link'] + "\n")

        # 2. Artist - Title File
        with open(OUTPUT_FILE_NAMES, "w", encoding="utf-8") as f:
            for song in ordered_songs:
                f.write(song['name'] + "\n")
        
        print("Files saved successfully.")

    except Exception as e:
        print(f"API Request failed: {e}")
        exit(1)

if __name__ == "__main__":
    run_scrape()
