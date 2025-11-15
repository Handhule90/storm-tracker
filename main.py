# main.py
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fetcher import get_all_rammb_storms

app = FastAPI(
    title="Metcycres API",
    description="Live tropical cyclone data from RAMMB/CIRA",
    version="1.0"
)

@app.get("/", response_class=JSONResponse)
async def root():
    """
    Root endpoint: Returns all current active tropical cyclones in GeoJSON format.
    """
    try:
        data = get_all_rammb_storms()
        return JSONResponse(content=data)
    except Exception as e:
        return JSONResponse(
            content={
                "error": "Failed to fetch storm data",
                "details": str(e)
            },
            status_code=500
        )

@app.get("/health")
async def health():
    """
    Simple health check endpoint.
    """
    return {"status": "ok"}
