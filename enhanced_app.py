import streamlit as st
import pandas as pd
import psycopg2
import traceback
from datetime import date, datetime, timedelta
import plotly.express as px
import io
import base64
import uuid
import json
import hashlib # For future password hashing

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
def init_database_supabase():
    """Initialize the database with required tables in Supabase (PostgreSQL)"""
    try:
        # Updated connection with SSL and proper Supabase settings
        conn = psycopg2.connect(
            host=st.secrets.postgres.host,
            port=st.secrets.postgres.port,
            dbname=st.secrets.postgres.dbname,
            user=st.secrets.postgres.user,
            password=st.secrets.postgres.password,
            sslmode='require',  # Required for Supabase
            connect_timeout=10,  # Add timeout
            keepalives_idle=600,
            keepalives_interval=30,
            keepalives_count=3
        )
        cursor = conn.cursor()

        # Create tables if they don't exist
        # Using IF NOT EXISTS and proper PostgreSQL types
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            category VARCHAR(255) NOT NULL,
            description TEXT,
            amount NUMERIC(10, 2) NOT NULL,
            receipt_no VARCHAR(255)
        )
        ''')

        cursor.execute('''
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
        ''')

        cursor.execute('''
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
            receipt_id VARCHAR(255) UNIQUE
        )
        ''')

        cursor.execute('''
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
        ''')

        # Add receipt_id column to uniform_sales if it doesn't exist
        # Check if column exists before adding
        cursor.execute("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_name='uniform_sales' AND column_name='receipt_id'
        """)
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE uniform_sales ADD COLUMN receipt_id VARCHAR(255)")

        conn.commit()
        cursor.close()
        return conn
    except psycopg2.OperationalError as e:
        st.error(f"Database connection failed: {str(e)}")
        st.error("Please check your Supabase connection settings and ensure:")
        st.error("1. Your Supabase project is active")
        st.error("2. Database credentials are correct")
        st.error("3. Your IP is whitelisted (if IP restrictions are enabled)")
        st.error("4. SSL is properly configured")
        st.code(traceback.format_exc())
        return None
    except Exception as e:
        st.error(f"Failed to initialize Supabase database: {str(e)}")
        st.code(traceback.format_exc())
        return None

# Alternative connection method using connection string
def init_database_supabase_alt():
    """Alternative connection method using full connection string"""
    try:
        # Construct connection string - replace [YOUR-PASSWORD] with actual password
        conn_string = f"postgresql://{st.secrets.postgres.user}:{st.secrets.postgres.password}@{st.secrets.postgres.host}:{st.secrets.postgres.port}/{st.secrets.postgres.dbname}?sslmode=require"
        
        conn = psycopg2.connect(conn_string)
        cursor = conn.cursor()

        # Test connection
        cursor.execute("SELECT version()")
        version = cursor.fetchone()
        st.success(f"Connected to PostgreSQL: {version[0]}")

        # Create tables (same as above)
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            date DATE NOT NULL,
            category VARCHAR(255) NOT NULL,
            description TEXT,
            amount NUMERIC(10, 2) NOT NULL,
            receipt_no VARCHAR(255)
        )
        ''')

        cursor.execute('''
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
        ''')

        cursor.execute('''
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
            receipt_id VARCHAR(255) UNIQUE
        )
        ''')

        cursor.execute('''
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
        ''')

        # Add receipt_id column to uniform_sales if it doesn't exist
        cursor.execute("""
            SELECT 1 FROM information_schema.columns 
            WHERE table_name='uniform_sales' AND column_name='receipt_id'
        """)
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE uniform_sales ADD COLUMN receipt_id VARCHAR(255)")

        conn.commit()
        cursor.close()
        return conn
    except Exception as e:
        st.error(f"Alternative connection method failed: {str(e)}")
        st.code(traceback.format_exc())
        return None

@st.cache_resource
def get_db_connection():
    """Get a cached database connection for Supabase"""
    # Try primary connection method first
    conn = init_database_supabase()
    
    # If primary fails, try alternative method
    if conn is None:
        st.warning("Primary connection failed, trying alternative method...")
        conn = init_database_supabase_alt()
    
    return conn

def execute_query(_conn, query, params=None, fetch=False):
    """Execute a SQL query with error handling for PostgreSQL"""
    if _conn is None:
        st.error("Database connection is not established.")
        return None

    try:
        cursor = _conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)

        if fetch:
            result = cursor.fetchall()
        else:
            _conn.commit()
            result = True

        cursor.close()
        return result
    except psycopg2.Error as e:
        st.error(f"Database error: {e.pgcode} - {e.pgerror}")
        st.code(traceback.format_exc())
        _conn.rollback() # Rollback in case of error
        return None
    except Exception as e:
        st.error(f"An unexpected error occurred during query execution: {str(e)}")
        st.code(traceback.format_exc())
        return None

