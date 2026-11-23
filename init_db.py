"""Create the database from schema.sql and load demo data.  Run: python init_db.py"""
import os, random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import mysql.connector
from werkzeug.security import generate_password_hash as h


def sanitize_filename(name):
    """Convert food name to a safe image filename."""
    safe = name.lower()
    safe = safe.replace(" ", "-")
    safe = safe.replace("(", "").replace(")", "")
    safe = safe.replace(",", "").replace("&", "and").replace("'", "")
    safe = "".join(c if c.isalnum() or c == "-" else "-" for c in safe)
    while "--" in safe:
        safe = safe.replace("--", "-")
    return safe + ".svg"

rng = random.Random(42)  # fixed seed: same demo data every run
now = datetime.now().replace(microsecond=0)

conn = mysql.connector.connect(host=os.environ.get("DB_HOST", "localhost"),
                               user=os.environ.get("DB_USER", "root"),
                               password=os.environ.get("DB_PASS", ""),
                               port=int(os.environ.get("DB_PORT", 3306)))
cur = conn.cursor()
cur.execute("DROP DATABASE IF EXISTS CampusCanteenDB")
sql = "\n".join(l for l in open("schema.sql", encoding="utf8") if not l.strip().startswith("--"))
for stmt in sql.split(";"):
    if stmt.strip():
        cur.execute(stmt)

def money(x):
    return Decimal(x).quantize(Decimal("0.01"), ROUND_HALF_UP)

# ---------------- categories ----------------
CATEGORIES = ["Breakfast", "Snacks", "Meals", "Beverages", "Desserts", "Biryani and Rice",
              "Chinese", "Burgers and Sandwiches", "Healthy", "Combos"]
cat_id = {}
for name in CATEGORIES:
    cur.execute("INSERT INTO Categories(category_name,description) VALUES(%s,%s)", (name, f"{name} items"))
    cat_id[name] = cur.lastrowid

