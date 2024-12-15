import mysql.connector

mydb = mysql.connector.connect(host= "localhost", user= "root", password= "1234", database= "cafe")

mycursor = mydb.cursor()

# mycursor.execute("create database cafe")

# mycursor.execute("create table menu(ord_name varchar(30), price int(10), ID int primary key auto_increment)")

# m1 = "insert into menu(ord_name,price) values(%s,%s)"
# name = [("Pizza", 400),
#         ("Pasta", 150),
#         ("Burger", 800),
#         ("Tea", 100),
#         ("Coffee", 250)]  
# mycursor.executemany(m1, name)
# mydb.commit()

mycursor.execute("select ord_name, price from menu")

result = mycursor.fetchall()

menu = {item[0] : item[1] for item in result}



print("Wellcome to RUFF Cafe.")
print("Menu: ")

for item, price in menu.items():
    print(f"{item:}: {price}$")

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