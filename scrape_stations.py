import os
import time
import requests
import yaml
import csv
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Selenium Imports
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
CONFIG_FILE = "stations.yaml"
BERLIN_TZ = ZoneInfo("Europe/Berlin")

# ==========================================
# UTILITIES
# ==========================================

def get_run_dates():
    """Returns (target_date, current_weekday_int)."""
    days_back = int(os.environ.get("DAYS_BACK", 0))
    now_berlin = datetime.now(BERLIN_TZ)
    target_date = now_berlin - timedelta(days=days_back)
    return target_date, target_date.weekday()

def calculate_time_window(config, target_date):
    """
    Determines start/end datetime based on config limits and current time.
    """
    cfg_start = config['time_range']['start']
    cfg_end = config['time_range']['end']

    start_dt = target_date.replace(hour=cfg_start, minute=0, second=0, microsecond=0)
    
    # Check if we are running for "Today"
    days_back = int(os.environ.get("DAYS_BACK", 0))
    now_berlin = datetime.now(BERLIN_TZ)
    is_today = (days_back == 0 and target_date.date() == now_berlin.date())

    # If today and currently earlier than the configured end time, stop at current hour
    if is_today and now_berlin.hour < cfg_end:
        # e.g. Config end is 18:00, but it is 14:15. We stop at 14:00.
        end_dt = target_date.replace(hour=now_berlin.hour, minute=0, second=0, microsecond=0)
    else:
        # Otherwise use the configured end time (e.g. 18:00)
        end_dt = target_date.replace(hour=cfg_end, minute=0, second=0, microsecond=0)

    return start_dt, end_dt

def extract_catalog_id(link):
    """Extracts Apple Music 'i' parameter."""
    if not link or "music.apple.com" not in link:
        return None
    try:
        parsed = urlparse(link)
        qs = parse_qs(parsed.query)
        return qs['i'][0] if 'i' in qs else None
    except:
        return None

def write_output(config, ordered_data):
    """Writes results to disk based on 'outputs' config."""
    if not ordered_data:
        return

    outputs = config.get('outputs', {})

    # 1. Links Output (CSV: Title, CatalogID)
    if 'links' in outputs:
        path = outputs['links']
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline='') as f:
            writer = csv.writer(f)
            c = 0
            for item in ordered_data:
                if item.get('link'):
                    writer.writerow([item['title'], item['link']])
                    c += 1
            print(f"   -> Saved {c} IDs to {path}")

    # 2. Playlist Output (Text: Artist - Title)
    if 'playlist' in outputs:
        path = outputs['playlist']
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for item in ordered_data:
                f.write(item['name'] + "\n")
            print(f"   -> Saved {len(ordered_data)} lines to {path}")

# ==========================================
# STRATEGY: API
# ==========================================

def fetch_api_chunk(config, start_dt, end_dt):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": config.get('referer', ''),
        "Origin": config.get('referer', '').rstrip('/'),
        "Accept": "application/json"
    }
    
    # Merge static params (station id) with dynamic time params
    params = config.get('params', {}).copy()
    params['start'] = start_dt.isoformat()
    params['end'] = end_dt.isoformat()

    try:
        if config.get('chunk_hours'):
            time.sleep(0.5)
        print(f"   API: {start_dt.strftime('%H:%M')} -> {end_dt.strftime('%H:%M')}...")
        
        resp = requests.get(config['url'], params=params, headers=headers)
        resp.raise_for_status()
        return resp.json().get("result", {}).get("entry", [])
    except Exception as e:
        print(f"   Error: {e}")
        return []

