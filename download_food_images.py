#!/usr/bin/env python3
"""Download Zimbabwean/African food images from Pixabay."""
import os
import requests
import json

API_KEY = "27970871-c474d538664ed4ce5ab390e01"
BASE_URL = "https://pixabay.com/api/"
MEDIA_DIR = "/home/cmazh/django/two_fish/media/menu/items"

# Ensure directory exists
os.makedirs(MEDIA_DIR, exist_ok=True)

# Image searches for menu items
SEARCHES = [
    # (search_term, filename, description)
    ("maize porridge pap", "sadza.jpg", "Sadza/Pap"),
    ("beef stew", "beef_stew.jpg", "Beef Stew"),
    ("chicken stew", "chicken_stew.jpg", "Chicken Stew"),
    ("collard greens", "muriwo.jpg", "Green Vegetables"),
    ("grilled t-bone steak", "tbone.jpg", "Grilled T-Bone"),
    ("chicken peanut sauce", "dovi_chicken.jpg", "Dovi Chicken"),
    ("grilled goat meat", "goat_meat.jpg", "Goat Meat"),
    ("fermented drink", "mageu.jpg", "Mageu Drink"),
    ("african food plate", "meal_combo.jpg", "Meal Combo"),
    ("rice beans", "rice_beans.jpg", "Rice & Beans"),
]

def download_image(url, filepath):
    """Download image from URL."""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        with open(filepath, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"  Error downloading: {e}")
        return False

def search_and_download():
    """Search Pixabay and download images."""
    downloaded = []
    failed = []
    
    for search_term, filename, description in SEARCHES:
        print(f"\nSearching: {search_term} ({description})")
        
        # Search Pixabay
        params = {
            "key": API_KEY,
            "q": search_term,
            "image_type": "photo",
            "per_page": 5,
            "safesearch": "true",
        }
        
        try:
            response = requests.get(BASE_URL, params=params, timeout=30)
            data = response.json()
            
            if not data.get("hits"):
                print(f"  No results found")
                failed.append((search_term, "No results"))
                continue
            
            # Get the first result's large image URL
            image_url = data["hits"][0]["largeImageURL"]
            filepath = os.path.join(MEDIA_DIR, filename)
            
            print(f"  Found: {data['hits'][0].get('tags', 'N/A')[:60]}...")
            print(f"  Downloading to: {filepath}")
            
            if download_image(image_url, filepath):
                downloaded.append((filename, description))
                print(f"  ✓ Success!")
            else:
                failed.append((search_term, "Download failed"))
                
        except Exception as e:
            print(f"  Error: {e}")
            failed.append((search_term, str(e)))
    
    # Summary
    print("\n" + "="*50)
    print(f"Downloaded: {len(downloaded)}/{len(SEARCHES)} images")
    print("\nSuccessful:")
    for filename, desc in downloaded:
        print(f"  ✓ {desc}: {filename}")
    
    if failed:
        print("\nFailed:")
        for term, reason in failed:
            print(f"  ✗ {term}: {reason}")

if __name__ == "__main__":
    search_and_download()
