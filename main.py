import os
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

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
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# Utility headers for LinkedIn public page requests
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/118.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def clean_text(text: Optional[str]) -> Optional[str]:
    if not text:
        return text
    return re.sub(r"\s+", " ", text).strip()


@app.get("/linkedin/scrape")
def scrape_linkedin(url: str = Query(..., description="Public LinkedIn profile URL")):
    if not url.startswith("http"):
        raise HTTPException(status_code=400, detail="Invalid URL")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Request failed: {e}")

    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail="Failed to fetch the page")

    soup = BeautifulSoup(resp.text, "lxml")

    # Basic meta tags
    title = soup.find("meta", property="og:title")
    description = soup.find("meta", property="og:description")
    image = soup.find("meta", property="og:image")

    # Fallbacks: page title and description
    page_title = soup.title.string if soup.title else None
    meta_desc = soup.find("meta", attrs={"name": "description"})

    # Attempt to extract visible name/headline sections (best effort on public pages)
    name = None
    headline = None

    # Common public selectors change often; try a few generic ones
    possible_name_selectors = [
        "h1",
        "h1.text-heading-xlarge",
        ".pv-text-details__left-panel h1",
        ".top-card-layout__title",
    ]
    for sel in possible_name_selectors:
        el = soup.select_one(sel)
        if el and clean_text(el.get_text()):
            name = clean_text(el.get_text())
            break

    possible_headline_selectors = [
        ".pv-text-details__left-panel .text-body-medium",
        ".top-card-layout__headline",
        "h2",
    ]
    for sel in possible_headline_selectors:
        el = soup.select_one(sel)
        if el and clean_text(el.get_text()):
            headline = clean_text(el.get_text())
            break

    # Experience and education (very best-effort; may be empty for public pages)
    experience = []
    for item in soup.select("section[id*=experience], section.experience, .experience__list li, .experience-section li"):
        text = clean_text(item.get_text(" "))
        if text and len(text) > 30:
            experience.append(text)
        if len(experience) >= 8:
            break

    education = []
    for item in soup.select("section[id*=education], section.education, .education__list li, .education-section li"):
        text = clean_text(item.get_text(" "))
        if text and len(text) > 20:
            education.append(text)
        if len(education) >= 8:
            break

    skills = []
    for item in soup.select("section[id*=skills] li, .pv-skill-category-list__skill, .skills-section li"):
        text = clean_text(item.get_text(" "))
        if text and 2 < len(text) < 80:
            skills.append(text)
        if len(skills) >= 25:
            break

    data = {
        "source": url,
        "status": "ok",
        "title": clean_text(title["content"]) if title and title.has_attr("content") else clean_text(page_title),
        "description": clean_text(description["content"]) if description and description.has_attr("content") else clean_text(meta_desc["content"]) if meta_desc and meta_desc.has_attr("content") else None,
        "image": image["content"] if image and image.has_attr("content") else None,
        "name": name,
        "headline": headline,
        "experience": experience,
        "education": education,
        "skills": skills,
    }

    return data


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
