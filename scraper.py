import sys
import os
import datetime
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- CONFIGURATION ---
# Output files are now prefixed with "docs/"
STATIONS = {
    "SWR3": {
        "url": "https://www.swr3.de/playlisten/index.html",
        "output_file": "docs/swr3.txt",
        "start_hour": 8,
        "end_hour": 18,     # 8 AM to 6 PM (ends at 17:59)
        "active_weekdays": [0, 1, 2, 3, 4] # Mon-Fri
    },
    "SWR1": {
        "url": "https://www.swr.de/swr1/rp/musikrecherche-swr1-rp-detail-100.html",
        "output_file": "docs/swr1.txt",
        "start_hour": 11,
        "end_hour": 16,     # 11 AM to 4 PM (ends at 15:59)
        "active_weekdays": [6] # Sunday
    }
}

DUPLICATE_LOOKBACK = 10 

def get_station_for_today():
    weekday = datetime.date.today().weekday() # 0=Mon, 6=Sun
    for name, config in STATIONS.items():
        if weekday in config["active_weekdays"]:
            return name, config
    return None, None

def scrape_hour(driver, url_base, date_str, hour):
    time_str = f"{hour:02d}:00"
    full_url = f"{url_base}?swx_date={date_str}&swx_time={time_str}"
    
    driver.get(full_url)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "list-playlist"))
        )
    except:
        return []

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    items = soup.find_all("li", class_="list-group-item")
    
    songs = []
    for item in items:
        artist_tag = item.find("dd", class_="playlist-item-artist")
        title_tag = item.find("dd", class_="playlist-item-song")

        if artist_tag and title_tag:
            artist = artist_tag.get_text(strip=True)
            title = title_tag.get_text(strip=True)
            songs.append(f"{artist} - {title}")
    
    songs.reverse() # Oldest -> Newest
    return songs

def main():
    # Ensure output directory exists
    os.makedirs("docs", exist_ok=True)

    station_name, config = get_station_for_today()
    
    if not station_name:
        print("💤 No station scheduled for today. Exiting.")
        return

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    print(f"🚀 Scraping {station_name} for {today_str} ({config['start_hour']}:00 - {config['end_hour']}:00)")

    # Setup Headless Chrome
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    clean_playlist = []

    try:
        for hour in range(config['start_hour'], config['end_hour']):
            print(f"   ⏳ Processing {hour:02d}:00...")
            raw_songs = scrape_hour(driver, config['url'], today_str, hour)
            
            # --- PROXIMITY DEDUPLICATION ---
            for song in raw_songs:
                # Check last N songs to avoid overlaps/duplicates
                if song in clean_playlist[-DUPLICATE_LOOKBACK:]:
                    continue
                clean_playlist.append(song)

        # Write to file in docs/
        if clean_playlist:
            with open(config['output_file'], "w", encoding="utf-8") as f:
                f.write("\n".join(clean_playlist))
                f.write("\n") # End with newline
            print(f"✅ Saved {len(clean_playlist)} songs to {config['output_file']}")
        else:
            print("⚠️ No songs found.")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
