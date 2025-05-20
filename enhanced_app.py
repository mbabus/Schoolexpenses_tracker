import streamlit as st
import pandas as pd
import sqlite3
import traceback
from datetime import date, datetime, timedelta
import plotly.express as px
import io
import base64
import os

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
                        st.experimental_rerun()
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
            reference TEXT
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

# --- MAIN APP ---
check_login()

st.set_page_config("School Expense Tracker", layout="wide", page_icon="📚")

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
        st.experimental_rerun()

# Main content
st.title("📚 School Expense and Uniform Tracker")
st.caption(f"Today's date: {date.today().strftime('%B %d, %Y')}")

tabs = st.tabs(["Expenses", "Uniform Stock", "Uniform Sales", "Reports", "Dashboard"])

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
                "INSERT INTO expenses (date, category, description, amount, receipt_no) VALUES (%s, %s, %s, %s, %s)",
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
        query = "SELECT id, date, category, description, amount, receipt_no FROM expenses WHERE date BETWEEN %s AND %s"
        params = [from_date, to_date]
        
        if search_term:
            query += " AND description ILIKE %s"
            params.append(f"%{search_term}%")
            
        if "All Categories" not in search_category and search_category:
            placeholders = ", ".join(["%s"] * len(search_category))
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
                "INSERT INTO uniform_stock (item, size, quantity, unit_cost, supplier, invoice_no) VALUES (%s, %s, %s, %s, %s, %s)",
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
            record_sale = st.form_submit_button("Record Sale")

        if record_sale and ssize.strip() and sqty > 0 and sprice > 0:
            success = execute_query(
                """INSERT INTO uniform_sales 
                   (date, student_name, student_class, item, size, quantity, selling_price, payment_mode, reference) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (sdate, student_name, student_class, stype, ssize, sqty, sprice, pmode, sref)
            )
            if success:
                st.success("✅ Sale recorded successfully!")
                
                # Update stock quantity
                execute_query(
                    "UPDATE uniform_stock SET quantity = quantity - %s WHERE item = %s AND size = %s",
                    (sqty, stype, ssize)
                )
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
            SELECT date, student_name, student_class, item, size, quantity, selling_price, payment_mode, reference 
            FROM uniform_sales WHERE date BETWEEN %s AND %s
        """
        sales_params = [sales_from, sales_to]
        
        if sales_search:
            sales_query += " AND (student_name ILIKE %s OR reference ILIKE %s)"
            sales_params.extend([f"%{sales_search}%", f"%{sales_search}%"])
            
        if sales_item != "All Items":
            sales_query += " AND item = %s"
            sales_params.append(sales_item)
            
        sales_query += " ORDER BY date DESC"
        
        # Execute sales search
        sales = execute_query(sales_query, sales_params, fetch=True)
        
        if sales:
            sales_df = pd.DataFrame(sales, columns=["Date", "Student", "Class", "Item", "Size", "Quantity", "Price", "Payment", "Reference"])
            sales_df["Total"] = sales_df["Quantity"] * sales_df["Price"]
            st.dataframe(sales_df, use_container_width=True)
            
            # Download buttons for sales results
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(get_download_link(sales_df, "uniform_sales", "📥 Download as CSV"), unsafe_allow_html=True)
            with col2:
                st.markdown(get_excel_download_link(sales_df, "uniform_sales", "📊 Download as Excel"), unsafe_allow_html=True)
        else:
            st.info("No sales match your search criteria.")

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
            FROM expenses WHERE date BETWEEN %s AND %s
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
            SELECT date, item, size, quantity, selling_price, payment_mode, student_name
            FROM uniform_sales WHERE date BETWEEN %s AND %s
            ORDER BY date
        """
        sales_data = execute_query(sales_query, [report_from, report_to], fetch=True)
        
        if sales_data:
            sales_df = pd.DataFrame(sales_data, columns=["Date", "Item", "Size", "Quantity", "Price", "Payment Mode", "Student"])
            sales_df["Total"] = sales_df["Quantity"] * sales_df["Price"]
            
            # Item summary
            item_summary = sales_df.groupby(["Item", "Size"])[["Quantity", "Total"]].sum().reset_index()
            payment_summary = sales_df.groupby("Payment Mode")["Total"].sum().reset_index()
            
            col1, col2 = st.columns([1, 1])
            with col1:
                st.write("#### Sales by Item")
                st.dataframe(item_summary, use_container_width=True)
                st.metric("Total Sales", f"KES {sales_df['Total'].sum():,.2f}")
            with col2:
                st.write("#### Sales by Payment Mode")
                fig = px.bar(payment_summary, x="Payment Mode", y="Total", title="Sales by Payment Method")
                st.plotly_chart(fig, use_container_width=True)
            
            st.write("#### Sales Details")
            st.dataframe(sales_df, use_container_width=True)
            
            # Download buttons for sales report
            sales_download_col1, sales_download_col2 = st.columns(2)
            with sales_download_col1:
                st.markdown(get_download_link(sales_df, f"uniform_sales_{report_from}_to_{report_to}", "📥 Download Sales Report (CSV)"), unsafe_allow_html=True)
            with sales_download_col2:
                st.markdown(get_excel_download_link(sales_df, f"uniform_sales_{report_from}_to_{report_to}", "📊 Download Sales Report (Excel)"), unsafe_allow_html=True)
        else:
            st.info("No sales data found for the selected date range.")
    
    if report_type == "Combined":
        st.write("### 💹 Combined Financial Report")
        
        # If we have both expense and sales data for the period
        if 'expense_df' in locals() and 'sales_df' in locals():
            # Create monthly summary
            if not expense_df.empty and not sales_df.empty:
                expense_df['Month'] = pd.to_datetime(expense_df['Date']).dt.strftime('%b %Y')
                sales_df['Month'] = pd.to_datetime(sales_df['Date']).dt.strftime('%b %Y')
                
                monthly_expenses = expense_df.groupby('Month')['Amount'].sum().reset_index()
                monthly_sales = sales_df.groupby('Month')['Total'].sum().reset_index().rename(columns={'Total': 'Sales'})
                
                # Merge into one dataframe
                monthly_df = pd.merge(monthly_expenses, monthly_sales, on='Month', how='outer').fillna(0)
                monthly_df['Profit'] = monthly_df['Sales'] - monthly_df['Amount']
                
                st.write("#### Monthly Summary")
                st.dataframe(monthly_df, use_container_width=True)
                
                # Create combined chart
                fig = px.line(monthly_df, x='Month', y=['Amount', 'Sales', 'Profit'], 
                              title='Monthly Financial Overview',
                              labels={'value': 'Amount (KES)', 'variable': 'Category'},
                              color_discrete_map={'Amount': 'red', 'Sales': 'green', 'Profit': 'blue'})
                st.plotly_chart(fig, use_container_width=True)
                
                # Download combined report
                st.markdown(get_excel_download_link(monthly_df, f"financial_summary_{report_from}_to_{report_to}", 
                                                  "📊 Download Combined Financial Report"), unsafe_allow_html=True)
            else:
                st.info("Insufficient data for combined report.")
        else:
            st.info("No data available for combined report.")

# --- Tab 5: Dashboard ---
with tabs[4]:
    st.subheader("📊 School Finance Dashboard")
    
    # Get overall statistics
    today = date.today()
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)
    
    # Monthly stats
    monthly_expenses = execute_query(
        "SELECT SUM(amount) FROM expenses WHERE date >= %s AND date <= %s",
        [start_of_month, today], fetch=True
    )
    
    monthly_sales = execute_query(
        "SELECT SUM(quantity * selling_price) FROM uniform_sales WHERE date >= %s AND date <= %s",
        [start_of_month, today], fetch=True
    )
    
    # Yearly stats
    yearly_expenses = execute_query(
        "SELECT SUM(amount) FROM expenses WHERE date >= %s AND date <= %s",
        [start_of_year, today], fetch=True
    )
    
    yearly_sales = execute_query(
        "SELECT SUM(quantity * selling_price) FROM uniform_sales WHERE date >= %s AND date <= %s",
        [start_of_year, today], fetch=True
    )
    
    # Display stats
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "This Month Expenses", 
            f"KES {monthly_expenses[0][0]:,.2f}" if monthly_expenses and monthly_expenses[0][0] else "KES 0.00"
        )
    
    with col2:
        st.metric(
            "This Month Sales", 
            f"KES {monthly_sales[0][0]:,.2f}" if monthly_sales and monthly_sales[0][0] else "KES 0.00"
        )
    
    with col3:
        st.metric(
            "This Year Expenses", 
            f"KES {yearly_expenses[0][0]:,.2f}" if yearly_expenses and yearly_expenses[0][0] else "KES 0.00"
        )
    
    with col4:
        st.metric(
            "This Year Sales", 
            f"KES {yearly_sales[0][0]:,.2f}" if yearly_sales and yearly_sales[0][0] else "KES 0.00"
        )
    
    # Get expense trends
    expense_trend = execute_query("""
        SELECT 
            date_trunc('month', date) as month,
            SUM(amount) as total
        FROM expenses 
        WHERE date >= %s 
        GROUP BY date_trunc('month', date)
        ORDER BY month
    """, [today - timedelta(days=365)], fetch=True)
    
    sales_trend = execute_query("""
        SELECT 
            date_trunc('month', date) as month,
            SUM(quantity * selling_price) as total
        FROM uniform_sales 
        WHERE date >= %s 
        GROUP BY date_trunc('month', date)
        ORDER BY month
    """, [today - timedelta(days=365)], fetch=True)
    
    # Create trend charts
    if expense_trend and sales_trend:
        expense_df = pd.DataFrame(expense_trend, columns=['Month', 'Amount'])
        sales_df = pd.DataFrame(sales_trend, columns=['Month', 'Amount'])
        
        expense_df['Type'] = 'Expenses'
        sales_df['Type'] = 'Sales'
        
        combined_df = pd.concat([expense_df, sales_df])
        combined_df['Month'] = pd.to_datetime(combined_df['Month']).dt.strftime('%b %Y')
        
        # Plot trends
        st.subheader("Annual Trends")
        fig = px.line(combined_df, x='Month', y='Amount', color='Type',
                     title='Financial Trends - Last 12 Months',
                     labels={'Amount': 'Amount (KES)'})
        st.plotly_chart(fig, use_container_width=True)
    
    # Top expenses by category
    top_expenses = execute_query("""
        SELECT category, SUM(amount) as total
        FROM expenses
        WHERE date >= %s
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """, [today - timedelta(days=90)], fetch=True)
    
    # Top uniform items sold
    top_items = execute_query("""
        SELECT item, SUM(quantity) as total_qty, SUM(quantity * selling_price) as total_sales
        FROM uniform_sales
        WHERE date >= %s
        GROUP BY item
        ORDER BY total_sales DESC
        LIMIT 5
    """, [today - timedelta(days=90)], fetch=True)
    
    # Display top items
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Top Expense Categories (Last 90 Days)")
        if top_expenses:
            top_exp_df = pd.DataFrame(top_expenses, columns=['Category', 'Amount'])
            fig = px.bar(top_exp_df, x='Category', y='Amount', title='Top Expense Categories')
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Top Uniform Items (Last 90 Days)")
        if top_items:
            top_items_df = pd.DataFrame(top_items, columns=['Item', 'Quantity', 'Sales'])
            fig = px.bar(top_items_df, x='Item', y='Sales', title='Top Uniform Sales')
            st.plotly_chart(fig, use_container_width=True)
    
    # Low stock alert
    low_stock = execute_query("""
        SELECT item, size, quantity 
        FROM uniform_stock
        WHERE quantity <= 5
        ORDER BY quantity ASC
    """, fetch=True)
    
    if low_stock:
        st.warning("⚠️ Low Stock Alert")
        low_stock_df = pd.DataFrame(low_stock, columns=['Item', 'Size', 'Quantity'])
        st.dataframe(low_stock_df, use_container_width=True)
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

# --- MAIN APP ---
check_login()

st.set_page_config("School Expense Tracker", layout="wide", page_icon="📚")

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
        st.experimental_rerun()

# Main content
st.title("📚 School Expense and Uniform Tracker")
st.caption(f"Today's date: {date.today().strftime('%B %d, %Y')}")

tabs = st.tabs(["Expenses", "Uniform Stock", "Uniform Sales", "Reports", "Dashboard"])

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
                "INSERT INTO expenses (date, category, description, amount, receipt_no) VALUES (%s, %s, %s, %s, %s)",
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
        query = "SELECT id, date, category, description, amount, receipt_no FROM expenses WHERE date BETWEEN %s AND %s"
        params = [from_date, to_date]
        
        if search_term:
            query += " AND description ILIKE %s"
            params.append(f"%{search_term}%")
            
        if "All Categories" not in search_category and search_category:
            placeholders = ", ".join(["%s"] * len(search_category))
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
                "INSERT INTO uniform_stock (item, size, quantity, unit_cost, supplier, invoice_no) VALUES (%s, %s, %s, %s, %s, %s)",
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
            record_sale = st.form_submit_button("Record Sale")

        if record_sale and ssize.strip() and sqty > 0 and sprice > 0:
            success = execute_query(
                """INSERT INTO uniform_sales 
                   (date, student_name, student_class, item, size, quantity, selling_price, payment_mode, reference) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (sdate, student_name, student_class, stype, ssize, sqty, sprice, pmode, sref)
            )
            if success:
                st.success("✅ Sale recorded successfully!")
                
                # Update stock quantity
                execute_query(
                    "UPDATE uniform_stock SET quantity = quantity - %s WHERE item = %s AND size = %s",
                    (sqty, stype, ssize)
                )
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
            SELECT date, student_name, student_class, item, size, quantity, selling_price, payment_mode, reference 
            FROM uniform_sales WHERE date BETWEEN %s AND %s
        """
        sales_params = [sales_from, sales_to]
        
        if sales_search:
            sales_query += " AND (student_name ILIKE %s OR reference ILIKE %s)"
            sales_params.extend([f"%{sales_search}%", f"%{sales_search}%"])
            
        if sales_item != "All Items":
            sales_query += " AND item = %s"
            sales_params.append(sales_item)
            
        sales_query += " ORDER BY date DESC"
        
        # Execute sales search
        sales = execute_query(sales_query, sales_params, fetch=True)
        
        if sales:
            sales_df = pd.DataFrame(sales, columns=["Date", "Student", "Class", "Item", "Size", "Quantity", "Price", "Payment", "Reference"])
            sales_df["Total"] = sales_df["Quantity"] * sales_df["Price"]
            st.dataframe(sales_df, use_container_width=True)
            
            # Download buttons for sales results
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(get_download_link(sales_df, "uniform_sales", "📥 Download as CSV"), unsafe_allow_html=True)
            with col2:
                st.markdown(get_excel_download_link(sales_df, "uniform_sales", "📊 Download as Excel"), unsafe_allow_html=True)
        else:
            st.info("No sales match your search criteria.")

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
            FROM expenses WHERE date BETWEEN %s AND %s
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
            SELECT date, item, size, quantity, selling_price, payment_mode, student_name
            FROM uniform_sales WHERE date BETWEEN %s AND %s
            ORDER BY date
        """
        sales_data = execute_query(sales_query, [report_from, report_to], fetch=True)
        
        if sales_data:
            sales_df = pd.DataFrame(sales_data, columns=["Date", "Item", "Size", "Quantity", "Price", "Payment Mode", "Student"])
            sales_df["Total"] = sales_df["Quantity"] * sales_df["Price"]
            
            # Item summary
            item_summary = sales_df.groupby(["Item", "Size"])[["Quantity", "Total"]].sum().reset_index()
            payment_summary = sales_df.groupby("Payment Mode")["Total"].sum().reset_index()
            
            col1, col2 = st.columns([1, 1])
            with col1:
                st.write("#### Sales by Item")
                st.dataframe(item_summary, use_container_width=True)
                st.metric("Total Sales", f"KES {sales_df['Total'].sum():,.2f}")
            with col2:
                st.write("#### Sales by Payment Mode")
                fig = px.bar(payment_summary, x="Payment Mode", y="Total", title="Sales by Payment Method")
                st.plotly_chart(fig, use_container_width=True)
            
            st.write("#### Sales Details")
            st.dataframe(sales_df, use_container_width=True)
            
            # Download buttons for sales report
            sales_download_col1, sales_download_col2 = st.columns(2)
            with sales_download_col1:
                st.markdown(get_download_link(sales_df, f"uniform_sales_{report_from}_to_{report_to}", "📥 Download Sales Report (CSV)"), unsafe_allow_html=True)
            with sales_download_col2:
                st.markdown(get_excel_download_link(sales_df, f"uniform_sales_{report_from}_to_{report_to}", "📊 Download Sales Report (Excel)"), unsafe_allow_html=True)
        else:
            st.info("No sales data found for the selected date range.")
    
    if report_type == "Combined":
        st.write("### 💹 Combined Financial Report")
        
        # If we have both expense and sales data for the period
        if 'expense_df' in locals() and 'sales_df' in locals():
            # Create monthly summary
            if not expense_df.empty and not sales_df.empty:
                expense_df['Month'] = pd.to_datetime(expense_df['Date']).dt.strftime('%b %Y')
                sales_df['Month'] = pd.to_datetime(sales_df['Date']).dt.strftime('%b %Y')
                
                monthly_expenses = expense_df.groupby('Month')['Amount'].sum().reset_index()
                monthly_sales = sales_df.groupby('Month')['Total'].sum().reset_index().rename(columns={'Total': 'Sales'})
                
                # Merge into one dataframe
                monthly_df = pd.merge(monthly_expenses, monthly_sales, on='Month', how='outer').fillna(0)
                monthly_df['Profit'] = monthly_df['Sales'] - monthly_df['Amount']
                
                st.write("#### Monthly Summary")
                st.dataframe(monthly_df, use_container_width=True)
                
                # Create combined chart
                fig = px.line(monthly_df, x='Month', y=['Amount', 'Sales', 'Profit'], 
                              title='Monthly Financial Overview',
                              labels={'value': 'Amount (KES)', 'variable': 'Category'},
                              color_discrete_map={'Amount': 'red', 'Sales': 'green', 'Profit': 'blue'})
                st.plotly_chart(fig, use_container_width=True)
                
                # Download combined report
                st.markdown(get_excel_download_link(monthly_df, f"financial_summary_{report_from}_to_{report_to}", 
                                                  "📊 Download Combined Financial Report"), unsafe_allow_html=True)
            else:
                st.info("Insufficient data for combined report.")
        else:
            st.info("No data available for combined report.")

