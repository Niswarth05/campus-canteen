-- ============================================
-- CAMPUS CANTEEN FOOD BOOKING AND MANAGEMENT
-- SYSTEM
-- Database: MySQL 8.0+
-- ============================================

CREATE DATABASE IF NOT EXISTS CampusCanteenDB;
USE CampusCanteenDB;

-- ============================================
-- 1. USERS TABLE
-- Stores students and administrators
-- ============================================

CREATE TABLE Users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    phone VARCHAR(15) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role ENUM('student', 'admin') DEFAULT 'student',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    account_status ENUM('active', 'inactive', 'blocked') DEFAULT 'active'
);

-- ============================================
-- 2. CANTEENS TABLE
-- Supports multiple campus canteens
-- ============================================

CREATE TABLE Canteens (
    canteen_id INT AUTO_INCREMENT PRIMARY KEY,
    canteen_name VARCHAR(100) NOT NULL,
    location VARCHAR(150) NOT NULL,
    opening_time TIME,
    closing_time TIME,
    manager_id INT,
    is_active BOOLEAN DEFAULT TRUE,

    FOREIGN KEY (manager_id)
        REFERENCES Users(user_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

-- ============================================
-- 3. CATEGORIES TABLE
-- Food categories
-- ============================================

CREATE TABLE Categories (
    category_id INT AUTO_INCREMENT PRIMARY KEY,
    category_name VARCHAR(60) NOT NULL UNIQUE,
    description VARCHAR(255)
);

-- ============================================
-- 4. FOOD ITEMS TABLE
-- Menu of individual canteens
-- ============================================

CREATE TABLE Food_Items (
    food_id INT AUTO_INCREMENT PRIMARY KEY,
    canteen_id INT NOT NULL,
    category_id INT NOT NULL,
    food_name VARCHAR(100) NOT NULL,
    description TEXT,
    image_url VARCHAR(255),
    price DECIMAL(10,2) NOT NULL,
    is_vegetarian BOOLEAN DEFAULT TRUE,
    preparation_time INT DEFAULT 10,
    is_available BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_food_price CHECK (price >= 0),
    CONSTRAINT chk_prep_time CHECK (preparation_time >= 0),

    FOREIGN KEY (canteen_id)
        REFERENCES Canteens(canteen_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    FOREIGN KEY (category_id)
        REFERENCES Categories(category_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

-- ============================================
-- 5. CART TABLE
-- One active cart per student per canteen.
-- Historical converted/abandoned carts are allowed.
-- ============================================

CREATE TABLE Cart (
    cart_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    canteen_id INT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    cart_status ENUM('active', 'converted', 'abandoned')
        DEFAULT 'active',

    -- 1 for active carts, NULL for historical ones, so only active carts are unique.
    active_flag TINYINT GENERATED ALWAYS AS (
        CASE WHEN cart_status = 'active' THEN 1 ELSE NULL END
    ) STORED,

    FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (canteen_id)
        REFERENCES Canteens(canteen_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    UNIQUE KEY uq_one_active_cart (user_id, canteen_id, active_flag)
);

-- ============================================
-- 6. CART ITEMS TABLE
-- Food items added to a cart
-- ============================================

CREATE TABLE Cart_Items (
    cart_item_id INT AUTO_INCREMENT PRIMARY KEY,
    cart_id INT NOT NULL,
    food_id INT NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_cart_quantity CHECK (quantity > 0),

    FOREIGN KEY (cart_id)
        REFERENCES Cart(cart_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (food_id)
        REFERENCES Food_Items(food_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    UNIQUE KEY uq_cart_food (cart_id, food_id)
);

-- ============================================
-- 7. ORDERS TABLE
-- Stores confirmed food bookings
-- ============================================

CREATE TABLE Orders (
    order_id INT AUTO_INCREMENT PRIMARY KEY,
    order_token VARCHAR(30) NOT NULL UNIQUE,
    user_id INT NOT NULL,
    canteen_id INT NOT NULL,
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pickup_time DATETIME,
    order_status ENUM(
        'placed',
        'accepted',
        'preparing',
        'ready',
        'completed',
        'cancelled'
    ) DEFAULT 'placed',
    subtotal DECIMAL(10,2) NOT NULL,
    discount_amount DECIMAL(10,2) DEFAULT 0.00,
    tax_amount DECIMAL(10,2) DEFAULT 0.00,
    total_amount DECIMAL(10,2) NOT NULL,
    special_instructions VARCHAR(500),

    CONSTRAINT chk_order_subtotal CHECK (subtotal >= 0),
    CONSTRAINT chk_order_discount CHECK (discount_amount >= 0),
    CONSTRAINT chk_order_tax CHECK (tax_amount >= 0),
    CONSTRAINT chk_order_total CHECK (total_amount >= 0),
    -- total is a stored snapshot of subtotal - discount + tax; the DBMS keeps it consistent
    CONSTRAINT chk_order_total_math CHECK (total_amount = subtotal - discount_amount + tax_amount),

    FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    FOREIGN KEY (canteen_id)
        REFERENCES Canteens(canteen_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    -- target of the composite foreign key used by Reviews
    UNIQUE KEY uq_order_owner (order_id, user_id, canteen_id)
);

-- ============================================
-- 8. ORDER ITEMS TABLE
-- Items belonging to each order.
-- Stores price snapshots so later menu price
-- changes do not change old order totals.
-- ============================================

CREATE TABLE Order_Items (
    order_item_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    food_id INT NOT NULL,
    food_name VARCHAR(100) NOT NULL,
    quantity INT NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    item_total DECIMAL(10,2) NOT NULL,

    CONSTRAINT chk_order_item_quantity CHECK (quantity > 0),
    CONSTRAINT chk_unit_price CHECK (unit_price >= 0),
    CONSTRAINT chk_item_total CHECK (item_total >= 0),
    CONSTRAINT chk_item_total_math CHECK (item_total = quantity * unit_price),

    FOREIGN KEY (order_id)
        REFERENCES Orders(order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (food_id)
        REFERENCES Food_Items(food_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

-- ============================================
-- 9. PAYMENTS TABLE
-- Payment transactions for orders
-- ============================================

CREATE TABLE Payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    payment_method ENUM(
        'UPI',
        'card',
        'cash',
        'net_banking',
        'wallet'
    ) NOT NULL,
    transaction_reference VARCHAR(100) UNIQUE,
    amount DECIMAL(10,2) NOT NULL,
    payment_status ENUM(
        'pending',
        'successful',
        'failed',
        'refunded'
    ) DEFAULT 'pending',
    payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_payment_amount CHECK (amount >= 0),

    FOREIGN KEY (order_id)
        REFERENCES Orders(order_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

-- ============================================
-- 10. COUPONS TABLE
-- Discount and promotional offers
-- ============================================

CREATE TABLE Coupons (
    coupon_id INT AUTO_INCREMENT PRIMARY KEY,
    coupon_code VARCHAR(30) NOT NULL UNIQUE,
    discount_type ENUM('percentage', 'fixed') NOT NULL,
    discount_value DECIMAL(10,2) NOT NULL,
    minimum_order_amount DECIMAL(10,2) DEFAULT 0.00,
    maximum_discount DECIMAL(10,2),
    usage_limit INT,
    per_user_limit INT DEFAULT 1,
    valid_from DATETIME NOT NULL,
    valid_until DATETIME NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,

    CONSTRAINT chk_coupon_discount CHECK (discount_value > 0),
    CONSTRAINT chk_coupon_minimum CHECK (minimum_order_amount >= 0),
    CONSTRAINT chk_coupon_period CHECK (valid_until > valid_from),
    CONSTRAINT chk_coupon_usage CHECK (usage_limit IS NULL OR usage_limit > 0),
    CONSTRAINT chk_coupon_user_limit CHECK (per_user_limit > 0),
    CONSTRAINT chk_coupon_max_discount CHECK (
        maximum_discount IS NULL OR maximum_discount >= 0
    )
);

-- ============================================
-- 11. ORDER COUPONS TABLE
-- Connects coupons with orders
-- ============================================

CREATE TABLE Order_Coupons (
    order_coupon_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL UNIQUE,
    coupon_id INT NOT NULL,
    discount_applied DECIMAL(10,2) NOT NULL,

    CONSTRAINT chk_applied_discount CHECK (discount_applied >= 0),

    FOREIGN KEY (order_id)
        REFERENCES Orders(order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (coupon_id)
        REFERENCES Coupons(coupon_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

-- ============================================
-- 12. REVIEWS TABLE
-- Student feedback and ratings
-- ============================================

CREATE TABLE Reviews (
    review_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    order_id INT NOT NULL,
    canteen_id INT NOT NULL,
    rating INT NOT NULL,
    comment TEXT,
    review_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_rating CHECK (rating BETWEEN 1 AND 5),

    FOREIGN KEY (user_id)
        REFERENCES Users(user_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    FOREIGN KEY (order_id)
        REFERENCES Orders(order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (canteen_id)
        REFERENCES Canteens(canteen_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE,

    -- user_id and canteen_id repeat facts stored on the order; this key makes it
    -- impossible for a review to disagree with its order
    CONSTRAINT fk_review_matches_order FOREIGN KEY (order_id, user_id, canteen_id)
        REFERENCES Orders(order_id, user_id, canteen_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    UNIQUE (user_id, order_id)
);

-- ============================================
-- 13. ORDER STATUS HISTORY TABLE
-- Tracks changes in order status
-- ============================================

CREATE TABLE Order_Status_History (
    history_id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    previous_status VARCHAR(20),
    new_status VARCHAR(20) NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    changed_by INT,

    FOREIGN KEY (order_id)
        REFERENCES Orders(order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    FOREIGN KEY (changed_by)
        REFERENCES Users(user_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

-- ============================================
-- INDEXES FOR BETTER QUERY PERFORMANCE
-- ============================================

CREATE INDEX idx_food_canteen
ON Food_Items(canteen_id);

CREATE INDEX idx_food_category
ON Food_Items(category_id);

CREATE INDEX idx_order_user
ON Orders(user_id);

CREATE INDEX idx_order_canteen
ON Orders(canteen_id);

CREATE INDEX idx_order_date
ON Orders(order_date);

CREATE INDEX idx_order_status
ON Orders(order_status);

CREATE INDEX idx_payment_order
ON Payments(order_id);

CREATE INDEX idx_cart_user
ON Cart(user_id);

CREATE INDEX idx_history_order
ON Order_Status_History(order_id);

-- ============================================
-- VIEWS
-- ============================================

-- One row per order with student, canteen and payment details
CREATE VIEW v_order_summary AS
SELECT o.order_id, o.order_token, u.full_name AS student, c.canteen_name,
       o.order_status, o.total_amount, o.order_date,
       p.payment_method, p.payment_status
FROM Orders o
JOIN Users u    ON u.user_id = o.user_id
JOIN Canteens c ON c.canteen_id = o.canteen_id
LEFT JOIN Payments p ON p.order_id = o.order_id;

-- Review count and average rating for each canteen
CREATE VIEW v_canteen_ratings AS
SELECT c.canteen_id, c.canteen_name,
       COUNT(r.review_id) AS review_count,
       ROUND(AVG(r.rating), 2) AS avg_rating
FROM Canteens c
LEFT JOIN Reviews r ON r.canteen_id = c.canteen_id
GROUP BY c.canteen_id, c.canteen_name;
