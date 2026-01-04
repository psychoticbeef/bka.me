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
    Parses simple ISO duration strings like "P-1D", "P2D".
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

def find_yearly_patterns(years):
    """
    Analyzes a list of sorted years and compresses them into 
    (start_year, interval, count) tuples.
    
    Returns a list of dicts: 
    [{'start': 1999, 'interval': 11, 'count': 3}, {'start': 2085, 'interval': 0, 'count': 1}]
    """
    years = sorted(list(set(years))) # Ensure unique and sorted
    patterns = []
    
    while years:
        start_year = years[0]
        
        # If only one year left, it's a single instance
        if len(years) == 1:
            patterns.append({'start': start_year, 'interval': 0, 'count': 1})
            years.pop(0)
            continue
            
        # Try to find the longest arithmetic progression starting at years[0]
        best_sequence = [start_year]
        
        # Check every subsequent year to establish a potential interval
        for i in range(1, len(years)):
            next_year = years[i]
            diff = next_year - start_year
            
            # Build a candidate sequence based on this difference
            current_sequence = [start_year, next_year]
            current_val = next_year
            
            # Look ahead for more matches
            while (current_val + diff) in years:
                current_val += diff
                current_sequence.append(current_val)
            
            # If this sequence is longer than what we found before, keep it
            if len(current_sequence) > len(best_sequence):
                best_sequence = current_sequence

        # Process the best sequence found
        if len(best_sequence) > 1:
            # We found a pattern (e.g., 1999, 2010, 2021 -> Interval 11)
            interval = best_sequence[1] - best_sequence[0]
            patterns.append({
                'start': start_year, 
                'interval': interval, 
                'count': len(best_sequence)
            })
            # Remove these years from the processing list
            for y in best_sequence:
                years.remove(y)
        else:
            # No pattern found starting with this year
            patterns.append({'start': start_year, 'interval': 0, 'count': 1})
            years.pop(0)
            
    return patterns

def create_pattern_event(title, start_date, uid, interval, count):
    """
    Creates an event using RRULE FREQ=YEARLY with INTERVAL.
    """
    event = Event()
    event.add('summary', title)
    event.add('dtstart', start_date)
    event.add('dtend', start_date + datetime.timedelta(days=1))
    event.add('dtstamp', datetime.datetime.now(datetime.timezone.utc))
    event.add('uid', uid)
    
    if interval > 0 and count > 1:
        # Use COUNT to be precise about how many times it repeats
        event.add('rrule', {'freq': 'yearly', 'interval': interval, 'count': count})
        
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
        # 1. FIXED HOLIDAYS (Standard Yearly RRULE)
        # ---------------------------------------------------------
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
                # Standard repetition until end of century
                event.add('rrule', {'freq': 'yearly', 'until': datetime.date(END_YEAR, 12, 31)})
                
                cal.add_component(event)

        # ---------------------------------------------------------
        # 2. VARIABLE HOLIDAYS (Compressed via Pattern Matching)
        # ---------------------------------------------------------
        if 'easter' in config:
            for title, details in config['easter'].items():
                offset = parse_iso_duration(details['diff'])
                
                # Step A: Collect all dates and group by "Month-Day"
                date_buckets = {}
                for year in range(START_YEAR, END_YEAR + 1):
                    easter_date = easter(year)
                    base_date = easter_date - datetime.timedelta(days=1)
                    final_date = base_date + offset
                    
                    key = (final_date.month, final_date.day)
                    if key not in date_buckets:
                        date_buckets[key] = []
                    date_buckets[key].append(year) # Store YEAR only

                # Step B: Find patterns inside each bucket
                for (month, day), years_list in date_buckets.items():
                    
                    patterns = find_yearly_patterns(years_list)
                    
                    for pat in patterns:
                        start_year = pat['start']
                        interval = pat['interval']
                        count = pat['count']
                        
                        start_date = datetime.date(start_year, month, day)
                        
                        # Generate a deterministic UID based on the rule parameters
                        # This ensures that "1999 + every 11 years" always gets the same UID
                        uid_key = f"rule_{month:02d}{day:02d}_{start_year}_{interval}"
                        uid = get_or_create_persistent_uid(details, uid_key)
                        
                        event = create_pattern_event(title, start_date, uid, interval, count)
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
