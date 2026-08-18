from flask import Flask, render_template, request, jsonify
import sqlite3
import os

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(__file__), '..', 'templates'))

# Use /tmp for database on Vercel
DATABASE = "/tmp/warehouse.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            sku TEXT NOT NULL UNIQUE,
            quantity INTEGER NOT NULL,
            minimum_stock INTEGER NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer TEXT NOT NULL,
            product TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            priority TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    # Sample products
    count = conn.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]

    if count == 0:

        sample_products = [
            ("Laptop", "LAP-001", 24, 5),
            ("Wireless Mouse", "MOU-021", 7, 10),
            ("Keyboard", "KEY-015", 0, 5),
            ("USB-C Hub", "USB-009", 18, 5)
        ]

        conn.executemany("""
            INSERT INTO products
            (name, sku, quantity, minimum_stock)
            VALUES (?, ?, ?, ?)
        """, sample_products)

    conn.commit()
    conn.close()


# Initialize database on startup
try:
    init_db()
except:
    pass


# HOME
@app.route("/")
def home():
    return render_template("index.html")


# GET PRODUCTS
@app.route("/api/products")
def get_products():
    conn = get_db()
    products = conn.execute(
        "SELECT * FROM products ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(p) for p in products])


# ADD PRODUCT
@app.route("/api/products", methods=["POST"])
def add_product():
    data = request.json
    name = data.get("name")
    sku = data.get("sku")
    quantity = int(data.get("quantity", 0))
    minimum_stock = int(data.get("minimum_stock", 0))

    if not name or not sku:
        return jsonify({
            "success": False,
            "message": "Product name and SKU required"
        }), 400

    try:
        conn = get_db()
        conn.execute("""
            INSERT INTO products
            (name, sku, quantity, minimum_stock)
            VALUES (?, ?, ?, ?)
        """, (name, sku, quantity, minimum_stock))
        conn.commit()
        conn.close()
        return jsonify({
            "success": True,
            "message": "Product added successfully"
        })
    except sqlite3.IntegrityError:
        return jsonify({
            "success": False,
            "message": "SKU already exists"
        }), 400


# DELETE PRODUCT
@app.route("/api/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM products WHERE id=?",
        (product_id,)
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# GET ORDERS
@app.route("/api/orders")
def get_orders():
    conn = get_db()
    orders = conn.execute(
        "SELECT * FROM orders ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(o) for o in orders])


# CREATE ORDER
@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.json
    customer = data.get("customer")
    product = data.get("product")
    quantity = int(data.get("quantity", 0))
    priority = data.get("priority")

    if not customer or not product or quantity <= 0:
        return jsonify({
            "success": False,
            "message": "Invalid order details"
        }), 400

    conn = get_db()
    product_data = conn.execute("""
        SELECT * FROM products
        WHERE name=?
    """, (product,)).fetchone()

    if not product_data:
        conn.close()
        return jsonify({
            "success": False,
            "message": "Product not found"
        }), 404

    conn.execute("""
        INSERT INTO orders
        (customer, product, quantity, priority, status)
        VALUES (?, ?, ?, ?, ?)
    """, (customer, product, quantity, priority, "Pending"))

    conn.commit()
    conn.close()
    return jsonify({
        "success": True,
        "message": "Order created successfully"
    })


# UPDATE ORDER STATUS
@app.route("/api/orders/<int:order_id>/status", methods=["PUT"])
def update_order_status(order_id):
    data = request.json
    status = data.get("status")
    conn = get_db()
    conn.execute("""
        UPDATE orders
        SET status=?
        WHERE id=?
    """, (status, order_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True})


# SMART ALLOCATION
@app.route("/api/allocation", methods=["POST"])
def allocation():
    data = request.json
    product_name = data.get("product")
    required = int(data.get("quantity", 0))
    priority = data.get("priority")

    conn = get_db()
    product = conn.execute("""
        SELECT * FROM products
        WHERE name=?
    """, (product_name,)).fetchone()
    conn.close()

    if not product:
        return jsonify({
            "success": False,
            "message": "Product not found"
        }), 404

    available = product["quantity"]
    allocated = min(required, available)
    shortage = max(required - available, 0)

    if priority == "Critical":
        decision = (
            f"Allocate {allocated} units immediately. "
            f"Shortage: {shortage} units. "
            "Create urgent replenishment request."
        )
    elif priority == "High":
        decision = (
            f"Allocate available stock first. "
            f"Shortage: {shortage} units. "
            "Prioritize incoming stock."
        )
    else:
        decision = (
            "Hold allocation if stock is insufficient. "
            "Critical orders should be fulfilled first."
        )

    return jsonify({
        "success": True,
        "required": required,
        "available": available,
        "allocated": allocated,
        "shortage": shortage,
        "decision": decision
    })


# DASHBOARD
@app.route("/api/dashboard")
def dashboard():
    conn = get_db()
    total_products = conn.execute(
        "SELECT COUNT(*) FROM products"
    ).fetchone()[0]
    total_stock = conn.execute(
        "SELECT COALESCE(SUM(quantity),0) FROM products"
    ).fetchone()[0]
    total_orders = conn.execute(
        "SELECT COUNT(*) FROM orders"
    ).fetchone()[0]
    low_stock = conn.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE quantity > 0
        AND quantity <= minimum_stock
    """).fetchone()[0]
    out_stock = conn.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE quantity = 0
    """).fetchone()[0]
    conn.close()

    return jsonify({
        "total_products": total_products,
        "total_stock": total_stock,
        "total_orders": total_orders,
        "low_stock": low_stock,
        "out_stock": out_stock
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
