import streamlit as st
import pandas as pd
import sqlite3
import traceback
from datetime import date, datetime, timedelta
import plotly.express as px
import io
import base64
import os
import uuid
import json

# Set page config at the very beginning before any other Streamlit command
st.set_page_config("School Expense Tracker", layout="wide", page_icon="📚")

# --- LOGIN GATE ---
def check_login():
    users = {
        "admin": "admin123",
        "user1": "user123"
    }
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.title("🔒 School Expense Login")
        with st.container():
            col1, col2 = st.columns([1, 1])
            with col1:
                st.image("https://via.placeholder.com/100x100.png?text=School", width=100)
            with col2:
                user = st.text_input("Username")
                pwd = st.text_input("Password", type="password")
                if st.button("Login", use_container_width=True):
                    if user in users and pwd == users[user]:
                        st.session_state.logged_in = True
                        st.session_state.username = user
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")
        st.stop()
        
# --- DATABASE CONNECTION (SQLITE) ---
@st.cache_resource
def get_connection():
    # Create a local SQLite database
    db_path = "school_expenses.db"
    conn = sqlite3.connect(db_path, check_same_thread=False)
    
    # Create tables if they don't exist
    with conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            category TEXT,
            description TEXT,
            amount REAL,
            receipt_no TEXT
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS uniform_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item TEXT,
            size TEXT,
            quantity INTEGER,
            unit_cost REAL,
            supplier TEXT,
            invoice_no TEXT
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS uniform_sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            student_name TEXT,
            student_class TEXT,
            item TEXT,
            size TEXT,
            quantity INTEGER,
            selling_price REAL,
            payment_mode TEXT,
            reference TEXT,
            receipt_id TEXT
        )
        ''')
        conn.execute('''
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            receipt_id TEXT UNIQUE,
            date TEXT,
            customer_name TEXT,
            items_json TEXT,  
            total_amount REAL,
            payment_mode TEXT,
            reference TEXT,
            issued_by TEXT
        )
        ''')
    return conn

def execute_query(query, params=None, fetch=False):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        
        # Convert PostgreSQL-style queries to SQLite syntax
        query = query.replace("%s", "?")
        query = query.replace("ILIKE", "LIKE")
        
        # Handle date_trunc function
        if "date_trunc" in query:
            query = query.replace("date_trunc('month', date)", "strftime('%Y-%m', date)")
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
            
        if fetch:
            result = cursor.fetchall()
        else:
            result = True
            conn.commit()
            
        return result
    except Exception:
        st.error("❌ Database error occurred:")
        st.code(traceback.format_exc())
        return None

# --- UTILITY FUNCTIONS ---
def get_download_link(df, filename, text):
    """Generates a link allowing the data in a given pandas dataframe to be downloaded"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}.csv">{text}</a>'
    return href

def get_excel_download_link(df, filename, text):
    """Generates an Excel download link for the given dataframe"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Sheet1', index=False)
    excel_data = output.getvalue()
    b64 = base64.b64encode(excel_data).decode()
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{filename}.xlsx">{text}</a>'
    return href

# --- RECEIPT GENERATION FUNCTIONS ---
def generate_receipt_html(receipt_data):
    """Generates HTML content for a receipt"""
    school_name = "ABC School"
    school_address = "123 Education Way, School District"
    school_contact = "Tel: 123-456-7890 | Email: info@abcschool.edu"
    
    receipt_html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; border: 1px solid #ccc;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h2>{school_name}</h2>
            <p>{school_address}<br>{school_contact}</p>
            <h3>RECEIPT</h3>
        </div>
        
        <div style="display: flex; justify-content: space-between; margin-bottom: 20px;">
            <div>
                <p><strong>Receipt #:</strong> {receipt_data['receipt_id']}</p>
                <p><strong>Date:</strong> {receipt_data['date']}</p>
            </div>
            <div>
                <p><strong>Student:</strong> {receipt_data['customer_name']}</p>
                <p><strong>Payment Method:</strong> {receipt_data['payment_mode']}</p>
                <p><strong>Reference:</strong> {receipt_data['reference']}</p>
            </div>
        </div>
        
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
            <thead>
                <tr style="background-color: #f2f2f2;">
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Item</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Size</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: right;">Price</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: right;">Qty</th>
                    <th style="border: 1px solid #ddd; padding: 8px; text-align: right;">Amount</th>
                </tr>
            </thead>
            <tbody>
    """
    
    # Add items to the receipt
    for item in receipt_data['items']:
        amount = item['price'] * item['quantity']
        receipt_html += f"""
                <tr>
                    <td style="border: 1px solid #ddd; padding: 8px;">{item['name']}</td>
                    <td style="border: 1px solid #ddd; padding: 8px;">{item['size']}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">KES {item['price']:,.2f}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">{item['quantity']}</td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;">KES {amount:,.2f}</td>
                </tr>
        """
    
    receipt_html += f"""
            </tbody>
            <tfoot>
                <tr>
                    <td colspan="4" style="border: 1px solid #ddd; padding: 8px; text-align: right;"><strong>Total:</strong></td>
                    <td style="border: 1px solid #ddd; padding: 8px; text-align: right;"><strong>KES {receipt_data['total_amount']:,.2f}</strong></td>
                </tr>
            </tfoot>
        </table>
        
        <div style="margin-top: 40px;">
            <p><strong>Issued By:</strong> {receipt_data['issued_by']}</p>
        </div>
        
        <div style="text-align: center; margin-top: 40px; font-size: 12px;">
            <p>Thank you for your business!</p>
            <p>This is a computer-generated receipt and does not require a signature.</p>
        </div>
    </div>
    """
    
    return receipt_html

def get_receipt_download_link(receipt_html, receipt_id):
    """Generates a download link for the receipt HTML content"""
    b64 = base64.b64encode(receipt_html.encode()).decode()
    href = f'<a href="data:text/html;base64,{b64}" download="receipt_{receipt_id}.html" target="_blank">📄 Download Receipt</a>'
    return href

def save_receipt_to_db(receipt_data):
    """Save receipt data to the database"""
    try:
        # Convert items list to JSON string
        items_json = json.dumps(receipt_data['items'])
        
        success = execute_query(
            """INSERT INTO receipts 
               (receipt_id, date, customer_name, items_json, total_amount, payment_mode, reference, issued_by) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (receipt_data['receipt_id'], receipt_data['date'], receipt_data['customer_name'],
             items_json, receipt_data['total_amount'], receipt_data['payment_mode'],
             receipt_data['reference'], receipt_data['issued_by'])
        )
        return success
    except Exception as e:
        st.error(f"Error saving receipt: {str(e)}")
        return False

def check_stock_availability(item, size, quantity):
    """Check if sufficient stock exists for a sale"""
    stock = execute_query(
        "SELECT quantity FROM uniform_stock WHERE item = ? AND size = ?",
        (item, size),
        fetch=True
    )
    if stock and stock[0][0] >= quantity:
        return True
    return False

# --- MAIN APP ---
check_login()

# Sidebar with user info and app navigation
with st.sidebar:
    st.write(f"👤 Logged in as: **{st.session_state.username}**")
    st.divider()
    
    st.subheader("💰 Quick Stats")
    total_expenses = execute_query("SELECT SUM(amount) FROM expenses", fetch=True)
    total_sales = execute_query("SELECT SUM(quantity * selling_price) FROM uniform_sales", fetch=True)
    
    if total_expenses and total_expenses[0][0]:
        st.metric("Total Expenses", f"KES {total_expenses[0][0]:,.2f}")
    if total_sales and total_sales[0][0]:
        st.metric("Uniform Sales", f"KES {total_sales[0][0]:,.2f}")
    
    if st.button("Logout", type="primary"):
        st.session_state.logged_in = False
        st.rerun()

# Main content
st.title("📚 School Expense and Uniform Tracker")
st.caption(f"Today's date: {date.today().strftime('%B %d, %Y')}")

tabs = st.tabs(["Expenses", "Uniform Stock", "Uniform Sales", "Reports", "Dashboard", "Settings"])

# --- Tab 1: Expenses ---
with tabs[0]:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("➕ Add Expense")
        with st.form("expense_form"):
            exp_date = st.date_input("Date", value=date.today())
            category = st.selectbox("Category", 
                ["Stationery", "Food", "Fuel", "Mechanic", "Development", "Utilities", 
                 "Maintenance", "Salaries", "Events", "Transportation", "Other"])
            description = st.text_input("Description")
            amount = st.number_input("Amount (KES)", min_value=0.0, format="%.2f")
            receipt_no = st.text_input("Receipt Number (optional)")
            submit = st.form_submit_button("Save Expense")

        if submit and description.strip() and amount > 0:
            success = execute_query(
                "INSERT INTO expenses (date, category, description, amount, receipt_no) VALUES (?, ?, ?, ?, ?)",
                (exp_date, category, description, amount, receipt_no)
            )
            if success:
                st.success("✅ Expense recorded successfully!")
        elif submit:
            st.warning("Please enter a description and amount.")
    
    with col2:
        st.subheader("🔍 Search Expenses")
        search_col1, search_col2 = st.columns(2)
        
        with search_col1:
            search_term = st.text_input("Search by description")
        with search_col2:
            search_category = st.multiselect("Filter by category", 
                ["All Categories", "Stationery", "Food", "Fuel", "Mechanic", "Development", 
                 "Utilities", "Maintenance", "Salaries", "Events", "Transportation", "Other"],
                default=["All Categories"])

        start_date, end_date = st.columns(2)
        with start_date:
            from_date = st.date_input("From date", value=date.today() - timedelta(days=30))
        with end_date:
            to_date = st.date_input("To date", value=date.today())

        # Build search query
        query = "SELECT id, date, category, description, amount, receipt_no FROM expenses WHERE date BETWEEN ? AND ?"
        params = [from_date, to_date]
        
        if search_term:
            query += " AND description LIKE ?"
            params.append(f"%{search_term}%")
            
        if "All Categories" not in search_category and search_category:
            placeholders = ", ".join(["?"] * len(search_category))
            query += f" AND category IN ({placeholders})"
            params.extend(search_category)
            
        query += " ORDER BY date DESC"
        
        # Execute search
        expenses = execute_query(query, params, fetch=True)
        
        if expenses:
            expenses_df = pd.DataFrame(expenses, columns=["ID", "Date", "Category", "Description", "Amount", "Receipt"])
            st.dataframe(expenses_df, use_container_width=True)
            
            # Download buttons for search results
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(get_download_link(expenses_df, "expenses_search", "📥 Download as CSV"), unsafe_allow_html=True)
            with col2:
                st.markdown(get_excel_download_link(expenses_df, "expenses_search", "📊 Download as Excel"), unsafe_allow_html=True)
        else:
            st.info("No expenses match your search criteria.")

# --- Tab 2: Uniform Stock ---
with tabs[1]:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("📦 Add Uniform Stock")
        with st.form("stock_form"):
            item = st.selectbox("Item", ["Sweater", "Tracksuit", "Dress", "Tshirt", "Trousers", "Shirt", "Tie", "Socks", "Blazer", "PE Kit"])
            size = st.text_input("Size")
            qty = st.number_input("Quantity", min_value=1, step=1)
            price = st.number_input("Unit Price (KES)", min_value=0.0)
            supplier = st.text_input("Supplier (optional)")
            invoice_no = st.text_input("Invoice Number (optional)")
            save_stock = st.form_submit_button("Add to Stock")

        if save_stock and size.strip() and qty > 0 and price > 0:
            success = execute_query(
                "INSERT INTO uniform_stock (item, size, quantity, unit_cost, supplier, invoice_no) VALUES (?, ?, ?, ?, ?, ?)",
                (item, size, qty, price, supplier, invoice_no)
            )
            if success:
                st.success("✅ Stock entry added!")
        elif save_stock:
            st.warning("Please complete all fields correctly.")
    
    with col2:
        st.subheader("📊 Current Stock")
        stock = execute_query(
            "SELECT item, size, quantity, unit_cost, supplier FROM uniform_stock ORDER BY item, size", fetch=True
        )
        if stock:
            stock_df = pd.DataFrame(stock, columns=["Item", "Size", "Quantity", "Unit Cost", "Supplier"])
            st.dataframe(stock_df, use_container_width=True)
            
            # Download buttons for stock
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(get_download_link(stock_df, "uniform_stock", "📥 Download as CSV"), unsafe_allow_html=True)
            with col2:
                st.markdown(get_excel_download_link(stock_df, "uniform_stock", "📊 Download as Excel"), unsafe_allow_html=True)
        else:
            st.info("No stock data found.")

# --- Tab 3: Uniform Sales ---
with tabs[2]:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("🛍 Record Uniform Sale")
        with st.form("sales_form"):
            sdate = st.date_input("Date of Sale", value=date.today())
            student_name = st.text_input("Student Name (optional)")
            student_class = st.text_input("Class/Grade (optional)")
            stype = st.selectbox("Item", ["Sweater", "Tracksuit", "Dress", "Tshirt", "Trousers", "Shirt", "Tie", "Socks", "Blazer", "PE Kit"])
            ssize = st.text_input("Size")
            sqty = st.number_input("Quantity", min_value=1, step=1)
            sprice = st.number_input("Selling Price (KES)", min_value=0.0)
            pmode = st.selectbox("Payment Mode", ["Cash", "Sacco Paybill", "Bank", "M-Pesa", "Cheque", "Other"])
            sref = st.text_input("Payment Reference")
            print_receipt = st.checkbox("Generate Receipt", value=True)
            record_sale = st.form_submit_button("Record Sale")

        if record_sale and ssize.strip() and sqty > 0 and sprice > 0:
            # Check stock availability
            if not check_stock_availability(stype, ssize, sqty):
                st.error("❌ Insufficient stock for this item/size!")
            else:
                # Generate a unique receipt ID
                receipt_id = f"REC-{date.today().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
                
                success = execute_query(
                    """INSERT INTO uniform_sales 
                       (date, student_name, student_class, item, size, quantity, selling_price, payment_mode, reference, receipt_id) 
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (sdate, student_name, student_class, stype, ssize, sqty, sprice, pmode, sref, receipt_id)
                )
                if success:
                    # Update stock quantity
                    execute_query(
                        "UPDATE uniform_stock SET quantity = quantity - ? WHERE item = ? AND size = ?",
                        (sqty, stype, ssize)
                    )
                    
                    st.success("✅ Sale recorded successfully!")
                    
                    # Generate receipt if requested
                    if print_receipt:
                        total_amount = sqty * sprice
                        
                        receipt_data = {
                            "receipt_id": receipt_id,
                            "date": sdate.strftime("%B %d, %Y"),
                            "customer_name": student_name if student_name else "Walk-in Customer",
                            "items": [
                                {
                                    "name": stype,
                                    "size": ssize,
                                    "price": sprice,
                                    "quantity": sqty
                                }
                            ],
                            "total_amount": total_amount,
                            "payment_mode": pmode,
                            "reference": sref,
                            "issued_by": st.session_state.username
                        }
                        
                        # Save receipt to database
                        save_receipt_to_db(receipt_data)
                        
                        # Generate receipt HTML
                        receipt_html = generate_receipt_html(receipt_data)
                        
                        # Display receipt in an expander
                        with st.expander("📄 View Receipt", expanded=True):
                            st.components.v1.html(receipt_html, height=600)
                            st.markdown(get_receipt_download_link(receipt_html, receipt_id), unsafe_allow_html=True)
        elif record_sale:
            st.warning("Please fill in all fields correctly.")
    
    with col2:
        st.subheader("🔍 Search Sales")
        search_col1, search_col2 = st.columns(2)
        
        with search_col1:
            sales_search = st.text_input("Search by student name or reference")
        with search_col2:
            sales_item = st.selectbox("Filter by item", ["All Items", "Sweater", "Tracksuit", "Dress", "Tshirt", "Trousers", "Shirt", "Tie", "Socks", "Blazer", "PE Kit"])

        sales_start, sales_end = st.columns(2)
        with sales_start:
            sales_from = st.date_input("Sales from", value=date.today() - timedelta(days=30))
        with sales_end:
            sales_to = st.date_input("Sales to", value=date.today())
            
        # Build search query for sales
        sales_query = """
            SELECT id, date, student_name, student_class, item, size, quantity, selling_price, payment_mode, reference, receipt_id
            FROM uniform_sales WHERE date BETWEEN ? AND ?
        """
        sales_params = [sales_from, sales_to]
        
        if sales_search:
            sales_query += " AND (student_name LIKE ? OR reference LIKE ?)"
            sales_params.extend([f"%{sales_search}%", f"%{sales_search}%"])
            
        if sales_item != "All Items":
            sales_query += " AND item = ?"
            sales_params.append(sales_item)
            
        sales_query += " ORDER BY date DESC"
        
        # Execute sales search
        sales = execute_query(sales_query, sales_params, fetch=True)
        
        if sales:
            sales_df = pd.DataFrame(sales, columns=["ID", "Date", "Student", "Class", "Item", "Size", "Quantity", "Price", "Payment", "Reference", "Receipt ID"])
            sales_df["Total"] = sales_df["Quantity"] * sales_df["Price"]
            
            # Display the dataframe
            st.dataframe(sales_df, use_container_width=True)
            
            # Download buttons for sales results
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(get_download_link(sales_df, "uniform_sales", "📥 Download as CSV"), unsafe_allow_html=True)
            with col2:
                st.markdown(get_excel_download_link(sales_df, "uniform_sales", "📊 Download as Excel"), unsafe_allow_html=True)
        else:
            st.info("No sales match your search criteria.")
        
        # Reprint receipt section
        st.subheader("🖨️ Reprint Receipt")
        with st.expander("Reprint Receipt"):
            receipt_id_input = st.text_input("Enter Receipt ID")
            if st.button("Find Receipt") and receipt_id_input:
                receipt_query = "SELECT * FROM receipts WHERE receipt_id = ?"
                receipt_data = execute_query(receipt_query, [receipt_id_input], fetch=True)
                
                if receipt_data:
                    receipt_record = receipt_data[0]
                    
                    # Parse items from JSON
                    items = json.loads(receipt_record[3])
                    
                    receipt_obj = {
                        "receipt_id": receipt_record[1],
                        "date": receipt_record[2],
                        "customer_name": receipt_record[3],
                        "items": items,
                        "total_amount": receipt_record[4],
                        "payment_mode": receipt_record[5],
                        "reference": receipt_record[6],
                        "issued_by": receipt_record[7]
                    }
                    
                    receipt_html = generate_receipt_html(receipt_obj)
                    
                    st.components.v1.html(receipt_html, height=600)
                    st.markdown(get_receipt_download_link(receipt_html, receipt_obj["receipt_id"]), unsafe_allow_html=True)
                else:
                    st.error("Receipt not found.")

# --- Tab 4: Reports ---
with tabs[3]:
    st.subheader("📈 Financial Reports")
    
    # Date range selector for reports
    report_col1, report_col2, report_col3 = st.columns(3)
    with report_col1:
        report_type = st.selectbox("Report Type", ["Expenses", "Uniform Sales", "Combined"])
    with report_col2:
        report_from = st.date_input("From", value=date.today().replace(day=1))
    with report_col3:
        report_to = st.date_input("To", value=date.today())
        
    if report_type == "Expenses" or report_type == "Combined":
        st.write("### 📂 Expense Summary")
        
        # Get expense data
        expense_query = """
            SELECT date, category, description, amount 
            FROM expenses WHERE date BETWEEN ? AND ?
            ORDER BY date
        """
        expense_data = execute_query(expense_query, [report_from, report_to], fetch=True)
        
        if expense_data:
            expense_df = pd.DataFrame(expense_data, columns=["Date", "Category", "Description", "Amount"])
            
            # Category summary
            cat_summary = expense_df.groupby("Category")["Amount"].sum().reset_index()
            
            col1, col2 = st.columns([2, 3])
            with col1:
                st.dataframe(cat_summary, use_container_width=True)
                st.metric("Total Expenses", f"KES {cat_summary['Amount'].sum():,.2f}")
            with col2:
                fig = px.pie(cat_summary, values="Amount", names="Category", title="Expense Distribution by Category")
                st.plotly_chart(fig, use_container_width=True)
            
            st.write("#### Expense Details")
            st.dataframe(expense_df, use_container_width=True)
            
            # Download buttons for expense report
            report_download_col1, report_download_col2 = st.columns(2)
            with report_download_col1:
                st.markdown(get_download_link(expense_df, f"expenses_{report_from}_to_{report_to}", "📥 Download Expense Report (CSV)"), unsafe_allow_html=True)
            with report_download_col2:
                st.markdown(get_excel_download_link(expense_df, f"expenses_{report_from}_to_{report_to}", "📊 Download Expense Report (Excel)"), unsafe_allow_html=True)
        else:
            st.info("No expense data found for the selected date range.")
            
    if report_type == "Uniform Sales" or report_type == "Combined":
        st.write("### 👕 Uniform Sales Summary")
        
        # Get sales data
        sales_query = """
            SELECT date, item, size, quantity, selling_price, payment_mode 
            FROM uniform_sales WHERE date BETWEEN ? AND ?
            ORDER BY date
        """
        sales_data = execute_query(sales_query, [report_from, report_to], fetch=True)
        
        if sales_data:
            sales_df = pd.DataFrame(sales_data, columns=["Date", "Item", "Size", "Quantity", "Price", "Payment Mode"])
            sales_df["Total"] = sales_df["Quantity"] * sales_df["Price"]
            
            # Item summary
            item_summary = sales_df.groupby("Item")["Total"].sum().reset_index()
            
            col1, col2 = st.columns([2, 3])
            with col1:
                st.dataframe(item_summary, use_container_width=True)
                st.metric("Total Sales", f"KES {item_summary['Total'].sum():,.2f}")
            with col2:
                fig = px.pie(item_summary, values="Total", names="Item", title="Sales Distribution by Item")
                st.plotly_chart(fig, use_container_width=True)
            
            st.write("#### Sales Details")
            st.dataframe(sales_df, use_container_width=True)
            
            # Download buttons for sales report
            report_download_col1, report_download_col2 = st.columns(2)
            with report_download_col1:
                st.markdown(get_download_link(sales_df, f"sales_{report_from}_to_{report_to}", "📥 Download Sales Report (CSV)"), unsafe_allow_html=True)
            with report_download_col2:
                st.markdown(get_excel_download_link(sales_df, f"sales_{report_from}_to_{report_to}", "📊 Download Sales Report (Excel)"), unsafe_allow_html=True)
        else:
            st.info("No sales data found for the selected date range.")

# --- Tab 5: Dashboard ---
with tabs[4]:
    st.subheader("📊 Financial Dashboard")
    
    # Get data for dashboard
    today = date.today()
    first_day = today.replace(day=1)
    last_month = first_day - timedelta(days=1)
    first_day_last_month = last_month.replace(day=1)
    
    # Current month metrics
    current_month_expenses = execute_query(
        "SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?",
        [first_day, today], fetch=True
    )
    current_month_sales = execute_query(
        "SELECT SUM(quantity * selling_price) FROM uniform_sales WHERE date BETWEEN ? AND ?",
        [first_day, today], fetch=True
    )
    
    # Last month metrics
    last_month_expenses = execute_query(
        "SELECT SUM(amount) FROM expenses WHERE date BETWEEN ? AND ?",
        [first_day_last_month, last_month], fetch=True
    )
    last_month_sales = execute_query(
        "SELECT SUM(quantity * selling_price) FROM uniform_sales WHERE date BETWEEN ? AND ?",
        [first_day_last_month, last_month], fetch=True
    )
    
    # Display metrics
    col1, col2 = st.columns(2)
    with col1:
        if current_month_expenses and current_month_expenses[0][0]:
            delta = None
            if last_month_expenses and last_month_expenses[0][0]:
                delta = current_month_expenses[0][0] - last_month_expenses[0][0]
            st.metric("Current Month Expenses", f"KES {current_month_expenses[0][0]:,.2f}", delta=f"KES {delta:,.2f}" if delta else None)
        else:
            st.metric("Current Month Expenses", "KES 0.00")
    
    with col2:
        if current_month_sales and current_month_sales[0][0]:
            delta = None
            if last_month_sales and last_month_sales[0][0]:
                delta = current_month_sales[0][0] - last_month_sales[0][0]
            st.metric("Current Month Sales", f"KES {current_month_sales[0][0]:,.2f}", delta=f"KES {delta:,.2f}" if delta else None)
        else:
            st.metric("Current Month Sales", "KES 0.00")
    
    # Expense trends chart
    st.write("### 📅 Monthly Trends")
    
    # Get monthly data for the last 12 months
    twelve_months_ago = today - timedelta(days=365)
    
    monthly_expenses = execute_query(
        """SELECT strftime('%Y-%m', date) as month, SUM(amount) 
           FROM expenses WHERE date BETWEEN ? AND ?
           GROUP BY strftime('%Y-%m', date) ORDER BY month""",
        [twelve_months_ago, today], fetch=True
    )
    
    monthly_sales = execute_query(
        """SELECT strftime('%Y-%m', date) as month, SUM(quantity * selling_price) 
           FROM uniform_sales WHERE date BETWEEN ? AND ?
           GROUP BY strftime('%Y-%m', date) ORDER BY month""",
        [twelve_months_ago, today], fetch=True
    )
    
    # Create DataFrames
    if monthly_expenses:
        expenses_df = pd.DataFrame(monthly_expenses, columns=["Month", "Expenses"])
    else:
        expenses_df = pd.DataFrame(columns=["Month", "Expenses"])
    
    if monthly_sales:
        sales_df = pd.DataFrame(monthly_sales, columns=["Month", "Sales"])
    else:
        sales_df = pd.DataFrame(columns=["Month", "Sales"])
    
    # Merge data
    trend_df = pd.merge(expenses_df, sales_df, on="Month", how="outer").fillna(0)
    
    # Plot trends
    if not trend_df.empty:
        fig = px.line(trend_df, x="Month", y=["Expenses", "Sales"], 
                      title="Monthly Expenses vs Sales",
                      labels={"value": "Amount (KES)", "variable": "Category"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available for trends analysis.")

# --- Tab 6: Settings ---
with tabs[5]:
    st.subheader("⚙️ Application Settings")
    
    if st.session_state.username == "admin":
        st.write("### Database Management")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Export Database Backup"):
                # Create a backup of the SQLite database
                conn = get_connection()
                with io.BytesIO() as f:
                    for line in conn.iterdump():
                        f.write(f"{line}\n".encode('utf-8'))
                    f.seek(0)
                    st.download_button(
                        label="Download Database Backup",
                        data=f,
                        file_name=f"school_expenses_backup_{today}.sql",
                        mime="application/sql"
                    )
        
        with col2:
            if st.button("Reset All Data (DANGER)"):
                st.warning("This will delete ALL data in the database!")
                if st.checkbox("I understand this cannot be undone"):
                    if st.button("Confirm Reset"):
                        execute_query("DELETE FROM expenses")
                        execute_query("DELETE FROM uniform_stock")
                        execute_query("DELETE FROM uniform_sales")
                        execute_query("DELETE FROM receipts")
                        st.success("Database has been reset")
    else:
        st.warning("Only admin users can access these settings")
    
    st.write("### About")
    st.write("""
    **School Expense and Uniform Tracker**  
    Version 1.0  
    Developed for Success Achievers School  
    © 2025 All Rights Reserved
    """)