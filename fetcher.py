import requests
import json
import re
from datetime import datetime
from typing import Dict, List, Any, Tuple

# --- 1. CONFIGURATION: Public Data Feeds ---

CIRA_BASE_URL = "https://rammb-data.cira.colostate.edu/tc_realtime/"

AGENCY_CONFIG = {
    "CIRA_RAMMB": {
        "url": CIRA_BASE_URL,
        "format": "CIRA_SCRAPE"
    },
    "NOAA": {
        "url": "https://www.nhc.noaa.gov/json/AL_Current.json",
        "format": "GeoJSON"
    },
    "JTWC": {
        "url": "https://www.metoc.navy.mil/jtwc/products/abpw10cur.txt",
        "format": "ATCF Text"
    },
}

# --- 2. PARSING FUNCTIONS ---

def parse_noaa_geojson(data: Dict[str, Any], agency: str) -> List[Dict[str, Any]]:
    features = []
    try:
        for feature in data.get('features', []):
            feature['properties']['source_agency'] = agency
            features.append(feature)
    except Exception:
        # fallback mock feature
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {
                "stormName": f"TEST STORM ({agency})",
                "maxWindKts": 0,
                "advisoryTime": datetime.utcnow().isoformat() + "Z",
                "source_agency": agency
            }
        })
    return features

def parse_atcf_text(data_text: str, identifier: str, storm_name: str, agency: str) -> List[Dict[str, Any]]:
    features = []
    latest_fix = None
    for line in reversed(data_text.strip().split('\n')):
        parts = [p.strip() for p in line.split(',')]
        if len(parts) >= 10 and parts[2].isdigit() and (parts[4].strip() in ["ADJ", "FIX", "BEST"]):
            try:
                max_wind_kts = int(parts[8]) if parts[8].isdigit() else 0
                lat_str = parts[6].strip()
                lon_str = parts[7].strip()
                lat_val = float(lat_str[:-1]) / 10.0 * (-1 if lat_str.endswith('S') else 1)
                lon_val = float(lon_str[:-1]) / 10.0 * (-1 if lon_str.endswith('W') else 1)
                advisory_time = datetime.strptime(parts[2].strip(), '%Y%m%d%H').isoformat() + "Z"

                latest_fix = {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon_val, lat_val]},
                    "properties": {
                        "stormId": identifier,
                        "stormName": storm_name,
                        "maxWindKts": max_wind_kts,
                        "advisoryTime": advisory_time,
                        "source_agency": agency
                    }
                }
                features.append(latest_fix)
                break
            except Exception:
                continue
    if not features:
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {
                "stormName": f"{storm_name} ({agency}) - NO DATA",
                "maxWindKts": 0,
                "advisoryTime": datetime.utcnow().isoformat() + "Z",
                "source_agency": agency
            }
        })
    return features

def get_cira_active_storms(index_url: str) -> List[Tuple[str, str]]:
    storm_list = []
    try:
        response = requests.get(index_url, timeout=10)
        response.raise_for_status()
        html_content = response.text
        pattern = re.compile(r'storm\.asp\?storm_identifier=([A-Z]{2}\d{4,6})">(.*?)\s?-\s?(.*?)</a>')
        matches = pattern.findall(html_content)
        for identifier, full_name, name_only in matches:
            final_name = name_only.strip() if name_only.strip() else full_name.strip()
            storm_list.append((identifier, final_name))
    except Exception:
        pass
    return list(set(storm_list))

def scrape_cira_data(agency_details: Dict[str, Any], agency: str) -> List[Dict[str, Any]]:
    base_url = agency_details['url']
    active_storms = get_cira_active_storms(base_url)
    all_features = []
    for identifier, storm_name in active_storms:
        storm_page_url = f"{base_url}storm_experimental.asp?storm_identifier={identifier}"
        try:
            storm_response = requests.get(storm_page_url, timeout=10)
            storm_response.raise_for_status()
            atcf_link_match = re.search(
                r'<a href="(/tc_realtime/products/\d{4}/[A-Z]{2}\d{4,6}/atcf/[A-Z]{2}\d{4,6}_atcf.txt)">Latest Text File</a>',
                storm_response.text, re.IGNORECASE
            )
            if atcf_link_match:
                relative_atcf_path = atcf_link_match.group(1).lstrip('/')
                full_atcf_url = f"https://rammb-data.cira.colostate.edu/{relative_atcf_path}"
                atcf_response = requests.get(full_atcf_url, timeout=10)
                atcf_response.raise_for_status()
                features = parse_atcf_text(atcf_response.text, identifier, storm_name, agency)
                all_features.extend(features)
        except Exception:
            all_features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [0, 0]},
                "properties": {
                    "stormName": f"{storm_name} ({agency}) - NO DATA",
                    "maxWindKts": 0,
                    "advisoryTime": datetime.utcnow().isoformat() + "Z",
                    "source_agency": agency
                }
            })
    return all_features

# --- 3. AGGREGATION FUNCTION ---

def combine_all_data(config: Dict[str, Any]) -> Dict[str, Any]:
    all_features = []
    for agency, details in config.items():
        try:
            if details['format'] == "CIRA_SCRAPE":
                features = scrape_cira_data(details, agency)
            elif details['format'] == "GeoJSON":
                response = requests.get(details['url'], timeout=15)
                response.raise_for_status()
                data = response.json()
                features = parse_noaa_geojson(data, agency)
            elif details['format'] == "ATCF Text":
                # Placeholder/mock for JTWC until full parser is implemented
                features = [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [50, 50]},
                    "properties": {
                        "stormId": "WP012025",
                        "stormName": "MOCK STORM JTWC",
                        "maxWindKts": 85,
                        "advisoryTime": datetime.utcnow().isoformat() + "Z",
                        "source_agency": agency
                    }
                }]
            else:
                features = []
            all_features.extend(features)
        except Exception:
            continue
    return {
        "type": "FeatureCollection",
        "metadata": {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_features": len(all_features),
            "source_type": "Aggregated Tropical Cyclone Feeds"
        },
        "features": all_features
    }
