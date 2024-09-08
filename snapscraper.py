import requests
import json
import time
import sys
import math, operator

from io import BytesIO
from PIL import Image, ImageChops
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

WEAR_LEVELS = {
    "NM": 0,
    "LP": 1,
    "MP": 2,
    "HP": 3,
    "DMG": 4
}

MIN_ACCEPTABLE_CONDITION = WEAR_LEVELS.get("MP")

# ECOMMERCE_PROVIDERS = {
#     "shopify": {
#         "unique_image_identifier": "shopify",
#         "add_cart_endpoint": "/cart/add.js?quantity=1&id="
#     },
#     "bigcommerce": {
#         "unique_image_identifier": "bigcommerce",
#         "add_cart_endpoint": None
#     },
#     "crystalcommerce": {
#         "unique_image_identifier": "digitaloceanspaces",
#         "add_cart_endpoint": None
#     },
#     "conduct": {
#         "unique_image_identifier": "conduct",
#         "add_cart_endpoint": None
#     }
# }

def rmsdiff(im1, im2):
    "Calculate the root-mean-square difference between two images"
    diff = ImageChops.difference(im1, im2)
    h = diff.histogram()
    sq = (value*((idx%256)**2) for idx, value in enumerate(h))
    sum_of_squares = sum(sq)
    rms = math.sqrt(sum_of_squares/float(im1.size[0] * im1.size[1]))
    return rms

def same_set(set1: str, set2: str):
    loweredSet1 = str.lower(set1)
    loweredSet2 = str.lower(set2)
    return [c for c in loweredSet1 if c.isalpha()] == [c for c in loweredSet2 if c.isalpha()]



def listing_to_cart(store_base_url: str, sku_variant_id):
    # Going to assume that snapcaster will only link to in-stock products
    # Shopfiy allows you to add an out-of-stock card to cart as longs as the 
    # variant id is associated with a product.
    response =  request_session.post(f'{store_base_url}/cart/add.js?quantity=1&id={sku_variant_id}')
    if response.status_code != 200:
        return False
    
    active_carts.add(f"{store_base_url}/cart")
    return True

def store_url_from_listing(listing: dict[str, str]):
    return listing['link'].split('/products/')[0]

request_session = requests.Session()
active_carts = set()
total_cost = 0
script_start_time = time.time()

# full_deck_url = sys.argv[1]
full_deck_id = "abcdefghijklmnopqrstuvwxyz"
full_deck_url = "https://www.moxfield.com/decks/{full_deck_id}"

if full_deck_url.startswith("https://www.moxfield.com/decks/"):
    deck_id = full_deck_url.split("decks/")[1]
else:
    deck_id = full_deck_url

headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'en-US,en;q=0.9',
    'authorization': 'Bearer undefined',
    'origin': 'https://www.moxfield.com',
    'priority': 'u=1, i',
    'referer': 'https://www.moxfield.com/',
    'sec-ch-ua': '"Chromium";v="128", "Not;A=Brand";v="24", "Google Chrome";v="128"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-site',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    'x-moxfield-version': '2024.09.07.1',
}

# Scrape moxfield for deck list and image data
print(f"{time.time() - script_start_time:.2f}s - [Moxfield] - Scraping Deck: '{deck_id}'")
moxfield_json = requests.get(f'https://api2.moxfield.com/v3/decks/all/{deck_id}', headers=headers)
if moxfield_json.status_code != 200:
    sys.exit(f"{time.time() - script_start_time:.2f}s - [Moxfield] - Response Status != 200: '{deck_id}'")
moxfield_response = json.loads(moxfield_json.text)
number_of_cards = len(moxfield_response["boards"]["mainboard"]["cards"].keys()) + len(moxfield_response["boards"]["commanders"]["cards"].keys())
print(f"{time.time() - script_start_time:.2f}s - [Moxfield] - Deck Response Received: {number_of_cards} Cards To Find")

moxfield_cards = {}
print(f"{time.time() - script_start_time:.2f}s - [Moxfield] - Parsing Response Data")
card_list = list(moxfield_response["boards"]["mainboard"]["cards"].values()) + list(moxfield_response["boards"]["commanders"]["cards"].values())
for card in card_list:
    data = card["card"]

    moxfield_card = {}
    moxfield_card["isFoil"] = card["isFoil"]
    moxfield_card["cardSet"] = data["set_name"]
    moxfield_card["cardName"] = data["name"]
    moxfield_card["cardImageUrl"] = f"https://assets.moxfield.net/cards/card-{data['id']}-normal.webp?{data['image_seq']}"
    moxfield_cards[data["name"]] = moxfield_card

# Use the image data as a filter during snapcaster step


card_names = moxfield_cards.keys()

