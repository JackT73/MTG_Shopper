import requests
import json
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

# WEAR_LEVELS = {
#     "NM": 0,
#     "LP": 1,
#     "MP": 2,
#     "HP": 3,
#     "DMG": 4
# }

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

request_session = requests.Session()
active_carts = set()

script_start_time = time.time()

def listing_to_cart(store_base_url: str, sku_variant_id):
    # Going to assume that snapcaster will only link to in-stock products
    # Shopfiy allows you to add an out-of-stock card to cart as longs as the 
    # variant id is associated with a product.
    response =  request_session.post(f'{store_base_url}/cart/add.js?quantity=1&id={sku_variant_id}')
    if response.status_code != 200:
        return False
    
    active_carts.add(f"{store_base_url}/cart")
    return True

deck_id = "abcdefghijklmnopqrstuvwxyz"
full_deck_url = "https://www.moxfield.com/decks/{full_deck_id}"
card_names = set()
with open("cardlist.txt", 'r') as card_file:
    for line in card_file:
        card_name = line.rstrip()
        card_names.add(card_name)

card_data = {}
for card_name in card_names:
    x = requests.get(f'https://catalog.snapcaster.ca/api/v1/search/?tcg=mtg&name={card_name}')
    request_time = time.time()
    print(f"{request_time - script_start_time:.2f}s - [Snapcaster] Scraping Listings for '{card_name}'")
    response_json = json.loads(x.text)
    card_data[card_name] = [listing for listing in response_json['data'] if listing['name'] == card_name and 'shopify' in listing["image"]]
    time.sleep(2)

for card_name, card_listings in card_data.items():
    listing_time = time.time()
    print(f"{listing_time - script_start_time:.2f}s - [Adding to Cart] '{card_name}'")
    sorted_listings = sorted(card_listings, key=lambda listing: listing['price'])
    for listing in sorted_listings:
        addedToCart = listing_to_cart(listing['link'].split('/products/')[0], listing["variant_id"])
        time.sleep(2)
        if addedToCart:
            break
        else:
            continue

browser_options = Options()
driver = webdriver.Chrome(chrome_options=browser_options)

cookie_time = time.time()
print(f"{cookie_time - script_start_time:.2f}s - [Cookies]")
driver.execute_cdp_cmd('Network.enable', {})
for cookie in request_session.cookies:
    cookie_dict = {'domain': cookie.domain, 'name': cookie.name, 'value': cookie.value, 'secure': cookie.secure}
    if cookie.expires:
        cookie_dict['expiry'] = cookie.expires
    if cookie.path_specified:
        cookie_dict['path'] = cookie.path
    driver.execute_cdp_cmd('Network.setCookie', cookie_dict)
driver.execute_cdp_cmd('Network.disable', {})


chrome_time = time.time()
print(f"{chrome_time - script_start_time:.2f}s - [Chrome Carts]")
chrome_opened = False
for store_url in active_carts:
    if chrome_opened:
        driver.switch_to.new_window('tab')
    else:
        chrome_opened = True
    driver.get(store_url)

done_time = time.time()
print(f"{done_time - script_start_time:.2f}s - [Done]")
while(True):
    pass
    