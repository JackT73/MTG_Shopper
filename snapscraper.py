import requests
import json
import time
import sys
import retailer_selection
import re
import imagehash
import matplotlib.pyplot as plt
from ListingException import ListingException
from io import BytesIO
from PIL import Image
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
SCRIPT_START_TIME = time.time()

DEFAULT_RATE_LIMIT_WAIT = 3
API_REQUEST_HISTORY = {
    "catalog.snapcaster.ca": {
        "min_time_between_requests": DEFAULT_RATE_LIMIT_WAIT,
        "number_of_requests": 0,
        "last_request_time": SCRIPT_START_TIME
    },
    "api2.moxfield.com": {
        "min_time_between_requests": DEFAULT_RATE_LIMIT_WAIT,
        "number_of_requests": 0,
        "last_request_time": SCRIPT_START_TIME
    },
    "api.scryfall.com": {
        "min_time_between_requests": 0.1,
        "number_of_requests": 0,
        "last_request_time": SCRIPT_START_TIME
    },
    "cards.scryfall.io": {
        "min_time_between_requests": 0.1,
        "number_of_requests": 0,
        "last_request_time": SCRIPT_START_TIME
    },
    "cdn.shopify.com": {
        "min_time_between_requests": 0.1,
        "number_of_requests": 0,
        "last_request_time": SCRIPT_START_TIME
    }
}

ART_SIZE = (146, 204)


full_deck_id = "abcdefghijklmnopqrstuvwxyz"
FULL_DECK_URL = f"https://www.moxfield.com/decks/{full_deck_id}"

def get_override(request_url: str, headers=None):
    rate_limit_config = check_rate_limit(request_url)

    if headers:
        response = requests.get(request_url, headers=headers)
    else:
        response = requests.get(request_url)
    if rate_limit_config:
        rate_limit_config["number_of_requests"] += 1
        rate_limit_config["last_request_time"] = time.time()

    return response

def post_override(request_url: str, session: requests.Session):
    rate_limit_config = check_rate_limit(request_url)
    response = session.post(request_url)

    if rate_limit_config:
        rate_limit_config["number_of_requests"] += 1
        rate_limit_config["last_request_time"] = time.time()

    return response

def check_rate_limit(full_url):
    match = re.search('https?://([A-Za-z_0-9.-]+).*', full_url)
    if match:
        base_url = match.group(1)
    else:
        print(f"{time.time() - SCRIPT_START_TIME:.2f}s - ERROR - [REQUESTS] - Could not identify domain from url: {full_url}")
        time.sleep(DEFAULT_RATE_LIMIT_WAIT)
        return None
            
    if base_url not in API_REQUEST_HISTORY:
        print(f"{time.time() - SCRIPT_START_TIME:.2f}s - DEBUG - [REQUESTS] - Rate limit not configured for domain: {base_url}")
        API_REQUEST_HISTORY[base_url] = {
            "min_time_between_requests": DEFAULT_RATE_LIMIT_WAIT,
            "number_of_requests": 0,
            "last_request_time": SCRIPT_START_TIME
        }

    url_config = API_REQUEST_HISTORY[base_url]
    min_time_between_requests = url_config["min_time_between_requests"]
    last_request_time = url_config["last_request_time"]

    wait_increment = min_time_between_requests / 10
    while time.time() - last_request_time < min_time_between_requests:
        time.sleep(wait_increment)
    return url_config

def same_set(set1: str, set2: str):
    loweredSet1 = str.lower(set1)
    loweredSet2 = str.lower(set2)
    return [c for c in loweredSet1 if c.isalpha()] == [c for c in loweredSet2 if c.isalpha()]

def listing_to_cart(store_base_url: str, sku_variant_id):
    # Going to assume that snapcaster will only link to in-stock products
    # Shopfiy allows you to add an out-of-stock card to cart as longs as the 
    # variant id is associated with a product.

    API_REQUEST_HISTORY[store_base_url] = {
        "min_time_between_requests": 1,
        "number_of_requests": 0,
        "last_request_time": SCRIPT_START_TIME
    }

    response = post_override(f'{store_base_url}/cart/add.js?quantity=1&id={sku_variant_id}', request_session)

    if response.status_code != 200:
        return False
    
    active_carts.add(f"{store_base_url}/cart")
    return True