# ---------------- canteens and menus ----------------
# (category, name, description, price, vegetarian, prep minutes)
CANTEENS = [
 ("Main Canteen", "Ground floor, Block A", "08:00", "20:00", [
   ("Breakfast", "Masala Dosa", "Crisp dosa with potato filling, sambar and chutney", 60, 1, 10),
   ("Breakfast", "Idli Sambar (3 pcs)", "Steamed idlis with sambar", 40, 1, 8),
   ("Snacks", "Samosa (2 pcs)", "Fried pastry with spiced potato", 30, 1, 5),
   ("Meals", "Veg Thali", "Rice, roti, dal, two sabzis and curd", 90, 1, 15),
   ("Meals", "Chicken Biryani", "Hyderabadi style with raita", 130, 0, 20),
   ("Beverages", "Masala Chai", "Hot ginger tea", 15, 1, 3)]),
 ("Food Court", "Near the sports complex", "10:00", "22:00", [
   ("Burgers and Sandwiches", "Veg Burger", "Aloo tikki burger with fries", 70, 1, 10),
   ("Burgers and Sandwiches", "Chicken Roll", "Egg paratha roll with chicken filling", 90, 0, 12),
   ("Meals", "Paneer Butter Masala Combo", "With 2 rotis and rice", 120, 1, 18),
   ("Chinese", "Egg Fried Rice", "Wok-tossed rice with egg", 80, 0, 12),
   ("Beverages", "Fresh Lime Soda", "Sweet or salted", 30, 1, 3),
   ("Desserts", "Chocolate Brownie", "Warm brownie", 50, 1, 4)]),
 ("Library Cafe", "Library, 1st floor", "09:00", "19:00", [
   ("Beverages", "Cold Coffee", "Blended with ice cream", 70, 1, 5),
   ("Burgers and Sandwiches", "Veg Sandwich", "Grilled, with cheese", 55, 1, 7),
   ("Desserts", "Gulab Jamun (2 pcs)", "Served warm", 35, 1, 3),
   ("Beverages", "Filter Coffee", "South Indian style", 25, 1, 4),
   ("Snacks", "Veg Puff", "Baked puff with vegetable filling", 25, 1, 3)]),
 ("Juice Bar", "Sports complex entrance", "07:00", "19:00", [
   ("Beverages", "Mango Shake", "Fresh mango and milk", 60, 1, 5),
   ("Beverages", "Watermelon Juice", "No added sugar", 40, 1, 4),
   ("Healthy", "Fruit Bowl", "Seasonal fruit", 70, 1, 5),
   ("Healthy", "Protein Smoothie", "Banana, peanut butter and milk", 90, 1, 6),
   ("Healthy", "Sprouts Salad", "Sprouts with lemon and spices", 50, 1, 5)]),
 ("Engineering Block Cafe", "Block C, ground floor", "09:00", "18:00", [
   ("Snacks", "Maggi", "Masala noodles", 40, 1, 7),
   ("Snacks", "French Fries", "Salted, with ketchup", 60, 1, 8),
   ("Burgers and Sandwiches", "Chicken Burger", "Crispy chicken patty", 90, 0, 10),
   ("Beverages", "Cold Drink", "300 ml bottle", 30, 1, 1),
   ("Chinese", "Veg Hakka Noodles", "Stir-fried noodles", 80, 1, 10)]),
 ("South Indian Corner", "Block B, ground floor", "07:30", "14:00", [
   ("Breakfast", "Upma", "Semolina with vegetables", 35, 1, 6),
   ("Breakfast", "Medu Vada (2 pcs)", "Crisp lentil donuts with sambar", 40, 1, 8),
   ("Breakfast", "Pongal", "Rice and moong dal with ghee", 45, 1, 8),
   ("Meals", "Curd Rice", "With pickle", 50, 1, 5),
   ("Beverages", "Filter Coffee", "Strong and hot", 20, 1, 4)]),
 ("North Indian Dhaba", "Behind the hostel block", "11:00", "21:30", [
   ("Meals", "Rajma Chawal", "Kidney beans curry with rice", 80, 1, 12),
   ("Meals", "Chole Bhature", "Two bhature with chole", 70, 1, 12),
   ("Meals", "Dal Tadka with Rice", "Yellow dal with jeera rice", 75, 1, 12),
   ("Breakfast", "Aloo Paratha", "With curd and pickle", 45, 1, 10),
   ("Beverages", "Sweet Lassi", "Thick and chilled", 40, 1, 3)]),
 ("Chinese Wok", "Food street", "12:00", "22:00", [
   ("Chinese", "Veg Manchurian", "Gravy or dry", 90, 1, 12),
   ("Chinese", "Chicken Noodles", "Spicy stir-fry", 100, 0, 12),
   ("Chinese", "Spring Rolls (4 pcs)", "With schezwan sauce", 60, 1, 8),
   ("Chinese", "Schezwan Fried Rice", "Hot and spicy", 85, 1, 10),
   ("Chinese", "Chilli Paneer", "Dry, with capsicum", 110, 1, 12)]),
 ("Biryani House", "Food street", "11:30", "22:00", [
   ("Biryani and Rice", "Veg Biryani", "With mixed vegetables and raita", 100, 1, 18),
   ("Biryani and Rice", "Chicken Dum Biryani", "Slow cooked, with raita", 140, 0, 22),
   ("Biryani and Rice", "Egg Biryani", "With boiled eggs and raita", 110, 0, 18),
   ("Biryani and Rice", "Curd Rice Bowl", "Cooling and light", 50, 1, 5),
   ("Beverages", "Buttermilk", "Spiced", 20, 1, 2)]),
 ("Dessert Studio", "Library lawn", "13:00", "21:00", [
   ("Desserts", "Ice Cream Scoop", "Vanilla, chocolate or strawberry", 40, 1, 2),
   ("Desserts", "Brownie with Ice Cream", "Hot brownie and vanilla scoop", 80, 1, 5),
   ("Desserts", "Rasmalai (2 pcs)", "Chilled", 50, 1, 2),
   ("Desserts", "Kulfi", "Malai kulfi on a stick", 45, 1, 2),
   ("Beverages", "Cold Chocolate", "Thick chocolate milk", 65, 1, 4)]),
]

# ---------------- users ----------------
cur.executemany("INSERT INTO Users(full_name,email,phone,password_hash,role) VALUES(%s,%s,%s,%s,%s)",
    [(f"{c[0]} Admin", f"admin{i}@campus.edu", f"90000000{i:02d}", h("admin123"), "admin")
     for i, c in enumerate(CANTEENS, 1)])
STUDENTS = ["Demo Student", "Aarav Sharma", "Diya Patel", "Rohan Mehta", "Ananya Reddy", "Kabir Singh",
            "Isha Nair", "Vihaan Gupta", "Meera Iyer", "Arjun Rao", "Sneha Kulkarni", "Karan Joshi",
            "Priya Menon", "Aditya Verma", "Nisha Das"]
