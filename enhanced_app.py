import streamlit as st
import pandas as pd
import psycopg2
from psycopg2.extras import RealDictCursor
import traceback
from datetime import date, datetime, timedelta
import plotly.express as px
import io
import base64
import uuid
import json
import hashlib
import os
from urllib.parse import urlparse

# ======================
# APP CONFIGURATION
# ======================
st.set_page_config(
    page_title="School Expense Tracker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======================
# DATABASE FUNCTIONS
# ======================

def get_database_url():
    """Get database URL from environment variables or Streamlit secrets"""
    # Try Railway environment variable first
    if "DATABASE_URL" in os.environ:
        return os.environ["DATABASE_URL"]
    
    # Try Railway-style private URL
    if "DATABASE_PRIVATE_URL" in os.environ:
        return os.environ["DATABASE_PRIVATE_URL"]
    
    # Fallback to Streamlit secrets
    try:
        if hasattr(st, 'secrets') and 'database' in st.secrets:
            # Railway-style connection string in secrets
            if 'url' in st.secrets.database:
                return st.secrets.database.url
        
        # Legacy Supabase format
        if hasattr(st, 'secrets') and 'postgres' in st.secrets:
            host = st.secrets.postgres.host
            port = st.secrets.postgres.port
            dbname = st.secrets.postgres.dbname
            user = st.secrets.postgres.user
            password = st.secrets.postgres.password
            return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"
            
    except Exception as e:
        st.error(f"Error reading secrets: {e}")
    
    return None

def is_connection_active(conn):
    """Check if the database connection is active."""
    if conn is None:
        return False
    try:
        # Pinging the database to check if the connection is still alive
        conn.cursor().execute("SELECT 1")
        return True
    except psycopg2.Error:
        return False
    except Exception:
        return False

def execute_query(conn, query, params=None, fetch=False, retry_count=0):
    """Execute database query with better error handling and retry mechanism."""
    max_retries = 1 # Allow one retry if connection fails
    
    try:
        if not is_connection_active(conn):
            st.warning("Database connection is not active. Attempting to re-establish...")
            # Re-establish connection through the cached function
            conn = get_db_connection(force_reconnect=True) 
            if not conn:
                st.error("Failed to re-establish database connection.")
                return False if not fetch else None

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            
            if fetch:
                return cursor.fetchall()
            else:
                conn.commit()
                return True
                
    except psycopg2.Error as e:
        # Check if the error is due to a closed connection and retry
        if "connection already closed" in str(e).lower() and retry_count < max_retries:
            st.warning(f"Connection closed during query. Retrying... (Attempt {retry_count + 1})")
            # Force re-initialization of the connection
            conn = get_db_connection(force_reconnect=True)
            if conn:
                return execute_query(conn, query, params, fetch, retry_count + 1)
            else:
                st.error("Failed to re-establish connection after retry.")
                return False if not fetch else None
        else:
            # Only rollback if the connection is still active to avoid nested errors
            if is_connection_active(conn):
                conn.rollback()
            st.error(f"Database error: {e}")
            st.code(traceback.format_exc()) # Show full traceback for database errors
            return False if not fetch else None
    except Exception as e:
        # For unexpected errors, log and return appropriate value
        # Do NOT attempt rollback here, as the connection state is unknown
        st.error(f"Unexpected error during query execution: {e}")
        st.code(traceback.format_exc())
        return False if not fetch else None

def init_database():
    """Initialize database with required tables"""
    try:
        database_url = get_database_url()
        if not database_url:
            st.error("❌ No database configuration found!")
            st.info("""
            **For Railway deployment:**
            1. Add PostgreSQL service to your Railway project
            2. Railway will automatically provide DATABASE_URL environment variable
            
            **For local development:**
            Add database URL to .streamlit/secrets.toml:
            ```
            [database]
            url = "postgresql://user:password@host:port/dbname"
            ```
            """)
            return None
            
        # Parse URL to show connection info (without password)
        parsed = urlparse(database_url)
        st.success(f"🚀 Connecting to PostgreSQL: {parsed.hostname}:{parsed.port}")
        
        # Connect to database
        conn = psycopg2.connect(
            database_url,
            sslmode='require',
            connect_timeout=30,
            application_name='school_expense_tracker'
        )
        
        # Test connection
        with conn.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            st.success(f"✅ Connected successfully!")
            
        # Create tables
        create_tables(conn)
        return conn
        
    except psycopg2.OperationalError as e:
        st.error("🚨 **Database Connection Failed**")
        error_msg = str(e).lower()
        
        if "could not connect" in error_msg:
            st.error("**Cannot reach database server.** Check:")
            st.markdown("""
            - PostgreSQL service is running
            - DATABASE_URL environment variable is set correctly
            - Network connectivity
            """)
        elif "authentication failed" in error_msg:
            st.error("**Authentication failed.** Check database credentials.")
        else:
            st.error(f"**Connection error:** {e}")
            
        return None
        
    except Exception as e:
        st.error(f"**Unexpected error during database initialization:** {e}")
        st.code(traceback.format_exc())
        return None

def create_tables(conn):
    """Create all required database tables"""
    tables = [
        '''
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            category VARCHAR(255) NOT NULL,
            description TEXT,
            amount NUMERIC(10, 2) NOT NULL,
            receipt_no VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS uniform_stock (
            id SERIAL PRIMARY KEY,
            item VARCHAR(255) NOT NULL,
            size VARCHAR(50) NOT NULL,
            quantity INTEGER NOT NULL,
            unit_cost NUMERIC(10, 2) NOT NULL,
            supplier VARCHAR(255),
            invoice_no VARCHAR(255),
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS uniform_sales (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            student_name VARCHAR(255),
            student_class VARCHAR(100),
            item VARCHAR(255) NOT NULL,
            size VARCHAR(50) NOT NULL,
            quantity INTEGER NOT NULL,
            selling_price NUMERIC(10, 2) NOT NULL,
            payment_mode VARCHAR(100) NOT NULL,
            reference VARCHAR(255),
            receipt_id VARCHAR(255) UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''',
        '''
        CREATE TABLE IF NOT EXISTS receipts (
            id SERIAL PRIMARY KEY,
            receipt_id VARCHAR(255) UNIQUE NOT NULL,
            date DATE NOT NULL,
            customer_name VARCHAR(255),
            items_json TEXT NOT NULL,
            total_amount NUMERIC(10, 2) NOT NULL,
            payment_mode VARCHAR(100) NOT NULL,
            reference VARCHAR(255),
            issued_by VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    ]
    
    try:
        with conn.cursor() as cursor:
            for table_sql in tables:
                cursor.execute(table_sql)
            
            # Add indexes for better performance
            indexes = [
                "CREATE INDEX IF NOT EXISTS idx_expenses_date ON expenses(date)",
                "CREATE INDEX IF NOT EXISTS idx_sales_date ON uniform_sales(date)",
                "CREATE INDEX IF NOT EXISTS idx_stock_item_size ON uniform_stock(item, size)",
                "CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(date)"
            ]
            
            for index_sql in indexes:
                cursor.execute(index_sql)

            # Ensure 'created_at' column exists in 'expenses' table for older deployments
            # This is a safe way to add the column if it's missing without dropping the table
            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='expenses' AND column_name='created_at') THEN
                        ALTER TABLE expenses ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
                    END IF;
                END
                $$;
            """)
                
        conn.commit()
        st.success("📊 Database tables initialized successfully!")
        
    except Exception as e:
        st.error(f"Failed to create tables: {e}")
        conn.rollback()

@st.cache_resource
def get_db_connection(force_reconnect=False):
    """Get cached database connection. 
    If force_reconnect is True, a new connection is established."""
    if force_reconnect:
        st.cache_resource.clear() # Clear the cache to force a new connection
    return init_database()

# ======================
# UTILITY FUNCTIONS
# ======================
def generate_unique_id(prefix=""):
    """Generate a unique ID with optional prefix"""
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"

def format_currency(amount):
    """Format amount as currency"""
    if amount is None:
        return "KES 0.00"
    return f"KES {float(amount):,.2f}"

def get_download_link(df, filename, text):
    """Generate a CSV download link"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}.csv">{text}</a>'

def get_excel_link(df, filename, text):
    """Generate an Excel download link"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    excel_data = output.getvalue()
    b64 = base64.b64encode(excel_data).decode()
    return f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}.xlsx">{text}</a>'

# ======================
# RECEIPT FUNCTIONS
# ======================
def generate_receipt_html(receipt_data):
    """Generate HTML receipt"""
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; border: 1px solid #ddd; border-radius: 5px;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h2>SUCCESS ACHIEVERS SCHOOL</h2>
            <p>395 Nkubu, Meru | Tel: 0720340953</p>
            <h3 style="border-top: 1px solid #ddd; border-bottom: 1px solid #ddd; padding: 10px 0;">RECEIPT</h3>
        </div>

        <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
            <div>
                <p><strong>Receipt #:</strong> {receipt_data['receipt_id']}</p>
                <p><strong>Date:</strong> {receipt_data['date']}</p>
            </div>
            <div>
                <p><strong>Student:</strong> {receipt_data['customer_name'] or 'Walk-in Customer'}</p>
                <p><strong>Payment Method:</strong> {receipt_data['payment_mode']}</p>
                <p><strong>Reference:</strong> {receipt_data['reference'] or 'N/A'}</p>
            </div>
        </div>

        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <thead>
                <tr style="background-color: #f5f5f5;">
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Item</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Size</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: right;">Price</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: right;">Qty</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: right;">Amount</th>
                </tr>
            </thead>
            <tbody>
    """

    for item in receipt_data['items']:
        amount = item['price'] * item['quantity']
        html += f"""
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;">{item['name']}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{item['size']}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{format_currency(item['price'])}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{item['quantity']}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{format_currency(amount)}</td>
                </tr>
        """

    html += f"""
            </tbody>
            <tfoot>
                <tr>
                    <td colspan="4" style="border: 1px solid #ddd; padding: 8px; text-align: right;"><strong>Total:</strong></td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;"><strong>{format_currency(receipt_data['total_amount'])}</strong></td>
                </tr>
            </tfoot>
        </table>

        <div style="margin-top: 30px; text-align: right;">
            <p><strong>Issued By:</strong> {receipt_data['issued_by']}</p>
            <p style="font-size: 0.9em; color: #666;">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>

        <div style="text-align: center; margin-top: 40px; font-size: 0.8em; color: #777;">
            <p>Thank you for your business!</p>
            <p>This is a computer-generated receipt</p>
        </div>
    </div>
    """
    return html

def save_receipt(conn, receipt_data):
    """Save receipt to database"""
    try:
        items_json = json.dumps(receipt_data['items'])
        query = """
            INSERT INTO receipts (
                receipt_id, date, customer_name, items_json,
                total_amount, payment_mode, reference, issued_by
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        params = (
            receipt_data['receipt_id'],
            receipt_data['date'],
            receipt_data['customer_name'],
            items_json,
            receipt_data['total_amount'],
            receipt_data['payment_mode'],
            receipt_data['reference'],
            receipt_data['issued_by']
        )
        return execute_query(conn, query, params)
    except Exception as e:
        st.error(f"Failed to save receipt: {str(e)}")
        st.code(traceback.format_exc())
        return False

# ======================
# STOCK MANAGEMENT
# ======================
def check_stock_availability(conn, item, size, quantity):
    """Check if sufficient stock exists"""
    query = """
        SELECT quantity FROM uniform_stock
        WHERE item = %s AND size = %s AND quantity >= %s
    """
    result = execute_query(conn, query, (item, size, quantity), fetch=True)
    return bool(result)

def update_stock(conn, item, size, quantity_change):
    """Update stock quantity"""
    query = """
        UPDATE uniform_stock
        SET quantity = quantity + %s, last_updated = CURRENT_TIMESTAMP
        WHERE item = %s AND size = %s
    """
    return execute_query(conn, query, (quantity_change, item, size))

# ======================
# APPLICATION PAGES
# ======================
def show_expenses_tab(conn):
    """Expenses management tab"""
    st.header("💰 Expense Management")

    with st.expander("➕ Add New Expense", expanded=True):
        with st.form("expense_form", clear_on_submit=True):
            cols = st.columns(3)
            with cols[0]:
                exp_date = st.date_input("Date", value=date.today())
            with cols[1]:
                category = st.selectbox("Category", [
                    "Stationery", "Food", "Fuel", "Maintenance",
                    "Salaries", "Utilities", "Transport", "Events","Mechanic", "Other"
                ])
            with cols[2]:
                amount = st.number_input("Amount (KES)", min_value=0.0, step=0.01, format="%.2f")

            description = st.text_area("Description", max_chars=500)
            receipt_no = st.text_input("Receipt/Invoice Number (optional)", max_chars=100)

            if st.form_submit_button("Save Expense", type="primary"):
                if amount > 0 and description.strip():
                    query = """
                        INSERT INTO expenses (date, category, description, amount, receipt_no)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    if execute_query(conn, query, (exp_date, category, description, amount, receipt_no)):
                        st.success("Expense recorded successfully!")
                        st.rerun()
                else:
                    st.warning("Please enter a valid amount and description")

    st.subheader("🔍 Expense Records")
    with st.expander("Filter Expenses"):
        cols = st.columns(3)
        with cols[0]:
            start_date = st.date_input("From", value=date.today() - timedelta(days=30))
        with cols[1]:
            end_date = st.date_input("To", value=date.today())
        with cols[2]:
            categories = st.multiselect("Categories", [
                "Stationery", "Food", "Fuel", "Maintenance",
                "Salaries", "Utilities", "Transport", "Events","Mechanic", "Other"
            ])

        search_term = st.text_input("Search Description")

    # Build query
    query = "SELECT date, category, description, amount, receipt_no FROM expenses WHERE date BETWEEN %s AND %s"
    params = [start_date, end_date]

    if categories:
        query += " AND category IN (" + ",".join(["%s"] * len(categories)) + ")"
        params.extend(categories)

    if search_term:
        query += " AND description ILIKE %s"
        params.append(f"%{search_term}%")

    query += " ORDER BY date DESC" # Changed to ORDER BY date DESC for robustness

    expenses = execute_query(conn, query, params, fetch=True)
    if expenses:
        df = pd.DataFrame(expenses, columns=["Date", "Category", "Description", "Amount", "Receipt No"])
        st.dataframe(df, use_container_width=True)

        # Summary stats
        total_expenses = df['Amount'].sum()
        st.metric("Total Expenses", format_currency(total_expenses))

        # Download options
        st.markdown(get_download_link(df, "expenses_report", "📥 Download as CSV"), unsafe_allow_html=True)
        st.markdown(get_excel_link(df, "expenses_report", "📊 Download as Excel"), unsafe_allow_html=True)
    else:
        st.info("No expenses found for the selected filters")

def show_stock_tab(conn):
    """Uniform stock management tab"""
    st.header("👕 Uniform Stock Management")

    with st.expander("📦 Add/Update Stock", expanded=True):
        with st.form("stock_form", clear_on_submit=True):
            cols = st.columns([2, 1, 1, 2])
            with cols[0]:
                item = st.selectbox("Item", [
                    "Sweater", "Tracksuit", "Dress", "T-shirt",
                    "Trousers", "Shirt", "Tie", "Socks", "Blazer", "PE Kit"
                ])
            with cols[1]:
                size = st.text_input("Size", placeholder="e.g., M, 12, etc.", max_chars=50).upper()
            with cols[2]:
                quantity = st.number_input("Quantity", min_value=1, step=1)
            with cols[3]:
                unit_cost = st.number_input("Unit Cost (KES)", min_value=0.0, step=0.01, format="%.2f")

            cols = st.columns(2)
            with cols[0]:
                supplier = st.text_input("Supplier (optional)", max_chars=255)
            with cols[1]:
                invoice_no = st.text_input("Invoice No. (optional)", max_chars=255)

            if st.form_submit_button("Update Stock", type="primary"):
                if size.strip():
                    # Check if item exists
                    check_query = "SELECT id FROM uniform_stock WHERE item = %s AND size = %s"
                    exists = execute_query(conn, check_query, (item, size), fetch=True)

                    if exists:
                        # Update existing stock
                        update_query = """
                            UPDATE uniform_stock
                            SET quantity = quantity + %s, unit_cost = %s, supplier = %s, invoice_no = %s, last_updated = CURRENT_TIMESTAMP
                            WHERE item = %s AND size = %s
                        """
                        if execute_query(conn, update_query,
                                       (quantity, unit_cost, supplier, invoice_no, item, size)):
                            st.success("Stock updated successfully!")
                            st.rerun()
                    else:
                        # Add new stock
                        insert_query = """
                            INSERT INTO uniform_stock (item, size, quantity, unit_cost, supplier, invoice_no)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        if execute_query(conn, insert_query,
                                       (item, size, quantity, unit_cost, supplier, invoice_no)):
                            st.success("New stock item added!")
                            st.rerun()
                else:
                    st.warning("Please enter a valid size")

    st.subheader("📊 Current Stock Levels")
    stock = execute_query(conn, "SELECT item, size, quantity, unit_cost FROM uniform_stock ORDER BY item, size", fetch=True)
    if stock:
        df = pd.DataFrame(stock, columns=["Item", "Size", "Quantity", "Unit Cost"])
        df["Total Value"] = df["Quantity"] * df["Unit Cost"]

        # Show summary
        total_items = df["Quantity"].sum()
        total_value = df["Total Value"].sum()

        cols = st.columns(2)
        cols[0].metric("Total Items in Stock", f"{total_items:,}")
        cols[1].metric("Total Stock Value", format_currency(total_value))

        st.dataframe(df, use_container_width=True)
        st.markdown(get_download_link(df, "stock_report", "📥 Download Stock Report CSV"), unsafe_allow_html=True)
        st.markdown(get_excel_link(df, "stock_report", "📊 Download Stock Report Excel"), unsafe_allow_html=True)
    else:
        st.info("No stock items found in inventory")

def show_sales_tab(conn):
    """Uniform sales management tab"""
    st.header("🛍 Uniform Sales")

    with st.expander("💳 Record New Sale", expanded=True):
        with st.form("sales_form", clear_on_submit=True):
            cols = st.columns(3)
            with cols[0]:
                sale_date = st.date_input("Date", value=date.today())
            with cols[1]:
                student_name = st.text_input("Student Name (optional)", max_chars=255)
            with cols[2]:
                student_class = st.text_input("Class/Grade (optional)", max_chars=100)

            cols = st.columns([2, 1, 1, 2])
            with cols[0]:
                item = st.selectbox("Item", [
                    "Sweater", "Tracksuit", "Dress", "T-shirt",
                    "Trousers", "Shirt", "Tie", "Socks", "Blazer", "PE Kit"
                ])
            with cols[1]:
                size = st.text_input("Size", max_chars=50).upper()
            with cols[2]:
                quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
            with cols[3]:
                price = st.number_input("Unit Price (KES)", min_value=0.0, step=0.01, format="%.2f")

            cols = st.columns(2)
            with cols[0]:
                payment_mode = st.selectbox("Payment Method", ["Cash", "M-Pesa", "Bank Transfer", "Cheque", "Other"])
            with cols[1]:
                reference = st.text_input("Payment Reference (optional)", max_chars=255)

            generate_receipt = st.checkbox("Generate Receipt", value=True)

            if st.form_submit_button("Record Sale", type="primary"):
                if size.strip() and price > 0 and quantity > 0:
                    # Check stock availability
                    if not check_stock_availability(conn, item, size, quantity):
                        st.error(f"Insufficient stock for {item} (Size: {size}). Please check inventory.")
                    else:
                        # Generate receipt ID
                        receipt_id = generate_unique_id("REC-")

                        # Record sale
                        sale_query = """
                            INSERT INTO uniform_sales (
                                date, student_name, student_class, item, size,
                                quantity, selling_price, payment_mode, reference, receipt_id
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        sale_params = (
                            sale_date, student_name, student_class, item, size,
                            quantity, price, payment_mode, reference, receipt_id
                        )

                        if execute_query(conn, sale_query, sale_params):
                            # Update stock
                            update_stock(conn, item, size, -quantity)
                            st.success("Sale recorded successfully!")

                            # Generate receipt if requested
                            if generate_receipt:
                                receipt_data = {
                                    "receipt_id": receipt_id,
                                    "date": sale_date.strftime("%Y-%m-%d"),
                                    "customer_name": student_name or "Walk-in Customer",
                                    "items": [{
                                        "name": item,
                                        "size": size,
                                        "price": price,
                                        "quantity": quantity
                                    }],
                                    "total_amount": float(price * quantity),
                                    "payment_mode": payment_mode,
                                    "reference": reference,
                                    "issued_by": st.session_state.get("username", "System")
                                }

                                # Save receipt
                                if save_receipt(conn, receipt_data):
                                    # Show receipt
                                    st.subheader("Generated Receipt")
                                    receipt_html = generate_receipt_html(receipt_data)
                                    with st.expander("📄 View Receipt", expanded=True):
                                        st.components.v1.html(receipt_html, height=600)
                                        # Download button for HTML receipt
                                        st.markdown(
                                            f'<a href="data:text/html;base64,{base64.b64encode(receipt_html.encode()).decode()}" '
                                            f'download="receipt_{receipt_id}.html" target="_blank">📄 Download Receipt HTML</a>',
                                            unsafe_allow_html=True
                                        )
                            st.rerun()
                else:
                    st.warning("Please ensure Size, Quantity, and Unit Price are valid and entered.")

    st.subheader("📋 Sales Records")
    with st.expander("Filter Sales"):
        cols = st.columns(3)
        with cols[0]:
            start_date = st.date_input("From Date", value=date.today() - timedelta(days=30))
        with cols[1]:
            end_date = st.date_input("To Date", value=date.today())
        with cols[2]:
            items = st.multiselect("Items", [
                "Sweater", "Tracksuit", "Dress", "T-shirt",
                "Trousers", "Shirt", "Tie", "Socks", "Blazer", "PE Kit"
            ])

        search_term = st.text_input("Search Student or Reference")

    # Build query
    query = """
        SELECT date, student_name, student_class, item, size,
               quantity, selling_price, payment_mode, reference, receipt_id
        FROM uniform_sales
        WHERE date BETWEEN %s AND %s
    """
    params = [start_date, end_date]

    if items:
        query += " AND item IN (" + ",".join(["%s"] * len(items)) + ")"
        params.extend(items)

    if search_term:
        query += " AND (student_name ILIKE %s OR reference ILIKE %s)"
        params.extend([f"%{search_term}%", f"%{search_term}%"])

    query += " ORDER BY date DESC"

    sales = execute_query(conn, query, params, fetch=True)
    if sales:
        df = pd.DataFrame(sales, columns=[
            "Date", "Student", "Class", "Item", "Size",
            "Quantity", "Price", "Payment", "Reference", "Receipt ID"
        ])
        df["Total"] = df["Quantity"] * df["Price"]

        # Summary stats
        total_sales = df["Total"].sum()
        total_items = df["Quantity"].sum()

        cols = st.columns(2)
        cols[0].metric("Total Sales", format_currency(total_sales))
        cols[1].metric("Items Sold", f"{total_items:,}")

        st.dataframe(df, use_container_width=True)
        st.markdown(get_download_link(df, "sales_report", "📥 Download Sales Report CSV"), unsafe_allow_html=True)
        st.markdown(get_excel_link(df, "sales_report", "📊 Download Sales Report Excel"), unsafe_allow_html=True)
    else:
        st.info("No sales found for the selected filters")

def show_reports_tab(conn):
    """Financial reports tab"""
    st.header("📈 Financial Reports")

    report_type = st.selectbox("Select Report Type", [
        "Expense Summary",
        "Sales Summary",
        "Inventory Valuation",
        "Monthly Trends"
    ])

    if report_type == "Expense Summary":
        st.subheader("💰 Expense Summary Report")
        cols = st.columns(2)
        with cols[0]:
            start_date = st.date_input("Start Date", value=date.today().replace(day=1))
        with cols[1]:
            end_date = st.date_input("End Date", value=date.today())

        query = """
            SELECT category, SUM(amount) as total
            FROM expenses
            WHERE date BETWEEN %s AND %s
            GROUP BY category
            ORDER BY total DESC
        """
        results = execute_query(conn, query, (start_date, end_date), fetch=True)

        if results:
            df = pd.DataFrame(results, columns=["Category", "Amount"])
            total = df["Amount"].sum()

            st.metric("Total Expenses", format_currency(total))

            cols = st.columns(2)
            with cols[0]:
                st.dataframe(df, use_container_width=True)
            with cols[1]:
                fig = px.pie(df, values="Amount", names="Category",
                            title="Expense Distribution")
                st.plotly_chart(fig, use_container_width=True)
            st.markdown(get_download_link(df, "expense_summary", "📥 Download CSV"), unsafe_allow_html=True)
        else:
            st.info("No expenses found for the selected period")

    elif report_type == "Sales Summary":
        st.subheader("🛍 Sales Summary Report")
        cols = st.columns(2)
        with cols[0]:
            start_date = st.date_input("Start Date", value=date.today().replace(day=1))
        with cols[1]:
            end_date = st.date_input("End Date", value=date.today())

        query = """
            SELECT item, SUM(quantity) as total_qty, SUM(quantity * selling_price) as total_sales
            FROM uniform_sales
            WHERE date BETWEEN %s AND %s
            GROUP BY item
            ORDER BY total_sales DESC
        """
        results = execute_query(conn, query, (start_date, end_date), fetch=True)

        if results:
            df = pd.DataFrame(results, columns=["Item", "Quantity Sold", "Total Sales"])
            total_revenue = df["Total Sales"].sum()
            total_items = df["Quantity Sold"].sum()

            cols = st.columns(2)
            cols[0].metric("Total Revenue", format_currency(total_revenue))
            cols[1].metric("Items Sold", f"{total_items:,}")

            cols = st.columns(2)
            with cols[0]:
                st.dataframe(df, use_container_width=True)
            with cols[1]:
                fig = px.bar(df, x="Item", y="Total Sales", 
                           title="Sales by Item Category")
                fig.update_xaxes(tickangle=45)
                st.plotly_chart(fig, use_container_width=True)

            st.markdown(get_download_link(df, "sales_summary", "📥 Download CSV"), unsafe_allow_html=True)
        else:
            st.info("No sales found for the selected period")

    elif report_type == "Inventory Valuation":
        st.subheader("📦 Inventory Valuation Report")
        
        query = """
            SELECT item, size, quantity, unit_cost, (quantity * unit_cost) as total_value
            FROM uniform_stock
            WHERE quantity > 0
            ORDER BY total_value DESC
        """
        results = execute_query(conn, query, fetch=True)

        if results:
            df = pd.DataFrame(results, columns=["Item", "Size", "Quantity", "Unit Cost", "Total Value"])
            total_inventory_value = df["Total Value"].sum()
            total_items = df["Quantity"].sum()

            cols = st.columns(3)
            cols[0].metric("Total Inventory Value", format_currency(total_inventory_value))
            cols[1].metric("Total Items", f"{total_items:,}")
            cols[2].metric("Average Item Value", format_currency(total_inventory_value / total_items if total_items > 0 else 0))

            st.dataframe(df, use_container_width=True)

            # Low stock alert
            low_stock = df[df["Quantity"] <= 5]
            if not low_stock.empty:
                st.warning("⚠️ Low Stock Alert")
                st.dataframe(low_stock, use_container_width=True)

            st.markdown(get_download_link(df, "inventory_valuation", "📥 Download CSV"), unsafe_allow_html=True)
        else:
            st.info("No inventory items found")

    elif report_type == "Monthly Trends":
        st.subheader("📊 Monthly Trends Analysis")
        
        # Get last 12 months data
        end_date = date.today()
        start_date = end_date.replace(year=end_date.year - 1)

        # Expenses trend
        expense_query = """
            SELECT DATE_TRUNC('month', date) as month, SUM(amount) as total_expenses
            FROM expenses
            WHERE date >= %s
            GROUP BY month
            ORDER BY month
        """
        expense_results = execute_query(conn, expense_query, (start_date,), fetch=True)

        # Sales trend
        sales_query = """
            SELECT DATE_TRUNC('month', date) as month, SUM(quantity * selling_price) as total_sales
            FROM uniform_sales
            WHERE date >= %s
            GROUP BY month
            ORDER BY month
        """
        sales_results = execute_query(conn, sales_query, (start_date,), fetch=True)

        if expense_results or sales_results:
            # Create combined dataframe
            expense_df = pd.DataFrame(expense_results, columns=["Month", "Expenses"]) if expense_results else pd.DataFrame(columns=["Month", "Expenses"])
            sales_df = pd.DataFrame(sales_results, columns=["Month", "Sales"]) if sales_results else pd.DataFrame(columns=["Month", "Sales"])

            # Merge dataframes
            if not expense_df.empty and not sales_df.empty:
                trend_df = pd.merge(expense_df, sales_df, on="Month", how="outer")
            elif not expense_df.empty:
                trend_df = expense_df.copy()
                trend_df["Sales"] = 0
            elif not sales_df.empty:
                trend_df = sales_df.copy()
                trend_df["Expenses"] = 0
            else:
                trend_df = pd.DataFrame()

            if not trend_df.empty:
                trend_df = trend_df.fillna(0)
                trend_df["Month"] = pd.to_datetime(trend_df["Month"])
                trend_df["Net"] = trend_df["Sales"] - trend_df["Expenses"]

                # Plot trends
                fig = px.line(trend_df, x="Month", y=["Expenses", "Sales", "Net"],
                            title="Monthly Financial Trends",
                            labels={"value": "Amount (KES)", "variable": "Category"})
                st.plotly_chart(fig, use_container_width=True)

                st.dataframe(trend_df, use_container_width=True)
                st.markdown(get_download_link(trend_df, "monthly_trends", "📥 Download CSV"), unsafe_allow_html=True)
            else:
                st.info("No data available for trend analysis")
        else:
            st.info("No data available for the last 12 months")

def show_receipts_tab(conn):
    """Receipt management tab"""
    st.header("🧾 Receipt Management")

    # Search and filter receipts
    with st.expander("🔍 Search Receipts"):
        cols = st.columns(3)
        with cols[0]:
            start_date = st.date_input("From Date", value=date.today() - timedelta(days=30))
        with cols[1]:
            end_date = st.date_input("To Date", value=date.today())
        with cols[2]:
            search_term = st.text_input("Search Receipt ID or Customer")

    # Build query
    query = """
        SELECT receipt_id, date, customer_name, total_amount, 
               payment_mode, reference, issued_by, created_at
        FROM receipts
        WHERE date BETWEEN %s AND %s
    """
    params = [start_date, end_date]

    if search_term:
        query += " AND (receipt_id ILIKE %s OR customer_name ILIKE %s)"
        params.extend([f"%{search_term}%", f"%{search_term}%"])

    query += " ORDER BY created_at DESC"

    receipts = execute_query(conn, query, params, fetch=True)

    if receipts:
        st.subheader("📋 Receipt History")
        
        for receipt in receipts:
            with st.expander(f"Receipt {receipt['receipt_id']} - {format_currency(receipt['total_amount'])} ({receipt['date']})"):
                cols = st.columns(2)
                with cols[0]:
                    st.write(f"**Customer:** {receipt['customer_name'] or 'Walk-in Customer'}")
                    st.write(f"**Date:** {receipt['date']}")
                    st.write(f"**Payment:** {receipt['payment_mode']}")
                with cols[1]:
                    st.write(f"**Total:** {format_currency(receipt['total_amount'])}")
                    st.write(f"**Reference:** {receipt['reference'] or 'N/A'}")
                    st.write(f"**Issued By:** {receipt['issued_by']}")

                # Reprint receipt button
                if st.button(f"🖨️ Reprint Receipt", key=f"reprint_{receipt['receipt_id']}"):
                    # Get receipt details
                    detail_query = "SELECT * FROM receipts WHERE receipt_id = %s"
                    receipt_detail = execute_query(conn, detail_query, (receipt['receipt_id'],), fetch=True)
                    
                    if receipt_detail:
                        receipt_data = receipt_detail[0]
                        items = json.loads(receipt_data['items_json'])
                        
                        receipt_info = {
                            "receipt_id": receipt_data['receipt_id'],
                            "date": receipt_data['date'].strftime("%Y-%m-%d"),
                            "customer_name": receipt_data['customer_name'],
                            "items": items,
                            "total_amount": float(receipt_data['total_amount']),
                            "payment_mode": receipt_data['payment_mode'],
                            "reference": receipt_data['reference'],
                            "issued_by": receipt_data['issued_by']
                        }
                        
                        receipt_html = generate_receipt_html(receipt_info)
                        st.components.v1.html(receipt_html, height=600)
                        
                        # Download link
                        st.markdown(
                            f'<a href="data:text/html;base64,{base64.b64encode(receipt_html.encode()).decode()}" '
                            f'download="receipt_{receipt_data["receipt_id"]}.html" target="_blank">📄 Download Receipt</a>',
                            unsafe_allow_html=True
                        )

        # Summary statistics
        total_receipts = len(receipts)
        total_amount = sum(float(r['total_amount']) for r in receipts)
        
        cols = st.columns(2)
        cols[0].metric("Total Receipts", total_receipts)
        cols[1].metric("Total Amount", format_currency(total_amount))

    else:
        st.info("No receipts found for the selected criteria")

def show_dashboard_tab(conn):
    """Dashboard with key metrics and comprehensive overview"""
    st.header("📊 Dashboard")

    # Current month metrics
    today = date.today()
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)
    
    # Get current month data with proper column aliases
    expense_query = "SELECT COALESCE(SUM(amount), 0) as total_expenses FROM expenses WHERE date >= %s"
    sales_query = "SELECT COALESCE(SUM(quantity * selling_price), 0) as total_sales FROM uniform_sales WHERE date >= %s"
    stock_query = "SELECT COALESCE(SUM(quantity * unit_cost), 0) as stock_value FROM uniform_stock"
    
    # Year-to-date queries
    ytd_expense_query = "SELECT COALESCE(SUM(amount), 0) as ytd_expenses FROM expenses WHERE date >= %s"
    ytd_sales_query = "SELECT COALESCE(SUM(quantity * selling_price), 0) as ytd_sales FROM uniform_sales WHERE date >= %s"
    
    try:
        # Current month data
        current_expenses = execute_query(conn, expense_query, (month_start,), fetch=True)
        current_sales = execute_query(conn, sales_query, (month_start,), fetch=True)
        stock_value = execute_query(conn, stock_query, fetch=True)
        
        # Year-to-date data
        ytd_expenses = execute_query(conn, ytd_expense_query, (year_start,), fetch=True)
        ytd_sales = execute_query(conn, ytd_sales_query, (year_start,), fetch=True)

        # Extract values using dictionary keys (since we're using RealDictCursor)
        expenses_amount = float(current_expenses[0]['total_expenses']) if current_expenses and current_expenses[0] else 0
        sales_amount = float(current_sales[0]['total_sales']) if current_sales and current_sales[0] else 0
        inventory_value = float(stock_value[0]['stock_value']) if stock_value and stock_value[0] else 0
        net_income = sales_amount - expenses_amount
        
        ytd_expenses_amount = float(ytd_expenses[0]['ytd_expenses']) if ytd_expenses and ytd_expenses[0] else 0
        ytd_sales_amount = float(ytd_sales[0]['ytd_sales']) if ytd_sales and ytd_sales[0] else 0
        ytd_net_income = ytd_sales_amount - ytd_expenses_amount

        # Display key metrics
        st.subheader("📈 This Month's Performance")
        cols = st.columns(4)
        with cols[0]:
            st.metric(
                "Monthly Revenue", 
                format_currency(sales_amount),
                delta=f"vs YTD Avg: {format_currency(ytd_sales_amount / max(today.month, 1))}"
            )
        with cols[1]:
            st.metric(
                "Monthly Expenses", 
                format_currency(expenses_amount),
                delta=f"vs YTD Avg: {format_currency(ytd_expenses_amount / max(today.month, 1))}"
            )
        with cols[2]:
            delta_color = "normal" if net_income >= 0 else "inverse"
            st.metric(
                "Monthly Net Income", 
                format_currency(net_income),
                delta=format_currency(net_income)
            )
        with cols[3]:
            st.metric("Inventory Value", format_currency(inventory_value))

        # Year-to-date summary
        st.subheader("📅 Year-to-Date Summary")
        cols = st.columns(3)
        with cols[0]:
            st.metric("YTD Revenue", format_currency(ytd_sales_amount))
        with cols[1]:
            st.metric("YTD Expenses", format_currency(ytd_expenses_amount))
        with cols[2]:
            st.metric("YTD Net Income", format_currency(ytd_net_income))

        # Recent activity section
        st.subheader("🕒 Recent Activity")
        
        cols = st.columns(2)
        
        with cols[0]:
            st.markdown("**📤 Recent Expenses**")
            # Changed ORDER BY to 'date' for robustness if 'created_at' is still an issue on some deployments
            recent_expenses = execute_query(conn, 
                "SELECT date, category, description, amount FROM expenses ORDER BY date DESC LIMIT 5", 
                fetch=True) 
            
            if recent_expenses:
                for exp in recent_expenses:
                    with st.container():
                        st.write(f"**{exp['date']}** - {exp['category']}")
                        st.write(f"*{exp['description'][:50]}{'...' if len(exp['description']) > 50 else ''}*")
                        st.write(f"**{format_currency(exp['amount'])}**")
                        st.markdown("---")
            else:
                st.info("No recent expenses recorded")

        with cols[1]:
            st.markdown("**🛍️ Recent Sales**")
            recent_sales = execute_query(conn,
                """SELECT date, item, size, quantity, selling_price, 
                   (quantity * selling_price) as total, student_name 
                   FROM uniform_sales ORDER BY created_at DESC LIMIT 5""",
                fetch=True)
            
            if recent_sales:
                for sale in recent_sales:
                    with st.container():
                        student = sale['student_name'] if sale['student_name'] else "Walk-in Customer"
                        st.write(f"**{sale['date']}** - {sale['item']} ({sale['size']})")
                        st.write(f"*Customer: {student} | Qty: {sale['quantity']}*")
                        st.write(f"**{format_currency(sale['total'])}**")
                        st.markdown("---")
            else:
                st.info("No recent sales recorded")

        # Category breakdown for current month
        st.subheader("📊 Monthly Expense Breakdown")
        category_query = """
            SELECT category, COALESCE(SUM(amount), 0) as total
            FROM expenses 
            WHERE date >= %s 
            GROUP BY category 
            ORDER BY total DESC
        """
        categories = execute_query(conn, category_query, (month_start,), fetch=True)
        
        if categories:
            cols = st.columns([2, 1])
            with cols[0]:
                # Create pie chart data
                category_names = [cat['category'] for cat in categories]
                category_amounts = [float(cat['total']) for cat in categories]
                
                if any(amount > 0 for amount in category_amounts):
                    fig = px.pie(
                        values=category_amounts, 
                        names=category_names,
                        title="Expense Distribution by Category"
                    )
                    st.plotly_chart(fig, use_container_width=True)
                else:
                    st.info("No expenses to display in chart")
            
            with cols[1]:
                st.markdown("**Category Totals:**")
                for cat in categories:
                    if cat['total'] > 0:
                        st.write(f"• **{cat['category']}**: {format_currency(cat['total'])}")

        # Top selling items
        st.subheader("🏆 Top Selling Items (This Month)")
        top_items_query = """
            SELECT item, SUM(quantity) as total_qty, 
                   SUM(quantity * selling_price) as total_revenue
            FROM uniform_sales 
            WHERE date >= %s 
            GROUP BY item 
            ORDER BY total_revenue DESC 
            LIMIT 5
        """
        top_items = execute_query(conn, top_items_query, (month_start,), fetch=True)
        
        if top_items:
            cols = st.columns(len(top_items))
            for i, item in enumerate(top_items):
                with cols[i]:
                    st.metric(
                        item['item'],
                        f"{item['total_qty']} sold",
                        delta=format_currency(item['total_revenue'])
                    )
        else:
            st.info("No sales data available for this month")

        # Low stock alerts
        st.subheader("⚠️ Low Stock Alerts")
        low_stock_query = """
            SELECT item, size, quantity, unit_cost
            FROM uniform_stock 
            WHERE quantity <= 5 AND quantity > 0
            ORDER BY quantity ASC
        """
        low_stock = execute_query(conn, low_stock_query, fetch=True)
        
        if low_stock:
            st.warning(f"🚨 {len(low_stock)} items are running low on stock!")
            cols = st.columns(min(len(low_stock), 4))
            for i, item in enumerate(low_stock[:4]):  # Show max 4 items
                with cols[i % 4]:
                    st.error(f"**{item['item']}** ({item['size']})")
                    st.write(f"Only {item['quantity']} left")
                    
            if len(low_stock) > 4:
                st.write(f"... and {len(low_stock) - 4} more items")
        else:
            st.success("✅ All items are adequately stocked")

        # Quick stats cards
        st.subheader("📈 Quick Statistics")
        
        # Get additional statistics
        stats_queries = {
            'total_transactions': "SELECT COUNT(*) as count FROM uniform_sales WHERE date >= %s",
            'avg_sale_value': "SELECT COALESCE(AVG(quantity * selling_price), 0) as avg FROM uniform_sales WHERE date >= %s",
            'unique_customers': "SELECT COUNT(DISTINCT student_name) as count FROM uniform_sales WHERE date >= %s AND student_name IS NOT NULL",
            'total_stock_items': "SELECT COALESCE(SUM(quantity), 0) as total FROM uniform_stock" # Added COALESCE here
        }
        
        stats_results = {}
        for key, query in stats_queries.items():
            if key == 'total_stock_items':
                result = execute_query(conn, query, fetch=True)
            else:
                result = execute_query(conn, query, (month_start,), fetch=True)
            stats_results[key] = result[0] if result else {}

        cols = st.columns(4)
        with cols[0]:
            transactions = stats_results['total_transactions'].get('count', 0) if stats_results['total_transactions'] else 0
            st.metric("Monthly Transactions", f"{transactions:,}")
        
        with cols[1]:
            avg_sale = stats_results['avg_sale_value'].get('avg', 0) if stats_results['avg_sale_value'] else 0
            st.metric("Avg Sale Value", format_currency(float(avg_sale)))
        
        with cols[2]:
            customers = stats_results['unique_customers'].get('count', 0) if stats_results['unique_customers'] else 0
            st.metric("Unique Customers", f"{customers:,}")
        
        with cols[3]:
            stock_items = stats_results['total_stock_items'].get('total', 0) if stats_results['total_stock_items'] else 0
            st.metric("Total Stock Items", f"{stock_items:,}")

    except Exception as e:
        st.error(f"Error loading dashboard data: {str(e)}")
        st.code(traceback.format_exc())

    # Quick actions
    st.subheader("⚡ Quick Actions")
    cols = st.columns(5)
    
    with cols[0]:
        if st.button("➕ Add Expense", use_container_width=True, type="primary"):
            st.session_state.active_tab = "Expenses"
            st.rerun()
    
    with cols[1]:
        if st.button("🛍️ Record Sale", use_container_width=True, type="primary"):
            st.session_state.active_tab = "Sales"
            st.rerun()
    
    with cols[2]:
        if st.button("📦 Manage Stock", use_container_width=True, type="primary"):
            st.session_state.active_tab = "Stock"
            st.rerun()
    
    with cols[3]:
        if st.button("📊 View Reports", use_container_width=True):
            st.session_state.active_tab = "Reports"
            st.rerun()
    
    with cols[4]:
        if st.button("🧾 View Receipts", use_container_width=True):
            st.session_state.active_tab = "Receipts"
            st.rerun()

    # Performance tips
    with st.expander("💡 Performance Tips"):
        st.markdown("""
        **To optimize your school's financial management:**
        
        • **Monitor cash flow**: Keep track of monthly net income trends
        • **Stock management**: Reorder items when they reach low stock levels
        • **Expense tracking**: Categorize all expenses for better budgeting
        • **Regular reports**: Review monthly and yearly performance reports
        • **Receipt management**: Keep digital copies of all transactions
        """)

    # System status
    with st.expander("🔧 System Status"):
        try:
            # Test database connection
            test_query = "SELECT COUNT(*) as count FROM expenses LIMIT 1"
            test_result = execute_query(conn, test_query, fetch=True)
            
            if test_result:
                st.success("✅ Database connection is healthy")
                st.info(f"📊 System last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            else:
                st.warning("⚠️ Database connection issue detected")
                
        except Exception as e:
            st.error(f"❌ System check failed: {str(e)}")

# ======================
# MAIN APPLICATION
# ======================
def main():
    """Main application function"""
    st.title("🏫 Success Achievers School - Expense Tracker")
    st.markdown("---")

    # Initialize database connection
    # Pass force_reconnect=False by default, only force reconnect if needed by execute_query
    conn = get_db_connection(force_reconnect=False) 
    if not conn:
        st.stop()

    # Initialize session state
    if "active_tab" not in st.session_state:
        st.session_state.active_tab = "Dashboard"

    # Sidebar navigation
    st.sidebar.title("Navigation")
    tabs = ["Dashboard", "Expenses", "Stock", "Sales", "Reports", "Receipts"]
    
    for tab in tabs:
        if st.sidebar.button(tab, use_container_width=True, 
                           type="primary" if st.session_state.active_tab == tab else "secondary"):
            st.session_state.active_tab = tab
            st.rerun()

    # Display selected tab
    try:
        if st.session_state.active_tab == "Dashboard":
            show_dashboard_tab(conn)
        elif st.session_state.active_tab == "Expenses":
            show_expenses_tab(conn)
        elif st.session_state.active_tab == "Stock":
            show_stock_tab(conn)
        elif st.session_state.active_tab == "Sales":
            show_sales_tab(conn)
        elif st.session_state.active_tab == "Reports":
            show_reports_tab(conn)
        elif st.session_state.active_tab == "Receipts":
            show_receipts_tab(conn)

    except Exception as e:
        st.error(f"An error occurred: {str(e)}")
        st.code(traceback.format_exc())

    finally:
        # Footer
        st.markdown("---")
        st.markdown(
            "<div style='text-align: center; color: #666;'>"
            "Success Achievers School Expense Tracker © 2025"
            "</div>", 
            unsafe_allow_html=True
        )

if __name__ == "__main__":
    main()