def store_url_from_listing(listing: dict[str, str]):
    return listing['link'].split('/products/')[0]

def get_cards_from_moxfield_deck(deck_id: str):
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
    print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Moxfield] - Scraping Deck: '{deck_id}'")
    moxfield_json = get_override(f'https://api2.moxfield.com/v3/decks/all/{deck_id}', headers=headers)
    if moxfield_json.status_code != 200:
        sys.exit(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Moxfield] - Response Status != 200: '{deck_id}'")
    moxfield_response = json.loads(moxfield_json.text)

    print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Moxfield] - Parsing Response Data")

    card_list = list(moxfield_response["boards"]["mainboard"]["cards"].values()) + list(moxfield_response["boards"]["commanders"]["cards"].values())
    cards = {}
    for card in card_list:
        data = card["card"]
        if str(data["type_line"]).startswith("Basic Land"):
            continue
        cardname = data["name"]

        moxfield_card = {}
        moxfield_card["isFoil"] = card["isFoil"]
        moxfield_card["cardSet"] = data["set_name"]
        moxfield_card["cardName"] = cardname
        moxfield_card["scryfall_id"] = data["scryfall_id"]
        moxfield_card["listings"] = {}
        cards[cardname] = moxfield_card
    print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Moxfield] - Response parsed: {len(cards)} Cards To Find")
    return cards

def get_listings_from_snapcaster(card_name: str):
    print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Snapcaster] - ({card_num}/{number_of_cards}) - Scraping Listings for '{card_name}'")
    x = get_override(f'https://catalog.snapcaster.ca/api/v1/search/?tcg=mtg&name={card_name}')
    response_json = json.loads(x.text)
    listings = response_json['data']
    return listings

def rmsdiff(im1, im2):
    # "Calculate the root-mean-square difference between two images"
    # diff = ImageChops.difference(im1, im2)
    # h = diff.histogram()
    # sq = (value*((idx%256)**2) for idx, value in enumerate(h))
    # sum_of_squares = sum(sq)
    # rms = math.sqrt(sum_of_squares/float(im1.size[0] * im1.size[1]))
    hash1 = imagehash.average_hash(im1)
    hash2 = imagehash.average_hash(im2)
    return hash1 - hash2

def display_images(images, titles=None):
    # Calculate the number of rows and columns based on the number of images
    num_images = len(images)
    if not num_images:
        return
    rows = max(1, (num_images + 3) // 4)  # Display 4 images per row
    cols = max(1, min(4, num_images))
    
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 4 * rows))
    axes = axes.flatten() if num_images > 1 else [axes]  # Flatten in case there's more than 1 image

    for i, img in enumerate(images):
        axes[i].imshow(img)
        if titles:
            axes[i].set_title(titles[i])
        axes[i].axis('off')  # Turn off axis labels

    # Hide empty axes (if any)
    for j in range(i + 1, len(axes)):
        axes[j].axis('off')

    plt.tight_layout()
    plt.show()
    pass

