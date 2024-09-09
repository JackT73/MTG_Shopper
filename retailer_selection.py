import math
from ortools.sat.python import cp_model

def process(moxfield_cards: dict, stores: set[str]):
    card_names = list(moxfield_cards.keys())
    card_name_list = []  # List of card names on their own
    card_name_index = {} # Maps card names to their index in card_name_list
    for index, card_name in enumerate(card_names):
        card_name_list.append(card_name)
        card_name_index[card_name] = index

    store_name_list = []  # List of store names on their own
    store_name_index = {} # Maps store names to their index in store_name_list
    for index, store_name in enumerate(stores):
        store_name_list.append(store_name)
        store_name_index[store_name] = index

    shipping_cost_list = []
    for store in store_name_list:
        shipping_cost_list.append(2)

    cost_matrix = [[] for card in card_name_list] # Values are the prices for the card at store based on list index
    for card_name, index in card_name_index.items():
        for store in store_name_list:
            if store in moxfield_cards[card_name]["listings"]:
                cost_matrix[index].append(moxfield_cards[card_name]["listings"][store]["price"])
            else:
                cost_matrix[index].append(100000)

    num_cards = len(card_name_list)
    all_cards = range(num_cards)

    num_stores = len(store_name_list)
    all_stores = range(num_stores)

    # Create Model
    model = cp_model.CpModel()

    # Variables

    # True means the card is assigned to this store
    y = {}
    for c in all_cards:
        for s in all_stores:
            y[(c, s)] = model.NewBoolVar(f"y[{card_name_list[c]},{store_name_list[s]}]")

    # z[s] = 1 if at least one card is bought from store `s`, else 0
    z = {}
    for s in all_stores:
        z[s] = model.NewBoolVar(f"z[{store_name_list[s]}]")

    # Constraints

    # Each card is assigned to exactly one store.
    for c in all_cards:
        model.Add(sum(y[(c, s)] for s in all_stores) == 1)

    # If any card is bought from a store, that store is "used" (i.e., z[s] == 1)
    for s in all_stores:
        for c in all_cards:
            model.Add(z[s] >= y[(c, s)])

    # Objective
    obj_expr = []

    # Add product costs to the objective
    for c in all_cards:
        for s in all_stores:
            obj_expr.append(y[(c, s)] * cost_matrix[c][s])

    # Add order processing fees to the objective (only charge once per store)
    for s in all_stores:
        obj_expr.append(z[s] * shipping_cost_list[s])

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
                    else:
                        moxfield_cards[card]["optimal_listing"] = None
        return solver.ObjectiveValue()
    return -1