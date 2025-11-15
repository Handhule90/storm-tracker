import requests
import json
import re
from datetime import datetime
from typing import Dict, List, Any, Tuple

# --- 1. CONFIGURATION: Public Data Feeds ---
# Replaced placeholders with the functional CIRA/RAMMB scrape target.
# Other agencies are kept as examples but are expected to fail without real parsing logic.

CIRA_BASE_URL = "https://rammb-data.cira.colostate.edu/tc_realtime/"

AGENCY_CONFIG = {
    # CIRA/RAMMB: The new target, scraped via multi-step process
    "CIRA_RAMMB": {
        "url": CIRA_BASE_URL,
        "format": "CIRA_SCRAPE"
    },
    # Placeholder for a true GeoJSON feed (requires finding an active link)
    "NOAA": {
        "url": "https://www.nhc.noaa.gov/json/AL_Current.json", 
        "format": "GeoJSON"
    },
    # Placeholder for ATCF Text data (JTWC)
    "JTWC": {
        "url": "https://www.metoc.navy.mil/jtwc/products/abpw10cur.txt", 
        "format": "ATCF Text"
    },
}

# --- 2. TRANSFORMATION: Standardize Data (GeoJSON Format) ---

def parse_noaa_geojson(data: Dict[str, Any], agency: str) -> List[Dict[str, Any]]:
    """
    Parses a NOAA-like GeoJSON response into a list of standardized GeoJSON Features.
    (This function remains a placeholder/example for GeoJSON data)
    """
    features = []
    
    # Simple example of parsing if a GeoJSON feed is active
    try:
        for feature in data.get('features', []):
            feature['properties']['source_agency'] = agency
            features.append(feature)
    except Exception as e:
        print(f"Error parsing {agency} GeoJSON: {e}")
        pass
        
    # Placeholder if the link is down or data is empty
    if not features:
        print(f"⚠️ {agency} GeoJSON link appears inactive or empty. Using mock data.")
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
    """
    Parses the standard ATCF text format (used by JTWC, CIRA, etc.) to extract the latest fix.
    
    ATCF line fields are comma-delimited or fixed width. We assume the standard ATCF format.
    We look for the latest FIX or ADVISORY (ADJ) line to get the current position and intensity.
    
    The relevant fields (indices approximate based on common format):
    [2]: Date/Time (YYYYMMDDHH)
    [6]: Latitude (e.g., 150N -> 15.0)
    [7]: Longitude (e.g., 0700W -> -70.0)
    [8]: Max Wind (Knots)
    """
    features = []
    latest_fix = None
    
    # Iterate lines backwards to find the LATEST fix efficiently
    for line in reversed(data_text.strip().split('\n')):
        parts = [p.strip() for p in line.split(',')]
        
        # Check for a complete line with the expected number of fields for a fix
        if len(parts) >= 10 and parts[2].isdigit() and (parts[4].strip() in ["ADJ", "FIX", "BEST"]):
            
            try:
                # 1. Parse Max Wind (Knots)
                max_wind_kts = int(parts[8]) if parts[8].isdigit() else 0
                
                # 2. Parse Lat/Lon
                lat_str = parts[6].strip()
                lon_str = parts[7].strip()
                
                # Convert '150N'/'150S' to float latitude
                lat_val = float(lat_str[:-1]) / 10.0
                if lat_str.endswith('S'):
                    lat_val *= -1
                    
                # Convert '0700W'/'0700E' to float longitude
                lon_val = float(lon_str[:-1]) / 10.0
                if lon_str.endswith('W'):
                    lon_val *= -1
                
                # 3. Parse Time (YYYYMMDDHH)
                time_str = parts[2].strip()
                advisory_time = datetime.strptime(time_str, '%Y%m%d%H').isoformat() + "Z"

                latest_fix = {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon_val, lat_val]}, # GeoJSON is [lon, lat]
                    "properties": {
                        "stormId": identifier,
                        "stormName": storm_name,
                        "maxWindKts": max_wind_kts,
                        "advisoryTime": advisory_time,
                        "source_agency": agency
                    }
                }
                
                # Found the latest fix, break the loop
                features.append(latest_fix)
                break 
                
            except Exception as e:
                # print(f"Error parsing ATCF line: {e}") # Debugging
                continue # Try the next line
                
    if not features:
        print(f"❌ Failed to find a valid ATCF fix for {storm_name} ({identifier}).")
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
    """
    Scrapes the CIRA/RAMMB index page to find active storm identifiers and names.
    Returns a list of (identifier, storm_name) tuples.
    """
    print("Scraping CIRA/RAMMB index page for active storms...")
    storm_list = []
    
    try:
        response = requests.get(index_url, timeout=10)
        response.raise_for_status()
        html_content = response.text
        
        # Regex to find links to storm pages in the format:
        # <a href="storm.asp?storm_identifier=AL012025">AL012025 - Tropical Storm ANDREA</a>
        # The storm identifier is a 8-character code (2 letters, 4 numbers, usually a year, but sometimes 6 numbers total)
        # We look for AL012025 or SH972025 style IDs
        # The regex captures: (IDENTIFIER) and (STORM NAME)
        pattern = re.compile(r'storm\.asp\?storm_identifier=([A-Z]{2}\d{4,6})">(.*?)\s?-\s?(.*?)</a>')
        matches = pattern.findall(html_content)
        
        for identifier, full_name, name_only in matches:
            # Full name might be "AL012025 - Tropical Storm ANDREA", we use the full text or just the name part
            final_name = name_only.strip() if name_only.strip() else full_name.strip()
            storm_list.append((identifier, final_name))
            
    except Exception as e:
        print(f"❌ Error scraping CIRA index: {e}")
        
    # Remove duplicates by converting to set and back to list, maintaining order roughly
    unique_storms = list(set(storm_list))
    print(f"Found {len(unique_storms)} unique storm(s).")
    return unique_storms


