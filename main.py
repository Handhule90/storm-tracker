from fastapi import FastAPI
from fetcher import combine_all_data, AGENCY_CONFIG

app = FastAPI()

@app.get("/storms")
def get_storms():
    # Fetch and return all storms
    result = combine_all_data(AGENCY_CONFIG)
    return result