def check_valid_image(card_name, card_data, card_image_map, listing, stat_map):
    if card_name not in card_image_map:
        card_image_map[card_name] = {}
        card_map = card_image_map[card_name]
        set_showcase_map = {}
        card_map["set_showcase_map"] = set_showcase_map
        printing_images = {}
        card_map["printing_images"] = printing_images
        bad_listings = []
        card_map["bad_listings"] = bad_listings
        good_listings = []
        card_map["good_listings"] = good_listings

        scryfall_card = json.loads(get_override(f"https://api.scryfall.com/cards/{card_data['scryfall_id']}").text)
        scryfall_printings_response = json.loads(get_override(f"{scryfall_card['prints_search_uri']}").text)
        scryfall_art_obj = scryfall_card if "card_faces" not in scryfall_card else scryfall_card["card_faces"][0]
        good_art_id = scryfall_art_obj["illustration_id"]
        card_map["good_art_id"] = good_art_id

        num_printings = scryfall_printings_response["total_cards"]
        card_map["num_printings"] = num_printings
        

        if num_printings < 30:
            good_art = Image.open(BytesIO(get_override(f"{scryfall_art_obj['image_uris']['small']}").content)).convert("RGB").resize(ART_SIZE, Image.Resampling.LANCZOS)
            card_map["good_art"] = good_art

            bad_arts = {}
            card_map["bad_arts"] = bad_arts

            scryfall_printings = scryfall_printings_response["data"]
            card_map["scryfall_printings"] = scryfall_printings
        
            unique_art_ids = {good_art_id}
            for printing in scryfall_printings:
                printing_art_obj = printing if "card_faces" not in printing else printing["card_faces"][0]
                unique_art_ids.add(printing_art_obj["illustration_id"])

            num_illustrations = len(unique_art_ids)
            card_map["num_illustrations"] = num_illustrations
    else:
        card_map = card_image_map[card_name]
        good_art_id = card_map["good_art_id"]
        num_printings = card_map["num_printings"]
        set_showcase_map = card_map["set_showcase_map"]
        printing_images = card_map["printing_images"]
        good_listings = card_map["good_listings"]
        bad_listings = card_map["bad_listings"]
        good_art = card_map.get("good_art", None)
        bad_arts = card_map.get("bad_arts", None)
        scryfall_printings = card_map.get("scryfall_printings", None)
        num_illustrations = card_map.get("num_illustrations", None)
        
    if num_printings < 30 and num_illustrations > 1:
        map_key = (listing["set"], listing["showcase"])
        if map_key in set_showcase_map:
            if not set_showcase_map[map_key]:
                stat_map["image"] += 1
                return False
        else:
            set_showcase_map[map_key] = False
            listing_img = Image.open(BytesIO(get_override(listing["image"]).content)).convert("RGB").resize(ART_SIZE, Image.Resampling.LANCZOS)
            stat_map["image_requests"] += 1
            good_art_best_comparison = 1000
            bad_art_best_comparison = 1000
            for printing in scryfall_printings:
                printing_art_obj = printing if "card_faces" not in printing else printing["card_faces"][0]
                art_id = printing_art_obj["illustration_id"] 
                card_id = printing["id"]
                if card_id not in printing_images:
                    printing_images[card_id] = Image.open(BytesIO(get_override(f"{printing_art_obj['image_uris']['small']}").content)).convert("RGB").resize(ART_SIZE, Image.Resampling.LANCZOS)
                    stat_map["image_requests"] += 1
                art = printing_images[card_id]
                art_comparison = rmsdiff(art, listing_img)
                if art_id == good_art_id:
                    good_art_best_comparison = min(good_art_best_comparison, art_comparison)
                else:
                    bad_art_best_comparison = min(bad_art_best_comparison, art_comparison)
            if bad_art_best_comparison < good_art_best_comparison:
                stat_map["image"] += 1
                bad_listings.append(listing_img)
                return False
            else:
                good_listings.append(listing_img)
            set_showcase_map[map_key] = True
    else:
        if num_illustrations == 1 and "one_art" not in card_map:
            card_map["one_art"] = True
            print(f"{time.time() - SCRIPT_START_TIME:.2f}s - DEBUG - [IMAGE COMPARE] - ({card_num}/{number_of_cards}) - '{card_name}' - Only one illustration available skipping image comparison")
        if num_printings >= 30 and "too_many_prints" not in card_map:
            card_map["too_many_prints"] = True
            print(f"{time.time() - SCRIPT_START_TIME:.2f}s - DEBUG - [IMAGE COMPARE] - ({card_num}/{number_of_cards}) - '{card_name}' - Too many printings skipping image comparison")
    
    return True

request_session = requests.Session()
active_carts = set()
total_cost = 0

if FULL_DECK_URL.startswith("https://www.moxfield.com/decks/"):
    moxfield_id = FULL_DECK_URL.split("decks/")[1]
else:
    moxfield_id = FULL_DECK_URL

moxfield_cards = get_cards_from_moxfield_deck(moxfield_id)
number_of_cards = len(moxfield_cards)

retailer_names = set()
cards_to_drop = set()

card_image_set_map = dict()
card_miss_stats = {card_name:{"nerdz": 0, "name": 0, "foil": 0, "art_series": 0, "shopify": 0, "condition": 0, "image": 0, "image_requests": 0, "valid_listings": 0} for card_name in moxfield_cards.keys()}

