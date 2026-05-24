import sqlite3
import pandas as pd
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "gold_data.db")

def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def run_query(sql: str, params=()) -> pd.DataFrame:
    conn = get_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
        return df
    finally:
        conn.close()

def get_schema_info() -> str:
    """Return schema description for Gemini context."""
    return """
Database: gold_data.db (SQLite) — E-commerce Supply Chain Data Warehouse

TABLES:
1. gold_fact_orders (112,650 rows)
   - OrderLineKey, order_id, short_order_id, order_item_id
   - DateKey (FK→gold_dim_date.DateKey)
   - ProductKey (FK→gold_dim_product.ProductKey)
   - CustomerKey (FK→gold_dim_customer.CustomerKey)
   - WarehouseKey (FK→gold_dim_warehouse.WarehouseKey)
   - price (revenue per item), cost (COGS)
   - order_status: 'delivered','shipped','canceled','processing','invoiced','approved','unavailable'
   - is_successful_order (1=success, 0=not)
   - order_purchase_date, order_estimated_delivery_date, order_delivered_customer_date
   - delay_days (negative=early, positive=late), is_late_delivery (1=late)

2. gold_fact_shipment (110,197 rows)
   - ShipmentKey, order_id, ProductKey, CustomerKey, WarehouseKey
   - PurchaseDateKey, DeliveryDateKey
   - price, freight_value
   - lead_time_days, total_shipping_days
   - is_late_delivery (1=late)
   - estimated_delivery_date, actual_delivery_date, order_delivered_carrier_date

3. gold_fact_inventory (7,117,416 rows — daily snapshots)
   - InventorySnapshotKey, DateKey, ProductKey, WarehouseKey
   - stock_quantity, is_stock_out (1=stockout)

4. gold_dim_date (1,096 rows — 2016-01-01 to 2018-12-31)
   - DateKey (YYYYMMDD int), full_date, day_of_month, day_of_week, day_name
   - month_number, month_name, year_number, quarter_number, is_weekend

5. gold_dim_product (32,951 rows)
   - ProductKey, product_id, product_category_name
   - product_weight_g, product_length_cm, product_height_cm, product_width_cm

6. gold_dim_customer (99,441 rows)
   - CustomerKey, customer_id, customer_unique_id, GeoKey

7. gold_dim_warehouse (6 rows)
   - WarehouseKey, warehouse_id, warehouse_name, location_state, capacity
   - Warehouses: W001 Sao Paulo (SP,50000), W002 Rio de Janeiro (RJ,30000),
     W003 Belo Horizonte (MG,25000), W004 Curitiba (PR,20000),
     W005 Porto Alegre (RS,15000), W006 Salvador (BA,12000)

Date range: 2016-09-04 to 2018-09-03
Total revenue (delivered): ~13.5M BRL
"""