# --- Tab 5: Dashboard ---
with tabs[4]:
    st.subheader("📊 School Finance Dashboard")
    
    # Get overall statistics
    today = date.today()
    start_of_month = today.replace(day=1)
    start_of_year = today.replace(month=1, day=1)
    
    # Monthly stats
    monthly_expenses = execute_query(
        "SELECT SUM(amount) FROM expenses WHERE date >= %s AND date <= %s",
        [start_of_month, today], fetch=True
    )
    
    monthly_sales = execute_query(
        "SELECT SUM(quantity * selling_price) FROM uniform_sales WHERE date >= %s AND date <= %s",
        [start_of_month, today], fetch=True
    )
    
    # Yearly stats
    yearly_expenses = execute_query(
        "SELECT SUM(amount) FROM expenses WHERE date >= %s AND date <= %s",
        [start_of_year, today], fetch=True
    )
    
    yearly_sales = execute_query(
        "SELECT SUM(quantity * selling_price) FROM uniform_sales WHERE date >= %s AND date <= %s",
        [start_of_year, today], fetch=True
    )
    
    # Display stats
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            "This Month Expenses", 
            f"KES {monthly_expenses[0][0]:,.2f}" if monthly_expenses and monthly_expenses[0][0] else "KES 0.00"
        )
    
    with col2:
        st.metric(
            "This Month Sales", 
            f"KES {monthly_sales[0][0]:,.2f}" if monthly_sales and monthly_sales[0][0] else "KES 0.00"
        )
    
    with col3:
        st.metric(
            "This Year Expenses", 
            f"KES {yearly_expenses[0][0]:,.2f}" if yearly_expenses and yearly_expenses[0][0] else "KES 0.00"
        )
    
    with col4:
        st.metric(
            "This Year Sales", 
            f"KES {yearly_sales[0][0]:,.2f}" if yearly_sales and yearly_sales[0][0] else "KES 0.00"
        )
    
    # Get expense trends
    expense_trend = execute_query("""
        SELECT 
            date_trunc('month', date) as month,
            SUM(amount) as total
        FROM expenses 
        WHERE date >= %s 
        GROUP BY date_trunc('month', date)
        ORDER BY month
    """, [today - timedelta(days=365)], fetch=True)
    
    sales_trend = execute_query("""
        SELECT 
            date_trunc('month', date) as month,
            SUM(quantity * selling_price) as total
        FROM uniform_sales 
        WHERE date >= %s 
        GROUP BY date_trunc('month', date)
        ORDER BY month
    """, [today - timedelta(days=365)], fetch=True)
    
    # Create trend charts
    if expense_trend and sales_trend:
        expense_df = pd.DataFrame(expense_trend, columns=['Month', 'Amount'])
        sales_df = pd.DataFrame(sales_trend, columns=['Month', 'Amount'])
        
        expense_df['Type'] = 'Expenses'
        sales_df['Type'] = 'Sales'
        
        combined_df = pd.concat([expense_df, sales_df])
        combined_df['Month'] = pd.to_datetime(combined_df['Month']).dt.strftime('%b %Y')
        
        # Plot trends
        st.subheader("Annual Trends")
        fig = px.line(combined_df, x='Month', y='Amount', color='Type',
                     title='Financial Trends - Last 12 Months',
                     labels={'Amount': 'Amount (KES)'})
        st.plotly_chart(fig, use_container_width=True)
    
    # Top expenses by category
    top_expenses = execute_query("""
        SELECT category, SUM(amount) as total
        FROM expenses
        WHERE date >= %s
        GROUP BY category
        ORDER BY total DESC
        LIMIT 5
    """, [today - timedelta(days=90)], fetch=True)
    
    # Top uniform items sold
    top_items = execute_query("""
        SELECT item, SUM(quantity) as total_qty, SUM(quantity * selling_price) as total_sales
        FROM uniform_sales
        WHERE date >= %s
        GROUP BY item
        ORDER BY total_sales DESC
        LIMIT 5
    """, [today - timedelta(days=90)], fetch=True)
    
    # Display top items
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Top Expense Categories (Last 90 Days)")
        if top_expenses:
            top_exp_df = pd.DataFrame(top_expenses, columns=['Category', 'Amount'])
            fig = px.bar(top_exp_df, x='Category', y='Amount', title='Top Expense Categories')
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.subheader("Top Uniform Items (Last 90 Days)")
        if top_items:
            top_items_df = pd.DataFrame(top_items, columns=['Item', 'Quantity', 'Sales'])
            fig = px.bar(top_items_df, x='Item', y='Sales', title='Top Uniform Sales')
            st.plotly_chart(fig, use_container_width=True)
    
    # Low stock alert
    low_stock = execute_query("""
        SELECT item, size, quantity 
        FROM uniform_stock
        WHERE quantity <= 5
        ORDER BY quantity ASC
    """, fetch=True)
    
    if low_stock:
        st.warning("⚠️ Low Stock Alert")
        low_stock_df = pd.DataFrame(low_stock, columns=['Item', 'Size', 'Quantity'])
        st.dataframe(low_stock_df, use_container_width=True)