student_ids = []
for i, name in enumerate(STUDENTS):
    email = "student@campus.edu" if i == 0 else name.lower().replace(" ", ".") + "@campus.edu"
    cur.execute("INSERT INTO Users(full_name,email,phone,password_hash,role) VALUES(%s,%s,%s,%s,'student')",
                (name, email, f"91111111{i:02d}", h("student123")))
    student_ids.append(cur.lastrowid)

# ---------------- canteens and food ----------------
foods = {}  # canteen_id -> [(food_id, name, price, prep)]
for idx, (cname, loc, op, cl, items) in enumerate(CANTEENS, 1):
    cur.execute("INSERT INTO Canteens(canteen_name,location,opening_time,closing_time,manager_id) VALUES(%s,%s,%s,%s,%s)",
                (cname, loc, op, cl, idx))
    cid = cur.lastrowid
    foods[cid] = []
    for cat, name, desc, price, veg, prep in items:
        image_url = f"/static/uploads/{sanitize_filename(name)}"
        cur.execute("INSERT INTO Food_Items(canteen_id,category_id,food_name,description,image_url,price,is_vegetarian,preparation_time) "
                    "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)", (cid, cat_id[cat], name, desc, image_url, price, veg, prep))
        foods[cid].append((cur.lastrowid, name, Decimal(price), prep))
cur.execute("UPDATE Food_Items SET is_available=0 WHERE food_name IN ('Rasmalai (2 pcs)','Egg Biryani')")

# ---------------- coupons ----------------
COUPONS = [  # code, type, value, min order, max discount, total uses, per student, from, until (days), active
 ("WELCOME10", "percentage", 10, 100, 50, None, 1, -30, 365, 1),
 ("FLAT20", "fixed", 20, 150, None, 500, 3, -30, 365, 1),
 ("STUDENT15", "percentage", 15, 200, 75, 300, 2, -30, 180, 1),
 ("LUNCH30", "fixed", 30, 250, None, 200, 2, -30, 90, 1),
 ("SNACK10", "percentage", 10, 50, 25, None, 5, -30, 120, 1),
 ("WEEKEND25", "percentage", 25, 300, 100, 100, 1, -30, 60, 1),
 ("FRESHER50", "fixed", 50, 400, None, 50, 1, -30, 30, 1),
 ("COFFEE5", "fixed", 5, 40, None, None, 10, -30, 200, 1),
 ("DIWALI20", "percentage", 20, 150, 60, 100, 1, -60, -5, 0),   # expired
 ("EXAM15", "percentage", 15, 100, 40, 150, 1, -30, 150, 0)]    # switched off
