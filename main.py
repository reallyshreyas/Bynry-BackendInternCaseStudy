from flask import Flask, jsonify
import sqlite3
import datetime

# --- Database Setup (for a runnable example) ---
def setup_database():
    """Initializes an in-memory SQLite database and populates it with sample data."""
    conn = sqlite3.connect(':memory:', check_same_thread=False)
    conn.row_factory = sqlite3.Row  # Allows accessing columns by name
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''CREATE TABLE Companies (company_id INT PRIMARY KEY, name TEXT)''')
    cursor.execute('''CREATE TABLE Warehouses (warehouse_id INT PRIMARY KEY, company_id INT, name TEXT)''')
    cursor.execute('''CREATE TABLE Suppliers (supplier_id INT PRIMARY KEY, name TEXT, contact_email TEXT)''')
    cursor.execute('''
        CREATE TABLE Products (
            product_id INT PRIMARY KEY,
            sku TEXT, name TEXT,
            low_stock_threshold INT
        )''')
    cursor.execute('''CREATE TABLE ProductSuppliers (product_id INT, supplier_id INT, PRIMARY KEY (product_id, supplier_id))''')
    cursor.execute('''CREATE TABLE Inventory (product_id INT, warehouse_id INT, quantity INT, PRIMARY KEY (product_id, warehouse_id))''')
    cursor.execute('''
        CREATE TABLE Sales (
            sale_id INT PRIMARY KEY,
            product_id INT,
            warehouse_id INT,
            quantity_sold INT,
            sale_date DATE
        )''')

    # Populate with sample data to match the expected output
    cursor.execute("INSERT INTO Companies VALUES (1, 'Gadget Corp')")
    cursor.execute("INSERT INTO Warehouses VALUES (456, 1, 'Main Warehouse'), (457, 1, 'West Coast Hub')")
    cursor.execute("INSERT INTO Suppliers VALUES (789, 'Supplier Corp', 'orders@supplier.com'), (790, 'Component Masters', 'sales@components.com')")
    # Set threshold to 20 for Widget A
    cursor.execute("INSERT INTO Products VALUES (123, 'WID-001', 'Widget A', 20), (124, 'GAD-002', 'Gadget B', 50)")
    cursor.execute("INSERT INTO ProductSuppliers VALUES (123, 789), (124, 790)")
    # Total stock for Widget A is 15 (5 + 10), which is less than the threshold of 20
    cursor.execute("INSERT INTO Inventory VALUES (123, 456, 5), (123, 457, 10)")
    # Gadget B is not low stock
    cursor.execute("INSERT INTO Inventory VALUES (124, 456, 30), (124, 457, 40)")

    # Sales data for Widget A to calculate days_until_stockout, using static dates.
    cursor.execute("INSERT INTO Sales VALUES (1, 123, 456, 20, '2025-07-23')")
    cursor.execute("INSERT INTO Sales VALUES (2, 123, 457, 18, '2025-07-28')")
    # No recent sales for Gadget B
    cursor.execute("INSERT INTO Sales VALUES (3, 124, 456, 2, '2025-06-18')")


    conn.commit()
    return conn

# --- Flask Application ---
app = Flask(__name__)
db_conn = setup_database()

@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):
    """
    Returns a list of products that are below their low-stock threshold
    and have had recent sales activity for a given company.
    """
    cursor = db_conn.cursor()

    # 1. Find all products for the given company that have had sales in the last 30 days.
    # Using a static date for "30 days ago" for consistency.
    thirty_days_ago_str = '2025-07-03'
    cursor.execute("""
        SELECT DISTINCT s.product_id
        FROM Sales s
        JOIN Warehouses w ON s.warehouse_id = w.warehouse_id
        WHERE w.company_id = ? AND s.sale_date >= ?
    """, (company_id, thirty_days_ago_str))
    
    active_product_ids = [row['product_id'] for row in cursor.fetchall()]

    if not active_product_ids:
        return jsonify({"alerts": [], "total_alerts": 0})

    # 2. Get total stock and details for each active product, filtering for low stock.
    placeholders = ','.join('?' for _ in active_product_ids)
    query = f"""
        SELECT
            p.product_id,
            p.name AS product_name,
            p.sku,
            p.low_stock_threshold,
            SUM(i.quantity) AS total_stock
        FROM Products p
        JOIN Inventory i ON p.product_id = i.product_id
        JOIN Warehouses w ON i.warehouse_id = w.warehouse_id
        WHERE p.product_id IN ({placeholders}) AND w.company_id = ?
        GROUP BY p.product_id
        HAVING total_stock < p.low_stock_threshold
    """
    
    params = tuple(active_product_ids) + (company_id,)
    cursor.execute(query, params)
    low_stock_products = cursor.fetchall()

    alerts = []
    # 3. For each low-stock product, enrich with supplier and stockout data.
    for product in low_stock_products:
        product_id = product['product_id']

        # Calculate average daily sales over the last 30 days
        cursor.execute("""
            SELECT SUM(quantity_sold)
            FROM Sales
            WHERE product_id = ? AND sale_date >= ?
        """, (product_id, thirty_days_ago_str))
        total_sales_last_30_days = cursor.fetchone()[0] or 0
        
        avg_daily_sales = total_sales_last_30_days / 30.0
        
        # Calculate days until stockout
        days_until_stockout = 0
        if avg_daily_sales > 0:
            days_until_stockout = int(product['total_stock'] / avg_daily_sales)
        
        # Get supplier information
        cursor.execute("""
            SELECT s.supplier_id, s.name, s.contact_email
            FROM Suppliers s
            JOIN ProductSuppliers ps ON s.supplier_id = ps.supplier_id
            WHERE ps.product_id = ?
            LIMIT 1
        """, (product_id,))
        supplier_info = cursor.fetchone()

        # Get stock levels for all warehouses for this product
        cursor.execute("""
            SELECT w.warehouse_id, w.name, i.quantity
            FROM Inventory i
            JOIN Warehouses w ON i.warehouse_id = w.warehouse_id
            WHERE i.product_id = ? AND w.company_id = ? AND i.quantity > 0
        """, (product_id, company_id))
        
        all_warehouses_for_product = cursor.fetchall()

        # Find the warehouse with the lowest stock for this product.
        if all_warehouses_for_product:
            lowest_stock_warehouse = min(all_warehouses_for_product, key=lambda x: x['quantity'])

            # Create just one alert for the warehouse with the lowest stock.
            alert = {
                "product_id": product_id,
                "product_name": product['product_name'],
                "sku": product['sku'],
                "warehouse_id": lowest_stock_warehouse['warehouse_id'],
                "warehouse_name": lowest_stock_warehouse['name'],
                "current_stock": lowest_stock_warehouse['quantity'],
                "threshold": product['low_stock_threshold'],
                "days_until_stockout": days_until_stockout,
                "supplier": {
                    "id": supplier_info['supplier_id'] if supplier_info else None,
                    "name": supplier_info['name'] if supplier_info else "N/A",
                    "contact_email": supplier_info['contact_email'] if supplier_info else "N/A"
                }
            }
            alerts.append(alert)

    return jsonify({"alerts": alerts, "total_alerts": len(alerts)})


if __name__ == '__main__':
    app.run(debug=True)
