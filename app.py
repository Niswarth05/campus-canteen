import os, random, string, time, json
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
import mysql.connector
from flask import Flask, g, render_template, request, redirect, url_for, session, flash, abort, Response, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-me-in-production")
app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024  # 2 MB max upload
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
DB = dict(host=os.environ.get("DB_HOST", "localhost"), user=os.environ.get("DB_USER", "root"),
          password=os.environ.get("DB_PASS", ""), database="CampusCanteenDB",
          port=int(os.environ.get("DB_PORT", 3306)))
TAX = Decimal("0.05")
NEXT = {"placed": ["accepted", "cancelled"], "accepted": ["preparing", "cancelled"],
        "preparing": ["ready"], "ready": ["completed"]}
METHODS = ["UPI", "card", "cash", "net_banking", "wallet"]
# Revision token: changes when an order is added, a status changes, or a menu item is added/edited/toggled/deleted.
REV_SQL = ("SELECT MD5(CONCAT(COUNT(*),':',COALESCE(MAX(o.order_id),0),':',"
           "COALESCE(MAX(h.history_id),0),':',(SELECT COALESCE(SUM(CRC32(CONCAT_WS('|',food_id,food_name,price,is_available,is_vegetarian,COALESCE(description,'')))),0) FROM Food_Items))) rev "
           "FROM Orders o LEFT JOIN Order_Status_History h ON h.order_id=o.order_id WHERE ")

# ---------- helpers ----------
def db():
    if "db" not in g:
        g.db = mysql.connector.connect(**DB)
    return g.db

@app.teardown_appcontext
def close_db(_=None):
    c = g.pop("db", None)
    if c:
        c.close()

def q(sql, args=(), one=False, commit=False):
    cur = db().cursor(dictionary=True)
    cur.execute(sql, args)
    if commit:
        db().commit(); n = cur.lastrowid; cur.close(); return n
    rows = cur.fetchall(); cur.close()
    return (rows[0] if rows else None) if one else rows

def current_uid(role=None):
    """Id of the account for `role` ('student'/'admin'), or either account."""
    if role:
        return session.get(f"{role}_uid")
    return session.get("student_uid") or session.get("admin_uid")

def current_role():
    if session.get("student_uid"): return "student"
    if session.get("admin_uid"): return "admin"
    return None

def safe_next(target):
    """Only allow redirects to local paths (never external URLs)."""
    ok = target and target.startswith("/") and not target.startswith("//") and "\\" not in target
    return target if ok else url_for("home")

def login_required(role=None):
    def deco(f):
        @wraps(f)
        def w(*a, **k):
            if not current_uid(role):
                extra = {"as_": role} if role else {}
                return redirect(url_for("login", next=request.path, **extra))
            return f(*a, **k)
        return w
    return deco

@app.template_filter("hm")
def hm(t):
    if t is None: return ""
    s = int(t.total_seconds()); return f"{s // 3600:02d}:{s % 3600 // 60:02d}"

@app.context_processor
def inject():
    n = 0
    if session.get("student_uid"):
        r = q("SELECT COALESCE(SUM(ci.quantity),0) n FROM Cart c JOIN Cart_Items ci ON ci.cart_id=c.cart_id "
              "WHERE c.user_id=%s AND c.cart_status='active'", (session["student_uid"],), one=True)
        n = int(r["n"])
    return dict(cart_count=n, is_student=bool(session.get("student_uid")),
                is_admin=bool(session.get("admin_uid")),
                student_name=session.get("student_name"), admin_name=session.get("admin_name"),
                live_scope=getattr(g, "live_scope", None))

# ---------- live updates (Server-Sent Events) ----------
def rev_query(scope):
    if scope == "admin":
        c = q("SELECT canteen_id FROM Canteens WHERE manager_id=%s", (current_uid("admin"),), one=True)
        return (REV_SQL + "o.canteen_id=%s", (c["canteen_id"],)) if c else (None, ())
    return (REV_SQL + "o.user_id=%s", (current_uid("student"),))

def revision(scope):
    sql, args = rev_query(scope)
    if not sql: return "0"
    r = q(sql, args, one=True)
    return r["rev"] if r and r["rev"] else "0"

