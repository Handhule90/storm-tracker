from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fetcher import combine_all_data

# Define the live RAMMB feed
AGENCY_CONFIG = {
    "CIRA_RAMMB": {
        "url": "https://rammb-data.cira.colostate.edu/tc_realtime/",
        "format": "CIRA_SCRAPE"
    }
}

app = FastAPI(title="Metcycres API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "Metcycres API is live. Visit /storms to get current tropical cyclones."}

@app.get("/storms")
def get_storms():
    try:
        data = combine_all_data(AGENCY_CONFIG)
        return data
    except Exception as e:
        return {"error": "Failed to fetch storm data", "details": str(e)}

@app.get("/health")
def health():
    return {"status": "ok"}