def run_api(config, start_dt, end_dt):
    chunk_size = config.get('chunk_hours', 0)
    all_entries = []

    if chunk_size > 0:
        # Loop by chunk_size hours
        curr = start_dt
        while curr < end_dt:
            next_hop = min(curr + timedelta(hours=chunk_size), end_dt)
            if curr >= next_hop: break
            
            entries = fetch_api_chunk(config, curr, next_hop)
            if entries: all_entries.extend(reversed(entries))
            curr = next_hop
    else:
        # Single request
        entries = fetch_api_chunk(config, start_dt, end_dt)
        if entries: all_entries.extend(reversed(entries))

    # Process Data
    ordered_data = []
    seen = set()

    for entry in all_entries:
        song = entry.get("song", {})
        tracks = song.get("entry", [])
        if not tracks: continue
        
        info = tracks[0]
        title = info.get("title", "").strip()
        
        artist_nest = info.get("artist", {}).get("entry", [])
        artist = artist_nest[0].get("name", "").strip() if artist_nest else ""

        if not title or not artist: continue

        fmt_name = f"{artist} - {title}"
        dedup_key = fmt_name.lower()
        
        if dedup_key not in seen:
            seen.add(dedup_key)
            link_id = extract_catalog_id(info.get("affiliate_url"))
            ordered_data.append({
                "name": fmt_name,
                "title": title,
                "link": link_id
            })
            
    print(f"   Found {len(ordered_data)} unique songs.")
    write_output(config, ordered_data)

# ==========================================
# STRATEGY: SELENIUM
# ==========================================

def run_selenium(config, start_dt, end_dt):
    date_str = start_dt.strftime("%Y-%m-%d")
    
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

    driver = None
    hour_data = [] # List of (name, title, key) tuples
    seen = set()
    ordered_data = []

    try:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        
        # Iterate strictly by hour integers as SWR uses "HH:00" format
        # Range is exclusive on the end, so we use int(end_dt.hour)
        for h in range(start_dt.hour, end_dt.hour):
            print(f"   Selenium: Scraping {h:02d}:00...")
            
            time_str = f"{h:02d}:00"
            base_url = config['url']
            sep = "&" if "?" in base_url else "?"
            full_url = f"{base_url}{sep}swx_date={date_str}&swx_time={time_str}"
            
            driver.get(full_url)
            
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "list-playlist"))
                )
            except:
                print(f"   Warning: No playlist found for {h}:00")
                continue

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.find_all("li", class_="list-group-item")
            
            # SWR lists are usually Newest -> Oldest per hour. 
            # We collect them, then reverse this hour's list before adding to main list
            # to maintain chronological order.
            this_hour = []
            for item in items:
                a_tag = item.find("dd", class_="playlist-item-artist")
                t_tag = item.find("dd", class_="playlist-item-song")
                if a_tag and t_tag:
                    artist = a_tag.get_text(strip=True)
                    title = t_tag.get_text(strip=True)
                    fmt = f"{artist} - {title}"
                    this_hour.append((fmt, title, fmt.lower()))
            
            # Add reversed hour to main list
            hour_data.extend(reversed(this_hour))

    except Exception as e:
        print(f"   Selenium Error: {e}")
    finally:
        if driver: driver.quit()

    # Deduplicate global list
    for fmt, title, key in hour_data:
        if key not in seen:
            seen.add(key)
            ordered_data.append({
                "name": fmt,
                "title": title,
                "link": None
            })

    print(f"   Found {len(ordered_data)} unique songs.")
    write_output(config, ordered_data)

# ==========================================
# MAIN
# ==========================================

def run():
    if not os.path.exists(CONFIG_FILE):
        print(f"Error: {CONFIG_FILE} missing.")
        exit(1)

    target_date, weekday = get_run_dates()
    print(f"🚀 Execution Date: {target_date.strftime('%Y-%m-%d')} (Weekday: {weekday})")

    with open(CONFIG_FILE, 'r') as f:
        stations = yaml.safe_load(f)

    for config in stations:
        print(f"\n--- {config['name']} ---")
        
        # 1. Schedule Check
        allowed = config.get('schedule', [0,1,2,3,4,5,6])
        if weekday not in allowed:
            print(f"   Skipping (Not scheduled for today).")
            continue

        # 2. Time Window
        start_dt, end_dt = calculate_time_window(config, target_date)
        if start_dt >= end_dt:
            print(f"   Skipping (Current time {start_dt.strftime('%H:%M')} is past end time {end_dt.strftime('%H:%M')}).")
            continue
        
        print(f"   Window: {start_dt.strftime('%H:%M')} - {end_dt.strftime('%H:%M')}")

        # 3. Execution
        method = config.get('method', 'api')
        if method == 'api':
            run_api(config, start_dt, end_dt)
        elif method == 'selenium':
            run_selenium(config, start_dt, end_dt)
        else:
            print(f"   Unknown method: {method}")

if __name__ == "__main__":
    run()