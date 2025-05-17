import streamlit as st
import streamlit as st

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
        user = st.text_input("Username")
        pwd = st.text_input("Password", type="password")
        if st.button("Login"):
            if user in users and pwd == users[user]:
                st.session_state.logged_in = True
                st.session_state.username = user
                st.experimental_rerun()
            else:
                st.error("Invalid username or password.")
        st.stop()

check_login()
import psycopg2
import traceback
from datetime import date

DB_HOST = "db.qutdtgopillckpvkwovx.supabase.co"
DB_NAME = "postgres"
DB_USER = "postgres"
DB_PASS = "Try2p@c123324305"
DB_PORT = 5432

@st.cache_resource
def get_connection():
    conn = psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        port=DB_PORT
    )
    conn.autocommit = True
    return conn

def execute_query(query, params=None, fetch=False):
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.fetchall() if fetch else True
    except Exception:
        st.error("❌ Database error occurred:")
        st.code(traceback.format_exc())
        return None

st.set_page_config("School Expense Tracker", layout="wide")
st.title("📚 School Expense and Uniform Tracker")

tabs = st.tabs(["Expenses", "Uniform Stock", "Uniform Sales", "Reports"])

# --- Tab 1: Expenses ---
with tabs[0]:
    st.subheader("➕ Add Expense")
    with st.form("expense_form"):
        exp_date = st.date_input("Date", value=date.today())
        category = st.selectbox("Category", ["Stationery", "Food", "Fuel", "Mechanic", "Development", "Other"])
        description = st.text_input("Description")
        amount = st.number_input("Amount (KES)", min_value=0.0, format="%.2f")
        submit = st.form_submit_button("Save Expense")

    if submit and description.strip() and amount > 0:
        success = execute_query(
            "INSERT INTO expenses (date, category, description, amount) VALUES (%s, %s, %s, %s)",
            (exp_date, category, description, amount)
        )
        if success:
            st.success("✅ Expense recorded successfully!")
    elif submit:
        st.warning("Please enter a description and amount.")

    st.divider()
    st.subheader("📅 Recent Expenses")
    expenses = execute_query(
        "SELECT date, category, description, amount FROM expenses ORDER BY date DESC LIMIT 20", fetch=True
    )
    if expenses:
        for row in expenses:
            st.write(f"📅 {row[0]} | 📂 {row[1]} | ✏️ {row[2]} | 💵 KES {row[3]:,.2f}")
    else:
        st.info("No expenses recorded yet.")

# --- Tab 2: Uniform Stock ---
with tabs[1]:
    st.subheader("📦 Add Uniform Stock")
    with st.form("stock_form"):
        item = st.selectbox("Item", ["Sweater", "Tracksuit", "Dress", "Tshirt", "Trousers", "Shirt", "Tie", "Socks"])
        size = st.text_input("Size")
        qty = st.number_input("Quantity", min_value=1, step=1)
        price = st.number_input("Unit Price (KES)", min_value=0.0)
        save_stock = st.form_submit_button("Add to Stock")

    if save_stock and size.strip() and qty > 0 and price > 0:
        success = execute_query(
            "INSERT INTO uniform_stock (item, size, quantity, unit_cost) VALUES (%s, %s, %s, %s)",
            (item, size, qty, price)
        )
        if success:
            st.success("✅ Stock entry added!")
    elif save_stock:
        st.warning("Please complete all fields correctly.")

    st.divider()
    st.subheader("📊 Current Stock")
    stock = execute_query(
        "SELECT item, size, quantity, unit_cost FROM uniform_stock ORDER BY item, size", fetch=True
    )
    if stock:
        for s in stock:
            st.write(f"{s[0]} - Size {s[1]}: Qty {s[2]}, KES {s[3]:,.2f}")
    else:
        st.info("No stock data found.")

# --- Tab 3: Uniform Sales ---
with tabs[2]:
    st.subheader("🛍 Record Uniform Sale")
    with st.form("sales_form"):
        sdate = st.date_input("Date of Sale", value=date.today())
        stype = st.selectbox("Item", ["Sweater", "Tracksuit", "Dress", "Tshirt", "Trousers", "Shirt", "Tie", "Socks"])
        ssize = st.text_input("Size")
        sqty = st.number_input("Quantity", min_value=1, step=1)
        sprice = st.number_input("Selling Price (KES)", min_value=0.0)
        pmode = st.selectbox("Payment Mode", ["Cash", "Sacco Paybill", "Bank", "Other"])
        sref = st.text_input("Payment Reference")
        record_sale = st.form_submit_button("Record Sale")

    if record_sale and ssize.strip() and sqty > 0 and sprice > 0:
        success = execute_query(
            "INSERT INTO uniform_sales (date, item, size, quantity, selling_price, payment_mode, reference) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (sdate, stype, ssize, sqty, sprice, pmode, sref)
        )
        if success:
            st.success("✅ Sale recorded successfully!")
    elif record_sale:
        st.warning("Please fill in all fields correctly.")

    st.divider()
    st.subheader("📋 Recent Sales")
    sales = execute_query(
        "SELECT date, item, size, quantity, selling_price, payment_mode FROM uniform_sales ORDER BY date DESC LIMIT 20",
        fetch=True
    )
    if sales:
        for s in sales:
            total = s[3] * s[4]
            st.write(f"📅 {s[0]} | {s[1]} Size {s[2]} | Qty: {s[3]} | 💵 KES {total:,.2f} via {s[5]}")
    else:
        st.info("No sales data recorded yet.")

# --- Tab 4: Reports ---
with tabs[3]:
    st.subheader("📈 Reports")

    st.write("### 📂 Expense Summary")
    exp_summary = execute_query(
        "SELECT category, SUM(amount) FROM expenses GROUP BY category ORDER BY category", fetch=True
    )
    if exp_summary:
        for row in exp_summary:
            st.write(f"{row[0]}: 💰 KES {row[1]:,.2f}")
    else:
        st.info("No expense summary available.")

    st.write("### 👕 Uniform Sales Summary")
    sales_summary = execute_query(
        "SELECT item, size, SUM(quantity), SUM(quantity * selling_price) FROM uniform_sales GROUP BY item, size ORDER BY item, size",
        fetch=True
    )
    if sales_summary:
        for row in sales_summary:
            st.write(f"{row[0]} Size {row[1]} — Sold: {row[2]} | Total: KES {row[3]:,.2f}")
    else:
        st.info("No sales summary available.")
