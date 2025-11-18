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

@app.get("/")
def read_root():
    return {"message": "Hello from FastAPI Backend!"}

@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}

@app.get("/api/extract-profile")
def extract_profile(username: str = Query(..., description="X/Twitter username (without @) or full URL")):
    uname = username.strip()
    if uname.startswith('http://') or uname.startswith('https://'):
        # parse URL
        try:
            from urllib.parse import urlparse
            u = urlparse(uname)
            path = u.path.lstrip('/')
            uname = path.split('/')[0]
        except Exception:
            pass
    uname = uname.replace('@', '')
    if not uname or any(ch for ch in uname if ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_'):
        raise HTTPException(status_code=400, detail={"message": "Invalid username"})

    # Unofficial public endpoint (no API key) used as a fallback to get basic info
    # Note: This does not provide all fields compared to @the-convocation/twitter-scraper
    syndication_url = f"https://cdn.syndication.twimg.com/widgets/followbutton/info.json?screen_names={quote(uname)}"
    try:
        r = requests.get(syndication_url, timeout=12)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail={"message": "Failed to fetch profile (rate limited or not found)"})
        arr = r.json()
        if not arr:
            raise HTTPException(status_code=404, detail={"message": "Username not found"})
        item = arr[0]
        # Map fields
        display_name = item.get('name')
        screen_name = item.get('screen_name') or uname
        avatar = item.get('profile_image_url_https') or item.get('profile_image_url')
        followers = item.get('followers_count')
        # Try to guess banner via known pattern if id available
        user_id = item.get('id') or item.get('id_str')
        banner = None
        if user_id:
            banner = f"https://pbs.twimg.com/profile_banners/{user_id}/1500x500"
        # Heuristic verified
        is_blue_verified = bool(item.get('verified'))
        data = {
            'avatar': avatar,
            'banner': banner,
            'displayName': display_name,
            'username': screen_name,
            'bio': None,
            'location': None,
            'website': None,
            'joined': None,
            'followers': followers,
            'following': None,
            'isBlueVerified': is_blue_verified,
        }
        return data
    except HTTPException:
        raise
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
        "collections": []
    }
    
    try:
        # Try to import database module
        from database import db
        
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
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
