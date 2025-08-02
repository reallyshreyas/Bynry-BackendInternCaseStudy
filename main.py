from flask import Flask, jsonify
import sqlite3
import datetime

def setup_database():
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

    # Populate with sample data
    cursor.execute("INSERT INTO Companies VALUES (1, 'Gadget Corp')")
    cursor.execute("INSERT INTO Warehouses VALUES (456, 1, 'Main Warehouse'), (457, 1, 'West Coast Hub')")
    cursor.execute("INSERT INTO Suppliers VALUES (789, 'Supplier Corp', 'orders@supplier.com'), (790, 'Component Masters', 'sales@components.com')")
    # Set threshold to 10 for simpler check
    cursor.execute("INSERT INTO Products VALUES (123, 'WID-001', 'Widget A', 10), (124, 'GAD-002', 'Gadget B', 50)")
    cursor.execute("INSERT INTO ProductSuppliers VALUES (123, 789), (124, 790)")
    # Stock for Widget A: 5 in one warehouse (low), 12 in another (not low)
    cursor.execute("INSERT INTO Inventory VALUES (123, 456, 5), (123, 457, 12)")
    cursor.execute("INSERT INTO Inventory VALUES (124, 456, 30), (124, 457, 40)")
    # Sales data (no longer used in the simplified logic, but kept for context)
    today = datetime.date.today()
    cursor.execute("INSERT INTO Sales VALUES (1, 123, 456, 10, ?)", (today - datetime.timedelta(days=10),))
    cursor.execute("INSERT INTO Sales VALUES (2, 123, 457, 5, ?)", (today - datetime.timedelta(days=5),))
    cursor.execute("INSERT INTO Sales VALUES (3, 124, 456, 2, ?)", (today - datetime.timedelta(days=45),))


    conn.commit()
    return conn

# --- Flask Application ---
app = Flask(__name__)
db_conn = setup_database()

@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):
    """
    Returns a simplified list of products that are below their low-stock threshold
    for a given company.

    This simplified version checks stock level per warehouse against the threshold,
    and does not check for recent sales or calculate days until stockout.
    """
    cursor = db_conn.cursor()

    # A single, simpler query to get all necessary data at once.
    # It joins inventory, products, warehouses, and suppliers.
    # The check `i.quantity < p.low_stock_threshold` is a simplification,
    # as it checks stock per warehouse, not total stock across all warehouses.
    query = """
        SELECT
            p.product_id,
            p.name AS product_name,
            p.sku,
            p.low_stock_threshold,
            w.warehouse_id,
            w.name AS warehouse_name,
            i.quantity AS current_stock,
            s.supplier_id,
            s.name AS supplier_name,
            s.contact_email
        FROM Inventory i
        JOIN Products p ON i.product_id = p.product_id
        JOIN Warehouses w ON i.warehouse_id = w.warehouse_id
        LEFT JOIN ProductSuppliers ps ON p.product_id = ps.product_id
        LEFT JOIN Suppliers s ON ps.supplier_id = s.supplier_id
        WHERE w.company_id = ? AND i.quantity < p.low_stock_threshold
    """
    cursor.execute(query, (company_id,))
    
    rows = cursor.fetchall()

    alerts = []
    for row in rows:
        alert = {
            "product_id": row['product_id'],
            "product_name": row['product_name'],
            "sku": row['sku'],
            "warehouse_id": row['warehouse_id'],
            "warehouse_name": row['warehouse_name'],
            "current_stock": row['current_stock'],
            "threshold": row['low_stock_threshold'],
            "supplier": {
                "id": row['supplier_id'] if row['supplier_id'] else None,
                "name": row['supplier_name'] if row['supplier_name'] else "N/A",
                "contact_email": row['contact_email'] if row['contact_email'] else "N/A"
            }
        }
        alerts.append(alert)

    return jsonify({"alerts": alerts, "total_alerts": len(alerts)})


if __name__ == '__main__':
    app.run(debug=True)
