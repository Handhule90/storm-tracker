import requests
import re
from datetime import datetime
from typing import List, Dict, Any

def get_cira_active_storms(index_url: str) -> List[Dict[str, Any]]:
    """
    Scrapes the RAMMB/CIRA TC Realtime index page to get all active storms.
    Returns a list of dicts: {stormId, stormName, atcf_url}
    """
    storm_list = []
    try:
        response = requests.get(index_url, timeout=10)
        response.raise_for_status()
        html = response.text

        # Regex to find storm identifiers and names on the page
        # Example: SH972026 - INVEST
        matches = re.findall(r'(SH|AL|EP|WP|IO)\d{6,8}\s*-\s*(.*?)<', html)
        for match in matches:
            identifier = match[0] + match[1][:6]  # e.g., SH972026
            name = match[1].strip()
            # Construct ATCF URL
            atcf_url = f"https://rammb-data.cira.colostate.edu/tc_realtime/products/{datetime.utcnow().year}/{identifier}/atcf/{identifier}_atcf.txt"
            storm_list.append({
                "stormId": identifier,
                "stormName": name,
                "atcf_url": atcf_url
            })
    except Exception as e:
        print(f"Error scraping RAMMB index page: {e}")
    
    return storm_list

def parse_atcf_text(url: str, stormId: str, stormName: str) -> List[Dict[str, Any]]:
    """
    Fetches the ATCF text file and extracts the latest fix.
    Returns as GeoJSON Feature.
    """
    features = []
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        lines = resp.text.strip().splitlines()

        for line in reversed(lines):
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 10 and parts[4] in ["ADJ","FIX","BEST"]:
                try:
                    lat_str = parts[6]
                    lon_str = parts[7]
                    max_wind = int(parts[8]) if parts[8].isdigit() else 0
                    time_str = parts[2]
                    # Convert lat/lon
                    lat = float(lat_str[:-1])/10.0 * (-1 if lat_str[-1]=='S' else 1)
                    lon = float(lon_str[:-1])/10.0 * (-1 if lon_str[-1]=='W' else 1)
                    advisory_time = datetime.strptime(time_str, '%Y%m%d%H').isoformat() + "Z"

                    feature = {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [lon, lat]},
                        "properties": {
                            "stormId": stormId,
                            "stormName": stormName,
                            "maxWindKts": max_wind,
                            "advisoryTime": advisory_time,
                            "source_agency": "CIRA_RAMMB"
                        }
                    }
                    features.append(feature)
                    break
                except:
                    continue
    except Exception as e:
        print(f"Error fetching/parsing ATCF for {stormName}: {e}")
    return features

def combine_all_data(AGENCY_CONFIG: dict) -> dict:
    """
    Main function to fetch and combine all storms.
    """
    all_features = []
    for agency, details in AGENCY_CONFIG.items():
        if details['format'] == "CIRA_SCRAPE":
            storms = get_cira_active_storms(details['url'])
            for s in storms:
                features = parse_atcf_text(s['atcf_url'], s['stormId'], s['stormName'])
                all_features.extend(features)
    return {
        "type": "FeatureCollection",
        "metadata": {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_features": len(all_features),
            "source_type": "RAMMB CIRA Live TC Feed"
        },
        "features": all_features
    }
