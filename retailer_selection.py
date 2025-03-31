import json
from ortools.sat.python import cp_model

def process(moxfield_cards: dict, stores: set[str]):
    card_names = list(moxfield_cards.keys())
    card_name_list = []  # List of card names on their own
    card_name_index = {}  # Maps card names to their index in card_name_list
    for index, card_name in enumerate(card_names):
        card_name_list.append(card_name)
        card_name_index[card_name] = index

    # Shipping cost (initially set to 2, but will depend on the number of items)
    with open("data/websites.json", 'r') as inFile:
        shipping_cost_map = json.load(inFile)["websites"]

    store_name_list = []  # List of store names on their own
    store_name_index = {}  # Maps store names to their index in store_name_list
    for index, store_name in enumerate(stores):
        store_name_list.append(store_name)
        store_name_index[store_name] = index
        if store_name not in shipping_cost_map:
            print(f"No shipping data found for: {store_name}")
            shipping_cost_map[store_name] = {
                "site_name": store_name,
                "link": store_name,
                "fees": {
                    "0": 0,
                    "1": 500
                },
                "fee_array": []
            }

    num_cards = len(card_name_list)
    all_cards = range(num_cards)

    num_stores = len(store_name_list)
    all_stores = range(num_stores)

    for cardsOrdered in range(num_cards+1):
        for store in store_name_list:
            store_shipping = shipping_cost_map[store]
            if str(cardsOrdered) in store_shipping["fees"]:
                shipFee = store_shipping["fees"][str(cardsOrdered)]
            else:
                shipFee = store_shipping["fee_array"][-1]
            store_shipping["fee_array"].append(shipFee)

    min_shipping_fee = None
    max_shipping_fee = None
    for store in store_name_list:
        store_fees = shipping_cost_map[store]["fee_array"]
        min_fee = min(store_fees)
        max_fee = max(store_fees)
        min_shipping_fee = min_fee if min_shipping_fee is None else min(min_shipping_fee, min_fee)  
        max_shipping_fee = max_fee if max_shipping_fee is None else max(max_shipping_fee, max_fee)

    # Cost matrix: contains the price of each card at each store
    cost_matrix = [[] for card in card_name_list]  # Values are the prices for the card at store based on list index
    for card_name, index in card_name_index.items():
        for store in store_name_list:
            if store in moxfield_cards[card_name]["listings"]:
                cost_matrix[index].append(round(100 * moxfield_cards[card_name]["listings"][store]["price"]))
            else:
                cost_matrix[index].append(10000000)



    # Create Model
    model = cp_model.CpModel()

    # Variables

    # y[c, s] = 1 if card `c` is bought from store `s`, else 0
    y = {}
    for c in all_cards:
        for s in all_stores:
            y[(c, s)] = model.NewBoolVar(f"y[{card_name_list[c]},{store_name_list[s]}]")

    # Number of items ordered from each store
    # Fee variables for each store (depends on the number of items)
    num_items_from_store = {}
    fee = {}
    for s in all_stores:
        store_name = store_name_list[s]

        # Number of items bought from each store
        num_items_from_store[s] = model.NewIntVar(0, num_cards, f"num_items_from_store[{store_name}]")
        model.Add(num_items_from_store[s] == sum(y[(c, s)] for c in all_cards))
        
        # Get the fee structure for this store from the shipping_cost_map
        fee[s] = model.NewIntVar(min_shipping_fee, max_shipping_fee, f"fee[{store_name}]")
        fees = shipping_cost_map[store_name]["fee_array"]
        
        # Apply the fees based on the number of items ordered
        for i in range(0, num_cards+1):
            condition = model.NewBoolVar(f"items_{i}_from_{store_name}")
            model.Add(num_items_from_store[s] == i).OnlyEnforceIf(condition)
            model.Add(num_items_from_store[s] != i).OnlyEnforceIf(condition.Not())
            shipping_fee = fees[-1]
            if i < len(fees):
                shipping_fee = fees[i]
            model.Add(fee[s] == shipping_fee).OnlyEnforceIf(condition)


    # Constraints
    # Each card is assigned to exactly one store.
    for c in all_cards:
        model.Add(sum(y[(c, s)] for s in all_stores) == 1)

    # Objective
    obj_expr = []

    # Add product costs to the objective
    for c in all_cards:
        for s in all_stores:
            obj_expr.append(y[(c, s)] * cost_matrix[c][s])

    # Add the tiered order processing fees to the objective
    for s in all_stores:
        obj_expr.append(fee[s])

    model.Minimize(sum(obj_expr))

    # Creates the solver and solve.
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL:
        for c in all_cards:
            for s in all_stores:
                if solver.Value(y[(c, s)]) == 1:
                    store = store_name_list[s]
                    card = card_name_list[c]
                    if store in moxfield_cards[card]["listings"]:
                        moxfield_cards[card]["optimal_listing"] = moxfield_cards[card]["listings"][store]
                        print(f"Buy {card} from {store} for: ${moxfield_cards[card]['listings'][store]['price']}")
                    else:
                        moxfield_cards[card]["optimal_listing"] = None
                        print(f"No optimal listing found for card: {card}")
        total_shipping = 0
        for s in all_stores:
            store = store_name_list[s]
            cards_bought = solver.Value(num_items_from_store[s])
            if cards_bought:
                print(f"Bought {cards_bought} cards from {store}: ${sum([cost_matrix[c][s] if solver.Value(y[(c, s)]) else 0 for c in all_cards])/100:.2f} + ${solver.Value(fee[s])/100:.2f} in fees")
                total_shipping += solver.Value(fee[s])
        print(f"Optimized Total Cost: ${(solver.ObjectiveValue()-total_shipping)/100:.2f} + ${total_shipping/100:.2f} in fees")

        return solver.ObjectiveValue()/100
    return -1