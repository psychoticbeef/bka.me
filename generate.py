import json
import datetime
import uuid
from pathlib import Path
from dateutil.easter import easter
from icalendar import Calendar, Event

# Configuration
INPUT_FILE = Path("calendar.json")
OUTPUT_DIR = Path("./docs")

# Timeframe
START_YEAR = 1999
END_YEAR = 2099

def parse_iso_duration(duration_str):
    """
    Parses simple ISO duration strings like "P-1D", "P2D", "P40D".
    """
    duration_str = duration_str.replace("P", "")
    days = int(duration_str.replace("D", ""))
    return datetime.timedelta(days=days)

def get_or_create_persistent_uid(details_dict, key_name):
    """
    Retrieves a UID or generates a new one.
    """
    if 'persistent_uids' not in details_dict:
        details_dict['persistent_uids'] = {}
    
    if key_name not in details_dict['persistent_uids']:
        details_dict['persistent_uids'][key_name] = str(uuid.uuid4())
        
    return details_dict['persistent_uids'][key_name]

def create_master_event(title, all_dates, uid):
    """
    Creates a single master event on the first date, 
    with all subsequent dates listed in RDATE.
    """
    # Sort just in case
    all_dates.sort()
    
    first_date = all_dates[0]
    subsequent_dates = all_dates[1:]
    
    event = Event()
    event.add('summary', title)
    event.add('dtstart', first_date)
    # For all-day events, dtend is usually dtstart + 1 day
    event.add('dtend', first_date + datetime.timedelta(days=1))
    event.add('dtstamp', datetime.datetime.now(datetime.timezone.utc))
    event.add('uid', uid)
    
    # Add all other years as RDATEs
    if subsequent_dates:
        event.add('rdate', subsequent_dates, parameters={'VALUE': 'DATE'})
        
    return event

def main():
    if not INPUT_FILE.exists():
        print("Error: calendar.json not found.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for region, config in data.items():
        print(f"Processing {region}...")
        cal = Calendar()
        cal.add('prodid', f'-//psychoticbeef//German Holidays//DE')
        cal.add('version', '2.0')
        cal.add('x-wr-calname', f'Feiertage {region}')

        # ---------------------------------------------------------
        # 1. FIXED HOLIDAYS (RRULE)
        # ---------------------------------------------------------
        # We stick to RRULE here because it is semantically correct 
        # for "Every year on this specific date".
        if 'repeat' in config:
            for title, details in config['repeat'].items():
                month = int(details['date'][0:2])
                day = int(details['date'][2:4])
                start_date = datetime.date(START_YEAR, month, day)
                
                uid = get_or_create_persistent_uid(details, 'master_fixed_uid')
                
                event = Event()
                event.add('summary', title)
                event.add('dtstart', start_date)
                event.add('dtend', start_date + datetime.timedelta(days=1))
                event.add('dtstamp', datetime.datetime.now(datetime.timezone.utc))
                event.add('uid', uid)
                event.add('rrule', {'freq': 'yearly', 'until': datetime.date(END_YEAR, 12, 31)})
                
                cal.add_component(event)

        # ---------------------------------------------------------
        # 2. VARIABLE HOLIDAYS (RDATE) - The "All-in-One" Method
        # ---------------------------------------------------------
        if 'easter' in config:
            for title, details in config['easter'].items():
                offset = parse_iso_duration(details['diff'])
                
                # 1. Collect ALL dates for this holiday from 1999 to 2099
                holiday_dates = []
                for year in range(START_YEAR, END_YEAR + 1):
                    easter_date = easter(year)
                    # Base = Saturday before Easter (Easter - 1 day)
                    base_date = easter_date - datetime.timedelta(days=1)
                    final_date = base_date + offset
                    holiday_dates.append(final_date)
                
                # 2. Get a single UID for this holiday type
                uid = get_or_create_persistent_uid(details, 'master_variable_uid')
                
                # 3. Create ONE event with 100 RDATE entries
                event = create_master_event(title, holiday_dates, uid)
                cal.add_component(event)

        # Write ICS file
        output_path = OUTPUT_DIR / f"{region.lower()}.ics"
        with open(output_path, 'wb') as f:
            f.write(cal.to_ical())

    # Save updated JSON
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, sort_keys=True)
    
    print("Done.")

if __name__ == "__main__":
    main()