from fastapi import FastAPI
from fetcher import combine_all_data, AGENCY_CONFIG
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Metcycres API", version="1.0")

# Optional: allow cross-origin requests (useful if your frontend is separate)
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
    """
    Fetches all active tropical cyclones from RAMMB (CIRA) and combines them
    into a single GeoJSON FeatureCollection.
    """
    try:
        data = combine_all_data(AGENCY_CONFIG)
        return data
    except Exception as e:
        # Return error info without crashing the server
        return {
            "error": "Failed to fetch storm data",
            "details": str(e)
        }

# Optional: Health check endpoint
@app.get("/health")
def health():
    return {"status": "ok"}
