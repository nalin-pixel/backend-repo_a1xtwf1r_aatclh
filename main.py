import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import requests
from urllib.parse import quote

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TW_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://platform.twitter.com/",
}


@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


def _parse_username(value: str) -> str:
    uname = value.strip()
    if uname.startswith("http://") or uname.startswith("https://"):
        try:
            from urllib.parse import urlparse

            u = urlparse(uname)
            path = u.path.lstrip("/")
            uname = path.split("/")[0]
        except Exception:
            pass
    uname = uname.replace("@", "")
    return uname


@app.get("/api/extract-profile")
def extract_profile(username: str = Query(..., description="X/Twitter username (without @) or full URL")):
    uname = _parse_username(username)

    # Basic validation
    if not uname or any(ch for ch in uname if ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_"):
        raise HTTPException(status_code=400, detail={"message": "Invalid username"})

    # Unofficial public endpoint (no API key) used to get basic info
    url_primary = f"https://cdn.syndication.twimg.com/widgets/followbutton/info.json?screen_names={quote(uname)}"
    url_fallback = f"https://syndication.twitter.com/widgets/followbutton/info.json?screen_names={quote(uname)}"

    def fetch_info(url: str):
        return requests.get(url, headers=TW_HEADERS, timeout=12)

    try:
        r = fetch_info(url_primary)
        if r.status_code != 200:
            # try fallback domain
            r2 = fetch_info(url_fallback)
            r = r2
        if r.status_code != 200:
            # Provide clearer error to frontend
            if r.status_code in (403, 429):
                raise HTTPException(status_code=502, detail={"message": "Rate limited by X. Please try again in a minute."})
            elif r.status_code == 404:
                raise HTTPException(status_code=404, detail={"message": "Username not found"})
            else:
                raise HTTPException(status_code=502, detail={"message": f"Upstream error from X ({r.status_code})"})
        arr = r.json()
        if not arr:
            raise HTTPException(status_code=404, detail={"message": "Username not found"})
        item = arr[0]
        # Map fields
        display_name = item.get("name")
        screen_name = item.get("screen_name") or uname
        avatar = item.get("profile_image_url_https") or item.get("profile_image_url")
        followers = item.get("followers_count")
        # Guess banner via known pattern if id available
        user_id = item.get("id") or item.get("id_str")
        banner = None
        if user_id:
            banner = f"https://pbs.twimg.com/profile_banners/{user_id}/1500x500"
        # Heuristic verified
        is_blue_verified = bool(item.get("verified"))
        data = {
            "avatar": avatar,
            "banner": banner,
            "displayName": display_name,
            "username": screen_name,
            "bio": None,
            "location": None,
            "website": None,
            "joined": None,
            "followers": followers,
            "following": None,
            "isBlueVerified": is_blue_verified,
        }
        return data
    except HTTPException:
        raise
    except requests.Timeout:
        raise HTTPException(status_code=504, detail={"message": "Timeout contacting X. Please try again."})
    except Exception as e:
        raise HTTPException(status_code=500, detail={"message": str(e)[:200]})


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": [],
    }

    try:
        # Try to import database module
        from database import db

        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Connected"
            response["connection_status"] = "Connected"

            # Try to list collections to verify connectivity
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]  # Show first 10 collections
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except ImportError:
        response["database"] = "❌ Database module not found (run enable-database first)"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    # Check environment variables
    import os

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