def scrape_cira_data(agency_details: Dict[str, Any], agency: str) -> List[Dict[str, Any]]:
    """
    Orchestrates the multi-step scrape for CIRA/RAMMB data.
    """
    base_url = agency_details['url']
    active_storms = get_cira_active_storms(base_url)
    all_features = []
    
    for identifier, storm_name in active_storms:
        print(f"  Processing storm: {storm_name} ({identifier})")
        
        # 1. Construct the URL for the storm's experimental page
        storm_page_url = f"{base_url}storm_experimental.asp?storm_identifier={identifier}"
        
        try:
            # 2. Fetch the storm's experimental page to find the ATCF link
            storm_response = requests.get(storm_page_url, timeout=10)
            storm_response.raise_for_status()
            
            # 3. Regex to find the "Latest Text File" link for the ATCF data (Dvorak Fix-Based Wind Radii)
            # The pattern looks for a link that has "Latest Text File" text and captures the relative path in href
            # Example link pattern: <a href="products/2025/AL012025/atcf/AL012025_atcf.txt">Latest Text File</a>
            # The regex is designed to find /products/YEAR/ID/atcf/ID_atcf.txt or similar paths.
            
            # Look for the link associated with "Latest Text File"
            # It should be near the Dvorak/Wind Radii section, but we'll use a broad capture.
            # We are looking for the 'atcf' folder in the path, which is a common giveaway.
            atcf_link_match = re.search(
                r'<a href="(/tc_realtime/products/\d{4}/[A-Z]{2}\d{4,6}/atcf/[A-Z]{2}\d{4,6}_atcf.txt)">Latest Text File</a>', 
                storm_response.text, 
                re.IGNORECASE
            )
            
            if not atcf_link_match:
                # If the specific atcf link is not found, try a more general approach, e.g., to the TC Vitals file
                # This is a fallback and may not always contain the fix data in the exact format
                atcf_link_match = re.search(
                    r'<a href="(/tc_realtime/products/\d{4}/[A-Z]{2}\d{4,6}/tc_vitals/[A-Z]{2}\d{4,6}.txt)">Latest Text File</a>', 
                    storm_response.text, 
                    re.IGNORECASE
                )
            
            if atcf_link_match:
                relative_atcf_path = atcf_link_match.group(1).lstrip('/') # Remove leading / if present
                full_atcf_url = f"https://rammb-data.cira.colostate.edu/{relative_atcf_path}"
                
                print(f"    Found ATCF URL: {full_atcf_url}")
                
                # 4. Fetch the ATCF data file
                atcf_response = requests.get(full_atcf_url, timeout=10)
                atcf_response.raise_for_status()
                
                # 5. Parse the ATCF data
                features = parse_atcf_text(atcf_response.text, identifier, storm_name, agency)
                all_features.extend(features)
                print(f"    ✅ Success. Added {len(features)} feature(s) from CIRA.")
                
            else:
                print(f"    ⚠️ Could not find the 'Latest Text File' ATCF link for {storm_name}.")
                
        except requests.exceptions.RequestException as e:
            print(f"    ❌ Failed to fetch storm data for {storm_name}. Error: {e}")
            
    return all_features


# --- 3. AGGREGATION: Fetch and Combine ---

def combine_all_data(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fetches data from all configured agencies, transforms it, and combines it
    into a single GeoJSON FeatureCollection.
    """
    all_features = []
    
    for agency, details in config.items():
        try:
            print(f"\nProcessing data from {agency} ({details['format']})...")
            
            # 1. Fetch & Scrape/Transform
            if details['format'] == "CIRA_SCRAPE":
                features = scrape_cira_data(details, agency)
                
            elif details['format'] == "GeoJSON":
                response = requests.get(details['url'], timeout=15)
                response.raise_for_status()
                data = response.json()
                features = parse_noaa_geojson(data, agency)

            elif details['format'] == "ATCF Text":
                # For JTWC ATCF, we treat the main link as the ATCF text file itself, 
                # but we need to know the storm ID/name to pass to the parser.
                # Since the URL is generic, we use placeholder logic or a different parser.
                
                # Using placeholder for full JTWC ATCF text parsing complexity
                print(f"⚠️ {agency} requires complex ATCF parsing logic. Using mock data.")
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
            # Print success message for non-CIRA sources only if data was actually fetched/mocked
            if details['format'] != "CIRA_SCRAPE" and features:
                print(f"✅ Success. Added {len(features)} feature(s) from {agency}.")

        except requests.exceptions.RequestException as e:
            print(f"❌ Failed to fetch data for {agency}. Error: {e}")
            
    # 3. Combine into a single GeoJSON FeatureCollection
    final_geojson = {
        "type": "FeatureCollection",
        "metadata": {
            "updated_at": datetime.utcnow().isoformat() + "Z",
            "total_features": len(all_features),
            "source_type": "Aggregated Tropical Cyclone Feeds"
        },
        "features": all_features
    }
    
    return final_geojson

# --- 4. EXECUTION ---

# Run the aggregation process
combined_api_result = combine_all_data(AGENCY_CONFIG)

# Print the final result
print("\n" + "="*50)
print("FINAL UNIFIED GEOJSON API RESPONSE")
print("="*50)
# Use json.dumps for pretty printing the result
print(json.dumps(combined_api_result, indent=2))

# Inspect the result
print("\n--- Summary ---")
print(f"Total features combined: {combined_api_result['metadata']['total_features']}")
# Safely construct the list of sources
sources = set(f['properties']['source_agency'] for f in combined_api_result['features'] if 'properties' in f and 'source_agency' in f['properties'])
print(f"Sources included: {', '.join(sources)}")
