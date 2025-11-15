import requests
import json
import re
from datetime import datetime
from typing import Dict, List, Any, Tuple

# --- CONFIGURATION ---
CIRA_BASE_URL = "https://rammb-data.cira.colostate.edu/tc_realtime/"

# --- PARSERS ---

def get_active_storms(index_url: str) -> List[Tuple[str, str]]:
    """
    Scrape the CIRA index page for active storm identifiers and names.
    Returns a list of (identifier, storm_name) tuples.
    """
    storm_list = []
    try:
        response = requests.get(index_url, timeout=10)
        response.raise_for_status()
        html_content = response.text
        
        # Match links like: storm.asp?storm_identifier=AL012025">AL012025 - Tropical Storm ANDREA</a>
        pattern = re.compile(
            r'storm\.asp\?storm_identifier=([A-Z]{2}\d{4,6})">.*?-\s?(.*?)</a>', 
            re.IGNORECASE
        )
        matches = pattern.findall(html_content)
        for identifier, storm_name in matches:
            storm_list.append((identifier, storm_name.strip()))
    except Exception as e:
        print(f"❌ Error scraping CIRA index: {e}")
    
    return list(set(storm_list))

def parse_atcf_text(data_text: str, identifier: str, storm_name: str) -> List[Dict[str, Any]]:
    """
    Parse ATCF text file to get latest fix and optional track history.
    """
    features = []
    track_history = []
    
    for line in data_text.strip().split('\n'):
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 10 and parts[2].isdigit() and parts[4] in ["ADJ", "FIX", "BEST"]:
            try:
                # Latitude
                lat_val = float(parts[6][:-1])/10.0
                if parts[6].endswith('S'):
                    lat_val *= -1
                # Longitude
                lon_val = float(parts[7][:-1])/10.0
                if parts[7].endswith('W'):
                    lon_val *= -1
                # Max wind
                max_wind_kts = int(parts[8]) if parts[8].isdigit() else 0
                # Time
                advisory_time = datetime.strptime(parts[2], '%Y%m%d%H').isoformat() + "Z"
                
                # Add to track history
                track_history.append({
                    "coordinates": [lon_val, lat_val],
                    "maxWindKts": max_wind_kts,
                    "advisoryTime": advisory_time
                })
            except:
                continue

    if track_history:
        latest_fix = track_history[-1]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": latest_fix["coordinates"]},
            "properties": {
                "stormId": identifier,
                "stormName": storm_name,
                "maxWindKts": latest_fix["maxWindKts"],
                "advisoryTime": latest_fix["advisoryTime"],
                "trackHistory": track_history,
                "source_agency": "CIRA_RAMMB"
            }
        })
    else:
        # Fallback if parsing fails
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0,0]},
            "properties": {
                "stormId": identifier,
                "stormName": f"{storm_name} - NO DATA",
                "maxWindKts": 0,
                "advisoryTime": datetime.utcnow().isoformat() + "Z",
                "trackHistory": [],
                "source_agency": "CIRA_RAMMB"
            }
        })
    return features

def scrape_cira() -> List[Dict[str, Any]]:
    """
    Scrape all active storms from CIRA/RAMMB and return standardized GeoJSON features.
    """
    features = []
    active_storms = get_active_storms(CIRA_BASE_URL)
    
    for identifier, storm_name in active_storms:
        print(f"Processing {storm_name} ({identifier})")
        storm_url = f"{CIRA_BASE_URL}storm_experimental.asp?storm_identifier={identifier}"
        try:
            resp = requests.get(storm_url, timeout=10)
            resp.raise_for_status()
            html = resp.text
            
            # Look for ATCF text link
            match = re.search(
                r'<a href="(/tc_realtime/products/\d{4}/[A-Z]{2}\d{4,6}/atcf/[A-Z]{2}\d{4,6}_atcf.txt)">Latest Text File</a>', 
                html, re.IGNORECASE
            )
            if match:
                atcf_path = match.group(1).lstrip('/')
                atcf_url = f"https://rammb-data.cira.colostate.edu/{atcf_path}"
                atcf_resp = requests.get(atcf_url, timeout=10)
                atcf_resp.raise_for_status()
                features.extend(parse_atcf_text(atcf_resp.text, identifier, storm_name))
            else:
                print(f"⚠️ No ATCF link found for {storm_name}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Failed {storm_name}: {e}")
    
    return features

# --- AGGREGATION ---

def build_geojson() -> Dict[str, Any]:
    """
    Return a full GeoJSON FeatureCollection of all CIRA active storms.
    """
    features = scrape_cira()
    return {
        "type": "FeatureCollection",
        "metadata": {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_features": len(features),
            "source_type": "CIRA_RAMMB"
        },
        "features": features
    }

# --- EXECUTION ---

if __name__ == "__main__":
    geojson_result = build_geojson()
    print(json.dumps(geojson_result, indent=2))