coupon = {}
for code, typ, val, mn, mx, lim, per, f, u, act in COUPONS:
    cur.execute("INSERT INTO Coupons(coupon_code,discount_type,discount_value,minimum_order_amount,maximum_discount,usage_limit,per_user_limit,valid_from,valid_until,is_active) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (code, typ, val, mn, mx, lim, per, now + timedelta(days=f), now + timedelta(days=u), act))
    coupon[code] = (cur.lastrowid, typ, Decimal(val), Decimal(mn), None if mx is None else Decimal(mx), per)
used = {}

def pick_coupon(uid, sub):
    for code in rng.sample(["WELCOME10", "FLAT20", "SNACK10"], 3):
        cpid, typ, val, mn, mx, per = coupon[code]
        if rng.random() < 0.4 and sub >= mn and used.get((uid, code), 0) < per:
            d = sub * val / 100 if typ == "percentage" else val
            if mx is not None:
                d = min(d, mx)
            used[(uid, code)] = used.get((uid, code), 0) + 1
            return cpid, money(min(d, sub))
    return None, Decimal("0.00")

# ---------------- orders, items, payments, history, reviews ----------------
METHODS = ["UPI", "UPI", "UPI", "card", "cash", "cash", "wallet", "net_banking"]
COMMENTS = {5: ["Hot and tasty, ready on time", "Best food on campus", "Great value for money", "Quick service"],
            4: ["Good food, slightly crowded at pickup", "Tasty, would order again", "Nice portions"],
            3: ["Okay, nothing special", "Food was a bit cold", "Average taste"],
            2: ["Waited too long", "Not as described"],
            1: ["Order was wrong"]}
PATH = ["placed", "accepted", "preparing", "ready", "completed"]
tokens = set()

def place_order(when, canteen_id, final_status, pickup=None):
    uid = rng.choice(student_ids[:-1])  # last student has no orders (demo for query Q6)
    menu = foods[canteen_id]
    chosen = rng.sample(menu, rng.randint(1, min(3, len(menu))))
    lines = [(f, n, p, rng.randint(1, 3)) for f, n, p, _ in chosen]
    sub = sum(p * q for _, _, p, q in lines)
    cpid, disc = pick_coupon(uid, sub)
    tax = money((sub - disc) * Decimal("0.05"))
    total = sub - disc + tax
    prep = max(pr for *_, pr in chosen)
    ready_off = prep + 6
    pickup = pickup or when + timedelta(minutes=ready_off + rng.randint(3, 15))
    while True:
        token = "CB" + "".join(rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ23456789", k=6))
        if token not in tokens:
            tokens.add(token); break
    cur.execute("INSERT INTO Orders(order_token,user_id,canteen_id,order_date,pickup_time,order_status,subtotal,discount_amount,tax_amount,total_amount,special_instructions) "
                "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (token, uid, canteen_id, when, pickup, final_status, sub, disc, tax, total,
                 rng.choice([None, None, None, "Less spicy please", "Extra napkins", "No onions"])))
    oid = cur.lastrowid
    cur.executemany("INSERT INTO Order_Items(order_id,food_id,food_name,quantity,unit_price,item_total) VALUES(%s,%s,%s,%s,%s,%s)",
                    [(oid, f, n, q, p, p * q) for f, n, p, q in lines])
    if cpid:
        cur.execute("INSERT INTO Order_Coupons(order_id,coupon_id,discount_applied) VALUES(%s,%s,%s)", (oid, cpid, disc))
    method = rng.choice(METHODS)
    if final_status == "cancelled":
        pstatus = "failed" if method == "cash" else "refunded"
    elif final_status == "completed" or method != "cash":
        pstatus = "successful"
    else:
        pstatus = "pending"
    cur.execute("INSERT INTO Payments(order_id,payment_method,transaction_reference,amount,payment_status,payment_date) VALUES(%s,%s,%s,%s,%s,%s)",
                (oid, method, None if method == "cash" else "TXN" + token, total, pstatus, when))
    manager = canteen_id  # manager user_id equals canteen_id (admins were inserted first, in canteen order)
    if final_status == "cancelled":
        steps = [("placed", 0, uid), ("cancelled", 3, uid)]
    else:
        offsets = [0, 2, 5, ready_off, int((pickup - when).total_seconds() // 60)]
        steps = [(s, offsets[i], uid if i == 0 else manager) for i, s in enumerate(PATH[:PATH.index(final_status) + 1])]
    prev = None
    for status, off, by in steps:
        cur.execute("INSERT INTO Order_Status_History(order_id,previous_status,new_status,changed_at,changed_by) VALUES(%s,%s,%s,%s,%s)",
                    (oid, prev, status, min(now, when + timedelta(minutes=off)), by))
        prev = status
    if final_status == "completed" and rng.random() < 0.75:
        rating = rng.choices([5, 4, 3, 2, 1], [38, 34, 16, 8, 4])[0]
        cur.execute("INSERT INTO Reviews(user_id,order_id,canteen_id,rating,comment,review_date) VALUES(%s,%s,%s,%s,%s,%s)",
                    (uid, oid, canteen_id, rating, rng.choice(COMMENTS[rating]), min(now, pickup + timedelta(hours=rng.randint(1, 6)))))

for _ in range(45):  # past orders over the last two weeks
    when = (now - timedelta(days=rng.randint(1, 14))).replace(hour=rng.randint(9, 19), minute=rng.randint(0, 59))
    place_order(when, rng.choices(range(1, 11), [5, 4, 3, 2, 2, 2, 2, 2, 2, 2])[0],
                rng.choices(["completed", "cancelled"], [85, 15])[0])
for status, cid in [("placed", 1), ("placed", 1), ("accepted", 1), ("preparing", 1), ("ready", 2), ("placed", 2), ("preparing", 9)]:
    place_order(now - timedelta(minutes=rng.randint(3, 25)), cid, status, now + timedelta(minutes=rng.randint(15, 40)))

conn.commit()
for t in ["Users", "Canteens", "Categories", "Food_Items", "Coupons", "Orders", "Order_Items", "Payments", "Order_Coupons", "Reviews", "Order_Status_History"]:
    cur.execute(f"SELECT COUNT(*) FROM {t}")
    print(f"{t:22s}{cur.fetchone()[0]:>5} rows")
print("\nDone. Admin: admin1@campus.edu ... admin10@campus.edu / admin123   Student: student@campus.edu / student123")
