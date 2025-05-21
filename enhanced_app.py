import streamlit as st
import pandas as pd
import sqlite3
import traceback
from datetime import date, datetime, timedelta
import plotly.express as px
import io
import base64
import uuid
import json

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
def init_database():
    """Initialize the database with required tables"""
    conn = sqlite3.connect('school_expenses.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Create tables if they don't exist
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT,
        amount REAL NOT NULL,
        receipt_no TEXT
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS uniform_stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item TEXT NOT NULL,
        size TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        unit_cost REAL NOT NULL,
        supplier TEXT,
        invoice_no TEXT,
        last_updated TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS uniform_sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        student_name TEXT,
        student_class TEXT,
        item TEXT NOT NULL,
        size TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        selling_price REAL NOT NULL,
        payment_mode TEXT NOT NULL,
        reference TEXT,
        receipt_id TEXT UNIQUE
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id TEXT UNIQUE NOT NULL,
        date TEXT NOT NULL,
        customer_name TEXT,
        items_json TEXT NOT NULL,
        total_amount REAL NOT NULL,
        payment_mode TEXT NOT NULL,
        reference TEXT,
        issued_by TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    # Add receipt_id column if it doesn't exist (for backward compatibility)
    try:
        cursor.execute("ALTER TABLE uniform_sales ADD COLUMN receipt_id TEXT")
    except sqlite3.OperationalError:
        pass
    
    conn.commit()
    return conn

@st.cache_resource
def get_db_connection():
    """Get a cached database connection"""
    return init_database()

def execute_query(_conn, query, params=None, fetch=False):
    """Execute a SQL query with error handling"""
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
        
        return result
    except Exception as e:
        st.error(f"Database error: {str(e)}")
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
        WHERE item = ? AND size = ? AND quantity >= ?
    """
    result = execute_query(conn, query, (item, size, quantity), fetch=True)
    return bool(result)

def update_stock(conn, item, size, quantity_change):
    """Update stock quantity"""
    query = """
        UPDATE uniform_stock 
        SET quantity = quantity + ?, last_updated = CURRENT_TIMESTAMP
        WHERE item = ? AND size = ?
    """
    return execute_query(conn, query, (quantity_change, item, size))

# ======================
# APPLICATION PAGES
# ======================
def show_expenses_tab(conn):
    """Expenses management tab"""
    st.header("💰 Expense Management")
    
    with st.expander("➕ Add New Expense", expanded=True):
        with st.form("expense_form"):
            cols = st.columns(3)
            with cols[0]:
                exp_date = st.date_input("Date", value=date.today())
            with cols[1]:
                category = st.selectbox("Category", [
                    "Stationery", "Food", "Fuel", "Maintenance",
                    "Salaries", "Utilities", "Transport", "Events", "Other"
                ])
            with cols[2]:
                amount = st.number_input("Amount (KES)", min_value=0.0, step=0.01)
            
            description = st.text_input("Description")
            receipt_no = st.text_input("Receipt/Invoice Number (optional)")
            
            if st.form_submit_button("Save Expense"):
                if amount > 0 and description.strip():
                    query = """
                        INSERT INTO expenses (date, category, description, amount, receipt_no)
                        VALUES (?, ?, ?, ?, ?)
                    """
                    if execute_query(conn, query, (exp_date, category, description, amount, receipt_no)):
                        st.success("Expense recorded successfully!")
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
                "Salaries", "Utilities", "Transport", "Events", "Other"
            ])
        
        search_term = st.text_input("Search Description")

    # Build query
    query = "SELECT date, category, description, amount, receipt_no FROM expenses WHERE date BETWEEN ? AND ?"
    params = [start_date, end_date]
    
    if categories:
        query += " AND category IN (" + ",".join(["?"] * len(categories)) + ")"
        params.extend(categories)
    
    if search_term:
        query += " AND description LIKE ?"
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
    else:
        st.info("No expenses found for the selected filters")

def show_stock_tab(conn):
    """Uniform stock management tab"""
    st.header("👕 Uniform Stock Management")
    
    with st.expander("📦 Add/Update Stock", expanded=True):
        with st.form("stock_form"):
            cols = st.columns([2, 1, 1, 2])
            with cols[0]:
                item = st.selectbox("Item", [
                    "Sweater", "Tracksuit", "Dress", "T-shirt",
                    "Trousers", "Shirt", "Tie", "Socks", "Blazer", "PE Kit"
                ])
            with cols[1]:
                size = st.text_input("Size", placeholder="e.g., M, 12, etc.")
            with cols[2]:
                quantity = st.number_input("Quantity", min_value=1, step=1)
            with cols[3]:
                unit_cost = st.number_input("Unit Cost (KES)", min_value=0.0, step=0.01)
            
            cols = st.columns(2)
            with cols[0]:
                supplier = st.text_input("Supplier (optional)")
            with cols[1]:
                invoice_no = st.text_input("Invoice No. (optional)")
            
            if st.form_submit_button("Update Stock"):
                if size.strip():
                    # Check if item exists
                    check_query = "SELECT id FROM uniform_stock WHERE item = ? AND size = ?"
                    exists = execute_query(conn, check_query, (item, size), fetch=True)
                    
                    if exists:
                        # Update existing stock
                        update_query = """
                            UPDATE uniform_stock 
                            SET quantity = quantity + ?, unit_cost = ?, supplier = ?, invoice_no = ?
                            WHERE item = ? AND size = ?
                        """
                        if execute_query(conn, update_query, 
                                       (quantity, unit_cost, supplier, invoice_no, item, size)):
                            st.success("Stock updated successfully!")
                    else:
                        # Add new stock
                        insert_query = """
                            INSERT INTO uniform_stock (item, size, quantity, unit_cost, supplier, invoice_no)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """
                        if execute_query(conn, insert_query, 
                                       (item, size, quantity, unit_cost, supplier, invoice_no)):
                            st.success("New stock item added!")
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
        st.markdown(get_download_link(df, "stock_report", "📥 Download Stock Report"), unsafe_allow_html=True)
    else:
        st.info("No stock items found in inventory")

def show_sales_tab(conn):
    """Uniform sales management tab"""
    st.header("🛍 Uniform Sales")
    
    with st.expander("💳 Record New Sale", expanded=True):
        with st.form("sales_form"):
            cols = st.columns(3)
            with cols[0]:
                sale_date = st.date_input("Date", value=date.today())
            with cols[1]:
                student_name = st.text_input("Student Name (optional)")
            with cols[2]:
                student_class = st.text_input("Class/Grade (optional)")
            
            cols = st.columns([2, 1, 1, 2])
            with cols[0]:
                item = st.selectbox("Item", [
                    "Sweater", "Tracksuit", "Dress", "T-shirt",
                    "Trousers", "Shirt", "Tie", "Socks", "Blazer", "PE Kit"
                ])
            with cols[1]:
                size = st.text_input("Size")
            with cols[2]:
                quantity = st.number_input("Quantity", min_value=1, step=1, value=1)
            with cols[3]:
                price = st.number_input("Unit Price (KES)", min_value=0.0, step=0.01)
            
            cols = st.columns(2)
            with cols[0]:
                payment_mode = st.selectbox("Payment Method", ["Cash", "M-Pesa", "Bank Transfer", "Cheque", "Other"])
            with cols[1]:
                reference = st.text_input("Payment Reference (optional)")
            
            generate_receipt = st.checkbox("Generate Receipt", value=True)
            
            if st.form_submit_button("Record Sale"):
                if size.strip() and price > 0:
                    # Check stock availability
                    if not check_stock_availability(conn, item, size, quantity):
                        st.error("Insufficient stock for this item!")
                    else:
                        # Generate receipt ID
                        receipt_id = generate_unique_id("REC-")
                        
                        # Record sale
                        sale_query = """
                            INSERT INTO uniform_sales (
                                date, student_name, student_class, item, size,
                                quantity, selling_price, payment_mode, reference, receipt_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                                    "total_amount": price * quantity,
                                    "payment_mode": payment_mode,
                                    "reference": reference,
                                    "issued_by": "System"  # Replace with actual user
                                }
                                
                                # Save receipt
                                if save_receipt(conn, receipt_data):
                                    # Show receipt
                                    receipt_html = generate_receipt_html(receipt_data)
                                    with st.expander("📄 View Receipt", expanded=True):
                                        st.components.v1.html(receipt_html, height=600)
                                        st.markdown(
                                            f'<a href="data:text/html;base64,{base64.b64encode(receipt_html.encode()).decode()}" '
                                            f'download="receipt_{receipt_id}.html" target="_blank">📄 Download Receipt</a>',
                                            unsafe_allow_html=True
                                        )
                else:
                    st.warning("Please complete all required fields")

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
        WHERE date BETWEEN ? AND ?
    """
    params = [start_date, end_date]
    
    if items:
        query += " AND item IN (" + ",".join(["?"] * len(items)) + ")"
        params.extend(items)
    
    if search_term:
        query += " AND (student_name LIKE ? OR reference LIKE ?)"
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
        st.markdown(get_download_link(df, "sales_report", "📥 Download Sales Report"), unsafe_allow_html=True)
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
            WHERE date BETWEEN ? AND ?
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
            WHERE date BETWEEN ? AND ?
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
        else:
            st.info("No inventory items found")
    
    elif report_type == "Monthly Trends":
        st.subheader("📅 Monthly Trends Analysis")
        
        # Get monthly expenses
        expense_query = """
            SELECT strftime('%Y-%m', date) as month, 
                   SUM(amount) as expenses
            FROM expenses
            GROUP BY month
            ORDER BY month
        """
        expenses = execute_query(conn, expense_query, fetch=True)
        
        # Get monthly sales
        sales_query = """
            SELECT strftime('%Y-%m', date) as month, 
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
            
            # Show metrics
            latest = df.iloc[-1] if not df.empty else None
            if latest is not None:
                cols = st.columns(3)
                cols[0].metric("Latest Month", latest["Month"])
                cols[1].metric("Expenses", format_currency(latest["Expenses"]))
                cols[2].metric("Sales", format_currency(latest["Sales"]))
                
                if len(df) > 1:
                    prev = df.iloc[-2]
                    delta_exp = latest["Expenses"] - prev["Expenses"]
                    delta_sales = latest["Sales"] - prev["Sales"]
                    
                    cols = st.columns(2)
                    cols[0].metric("Expenses Change", format_currency(delta_exp))
                    cols[1].metric("Sales Change", format_currency(delta_sales))
            
            # Show trend chart
            fig = px.line(df, x="Month", y=["Expenses", "Sales", "Profit"],
                         title="Monthly Financial Trends",
                         labels={"value": "Amount (KES)", "variable": "Category"})
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(df, use_container_width=True)
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
        WHERE date BETWEEN ? AND ?
    """
    current_expenses = execute_query(conn, expense_query, (first_day, today), fetch=True)
    current_expenses = current_expenses[0][0] if current_expenses and current_expenses[0][0] else 0
    
    # Sales metrics
    sales_query = """
        SELECT SUM(quantity * selling_price) FROM uniform_sales 
        WHERE date BETWEEN ? AND ?
    """
    current_sales = execute_query(conn, sales_query, (first_day, today), fetch=True)
    current_sales = current_sales[0][0] if current_sales and current_sales[0][0] else 0
    
    # Inventory metrics
    inventory_query = "SELECT SUM(quantity * unit_cost) FROM uniform_stock"
    inventory_value = execute_query(conn, inventory_query, fetch=True)
    inventory_value = inventory_value[0][0] if inventory_value and inventory_value[0][0] else 0
    
    # Display metrics
    cols = st.columns(3)
    cols[0].metric("Current Month Expenses", format_currency(current_expenses))
    cols[1].metric("Current Month Sales", format_currency(current_sales))
    cols[2].metric("Inventory Value", format_currency(inventory_value))
    
    # Recent transactions
    st.subheader("Recent Activity")
    
    cols = st.columns(2)
    with cols[0]:
        st.markdown("**Last 5 Expenses**")
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
        st.markdown("**Last 5 Sales**")
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
        
        cols = st.columns(2)
        with cols[0]:
            if st.button("Export Database Backup"):
                try:
                    with io.BytesIO() as f:
                        for line in conn.iterdump():
                            f.write(f"{line}\n".encode('utf-8'))
                        f.seek(0)
                        st.download_button(
                            label="Download Backup",
                            data=f,
                            file_name=f"school_expenses_backup_{date.today()}.sql",
                            mime="application/sql"
                        )
                except Exception as e:
                    st.error(f"Backup failed: {str(e)}")
        
        with cols[1]:
            if st.button("Reset All Data", type="secondary"):
                st.warning("This will delete ALL data in the database!")
                if st.checkbox("I understand this cannot be undone"):
                    if st.button("Confirm Reset", type="primary"):
                        execute_query(conn, "DELETE FROM expenses")
                        execute_query(conn, "DELETE FROM uniform_stock")
                        execute_query(conn, "DELETE FROM uniform_sales")
                        execute_query(conn, "DELETE FROM receipts")
                        st.success("Database has been reset")
    else:
        st.warning("Only admin users can access these settings")
    
    st.subheader("About")
    st.write("""
    **School Expense and Uniform Tracker**  
    Version 2.0  
    Developed for Success Achievers School  
    © 2023 All Rights Reserved
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
            
            if st.form_submit_button("Login"):
                # Simple demo authentication - replace with real auth
                if username == "admin" and password == "admin123":
                    st.session_state.logged_in = True
                    st.session_state.username = username
                    st.rerun()
                else:
                    st.error("Invalid credentials")
        return
    
    # Get database connection
    conn = get_db_connection()
    
    # Sidebar navigation
    with st.sidebar:
        st.title(f"Welcome, {st.session_state.username}")
        st.divider()
        
        # Quick stats
        total_expenses = execute_query(conn, "SELECT SUM(amount) FROM expenses", fetch=True)
        total_sales = execute_query(conn, "SELECT SUM(quantity * selling_price) FROM uniform_sales", fetch=True)
        
        if total_expenses and total_expenses[0][0]:
            st.metric("Total Expenses", format_currency(total_expenses[0][0]))
        if total_sales and total_sales[0][0]:
            st.metric("Total Sales", format_currency(total_sales[0][0]))
        
        st.divider()
        
        # Navigation
        app_page = st.radio("Navigation", [
            "Dashboard", "Expenses", "Uniform Stock", 
            "Uniform Sales", "Reports", "Settings"
        ])
        
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.session_state.username = ""
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