@app.route("/api/stream")
@login_required()
def stream():
    scope = request.args.get("scope")
    if scope not in ("student", "admin") or not current_uid(scope):
        abort(403)
    sql, args = rev_query(scope)
    if not sql: abort(403)
    last = revision(scope)  # computed while the request/session context is still alive

    def events():
        nonlocal last
        yield f"data: {json.dumps({'rev': last})}\n\n"
        conn = cur = None
        try:
            conn = mysql.connector.connect(**DB)
            conn.autocommit = True  # each poll must see freshly committed changes
            cur = conn.cursor(dictionary=True)
            while True:
                time.sleep(2)
                try:
                    conn.ping(reconnect=True, attempts=1, delay=0)
                    cur.execute(sql, args)
                    row = cur.fetchone()
                    rev = row["rev"] if row and row["rev"] else "0"
                except mysql.connector.Error:
                    rev = last
                if rev != last:
                    last = rev
                    yield f"data: {json.dumps({'rev': rev})}\n\n"
        finally:
            if cur:
                try: cur.close()
                except Exception: pass
            if conn:
                try: conn.close()
                except Exception: pass

    return Response(events(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ---------- auth ----------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form; name, email, phone, pw = f["full_name"].strip(), f["email"].strip().lower(), f.get("phone", "").strip() or None, f["password"]
        if len(pw) < 6:
            flash("Password must be at least 6 characters", "error")
        elif q("SELECT 1 FROM Users WHERE email=%s OR (phone IS NOT NULL AND phone=%s)", (email, phone), one=True):
            flash("That email or phone is already registered", "error")
        else:
            q("INSERT INTO Users(full_name,email,phone,password_hash) VALUES(%s,%s,%s,%s)",
              (name, email, phone, generate_password_hash(pw)), commit=True)
            flash("Account created. Please log in.", "ok"); return redirect(url_for("login"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = q("SELECT * FROM Users WHERE email=%s", (request.form["email"].strip().lower(),), one=True)
        if not u or not check_password_hash(u["password_hash"], request.form["password"]):
            flash("Wrong email or password", "error")
        elif u["account_status"] != "active":
            flash("This account is not active. Contact the canteen office.", "error")
        else:
            role = u["role"]
            session[f"{role}_uid"] = u["user_id"]
            session[f"{role}_name"] = u["full_name"]
            if role == "admin": return redirect(url_for("admin"))
            return redirect(safe_next(request.args.get("next")))
    return render_template("auth.html", mode="login", as_role=request.args.get("as_"))

@app.route("/logout")
def logout():
    role = request.args.get("role")
    if role in ("student", "admin"):
        session.pop(f"{role}_uid", None); session.pop(f"{role}_name", None)
    else:
        session.pop("student_uid", None); session.pop("student_name", None)
        session.pop("admin_uid", None); session.pop("admin_name", None)
    return redirect(url_for("home"))

@app.route("/profile", methods=["GET", "POST"])
@login_required()
def profile():
    role = current_role(); uid = current_uid(role)
    if request.method == "POST":
        f = request.form
        try:
            q("UPDATE Users SET full_name=%s, phone=%s WHERE user_id=%s",
              (f["full_name"].strip(), f.get("phone", "").strip() or None, uid), commit=True)
            session[f"{role}_name"] = f["full_name"].strip()
            if f.get("new_password"):
                u = q("SELECT password_hash FROM Users WHERE user_id=%s", (uid,), one=True)
                if not check_password_hash(u["password_hash"], f.get("old_password", "")) or len(f["new_password"]) < 6:
                    flash("Password not changed: check your current password; new one needs 6+ characters", "error")
                    return redirect(url_for("profile"))
                q("UPDATE Users SET password_hash=%s WHERE user_id=%s", (generate_password_hash(f["new_password"]), uid), commit=True)
            flash("Profile saved", "ok")
        except mysql.connector.Error:
            flash("That phone number is already in use", "error")
        return redirect(url_for("profile"))
    return render_template("profile.html", u=q("SELECT * FROM Users WHERE user_id=%s", (uid,), one=True))

# ---------- student: browse ----------
@app.route("/")
def home():
    canteens = q("""SELECT c.*, ROUND(AVG(r.rating),1) avg_rating, COUNT(r.review_id) reviews
                    FROM Canteens c LEFT JOIN Reviews r ON r.canteen_id=c.canteen_id
                    WHERE c.is_active GROUP BY c.canteen_id ORDER BY c.canteen_name""")
    return render_template("home.html", canteens=canteens)

@app.route("/canteen/<int:cid>")
def menu(cid):
    c = q("SELECT * FROM Canteens WHERE canteen_id=%s AND is_active", (cid,), one=True) or abort(404)
    if session.get("student_uid"): g.live_scope = "student"
    s = request.args.get("q", "").strip(); cat = request.args.get("cat", type=int); veg = request.args.get("veg")
    sql = "SELECT f.*, k.category_name FROM Food_Items f JOIN Categories k ON k.category_id=f.category_id WHERE f.canteen_id=%s"
    a = [cid]
    if s: sql += " AND (f.food_name LIKE %s OR f.description LIKE %s)"; a += [f"%{s}%"] * 2
    if cat: sql += " AND f.category_id=%s"; a.append(cat)
    if veg: sql += " AND f.is_vegetarian=1"
    foods = q(sql + " ORDER BY f.is_available DESC, f.food_name", a)
    reviews = q("SELECT r.*, u.full_name FROM Reviews r JOIN Users u ON u.user_id=r.user_id WHERE r.canteen_id=%s "
                "ORDER BY review_date DESC LIMIT 5", (cid,))
    return render_template("menu.html", c=c, foods=foods, reviews=reviews, cats=q("SELECT * FROM Categories ORDER BY category_name"),
                           s=s, cat=cat, veg=veg)

# ---------- student: cart ----------
def cart_data(uid):
    out = []
    for c in q("SELECT c.cart_id, c.canteen_id, ca.canteen_name FROM Cart c JOIN Canteens ca ON ca.canteen_id=c.canteen_id "
               "WHERE c.user_id=%s AND c.cart_status='active'", (uid,)):
        c["items"] = q("SELECT ci.cart_item_id, ci.food_id, ci.quantity, f.food_name, f.price, f.is_available, f.price*ci.quantity line "
                       "FROM Cart_Items ci JOIN Food_Items f ON f.food_id=ci.food_id WHERE ci.cart_id=%s", (c["cart_id"],))
        if c["items"]:
            c["subtotal"] = sum(i["line"] for i in c["items"]); out.append(c)
    return out

@app.route("/cart")
@login_required("student")
def cart():
    return render_template("cart.html", carts=cart_data(current_uid("student")))

@app.post("/cart/add")
@login_required("student")
def cart_add():
    back = request.referrer or url_for("home")
    f = q("SELECT f.*, c.is_active FROM Food_Items f JOIN Canteens c ON c.canteen_id=f.canteen_id WHERE f.food_id=%s",
          (request.form.get("food_id", type=int),), one=True)
    if not f or not f["is_available"] or not f["is_active"]:
        flash("That item is not available right now", "error"); return redirect(back)
    uid = current_uid("student")
    cart = q("SELECT cart_id FROM Cart WHERE user_id=%s AND canteen_id=%s AND cart_status='active'", (uid, f["canteen_id"]), one=True)
    cid = cart["cart_id"] if cart else q("INSERT INTO Cart(user_id,canteen_id) VALUES(%s,%s)", (uid, f["canteen_id"]), commit=True)
    q("INSERT INTO Cart_Items(cart_id,food_id) VALUES(%s,%s) ON DUPLICATE KEY UPDATE quantity=quantity+1", (cid, f["food_id"]), commit=True)
    flash(f"{f['food_name']} added to cart", "ok"); return redirect(back)

@app.post("/cart/update")
@login_required("student")
def cart_update():
    iid, d, uid = request.form.get("item_id", type=int), request.form.get("delta", type=int, default=0), current_uid("student")
    j = "FROM Cart_Items ci JOIN Cart c ON c.cart_id=ci.cart_id WHERE ci.cart_item_id=%s AND c.user_id=%s"
    q("DELETE ci " + j + " AND ci.quantity+%s<=0", (iid, uid, d), commit=True)
    q("UPDATE Cart_Items ci JOIN Cart c ON c.cart_id=ci.cart_id SET ci.quantity=ci.quantity+%s "
      "WHERE ci.cart_item_id=%s AND c.user_id=%s AND ci.quantity+%s>0", (d, iid, uid, d), commit=True)
    return redirect(url_for("cart"))

# ---------- student: checkout ----------
def check_coupon(code, uid, subtotal):
    c = q("SELECT * FROM Coupons WHERE coupon_code=%s AND is_active AND NOW() BETWEEN valid_from AND valid_until", (code.upper(),), one=True)
    if not c: return None, "Invalid or expired coupon"
    if subtotal < c["minimum_order_amount"]: return None, f"This coupon needs a minimum order of ₹{c['minimum_order_amount']}"
    u = q("SELECT COUNT(*) n, COALESCE(SUM(o.user_id=%s),0) mine FROM Order_Coupons oc JOIN Orders o ON o.order_id=oc.order_id "
          "WHERE oc.coupon_id=%s AND o.order_status<>'cancelled'", (uid, c["coupon_id"]), one=True)
    if c["usage_limit"] and u["n"] >= c["usage_limit"]: return None, "This coupon has been fully redeemed"
    if int(u["mine"]) >= c["per_user_limit"]: return None, "You have already used this coupon"
    d = subtotal * c["discount_value"] / 100 if c["discount_type"] == "percentage" else c["discount_value"]
    if c["maximum_discount"] is not None: d = min(d, c["maximum_discount"])
    return (c, min(d, subtotal).quantize(Decimal("0.01"))), None

def pickup_slots(canteen, prep):
    t = datetime.now() + timedelta(minutes=prep + 5)
    t = t.replace(second=0, microsecond=0) + timedelta(minutes=(15 - t.minute % 15) % 15)
    end = datetime.combine(t.date(), datetime.min.time()) + canteen["closing_time"] if canteen["closing_time"] else None
    out = []
    while len(out) < 10 and (end is None or t <= end):
        out.append(t); t += timedelta(minutes=15)
    return out

@app.route("/checkout/<int:cart_id>", methods=["GET", "POST"])
@login_required("student")
def checkout(cart_id):
    uid = current_uid("student")
    cart = next((c for c in cart_data(uid) if c["cart_id"] == cart_id), None) or abort(404)
    if any(not i["is_available"] for i in cart["items"]):
        flash("Remove unavailable items before checkout", "error"); return redirect(url_for("cart"))
    canteen = q("SELECT * FROM Canteens WHERE canteen_id=%s", (cart["canteen_id"],), one=True)
    prep = q("SELECT MAX(f.preparation_time) m FROM Cart_Items ci JOIN Food_Items f ON f.food_id=ci.food_id WHERE ci.cart_id=%s", (cart_id,), one=True)["m"] or 10
    slots = pickup_slots(canteen, prep)
    code = (request.values.get("coupon") or "").strip(); coupon, disc = None, Decimal("0")
    if code:
        res, err = check_coupon(code, uid, cart["subtotal"])
        if err: flash(err, "error")
        else: coupon, disc = res; flash(f"{coupon['coupon_code']} applied: you save ₹{disc}", "ok")
    sub = cart["subtotal"]; tax = ((sub - disc) * TAX).quantize(Decimal("0.01")); total = sub - disc + tax
    if request.method == "POST" and request.form.get("action") == "place":
        method, pickup = request.form.get("method"), request.form.get("pickup")
        if method not in METHODS or not pickup:
            flash("Choose a pickup time and a payment method", "error")
        else:
            conn = db(); cur = conn.cursor()
            try:
                token = "CB" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
                cur.execute("INSERT INTO Orders(order_token,user_id,canteen_id,pickup_time,subtotal,discount_amount,tax_amount,total_amount,special_instructions) "
                            "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (token, uid, cart["canteen_id"], datetime.fromisoformat(pickup), sub, disc, tax, total,
                                                                   request.form.get("notes", "")[:500] or None))
                oid = cur.lastrowid
                cur.executemany("INSERT INTO Order_Items(order_id,food_id,food_name,quantity,unit_price,item_total) VALUES(%s,%s,%s,%s,%s,%s)",
                                [(oid, i["food_id"], i["food_name"], i["quantity"], i["price"], i["line"]) for i in cart["items"]])
                if coupon:
                    cur.execute("INSERT INTO Order_Coupons(order_id,coupon_id,discount_applied) VALUES(%s,%s,%s)", (oid, coupon["coupon_id"], disc))
                # Payment gateway is simulated: cash is paid at pickup, everything else succeeds immediately.
                cur.execute("INSERT INTO Payments(order_id,payment_method,transaction_reference,amount,payment_status) VALUES(%s,%s,%s,%s,%s)",
                            (oid, method, None if method == "cash" else "TXN" + token, total, "pending" if method == "cash" else "successful"))
                cur.execute("INSERT INTO Order_Status_History(order_id,previous_status,new_status,changed_by) VALUES(%s,NULL,'placed',%s)", (oid, uid))
                cur.execute("UPDATE Cart SET cart_status='converted' WHERE cart_id=%s", (cart_id,))
                conn.commit()
                flash(f"Order {token} placed", "ok"); return redirect(url_for("orders"))
            except Exception:
                conn.rollback()
                app.logger.exception("Could not place order")
                flash("Could not place the order. Please try again.", "error")
            finally:
                cur.close()
    return render_template("checkout.html", cart=cart, canteen=canteen, slots=slots, sub=sub, disc=disc, tax=tax, total=total, code=code, methods=METHODS)

# ---------- student: orders and reviews ----------
@app.route("/orders")
@login_required("student")
def orders():
    g.live_scope = "student"
    rows = q("SELECT o.*, c.canteen_name, p.payment_method, p.payment_status, r.rating FROM Orders o "
             "JOIN Canteens c ON c.canteen_id=o.canteen_id LEFT JOIN Payments p ON p.order_id=o.order_id "
             "LEFT JOIN Reviews r ON r.order_id=o.order_id WHERE o.user_id=%s ORDER BY o.order_date DESC", (current_uid("student"),))
    for o in rows:
        o["items"] = q("SELECT * FROM Order_Items WHERE order_id=%s", (o["order_id"],))
    return render_template("orders.html", orders=rows)

@app.post("/orders/<int:oid>/cancel")
@login_required("student")
def cancel_order(oid):
    if q("SELECT 1 FROM Orders WHERE order_id=%s AND user_id=%s AND order_status='placed'", (oid, current_uid("student")), one=True):
        set_status(oid, "cancelled", current_uid("student")); flash("Order cancelled", "ok")
    else:
        flash("Only orders the canteen has not accepted yet can be cancelled", "error")
    return redirect(url_for("orders"))

@app.post("/orders/<int:oid>/review")
@login_required("student")
def review(oid):
    o = q("SELECT canteen_id FROM Orders WHERE order_id=%s AND user_id=%s AND order_status='completed'", (oid, current_uid("student")), one=True)
    rating = request.form.get("rating", type=int)
    if not o or not rating or not 1 <= rating <= 5:
        flash("You can review completed orders with a rating of 1 to 5", "error")
    else:
        q("INSERT INTO Reviews(user_id,order_id,canteen_id,rating,comment) VALUES(%s,%s,%s,%s,%s) "
          "ON DUPLICATE KEY UPDATE rating=VALUES(rating), comment=VALUES(comment)",
          (current_uid("student"), oid, o["canteen_id"], rating, request.form.get("comment", "").strip() or None), commit=True)
        flash("Thanks for your review", "ok")
    return redirect(url_for("orders"))

def set_status(oid, new, actor=None):
    o = q("SELECT order_status FROM Orders WHERE order_id=%s", (oid,), one=True)
    q("UPDATE Orders SET order_status=%s WHERE order_id=%s", (new, oid), commit=True)
    q("INSERT INTO Order_Status_History(order_id,previous_status,new_status,changed_by) VALUES(%s,%s,%s,%s)", (oid, o["order_status"], new, actor or current_uid()), commit=True)
    if new == "cancelled":
        q("UPDATE Payments SET payment_status=IF(payment_status='successful','refunded','failed') WHERE order_id=%s AND payment_status IN ('successful','pending')", (oid,), commit=True)
    if new == "completed":
        q("UPDATE Payments SET payment_status='successful' WHERE order_id=%s AND payment_status='pending'", (oid,), commit=True)

# ---------- admin ----------
def my_canteen():
    return q("SELECT * FROM Canteens WHERE manager_id=%s", (current_uid("admin"),), one=True) or abort(403)

def back(tab): return redirect(url_for("admin", tab=tab))

@app.route("/admin")
@app.route("/admin/<tab>")
@login_required("admin")
def admin(tab="dashboard"):
    c = my_canteen(); cid = c["canteen_id"]; d = {}
    if tab in ("dashboard", "orders"): g.live_scope = "admin"
    if tab == "dashboard":
        d["today"] = q("SELECT COUNT(*) orders, COALESCE(SUM(total_amount),0) revenue, COALESCE(SUM(order_status='placed'),0) pending FROM Orders "
                       "WHERE canteen_id=%s AND DATE(order_date)=CURDATE() AND order_status<>'cancelled'", (cid,), one=True)
        d["daily"] = q("SELECT DATE(order_date) d, COUNT(*) orders, SUM(total_amount) revenue FROM Orders WHERE canteen_id=%s AND order_status<>'cancelled' "
                       "AND order_date>=CURDATE()-INTERVAL 6 DAY GROUP BY DATE(order_date) ORDER BY d", (cid,))
        d["top"] = q("SELECT oi.food_name, SUM(oi.quantity) qty, SUM(oi.item_total) rev FROM Order_Items oi JOIN Orders o ON o.order_id=oi.order_id "
                     "WHERE o.canteen_id=%s AND o.order_status<>'cancelled' GROUP BY oi.food_name ORDER BY qty DESC LIMIT 5", (cid,))
        d["rating"] = q("SELECT ROUND(AVG(rating),1) a, COUNT(*) n FROM Reviews WHERE canteen_id=%s", (cid,), one=True)
    elif tab == "orders":
        d["orders"] = q("SELECT o.*, u.full_name, u.phone, p.payment_method, p.payment_status FROM Orders o JOIN Users u ON u.user_id=o.user_id "
                        "LEFT JOIN Payments p ON p.order_id=o.order_id WHERE o.canteen_id=%s "
                        "ORDER BY o.order_status IN ('completed','cancelled'), o.pickup_time LIMIT 60", (cid,))
        for o in d["orders"]: o["items"] = q("SELECT * FROM Order_Items WHERE order_id=%s", (o["order_id"],))
        d["next"] = NEXT
    elif tab == "foods":
        d["foods"] = q("SELECT f.*, k.category_name FROM Food_Items f JOIN Categories k ON k.category_id=f.category_id WHERE f.canteen_id=%s ORDER BY k.category_name, f.food_name", (cid,))
        d["cats"] = q("SELECT * FROM Categories ORDER BY category_name")
        d["edit"] = q("SELECT * FROM Food_Items WHERE food_id=%s AND canteen_id=%s", (request.args.get("edit", type=int), cid), one=True)
    elif tab == "categories":
        d["cats"] = q("SELECT k.*, COUNT(f.food_id) n FROM Categories k LEFT JOIN Food_Items f ON f.category_id=k.category_id GROUP BY k.category_id ORDER BY category_name")
    elif tab == "coupons":
        d["coupons"] = q("SELECT c.*, COUNT(oc.order_id) used FROM Coupons c LEFT JOIN Order_Coupons oc ON oc.coupon_id=c.coupon_id GROUP BY c.coupon_id ORDER BY valid_until DESC")
    elif tab == "payments":
        d["payments"] = q("SELECT p.*, o.order_token, u.full_name FROM Payments p JOIN Orders o ON o.order_id=p.order_id JOIN Users u ON u.user_id=o.user_id "
                          "WHERE o.canteen_id=%s ORDER BY p.payment_date DESC LIMIT 100", (cid,))
    elif tab == "reviews":
        d["reviews"] = q("SELECT r.*, u.full_name, o.order_token FROM Reviews r JOIN Users u ON u.user_id=r.user_id JOIN Orders o ON o.order_id=r.order_id "
                         "WHERE r.canteen_id=%s ORDER BY review_date DESC", (cid,))
    else:
        abort(404)
    return render_template("admin.html", tab=tab, canteen=c, **d)

@app.post("/admin/orders/<int:oid>/status")
@login_required("admin")
def admin_status(oid):
    o = q("SELECT order_status FROM Orders WHERE order_id=%s AND canteen_id=%s", (oid, my_canteen()["canteen_id"]), one=True) or abort(404)
    new = request.form.get("status")
    if new in NEXT.get(o["order_status"], []): set_status(oid, new, current_uid("admin"))
    else: flash("That status change is not allowed", "error")
    return back("orders")

@app.post("/admin/foods/save")
@login_required("admin")
def food_save():
    cid = my_canteen()["canteen_id"]; f = request.form; fid = f.get("food_id", type=int)
    image_url = f.get("image_url") or None

    # Handle image file upload
    file = request.files.get("image")
    if file and file.filename and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        image_url = f"/static/uploads/{filename}"
    elif fid:
        # editing: keep existing image if no new file or text supplied
        cur_row = q("SELECT image_url FROM Food_Items WHERE food_id=%s AND canteen_id=%s", (fid, cid), one=True)
        if cur_row and not image_url:
            image_url = cur_row["image_url"]

    v = (f["food_name"].strip(), f.get("category_id", type=int), f.get("description") or None, image_url,
         f["price"], 1 if f.get("is_vegetarian") else 0, f.get("preparation_time", type=int, default=10))
    try:
        if fid:
            q("UPDATE Food_Items SET food_name=%s,category_id=%s,description=%s,image_url=%s,price=%s,is_vegetarian=%s,preparation_time=%s "
              "WHERE food_id=%s AND canteen_id=%s", v + (fid, cid), commit=True)
        else:
            q("INSERT INTO Food_Items(food_name,category_id,description,image_url,price,is_vegetarian,preparation_time,canteen_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)", v + (cid,), commit=True)
        flash("Item saved", "ok")
    except mysql.connector.Error:
        flash("Could not save: check the price and preparation time", "error")
    return back("foods")

@app.post("/admin/foods/<int:fid>/<act>")
@login_required("admin")
def food_act(fid, act):
    cid = my_canteen()["canteen_id"]
    if act == "toggle":
        q("UPDATE Food_Items SET is_available=NOT is_available WHERE food_id=%s AND canteen_id=%s", (fid, cid), commit=True)
    elif act == "delete":
        try:
            q("DELETE FROM Food_Items WHERE food_id=%s AND canteen_id=%s", (fid, cid), commit=True); flash("Item deleted", "ok")
        except mysql.connector.Error:  # referenced by old orders/carts
            q("UPDATE Food_Items SET is_available=0 WHERE food_id=%s AND canteen_id=%s", (fid, cid), commit=True)
            flash("This item is in past orders, so it was marked unavailable instead of deleted", "ok")
    return back("foods")

@app.post("/admin/categories/add")
@login_required("admin")
def cat_add():
    try: q("INSERT INTO Categories(category_name,description) VALUES(%s,%s)", (request.form["name"].strip(), request.form.get("description") or None), commit=True)
    except mysql.connector.Error: flash("That category already exists", "error")
    return back("categories")

@app.post("/admin/categories/<int:kid>/delete")
@login_required("admin")
def cat_delete(kid):
    try: q("DELETE FROM Categories WHERE category_id=%s", (kid,), commit=True)
    except mysql.connector.Error: flash("This category still has food items", "error")
    return back("categories")

@app.post("/admin/coupons/add")
@login_required("admin")
def coupon_add():
    f = request.form
    try:
        q("INSERT INTO Coupons(coupon_code,discount_type,discount_value,minimum_order_amount,maximum_discount,usage_limit,per_user_limit,valid_from,valid_until) "
          "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)", (f["code"].strip().upper(), f["type"], f["value"], f.get("min") or 0, f.get("max") or None,
          f.get("limit") or None, f.get("per_user") or 1, f["from"].replace("T", " "), f["until"].replace("T", " ")), commit=True)
        flash("Coupon created", "ok")
    except mysql.connector.Error:
        flash("Could not create coupon: the code may exist or the dates are invalid", "error")
    return back("coupons")

@app.post("/admin/coupons/<int:cid>/toggle")
@login_required("admin")
def coupon_toggle(cid):
    q("UPDATE Coupons SET is_active=NOT is_active WHERE coupon_id=%s", (cid,), commit=True); return back("coupons")

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "1") == "1", threaded=True)
