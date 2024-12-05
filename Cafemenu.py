menu = {
    'Pizza'  : 40,
    'Pasta'  : 60,
    'Burger' : 80,
    'Tea'    : 40,
    'Coffee' : 120
}

print("Wellcome to RUFF Cafe.")
print(" Pizza: 40$\n Pasta: 60$\n Burger: 80$\n Tea: 40$\n Coffee: 120$")

order_total = 0

item_1 = input("Enter the name of item you want to order = ")
if item_1 in menu:
    order_total += menu[item_1]
    print(f"Your item {item_1} has been ordered.\n")
else:
    print(f"Selected item {item_1} is no availble now.")

another_order = input("Do you want to order anther item? (YES/NO) ")
if another_order == "Yes" :
    item_2 = input("Enter the name of another item you want to order = ")
    if item_2 in menu: 
        order_total += menu[item_2]
        print(f"Your item {item_2} has been ordered.")
    else:
        print(f"Selected item {item_2} is no availble now.")

print(f"\nThe total amount of items to pay is {order_total}")