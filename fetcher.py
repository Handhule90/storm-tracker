import requests
import re
from datetime import datetime
from typing import List, Dict, Any

CIRA_BASE_URL = "https://rammb-data.cira.colostate.edu/tc_realtime/"

# --- 1. SCRAPE ACTIVE STORMS ---

def get_cira_active_storms(index_url: str) -> List[tuple]:
    """
    Scrape the RAMMB TC Realtime page for active storms.
    Returns a list of tuples: (storm_identifier, storm_name)
    """
    storm_list = []
    try:
        response = requests.get(index_url, timeout=10)
        response.raise_for_status()
        html_content = response.text

        # Match lines like: SH972026 - INVEST
        pattern = re.compile(r'([A-Z]{2}\d{6})\s*-\s*(\w+)')
        matches = pattern.findall(html_content)

        for identifier, name in matches:
            storm_list.append((identifier, name))

    except Exception as e:
        print(f"❌ Error scraping CIRA index: {e}")

    print(f"Found {len(storm_list)} active storm(s).")
    return storm_list

# --- 2. PARSE ATCF FIX ---

def parse_atcf_text(data_text: str, identifier: str, storm_name: str) -> List[Dict[str, Any]]:
    """
    Parse ATCF text file for the latest fix.
    Returns a list with one GeoJSON Feature.
    """
    features = []
    latest_fix = None

    for line in reversed(data_text.strip().split('\n')):
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 10 and parts[2].isdigit() and parts[4] in ["ADJ", "FIX", "BEST"]:
            try:
                # Max wind
                max_wind = int(parts[8]) if parts[8].isdigit() else 0

                # Latitude
                lat_str = parts[6]
                lat = float(lat_str[:-1]) / 10.0
                if lat_str.endswith('S'):
                    lat *= -1

                # Longitude
                lon_str = parts[7]
                lon = float(lon_str[:-1]) / 10.0
                if lon_str.endswith('W'):
                    lon *= -1

                # Advisory time
                time_str = parts[2]
                advisory_time = datetime.strptime(time_str, '%Y%m%d%H').isoformat() + "Z"

                latest_fix = {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "stormId": identifier,
                        "stormName": storm_name,
                        "maxWindKts": max_wind,
                        "advisoryTime": advisory_time,
                        "source_agency": "CIRA_RAMMB"
                    }
                }
                features.append(latest_fix)
                break
            except Exception:
                continue

    if not features:
        # If no fix found, fallback feature at [0,0]
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {
                "stormId": identifier,
                "stormName": storm_name + " - NO DATA",
                "maxWindKts": 0,
                "advisoryTime": datetime.utcnow().isoformat() + "Z",
                "source_agency": "CIRA_RAMMB"
            }
        })

    return features

# --- 3. SCRAPE STORM DATA ---

def scrape_cira_data() -> List[Dict[str, Any]]:
    """
    Scrape all active storms from RAMMB/CIRA and parse latest fixes.
    """
    active_storms = get_cira_active_storms(CIRA_BASE_URL)
    all_features = []

    for identifier, storm_name in active_storms:
        print(f"Processing {storm_name} ({identifier})...")
        storm_page_url = f"{CIRA_BASE_URL}storm_experimental.asp?storm_identifier={identifier}"
        try:
            response = requests.get(storm_page_url, timeout=10)
            response.raise_for_status()
            page_text = response.text

            # Find the ATCF text file link
            atcf_match = re.search(
                r'href="(/tc_realtime/products/\d{4}/[A-Z]{2}\d{6}/atcf/[A-Z]{2}\d{6}_atcf.txt)"',
                page_text
            )
            if atcf_match:
                atcf_url = f"https://rammb-data.cira.colostate.edu{atcf_match.group(1)}"
                atcf_response = requests.get(atcf_url, timeout=10)
                atcf_response.raise_for_status()
                features = parse_atcf_text(atcf_response.text, identifier, storm_name)
                all_features.extend(features)
                print(f"✅ Added {len(features)} feature(s) for {storm_name}.")
            else:
                print(f"⚠️ No ATCF link found for {storm_name}.")
        except Exception as e:
            print(f"❌ Failed to fetch data for {storm_name}: {e}")

    return all_features

# --- 4. COMBINE INTO GEOJSON ---

def combine_all_data() -> Dict[str, Any]:
    features = scrape_cira_data()
    return {
        "type": "FeatureCollection",
        "metadata": {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_features": len(features),
            "source_type": "CIRA_RAMMB Live Tropical Cyclone Data"
        },
        "features": features
    }

# --- 5. EXECUTE ---

if __name__ == "__main__":
    data = combine_all_data()
    import json
    print(json.dumps(data, indent=2))
