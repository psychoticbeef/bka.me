import json
import datetime
from pathlib import Path
from dateutil.easter import easter
from dateutil.relativedelta import relativedelta
from icalendar import Calendar, Event, Timezone

# Configuration
INPUT_FILE = Path("calendar.json")
OUTPUT_DIR = Path("./docs")
YEARS_TO_PROCESS = [datetime.date.today().year + i for i in range(-1, 3)] # Current year -1 to +2

def parse_iso_duration(duration_str):
    """
    Parses simple ISO duration strings like "P-1D", "P2D", "P40D".
    """
    duration_str = duration_str.replace("P", "")
    days = int(duration_str.replace("D", ""))
    return datetime.timedelta(days=days)

def get_or_create_uid(data_dict, key):
    """
    Preserves existing UIDs or generates new unique ones.
    """
    if key not in data_dict:
        # Generate a modern, random UUID
        import uuid
        data_dict[key] = str(uuid.uuid4())
    return data_dict[key]

def create_event(title, date_obj, uid):
    """
    Helper to create an iCal Event object.
    """
    event = Event()
    event.add('summary', title)
    event.add('dtstart', date_obj)
    event.add('dtend', date_obj + datetime.timedelta(days=1))
    event.add('dtstamp', datetime.datetime.now(datetime.timezone.utc))
    event.add('uid', uid)
    return event

def main():
    if not INPUT_FILE.exists():
        print("Error: calendar.json not found.")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for region, config in data.items():
        print(f"Processing {region}...")
        cal = Calendar()
        cal.add('prodid', f'-//psychoticbeef//German Holidays//DE')
        cal.add('version', '2.0')
        cal.add('x-wr-calname', f'Feiertage {region}')

        # 1. Handle Fixed Repeating Events (e.g., New Year)
        if 'repeat' in config:
            for title, details in config['repeat'].items():
                # We add them for the requested years to make them distinct instances
                # or we can use RRULE. Your PHP used RRULE for fixed days.
                # Let's use RRULE for fixed days as per your original logic.
                
                base_year = YEARS_TO_PROCESS[0]
                month = int(details['date'][0:2])
                day = int(details['date'][2:4])
                start_date = datetime.date(base_year, month, day)
                
                uid = get_or_create_uid(details, 'uid')
                
                event = create_event(title, start_date, uid)
                event.add('rrule', {'freq': 'yearly'})
                cal.add_component(event)

        # 2. Handle Easter-based (Variable) Events
        if 'easter' in config:
            for title, details in config['easter'].items():
                offset = parse_iso_duration(details['diff'])
                
                for year in YEARS_TO_PROCESS:
                    # Calculate Easter Sunday (Standard Western/Gregorian)
                    easter_date = easter(year)
                    
                    # Apply offset
                    # Note: Your JSON has logic like "Karfreitag = P-1D". 
                    # In reality Karfreitag is -2 days from Sunday.
                    # If your JSON assumes Base = Saturday, we adjust here:
                    # Adjusting base to match your legacy JSON logic (Base = Saturday)
                    base_date = easter_date - datetime.timedelta(days=1)
                    
                    final_date = base_date + offset
                    
                    # Manage UID per year
                    uid_key = f"uid_{year}"
                    uid = get_or_create_uid(details, uid_key)
                    
                    event = create_event(title, final_date, uid)
                    cal.add_component(event)

        # Write ICS file
        output_path = OUTPUT_DIR / f"{region.lower()}.ics"
        with open(output_path, 'wb') as f:
            f.write(cal.to_ical())

    # Save updated JSON (with new UIDs)
    with open(INPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, sort_keys=True)
    
    print("Done.")

if __name__ == "__main__":
    main()
