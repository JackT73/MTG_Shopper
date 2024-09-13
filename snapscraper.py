import requests
import json
import time
import sys
import math, operator
import retailer_selection
from ListingException import ListingException

from io import BytesIO
from PIL import Image, ImageChops
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

FILTERED_SITES = [
    "ergames",
    "nerdz",
    "fantasyforged",
    "everythinggames",
    "hairyt",
    "gamebridge"
]

WEAR_LEVELS = {
    "NM": 0,
    "LP": 1,
    "MP": 2,
    "HP": 3,
    "DMG": 4
}

MIN_ACCEPTABLE_CONDITION = WEAR_LEVELS.get("MP")

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
print(f"{time.time() - script_start_time:.2f}s - INFO - [Moxfield] - Scraping Deck: '{deck_id}'")
moxfield_json = requests.get(f'https://api2.moxfield.com/v3/decks/all/{deck_id}', headers=headers)
if moxfield_json.status_code != 200:
    sys.exit(f"{time.time() - script_start_time:.2f}s - INFO - [Moxfield] - Response Status != 200: '{deck_id}'")
moxfield_response = json.loads(moxfield_json.text)

number_of_cards = 0
moxfield_cards = {}
print(f"{time.time() - script_start_time:.2f}s - INFO - [Moxfield] - Parsing Response Data")
card_list = list(moxfield_response["boards"]["mainboard"]["cards"].values()) + list(moxfield_response["boards"]["commanders"]["cards"].values())
for card in card_list:
    data = card["card"]
    if str(data["type_line"]).startswith("Basic Land"):
        continue

    moxfield_card = {}
    moxfield_card["isFoil"] = card["isFoil"]
    moxfield_card["cardSet"] = data["set_name"]
    moxfield_card["cardName"] = data["name"]
    card_face = data["card_faces"][0]["id"] if data["card_faces"] else data["id"]
    moxfield_card["cardImageUrl"] = f"https://assets.moxfield.net/cards/card-{card_face}-normal.webp?{data['image_seq']}"
    moxfield_cards[data["name"]] = moxfield_card
    number_of_cards += 1

print(f"{time.time() - script_start_time:.2f}s - INFO - [Moxfield] - Deck Response Received: {number_of_cards} Cards To Find")

retailer_names = set()
cards_to_drop = set()

card_image_set_map = {card_name:{} for card_name in moxfield_cards.keys()}
card_miss_stats = {card_name:{"nerdz": 0, "name": 0, "foil": 0, "art_series": 0, "shopify": 0, "condition": 0, "image": 0, "image_requests": 0, "valid_listings": 0} for card_name in moxfield_cards.keys()}
request_time = time.time() - 3
image_request_time = time.time() - 3
card_num = 0
for card_name, card_data in moxfield_cards.items():
    try:
        card_data["listings"] = {}
        image_map = card_image_set_map[card_name]
        stat_map = card_miss_stats[card_name]
        card_num += 1
        while time.time() - request_time < 3:
            time.sleep(0.1)
        print(f"{time.time() - script_start_time:.2f}s - INFO - [Snapcaster] - ({card_num}/{number_of_cards}) - Scraping Listings for '{card_name}'")
        x = requests.get(f'https://catalog.snapcaster.ca/api/v1/search/?tcg=mtg&name={card_name}')
        response_json = json.loads(x.text)
        listings = response_json['data']
        number_of_listings = min(len(listings), 100)
        card_data["all_listings"] = listings[:number_of_listings]

        mox_img_response = requests.get(card_data["cardImageUrl"])
        request_time = time.time()
        if mox_img_response.status_code != 200:
            raise ListingException("Failed to get image from Moxfield", listings)
        mox_img = Image.open(BytesIO(mox_img_response.content)).convert("RGB").resize((323, 450), Image.ANTIALIAS)

        listing_num = 0
        for listing in listings[:number_of_listings]:
            listing_num += 1
            # print(f"{time.time() - script_start_time:.2f}s - DEBUG - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Parsing listing ({listing_num}/{number_of_listings})")
            store_base_url = store_url_from_listing(listing)

            bad_site = False
            for site in FILTERED_SITES:
                if site in store_base_url:
                    bad_site = True
            if bad_site:
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
                while time.time() - image_request_time < 3:
                    time.sleep(0.1)
                listing_img = Image.open(BytesIO(requests.get(listing["image"]).content)).convert("RGB").resize((323, 450), Image.ANTIALIAS)
                image_request_time = time.time()
                stat_map["image_requests"] += 1
                if rmsdiff(mox_img, listing_img) > 69:
                    stat_map["image"] += 1
                    continue
                image_map[map_key] = True

            retailer = listing["website"]
            stat_map["valid_listings"] += 1
            if retailer in card_data["listings"]:
                stored_price = card_data["listings"][retailer]["price"]
                if listing["price"] >= stored_price:
                    continue
            
            retailer_names.add(retailer)
            card_data["listings"][retailer] = listing
        if not len(card_data['listings'].values()):
            raise ListingException("Failed to find a valid listing in snapcaster response", listings)
        else:
            print(f"{time.time() - script_start_time:.2f}s - INFO - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Found {len(card_data['listings'].values())} valid listings")

    except ListingException as le:
        print(f"{time.time() - script_start_time:.2f}s - ERROR - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - No valid listings, defaulting to first 10")
        found_backup = False
        for listing in le.listings[:min(len(le.listings), 30)]:
            store_base_url = store_url_from_listing(listing)
            bad_site = False
            for site in FILTERED_SITES:
                if site in store_base_url:
                    bad_site = True
                    break

            if bad_site or listing["name"] != card_name or "shopify" not in listing["image"]:
                continue
            retailer = listing["website"]
            if retailer in card_data["listings"]:
                stored_price = card_data["listings"][retailer]["price"]
                if listing["price"] >= stored_price:
                    continue
            retailer_names.add(retailer)
            card_data["listings"][retailer] = listing
            found_backup = True
        if not found_backup:
            cards_to_drop.add(card_name)
            print(f"{time.time() - script_start_time:.2f}s - ERROR - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Default listings are all invalid")    
        continue
    except Exception as e:
        cards_to_drop.add(card_name)
        print(f"{time.time() - script_start_time:.2f}s - ERROR - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Dropping card due to unexpected error: {e}")