card_image_set_map = {card_name:{} for card_name in card_names}
card_miss_stats = {card_name:{"nerdz": 0, "name": 0, "foil": 0, "art_series": 0, "shopify": 0, "condition": 0, "image": 0, "image_requests": 0, "valid_listings": 0} for card_name in card_names}
request_time = script_start_time
card_num = 0
for card_name, card_data in moxfield_cards.items():
    try:
        valid_listings = []
        card_data["listings"] = valid_listings
        image_map = card_image_set_map[card_name]
        stat_map = card_miss_stats[card_name]
        card_num += 1
        while time.time() - request_time < 3:
            time.sleep(0.1)
        request_time = time.time()
        print(f"{request_time - script_start_time:.2f}s - [Snapcaster] - ({card_num}/{number_of_cards}) - Scraping Listings for '{card_name}'")
        x = requests.get(f'https://catalog.snapcaster.ca/api/v1/search/?tcg=mtg&name={card_name}')
        mox_img_response = requests.get(card_data["cardImageUrl"])
        if mox_img_response.status_code != 200:
            stat_map["valid_listings"] -= 1
            continue
        mox_img = Image.open(BytesIO(mox_img_response.content)).convert("RGB").resize((323, 450), Image.ANTIALIAS)
        response_json = json.loads(x.text)
        listing_num = 0
        listings = response_json['data']
        number_of_listings = min(len(listings), 100)
        for listing in listings[:number_of_listings]:
            listing_num += 1
            print(f"{time.time() - script_start_time:.2f}s - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Parsing listing ({listing_num}/{number_of_listings})")
            store_base_url = store_url_from_listing(listing)
            if "nerdz" in store_base_url or "fantasyforged" in store_base_url or "everythinggames" in store_base_url:
                stat_map["nerdz"] += 1
                continue
            
            if listing["name"] != card_name:
                stat_map["name"] += 1
                continue

            if (listing["foil"] != '') != (card_data["isFoil"] == True):
                stat_map["foil"] += 1
                continue

            if listing["art_series"]:
                stat_map["art_series"] += 1
                continue

            if "shopify" not in listing["image"]:
                stat_map["shopify"] += 1
                continue

            if WEAR_LEVELS[listing["condition"]] > MIN_ACCEPTABLE_CONDITION:
                stat_map["condition"] += 1
                continue
            
            map_key = (listing["set"], listing["showcase"])
            if map_key in image_map:
                if not image_map[map_key]:
                    stat_map["image"] += 1
                    continue
            else:
                image_map[map_key] = False
                listing_img = Image.open(BytesIO(requests.get(listing["image"]).content)).convert("RGB").resize((323, 450), Image.ANTIALIAS)
                stat_map["image_requests"] += 1
                if rmsdiff(mox_img, listing_img) >= 70:
                    stat_map["image"] += 1
                    continue
                image_map[map_key] = True

            print(f"{time.time() - script_start_time:.2f}s - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Listing ({listing_num}/{number_of_listings}) is Valid")
            stat_map["valid_listings"] += 1
            valid_listings.append(listing)
        card_data["listings"] = valid_listings
    except:
        continue

num_added_to_cart = 1
for card_name, card_data in moxfield_cards.items():
    listing_time = time.time()
    print(f"{listing_time - script_start_time:.2f}s - [Adding to Cart] - ({num_added_to_cart}/{number_of_cards}) - '{card_name}'")
    card_listings = card_data["listings"]
    sorted_listings = sorted(card_listings, key=lambda listing: listing['price'])
    for listing in sorted_listings:
        addedToCart = listing_to_cart(store_url_from_listing(listing), listing["variant_id"])
        time.sleep(2)
        if addedToCart:
            total_cost += listing["price"]
            num_added_to_cart += 1
            break
        else:
            continue

browser_options = Options()
driver = webdriver.Chrome(chrome_options=browser_options)

cookie_time = time.time()
print(f"{cookie_time - script_start_time:.2f}s - [Cookies] - Importing cart cookies into Selenium")
driver.execute_cdp_cmd('Network.enable', {})
for cookie in request_session.cookies:
    cookie_dict = {'domain': cookie.domain, 'name': cookie.name, 'value': cookie.value, 'secure': cookie.secure}
    if cookie.expires:
        cookie_dict['expiry'] = cookie.expires
    if cookie.path_specified:
        cookie_dict['path'] = cookie.path
    set_cookie = driver.execute_cdp_cmd('Network.setCookie', cookie_dict)
driver.execute_cdp_cmd('Network.disable', {})


chrome_time = time.time()
print(f"{chrome_time - script_start_time:.2f}s - [Chrome Carts] - {len(active_carts)} Active Carts")
chrome_opened = False
for store_url in active_carts:
    if chrome_opened:
        driver.switch_to.new_window('tab')
    else:
        chrome_opened = True
    driver.get(store_url)

done_time = time.time()
print(f"{done_time - script_start_time:.2f}s - [Done] - Total Cost ${total_cost:.2f}")
while(True):
    pass