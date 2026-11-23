# CampusBite

A campus canteen food booking and management website. Students browse canteens, order ahead and pick up their food; canteen admins manage the menu, orders and sales. Built as a DBMS project with Flask and MySQL 8.

## Features

**Students**
- Register, log in, edit profile
- Browse canteens with ratings and opening hours
- Search the menu, filter by category and veg/non-veg
- Cart per canteen, coupon codes, 5% GST, pickup time slots
- Order tracking (placed, accepted, preparing, ready, completed), cancel before acceptance
- Order history and canteen reviews

**Admins (one per canteen)**
- Dashboard: today's orders and sales, 7-day sales chart, top sellers, average rating
- Accept or reject orders and update preparation status (every change is logged)
- Add, edit, delete and sold-out toggle for food items; manage categories
- Create and disable coupons
- View payments and customer reviews

## Tech stack

| Part | Technology |
| --- | --- |
| Frontend | HTML, CSS, JavaScript, Jinja2 templates, Lucide icons |
| Backend | Python 3, Flask |
| Database | MySQL 8 (13 tables, see `schema.sql`) |
| Connector | mysql-connector-python |

## Quick start

Requirements: Python 3.10+, `make`, and Docker (or your own MySQL 8 server).

```bash
git clone https://github.com/Niswarth05/campus-canteen.git && cd campus-canteen
make setup     # creates .env and .venv, starts MySQL 8 in Docker, loads demo data
make run       # http://127.0.0.1:5000
```

If your user cannot run Docker without sudo: `make setup DOCKER="sudo docker"`.

**Using your own MySQL server instead of Docker:** copy `.env.example` to `.env`, set `DB_HOST`, `DB_PORT`, `DB_USER` and `DB_PASS`, then run `make install db run`. The user needs permission to create databases.

`make db` **drops and recreates** `CampusCanteenDB`. Do not run it on data you want to keep.

Run `make help` to see every target.

## Demo accounts

| Role | Email | Password |
| --- | --- | --- |
| Student | student@campus.edu | student123 |
| Admin (Main Canteen) | admin1@campus.edu | admin123 |
| Admin (Food Court) | admin2@campus.edu | admin123 |
| Other canteens | admin3@campus.edu to admin10@campus.edu | admin123 |

Each admin manages one canteen. The demo data has 10 canteens, 52 menu items, 25 users, 52 orders with payments, status history and reviews, and 10 coupons. Admin 1 and 2 have live orders to accept and update.

## Using both sides at once

You can stay signed in as a student **and** an admin in the same browser. Sign in as a student in one tab, then sign in as an admin in another — each page uses the login for its role, so neither session replaces the other. When both are signed in, the navigation shows separate "Log out student" and "Log out admin" links.

## Live updates

The student *My orders* page, the admin *Dashboard*/*Orders* pages and the canteen menu refresh automatically within about 2 seconds when something changes — a new order, a status update, or a food item edited or marked sold out/available. This uses Server-Sent Events (`GET /api/stream?scope=student|admin`); no manual refresh is needed. A small orange dot next to the logo shows that live updates are active.

## Project layout

```
app.py            Flask routes (student and admin)
init_db.py        creates the database from schema.sql and loads demo data
schema.sql        MySQL schema: 13 tables, constraints, indexes, 2 views
queries.sql       17 example queries (joins, GROUP BY, HAVING, subqueries, views) plus insert/update/delete
connect-workbench.txt  step-by-step guide to browse and query the database in MySQL Workbench
templates/        Jinja2 pages
static/style.css  styling
Makefile          setup, run and database helpers
.env.example      configuration template
```

## Database design

`Users`, `Canteens`, `Categories`, `Food_Items`, `Cart`, `Cart_Items`, `Orders`, `Order_Items`, `Payments`, `Coupons`, `Order_Coupons`, `Reviews`, `Order_Status_History`.

- Order items store a price snapshot, so later menu price changes never alter old orders.
- A generated column plus a unique key allows only one active cart per student per canteen.
- Orders are placed in a single transaction: order, items, coupon, payment, history and cart conversion succeed or fail together.
- Views: `v_order_summary` (orders with student, canteen and payment) and `v_canteen_ratings` (average rating per canteen).
- Integrity: a composite foreign key forces every review to match the student and canteen of its order, and CHECK constraints keep `Orders.total_amount` and `Order_Items.item_total` consistent with the amounts they are derived from.
- `docs/er-diagram.png` is the ER diagram (generated from the database schema).
- `queries.sql` can be opened in MySQL Workbench (File > Open SQL Script) and run as is. See `connect-workbench.txt` for connecting.

## Notes and limitations

- Payments are simulated (no real gateway). Cash stays pending until the order is completed.
- Coupons apply to all canteens.
- Set a strong `SECRET_KEY` and `FLASK_DEBUG=0` before any real deployment, and use a production server such as gunicorn with a streaming-friendly worker (e.g. gevent) for the live-update endpoints.
- Food images are optional: paste an image URL when editing a food item.

## License

MIT, see `LICENSE`.