# ======================
# UTILITY FUNCTIONS
# ======================
def generate_unique_id(prefix=""):
    """Generate a unique ID with optional prefix"""
    return f"{prefix}{uuid.uuid4().hex[:8].upper()}"

def format_currency(amount):
    """Format amount as currency"""
    return f"KES {amount:,.2f}"

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
                        st.rerun() # Rerun to clear form and update data
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
        query += " AND description ILIKE %s" # ILIKE for case-insensitive search in PostgreSQL
        params.append(f"%{search_term}%")

    query += " ORDER BY date DESC"

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
                                    "total_amount": float(price * quantity), # Ensure float for JSON
                                    "payment_mode": payment_mode,
                                    "reference": reference,
                                    "issued_by": st.session_state.username # Use logged-in user
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
                                            f'download="receipt_{receipt_id}.html" target="_blank" class="st-emotion-cache-l9bibl effi0qh1">📄 Download Receipt HTML</a>',
                                            unsafe_allow_html=True
                                        )
                            st.rerun() # Rerun to clear form and update data
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
        query += " AND (student_name ILIKE %s OR reference ILIKE %s)" # ILIKE for case-insensitive
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
            st.markdown(get_download_link(df, "expense_summary", "📥 Download Expense Summary CSV"), unsafe_allow_html=True)
            st.markdown(get_excel_link(df, "expense_summary", "📊 Download Expense Summary Excel"), unsafe_allow_html=True)
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
            SELECT item, SUM(quantity) as total_qty,
                   SUM(quantity * selling_price) as total_value
            FROM uniform_sales
            WHERE date BETWEEN %s AND %s
            GROUP BY item
            ORDER BY total_value DESC
        """
        results = execute_query(conn, query, (start_date, end_date), fetch=True)

        if results:
            df = pd.DataFrame(results, columns=["Item", "Quantity", "Total Value"])
            total_value = df["Total Value"].sum()
            total_qty = df["Quantity"].sum()

            cols = st.columns(2)
            cols[0].metric("Total Sales Value", format_currency(total_value))
            cols[1].metric("Total Items Sold", f"{total_qty:,}")

            cols = st.columns(2)
            with cols[0]:
                st.dataframe(df, use_container_width=True)
            with cols[1]:
                fig = px.bar(df, x="Item", y="Total Value",
                            title="Sales by Item")
                st.plotly_chart(fig, use_container_width=True)
            st.markdown(get_download_link(df, "sales_summary", "📥 Download Sales Summary CSV"), unsafe_allow_html=True)
            st.markdown(get_excel_link(df, "sales_summary", "📊 Download Sales Summary Excel"), unsafe_allow_html=True)
        else:
            st.info("No sales found for the selected period")

    elif report_type == "Inventory Valuation":
        st.subheader("📦 Inventory Valuation Report")

        query = """
            SELECT item, size, quantity, unit_cost,
                   (quantity * unit_cost) as total_value
            FROM uniform_stock
            ORDER BY total_value DESC
        """
        results = execute_query(conn, query, fetch=True)

        if results:
            df = pd.DataFrame(results, columns=["Item", "Size", "Quantity", "Unit Cost", "Total Value"])
            total_value = df["Total Value"].sum()

            st.metric("Total Inventory Value", format_currency(total_value))
            st.dataframe(df, use_container_width=True)

            fig = px.treemap(df, path=["Item", "Size"], values="Total Value",
                            title="Inventory Value Distribution")
            st.plotly_chart(fig, use_container_width=True)
            st.markdown(get_download_link(df, "inventory_valuation", "📥 Download Inventory Valuation CSV"), unsafe_allow_html=True)
            st.markdown(get_excel_link(df, "inventory_valuation", "📊 Download Inventory Valuation Excel"), unsafe_allow_html=True)
        else:
            st.info("No inventory items found")

    elif report_type == "Monthly Trends":
        st.subheader("📅 Monthly Trends Analysis")

        # Get monthly expenses
        expense_query = """
            SELECT TO_CHAR(date, 'YYYY-MM') as month,
                   SUM(amount) as expenses
            FROM expenses
            GROUP BY month
            ORDER BY month
        """
        expenses = execute_query(conn, expense_query, fetch=True)

        # Get monthly sales
        sales_query = """
            SELECT TO_CHAR(date, 'YYYY-MM') as month,
                   SUM(quantity * selling_price) as sales
            FROM uniform_sales
            GROUP BY month
            ORDER BY month
        """
        sales = execute_query(conn, sales_query, fetch=True)

        # Create DataFrames
        expense_df = pd.DataFrame(expenses or [], columns=["Month", "Expenses"])
        sales_df = pd.DataFrame(sales or [], columns=["Month", "Sales"])

        # Merge data
        if not expense_df.empty or not sales_df.empty:
            df = pd.merge(expense_df, sales_df, on="Month", how="outer").fillna(0)

            # Calculate profit
            df["Profit"] = df["Sales"] - df["Expenses"]
            df = df.sort_values(by="Month").reset_index(drop=True)

            # Show metrics
            if not df.empty:
                latest = df.iloc[-1]
                cols = st.columns(3)
                cols[0].metric("Latest Month", latest["Month"])
                cols[1].metric("Expenses", format_currency(latest["Expenses"]))
                cols[2].metric("Sales", format_currency(latest["Sales"]))

                if len(df) > 1:
                    prev = df.iloc[-2]
                    delta_exp = latest["Expenses"] - prev["Expenses"]
                    delta_sales = latest["Sales"] - prev["Sales"]

                    cols = st.columns(2)
                    cols[0].metric("Expenses Change (vs Prev. Month)", format_currency(delta_exp), delta=f"{delta_exp:,.2f}")
                    cols[1].metric("Sales Change (vs Prev. Month)", format_currency(delta_sales), delta=f"{delta_sales:,.2f}")

            # Show trend chart
            fig = px.line(df, x="Month", y=["Expenses", "Sales", "Profit"],
                         title="Monthly Financial Trends",
                         labels={"value": "Amount (KES)", "variable": "Category"},
                         hover_data={"value": ":,.2f"}) # Format hover tooltip
            fig.update_layout(hovermode="x unified") # Show hover for all lines on same x-axis
            st.plotly_chart(fig, use_container_width=True)

            st.dataframe(df, use_container_width=True)
            st.markdown(get_download_link(df, "monthly_trends", "📥 Download Monthly Trends CSV"), unsafe_allow_html=True)
            st.markdown(get_excel_link(df, "monthly_trends", "📊 Download Monthly Trends Excel"), unsafe_allow_html=True)
        else:
            st.info("No financial data available for trend analysis")

def show_dashboard(conn):
    """Main dashboard view"""
    st.header("📊 Financial Dashboard")

    # Current month metrics
    today = date.today()
    first_day = today.replace(day=1)

    # Expense metrics
    expense_query = """
        SELECT SUM(amount) FROM expenses
        WHERE date BETWEEN %s AND %s
    """
    current_expenses_data = execute_query(conn, expense_query, (first_day, today), fetch=True)
    current_expenses = current_expenses_data[0][0] if current_expenses_data and current_expenses_data[0][0] else 0.0

    # Sales metrics
    sales_query = """
        SELECT SUM(quantity * selling_price) FROM uniform_sales
        WHERE date BETWEEN %s AND %s
    """
    current_sales_data = execute_query(conn, sales_query, (first_day, today), fetch=True)
    current_sales = current_sales_data[0][0] if current_sales_data and current_sales_data[0][0] else 0.0

    # Inventory metrics
    inventory_query = "SELECT SUM(quantity * unit_cost) FROM uniform_stock"
    inventory_value_data = execute_query(conn, inventory_query, fetch=True)
    inventory_value = inventory_value_data[0][0] if inventory_value_data and inventory_value_data[0][0] else 0.0

    # Display metrics
    cols = st.columns(3)
    cols[0].metric("Current Month Expenses", format_currency(current_expenses))
    cols[1].metric("Current Month Sales", format_currency(current_sales))
    cols[2].metric("Inventory Value", format_currency(inventory_value))

    # Recent transactions
    st.subheader("Recent Activity")

    cols = st.columns(2)
    with cols[0]:
        st.markdown("**:blue[Last 5 Expenses]**")
        expenses = execute_query(conn, """
            SELECT date, category, description, amount
            FROM expenses ORDER BY date DESC LIMIT 5
        """, fetch=True)
        if expenses:
            st.dataframe(pd.DataFrame(expenses, columns=["Date", "Category", "Description", "Amount"]),
                        use_container_width=True)
        else:
            st.info("No recent expenses")

    with cols[1]:
        st.markdown("**:green[Last 5 Sales]**")
        sales = execute_query(conn, """
            SELECT date, student_name, item, quantity, selling_price
            FROM uniform_sales ORDER BY date DESC LIMIT 5
        """, fetch=True)
        if sales:
            st.dataframe(pd.DataFrame(sales, columns=["Date", "Student", "Item", "Qty", "Price"]),
                        use_container_width=True)
        else:
            st.info("No recent sales")

def show_settings(conn):
    """Application settings tab"""
    st.header("⚙️ Settings")

    if st.session_state.get("username") == "admin":
        st.subheader("Database Management")

        # Database Backup (for Supabase, this is usually managed via Supabase dashboard backups)
        st.info("For Supabase, database backups are typically managed directly from the Supabase dashboard. "
                "You can export your data in CSV/JSON formats from individual tables or use Supabase's built-in "
                "backup features for full database snapshots.")

        if st.button("Reset All Data", type="secondary"):
            st.warning("This will delete ALL data in the database! This action is irreversible.")
            if st.checkbox("I understand this cannot be undone and wish to proceed."):
                if st.button("Confirm Reset", type="primary"):
                    try:
                        execute_query(conn, "DELETE FROM expenses")
                        execute_query(conn, "DELETE FROM uniform_stock")
                        execute_query(conn, "DELETE FROM uniform_sales")
                        execute_query(conn, "DELETE FROM receipts")
                        st.success("Database has been reset successfully!")
                        st.cache_resource.clear() # Clear cache to reflect empty data
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to reset database: {str(e)}")
                        st.code(traceback.format_exc())
    else:
        st.warning("Only admin users can access these settings")

    st.subheader("About")
    st.write("""
    **School Expense and Uniform Tracker** Version 2.1 (Supabase Enabled)  
    Developed for Success Achievers School  
    © 2024 All Rights Reserved
    """)

# ======================
# MAIN APPLICATION
# ======================
def main():
    """Main application function"""
    # Initialize session state
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
    if 'username' not in st.session_state:
        st.session_state.username = ""

    # Simple login - replace with your actual authentication
    if not st.session_state.logged_in:
        with st.form("login_form"):
            st.title("School Expense Tracker Login")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")

            if st.form_submit_button("Login", type="primary"):
                # Simple demo authentication - replace with real auth (e.g., Supabase Auth, password hashing)
                # For production, hash passwords and store them securely, then verify hash here.
                # Example: hashed_password = hashlib.sha256(password.encode()).hexdigest()
                # Check against stored hash.
                if username == "admin" and password == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.success("Logged in successfully!")
                    st.rerun()
                else:
                    st.error("Invalid username or password")
        return

    # Get database connection
    conn = get_db_connection()
    if conn is None:
        st.stop() # Stop execution if database connection fails

    # Sidebar navigation
    with st.sidebar:
        st.title(f"Welcome, {st.session_state.username.capitalize()} 👋")
        st.divider()

        # Quick stats for the current month
        today = date.today()
        first_day = today.replace(day=1)

        total_expenses_data = execute_query(conn, "SELECT SUM(amount) FROM expenses WHERE date BETWEEN %s AND %s", (first_day, today), fetch=True)
        total_expenses = total_expenses_data[0][0] if total_expenses_data and total_expenses_data[0][0] else 0.0

        total_sales_data = execute_query(conn, "SELECT SUM(quantity * selling_price) FROM uniform_sales WHERE date BETWEEN %s AND %s", (first_day, today), fetch=True)
        total_sales = total_sales_data[0][0] if total_sales_data and total_sales_data[0][0] else 0.0

        st.metric("This Month's Expenses", format_currency(total_expenses))
        st.metric("This Month's Sales", format_currency(total_sales))

        st.divider()

        # Navigation
        app_page = st.radio("Navigation", [
            "Dashboard", "Expenses", "Uniform Stock",
            "Uniform Sales", "Reports", "Settings"
        ], index=0) # Set default to Dashboard

        st.divider()
        if st.button("Logout", type="secondary"):
            st.session_state.logged_in = False
            st.session_state.username = ""
            st.cache_resource.clear() # Clear database connection cache on logout
            st.rerun()

    # Main content area
    if app_page == "Dashboard":
        show_dashboard(conn)
    elif app_page == "Expenses":
        show_expenses_tab(conn)
    elif app_page == "Uniform Stock":
        show_stock_tab(conn)
    elif app_page == "Uniform Sales":
        show_sales_tab(conn)
    elif app_page == "Reports":
        show_reports_tab(conn)
    elif app_page == "Settings":
        show_settings(conn)

if __name__ == "__main__":
    main()