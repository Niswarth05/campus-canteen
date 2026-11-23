-- ============================================================
-- CAMPUSBITE - SAMPLE SQL QUERIES
-- Run after: python init_db.py   (MySQL Workbench: File > Open SQL Script)
-- ============================================================
USE CampusCanteenDB;

-- Q1. WHERE + ORDER BY: vegetarian items under Rs.80 that are available, cheapest first
SELECT food_name, price, preparation_time
FROM Food_Items
WHERE is_vegetarian = 1 AND is_available = 1 AND price < 80
ORDER BY price ASC, food_name;

-- Q2. JOIN (3 tables): full menu with canteen and category
SELECT c.canteen_name, k.category_name, f.food_name, f.price
FROM Food_Items f
JOIN Canteens c   ON c.canteen_id = f.canteen_id
JOIN Categories k ON k.category_id = f.category_id
ORDER BY c.canteen_name, k.category_name, f.food_name;

-- Q3. GROUP BY + aggregates: revenue and order count per canteen (cancelled excluded)
SELECT c.canteen_name,
       COUNT(o.order_id)    AS orders,
       SUM(o.total_amount)  AS revenue,
       ROUND(AVG(o.total_amount), 2) AS avg_order_value
FROM Canteens c
JOIN Orders o ON o.canteen_id = c.canteen_id
WHERE o.order_status <> 'cancelled'
GROUP BY c.canteen_id, c.canteen_name
ORDER BY revenue DESC;

-- Q4. GROUP BY + HAVING: canteens rated 4.0 or higher with at least 3 reviews
SELECT c.canteen_name, COUNT(*) AS reviews, ROUND(AVG(r.rating), 2) AS avg_rating
FROM Reviews r
JOIN Canteens c ON c.canteen_id = r.canteen_id
GROUP BY c.canteen_id, c.canteen_name
HAVING COUNT(*) >= 3 AND AVG(r.rating) >= 4.0
ORDER BY avg_rating DESC;

-- Q5. Subquery: items priced above the average price of all items
SELECT food_name, price
FROM Food_Items
WHERE price > (SELECT AVG(price) FROM Food_Items)
ORDER BY price DESC;

-- Q6. Subquery (NOT IN): students who have never placed an order
SELECT user_id, full_name, email
FROM Users
WHERE role = 'student'
  AND user_id NOT IN (SELECT user_id FROM Orders);

-- Q7. Correlated subquery: the most expensive item of every canteen
SELECT c.canteen_name, f.food_name, f.price
FROM Food_Items f
JOIN Canteens c ON c.canteen_id = f.canteen_id
WHERE f.price = (SELECT MAX(f2.price) FROM Food_Items f2 WHERE f2.canteen_id = f.canteen_id)
ORDER BY f.price DESC;

-- Q8. VIEW: today's open orders (not completed or cancelled) from the order summary view
SELECT order_token, student, canteen_name, order_status, total_amount
FROM v_order_summary
WHERE order_status NOT IN ('completed', 'cancelled')
ORDER BY order_date DESC;

-- Q9. VIEW: canteens ranked by rating
SELECT canteen_name, review_count, avg_rating
FROM v_canteen_ratings
ORDER BY avg_rating DESC, review_count DESC;

-- Q10. Aggregate + JOIN + LIMIT: top 5 best-selling items
SELECT oi.food_name, SUM(oi.quantity) AS units_sold, SUM(oi.item_total) AS revenue
FROM Order_Items oi
JOIN Orders o ON o.order_id = oi.order_id
WHERE o.order_status <> 'cancelled'
GROUP BY oi.food_name
ORDER BY units_sold DESC
LIMIT 5;

-- Q11. GROUP BY + HAVING: students who spent more than Rs.300 in total
SELECT u.full_name, COUNT(o.order_id) AS orders, SUM(o.total_amount) AS total_spent
FROM Users u
JOIN Orders o ON o.user_id = u.user_id
WHERE o.order_status = 'completed'
GROUP BY u.user_id, u.full_name
HAVING SUM(o.total_amount) > 300
ORDER BY total_spent DESC;

-- Q12. Payments grouped by method and status
SELECT payment_method, payment_status, COUNT(*) AS payments, SUM(amount) AS amount
FROM Payments
GROUP BY payment_method, payment_status
ORDER BY payment_method, payment_status;

-- Q13. Coupon usage: how often each coupon was used and the total discount given
SELECT cp.coupon_code, COUNT(oc.order_id) AS times_used, COALESCE(SUM(oc.discount_applied), 0) AS total_discount
FROM Coupons cp
LEFT JOIN Order_Coupons oc ON oc.coupon_id = cp.coupon_id
GROUP BY cp.coupon_id, cp.coupon_code
ORDER BY times_used DESC;

-- Q14. LEFT JOIN + HAVING: categories that have 3 or more menu items
SELECT k.category_name, COUNT(f.food_id) AS items
FROM Categories k
LEFT JOIN Food_Items f ON f.category_id = k.category_id
GROUP BY k.category_id, k.category_name
HAVING COUNT(f.food_id) >= 3
ORDER BY items DESC;

-- Q15. Daily sales for the last 7 days
SELECT DATE(order_date) AS day, COUNT(*) AS orders, SUM(total_amount) AS sales
FROM Orders
WHERE order_status <> 'cancelled' AND order_date >= CURDATE() - INTERVAL 6 DAY
GROUP BY DATE(order_date)
ORDER BY day;

-- Q16. Search with LIKE: any item with "biryani" in its name
SELECT c.canteen_name, f.food_name, f.price
FROM Food_Items f JOIN Canteens c ON c.canteen_id = f.canteen_id
WHERE f.food_name LIKE '%biryani%';

-- Q17. Order timeline: full status history of the newest order
SELECT o.order_token, h.previous_status, h.new_status, h.changed_at, u.full_name AS changed_by
FROM Order_Status_History h
JOIN Orders o ON o.order_id = h.order_id
LEFT JOIN Users u ON u.user_id = h.changed_by
WHERE o.order_id = (SELECT MAX(order_id) FROM Orders)
ORDER BY h.changed_at;

-- ------------------------------------------------------------
-- DML EXAMPLES (insert / update / delete)
-- ------------------------------------------------------------
INSERT INTO Categories (category_name, description) VALUES ('Specials', 'Chef specials');

UPDATE Food_Items SET price = price + 5 WHERE food_name = 'Masala Chai';

DELETE FROM Categories WHERE category_name = 'Specials';