with open(f"data/{deck_id}", 'w') as card_data_file:
    json.dump(moxfield_cards, card_data_file, indent=4)

for drop in cards_to_drop:
    del moxfield_cards[drop]

print(f"{time.time() - script_start_time:.2f}s - INFO - [Optimization] - Optimizing retailers by cost and shipping fees")
optimal_cost = retailer_selection.process(moxfield_cards, retailer_names)
print(f"{time.time() - script_start_time:.2f}s - INFO - [Optimization] - Optimization complete. Total cost: ${optimal_cost:.2f}")

with open(f"data/{deck_id}", 'r') as card_data_file:
    file_dict = json.load(card_data_file)

for name, data in moxfield_cards.items():
    if name in file_dict:
        if "optimal_listing" in data:
            file_dict[name]["optimal_listing"] = data["optimal_listing"]
        else:
            file_dict[name]["optimal_listing"] = {}

with open(f"data/{deck_id}", 'w') as card_data_file:
    json.dump(file_dict, card_data_file, indent=4)
    
num_added_to_cart = 0
for card_name, card_data in moxfield_cards.items():
    num_added_to_cart += 1
    print(f"{time.time() - script_start_time:.2f}s - INFO - [Adding to Cart] - ({num_added_to_cart}/{number_of_cards}) - '{card_name}'")
    listing = card_data["optimal_listing"]
    if not listing:
        print(f"{time.time() - script_start_time:.2f}s - ERROR - [Adding to Cart] - ({num_added_to_cart}/{number_of_cards}) - '{card_name}' Had no optimal listing")
        continue
    addedToCart = listing_to_cart(store_url_from_listing(listing), listing["variant_id"])
    time.sleep(2)
    if addedToCart:
        total_cost += listing["price"]
    else:
        print(f"{time.time() - script_start_time:.2f}s - ERROR - [Adding to Cart] - ({num_added_to_cart}/{number_of_cards}) - Failed to add '{card_name}' to {listing['website']} cart")


browser_options = Options()
driver = webdriver.Chrome(chrome_options=browser_options)

print(f"{time.time() - script_start_time:.2f}s - INFO - [Cookies] - Importing cart cookies into Selenium")
driver.execute_cdp_cmd('Network.enable', {})
for cookie in request_session.cookies:
    cookie_dict = {'domain': cookie.domain, 'name': cookie.name, 'value': cookie.value, 'secure': cookie.secure}
    if cookie.expires:
        cookie_dict['expiry'] = cookie.expires
    if cookie.path_specified:
        cookie_dict['path'] = cookie.path
    set_cookie = driver.execute_cdp_cmd('Network.setCookie', cookie_dict)
driver.execute_cdp_cmd('Network.disable', {})


print(f"{time.time() - script_start_time:.2f}s - INFO - [Chrome Carts] - {len(active_carts)} Active Carts")
chrome_opened = False
for store_url in active_carts:
    if chrome_opened:
        driver.switch_to.new_window('tab')
    else:
        chrome_opened = True
    driver.get(store_url)

done_time = time.time()
print(f"{done_time - script_start_time:.2f}s - INFO - [Done] - Total Cost ${total_cost:.2f}")
while(True):
    pass