card_num = 0
for card_name, card_data in moxfield_cards.items():
    try:
        card_num += 1
        stat_map = card_miss_stats[card_name]

        listings = get_listings_from_snapcaster(card_name)
        number_of_listings = min(len(listings), 100)
        card_data["all_listings"] = listings[:number_of_listings]
        
        listing_num = 0
        for listing in listings[:number_of_listings]:
            listing_num += 1
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
            
            if not check_valid_image(card_name, card_data, card_image_set_map, listing, stat_map):
                stat_map["image"] += 1
                continue

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
            print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Found {len(card_data['listings'].values())} valid listings")

    except ListingException as le:
        print(f"{time.time() - SCRIPT_START_TIME:.2f}s - ERROR - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - No valid listings, defaulting to first 10")
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
            print(f"{time.time() - SCRIPT_START_TIME:.2f}s - ERROR - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Default listings are all invalid")    
        continue
    except Exception as e:
        cards_to_drop.add(card_name)
        print(f"{time.time() - SCRIPT_START_TIME:.2f}s - ERROR - [Snapcaster] - ({card_num}/{number_of_cards}) - '{card_name}' - Dropping card due to unexpected error: {e}")
    
    display_images(card_image_set_map[card_name]["good_listings"])
    display_images(card_image_set_map[card_name]["bad_listings"])

with open(f"data/{moxfield_id}", 'w') as card_data_file:
    json.dump(moxfield_cards, card_data_file, indent=4)

for drop in cards_to_drop:
    del moxfield_cards[drop]

print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Optimization] - Optimizing retailers by cost and shipping fees")
optimal_cost = retailer_selection.process(moxfield_cards, retailer_names)
print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Optimization] - Optimization complete. Total cost: ${optimal_cost:.2f}")

with open(f"data/{moxfield_id}", 'r') as card_data_file:
    file_dict = json.load(card_data_file)

for name, data in moxfield_cards.items():
    if name in file_dict:
        if "optimal_listing" in data:
            file_dict[name]["optimal_listing"] = data["optimal_listing"]
        else:
            file_dict[name]["optimal_listing"] = {}

with open(f"data/{moxfield_id}", 'w') as card_data_file:
    json.dump(file_dict, card_data_file, indent=4)
    
num_added_to_cart = 0
for card_name, card_data in moxfield_cards.items():
    num_added_to_cart += 1
    print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Adding to Cart] - ({num_added_to_cart}/{number_of_cards}) - '{card_name}'")
    listing = card_data["optimal_listing"]
    if not listing:
        print(f"{time.time() - SCRIPT_START_TIME:.2f}s - ERROR - [Adding to Cart] - ({num_added_to_cart}/{number_of_cards}) - '{card_name}' Had no optimal listing")
        continue
    addedToCart = listing_to_cart(store_url_from_listing(listing), listing["variant_id"])
    if addedToCart:
        total_cost += listing["price"]
    else:
        print(f"{time.time() - SCRIPT_START_TIME:.2f}s - ERROR - [Adding to Cart] - ({num_added_to_cart}/{number_of_cards}) - Failed to add '{card_name}' to {listing['website']} cart")


browser_options = Options()
driver = webdriver.Chrome(chrome_options=browser_options)

print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Cookies] - Importing cart cookies into Selenium")
driver.execute_cdp_cmd('Network.enable', {})
for cookie in request_session.cookies:
    cookie_dict = {'domain': cookie.domain, 'name': cookie.name, 'value': cookie.value, 'secure': cookie.secure}
    if cookie.expires:
        cookie_dict['expiry'] = cookie.expires
    if cookie.path_specified:
        cookie_dict['path'] = cookie.path
    set_cookie = driver.execute_cdp_cmd('Network.setCookie', cookie_dict)
driver.execute_cdp_cmd('Network.disable', {})


print(f"{time.time() - SCRIPT_START_TIME:.2f}s - INFO - [Chrome Carts] - {len(active_carts)} Active Carts")
chrome_opened = False
for store_url in active_carts:
    if chrome_opened:
        driver.switch_to.new_window('tab')
    else:
        chrome_opened = True
    driver.get(store_url)

done_time = time.time()
print(f"{done_time - SCRIPT_START_TIME:.2f}s - INFO - [Done] - Total Cost ${total_cost:.2f}")
while(True):
    pass