import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime

# --- 1. CONFIGURATION ---
RAMMB_INDEX_URL = "https://rammb-data.cira.colostate.edu/tc_realtime/current_cyclones.asp"

# --- 2. HELPER FUNCTIONS ---

def get_active_storms():
    """
    Scrape the RAMMB index page to get all active storms with their storm ID and name.
    Returns a list of tuples: (storm_id, storm_name)
    """
    storms = []
    try:
        r = requests.get(RAMMB_INDEX_URL, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # The active storms are in <a> tags linking to storm pages
        # Example: <a href="storm.asp?storm_identifier=sh972026">SH972026 - INVEST</a>
        for a in soup.find_all("a", href=True):
            href = a['href']
            if "storm_identifier=" in href:
                storm_id = href.split("storm_identifier=")[1].upper()
                storm_name = a.text.split("-")[-1].strip()
                storms.append((storm_id, storm_name))
    except Exception as e:
        print(f"❌ Failed to fetch active storms: {e}")
    
    return storms

def get_storm_data(storm_id, storm_name):
    """
    Scrape an individual storm page to extract coordinates, max wind, and advisory time.
    Returns a GeoJSON Feature dictionary.
    """
    storm_url = f"https://rammb-data.cira.colostate.edu/tc_realtime/storm.asp?storm_identifier={storm_id}"
    try:
        r = requests.get(storm_url, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Find lat/lon table or info; RAMMB pages usually include something like:
        # <b>Latitude:</b> 15.0 N<br><b>Longitude:</b> 120.5 E<br><b>Max Wind:</b> 65 kt<br><b>Advisory Time:</b> 2025-11-15 06:00 UTC
        text = soup.get_text(separator="\n")
        
        lat, lon, max_wind, advisory_time = 0, 0, 0, datetime.utcnow().isoformat() + "Z"

        for line in text.split("\n"):
            line = line.strip()
            if line.lower().startswith("latitude:"):
                try:
                    value, hemi = line.split(":")[1].strip().split()
                    lat = float(value)
                    if hemi.upper() == "S":
                        lat *= -1
                except:
                    continue
            elif line.lower().startswith("longitude:"):
                try:
                    value, hemi = line.split(":")[1].strip().split()
                    lon = float(value)
                    if hemi.upper() == "W":
                        lon *= -1
                except:
                    continue
            elif line.lower().startswith("max wind:"):
                try:
                    max_wind = int(line.split(":")[1].strip().split()[0])
                except:
                    continue
            elif line.lower().startswith("advisory time:"):
                try:
                    advisory_time = datetime.strptime(
                        line.split(":")[1].strip(), "%Y-%m-%d %H:%M %Z"
                    ).isoformat() + "Z"
                except:
                    continue

        feature = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {
                "stormId": storm_id,
                "stormName": storm_name,
                "maxWindKts": max_wind,
                "advisoryTime": advisory_time,
                "source_agency": "RAMMB CIRA"
            }
        }
        return feature

    except Exception as e:
        print(f"❌ Failed to fetch storm data for {storm_name} ({storm_id}): {e}")
        return {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {
                "stormId": storm_id,
                "stormName": storm_name + " - NO DATA",
                "maxWindKts": 0,
                "advisoryTime": datetime.utcnow().isoformat() + "Z",
                "source_agency": "RAMMB CIRA"
            }
        }

# --- 3. AGGREGATION ---

def get_all_rammb_storms():
    """
    Fetches all active RAMMB storms and returns a GeoJSON FeatureCollection
    """
    features = []
    storms = get_active_storms()
    print(f"Found {len(storms)} active storm(s).")
    for storm_id, storm_name in storms:
        feature = get_storm_data(storm_id, storm_name)
        features.append(feature)
    
    geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_features": len(features),
            "source_type": "RAMMB CIRA Live TC Feed"
        },
        "features": features
    }
    return geojson

# --- 4. EXECUTION (for testing) ---
if __name__ == "__main__":
    data = get_all_rammb_storms()
    print(json.dumps(data, indent=2))
