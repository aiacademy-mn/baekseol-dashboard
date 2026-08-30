import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import data_loader
import google.generativeai as genai
import os

def safe_float(val, default=0.0):
    if pd.isna(val):
        return default
    s_val = str(val).strip()
    if s_val == "" or s_val == "-" or s_val == "nan" or s_val == "None":
        return default
    clean_val = s_val.replace('₮', '').replace(',', '').replace(' ', '').replace('\xa0', '')
    try:
        return float(clean_val)
    except ValueError:
        return default

# Page config
st.set_page_config(
    page_title="Baekseol Beauty Dashboard",
    page_icon="💅",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Shared CSS for Minimalist Design
st.markdown("""
<style>
    .metric-card {
        background-color: #F8F9FA;
        border: 1px solid #E9ECEF;
        border-radius: 8px;
        padding: 20px;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .metric-label {
        font-size: 14px;
        color: #6C757D;
        font-family: 'DM Sans', sans-serif;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #212529;
        font-family: 'JetBrains Mono', monospace;
        margin-top: 5px;
    }
    .main-title {
        font-family: 'DM Sans', sans-serif;
        font-weight: 700;
        color: #1A1A1A;
    }
</style>
""", unsafe_allow_html=True)

# Password Protection
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
        
    if st.session_state["authenticated"]:
        return True
        
    st.markdown("<h2 class='main-title' style='text-align: center;'>💅 BAEKSEOL BEAUTY</h2>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #666;'>Дашборд системд нэвтрэх нууц үгээ оруулна уу.</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        password = st.text_input("Нууц үг (Password):", type="password", key="login_pass")
        if st.button("Нэвтрэх", use_container_width=True):
            if password == "baekseol2026":
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Нууц үг буруу байна! Дахин оролдоно уу.")
    return False

if check_password():
    # Load Data
    data = data_loader.get_processed_data()
    
    if data is not None:
        sales_df = data["sales"]
        expense_df = data["expenses"]
        service_master = data["service_master"]
        product_master = data["product_master"]
        purchases_df = data["purchases"]
        prod_warehouse = data["product_warehouse"]
        mat_warehouse = data["material_warehouse"]
        course_master = data["course_master"]
        payment_master = data["payment_master"]
        recipe_bom = data["recipe_bom"]
        
        # 1. Function to reconstruct course liabilities as of end_dt
        def get_course_liabilities_as_of(end_dt, course_master, sales_df, service_master):
            service_cost_map = {}
            if not service_master.empty:
                for idx, s_row in service_master.iterrows():
                    name = str(s_row['Үйлчилгээний нэр']).strip()
                    labor = float(s_row['Ажлын хөлс (₮)']) if not pd.isna(s_row['Ажлын хөлс (₮)']) else 0.0
                    material = float(s_row['Материалын өртөг (₮)']) if not pd.isna(s_row['Материалын өртөг (₮)']) else 0.0
                    service_cost_map[name] = labor + material
                    
            if course_master.empty:
                return 0.0, 0.0
                
            sales_after = sales_df[sales_df['date'] > end_dt] if not sales_df.empty else pd.DataFrame()
            total_selling_val = 0.0
            total_cost_val = 0.0
            
            for idx, c_row in course_master.iterrows():
                cust_name = str(c_row['Нэр']).strip() if 'Нэр' in c_row else ""
                phone = str(c_row['Утас']).strip() if 'Утас' in c_row else ""
                service = str(c_row['Үйлчилгээ']).strip() if 'Үйлчилгээ' in c_row else ""
                curr_rem = safe_float(c_row['Үлдсэн оролт']) if 'Үлдсэн оролт' in c_row else 0.0
                unit_price = safe_float(c_row['Нэгж оролтын үнэ']) if 'Нэгж оролтын үнэ' in c_row else 0.0
                
                used_after = 0.0
                purchased_after_sessions = 0.0
                
                if not sales_after.empty:
                    cust_sales = sales_after[
                        (sales_after['customer'].str.contains(cust_name, case=False, na=False)) |
                        (sales_after['customer'] == cust_name)
                    ]
                    cust_service_sales = cust_sales[cust_sales['service_name'] == service]
                    used_after = cust_service_sales['course_sessions_used'].sum()
                    
                    purchases = cust_service_sales[cust_service_sales['service_cash'] >= 300000]
                    for p_idx, p_row in purchases.iterrows():
                        if unit_price > 0:
                            purchased_after_sessions += round(p_row['service_cash'] / unit_price)
                        else:
                            purchased_after_sessions += 5.0
                            
                rem_as_of = curr_rem + used_after - purchased_after_sessions
                rem_as_of = max(0.0, rem_as_of)
                
                selling_debt = rem_as_of * unit_price
                cost = service_cost_map.get(service, 0.0)
                if cost == 0.0:
                    for k, v in service_cost_map.items():
                        if k in service or service in k:
                            cost = v
                            break
                cost_debt = rem_as_of * cost
                
                total_selling_val += selling_debt
                total_cost_val += cost_debt
                
            return total_selling_val, total_cost_val
            
        # 2. Function to rollback product warehouse inventory as of end_dt
        def roll_back_prod_warehouse(end_dt, prod_warehouse, sales_df, purchases_df, product_master):
            if prod_warehouse.empty:
                return prod_warehouse
                
            cost_map = {}
            if not product_master.empty:
                for idx, row in product_master.iterrows():
                    name_clean = str(row['Материалын нэр_clean']).strip() if 'Материалын нэр_clean' in row else str(row['Материалын нэр']).strip()
                    cost_map[name_clean] = safe_float(row['Худалдан авсан үнэ'])
                    
            pw = prod_warehouse.copy()
            sales_after = sales_df[sales_df['date'] > end_dt] if not sales_df.empty else pd.DataFrame()
            purchases_after = purchases_df[purchases_df['Огноо'] > end_dt] if not purchases_df.empty else pd.DataFrame()
            
            sales_sums = {}
            if not sales_after.empty:
                for idx, row in sales_after.iterrows():
                    for p_name, qty in row['product_qtys'].items():
                        sales_sums[p_name] = sales_sums.get(p_name, 0.0) + qty
                        
            purchases_sums = {}
            if not purchases_after.empty:
                purchases_only = purchases_after[purchases_after['Төрөл'].str.contains('Орлого', na=False)]
                for idx, row in purchases_only.iterrows():
                    p_name = str(row['Материалын нэр']).strip()
                    qty = safe_float(row['Тоо хэмжээ'])
                    purchases_sums[p_name] = purchases_sums.get(p_name, 0.0) + qty
                    
            recalc_rows = []
            for idx, row in pw.iterrows():
                name = str(row['Материалын нэр']).strip()
                curr_stock = safe_float(row['Одоогийн үлдэгдэл'])
                
                unit_cost = cost_map.get(name, 0.0)
                if unit_cost == 0.0:
                    for k, v in cost_map.items():
                        if k in name or name in k:
                            unit_cost = v
                            break
                if unit_cost == 0.0:
                    tot_val = safe_float(row['Нийт хөрөнгийн дүн'])
                    if curr_stock > 0:
                        unit_cost = tot_val / curr_stock
                
                sold_after = sales_sums.get(name, 0.0)
                if sold_after == 0.0:
                    for k, v in sales_sums.items():
                        if k in name or name in k:
                            sold_after = v
                            break
                            
                bought_after = purchases_sums.get(name, 0.0)
                if bought_after == 0.0:
                    for k, v in purchases_sums.items():
                        if k in name or name in k:
                            bought_after = v
                            break
                            
                stock_as_of = max(0.0, curr_stock + sold_after - bought_after)
                row['Одоогийн үлдэгдэл'] = stock_as_of
                row['Нийт хөрөнгийн дүн'] = stock_as_of * unit_cost
                recalc_rows.append(row)
            return pd.DataFrame(recalc_rows)
            
        # 3. Function to rollback material warehouse inventory as of end_dt
        def roll_back_mat_warehouse(end_dt, mat_warehouse, sales_df, purchases_df, bom_df):
            if mat_warehouse.empty:
                return mat_warehouse
            mw = mat_warehouse.copy()
            sales_after = sales_df[sales_df['date'] > end_dt] if not sales_df.empty else pd.DataFrame()
            purchases_after = purchases_df[purchases_df['Огноо'] > end_dt] if not purchases_df.empty else pd.DataFrame()
            
            mat_used_sums = {}
            if not sales_after.empty and not bom_df.empty:
                for idx, row in sales_after.iterrows():
                    srv = row['service_name']
                    if srv != "":
                        recipe = bom_df[bom_df['Үйлчилгээний нэр'] == srv]
                        if recipe.empty:
                            for k in bom_df['Үйлчилгээний нэр'].unique():
                                if k in srv or srv in k:
                                    recipe = bom_df[bom_df['Үйлчилгээний нэр'] == k]
                                    break
                        for r_idx, r_row in recipe.iterrows():
                            m_name = str(r_row['Материалын нэр']).strip()
                            qty = safe_float(r_row['Орц хэмжээ'])
                            mat_used_sums[m_name] = mat_used_sums.get(m_name, 0.0) + qty
                            
            mat_bought_sums = {}
            if not purchases_after.empty:
                purchases_only = purchases_after[purchases_after['Төрөл'].str.contains('Орлого', na=False)]
                for idx, row in purchases_only.iterrows():
                    name = str(row['Материалын нэр']).strip()
                    qty = safe_float(row['Тоо хэмжээ'])
                    mat_bought_sums[name] = mat_bought_sums.get(name, 0.0) + qty
                    
            recalc_rows = []
            for idx, row in mw.iterrows():
                name = str(row['Материалын нэр']).strip()
                curr_stock = safe_float(row['Одоогийн үлдэгдэл'])
                
                used_after = mat_used_sums.get(name, 0.0)
                if used_after == 0.0:
                    for k, v in mat_used_sums.items():
                        if k in name or name in k:
                            used_after = v
                            break
                            
                bought_after = mat_bought_sums.get(name, 0.0)
                if bought_after == 0.0:
                    for k, v in mat_bought_sums.items():
                        if k in name or name in k:
                            bought_after = v
                            break
                            
                stock_as_of = max(0.0, curr_stock + used_after - bought_after)
                row['Одоогийн үлдэгдэл'] = stock_as_of
                recalc_rows.append(row)
            return pd.DataFrame(recalc_rows)
        
        # Sidebar Controls
        st.sidebar.markdown("### ⚙️ Сонголтууд")
        
        # Refresh Data
        if st.sidebar.button("🔄 Мэдээлэл шинэчлэх", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
            
        st.sidebar.markdown("---")
        
        # Date Picker Setup
        min_date = sales_df['date'].min() if not sales_df.empty else pd.Timestamp('2026-08-01')
        max_date = sales_df['date'].max() if not sales_df.empty else pd.Timestamp('2026-08-31')
        
        st.sidebar.markdown("### 📅 Хугацааны шүүлтүүр")
        period_type = st.sidebar.selectbox(
            "Шүүх ангилал:",
            ["Сараар", "Өдрөөр", "Улирлаар", "Жилээр", "Хувийн тохиргоо"],
            index=0
        )
        
        years = sorted(list(sales_df['date'].dt.year.unique())) if not sales_df.empty else [2026]
        
        if period_type == "Жилээр":
            sel_year = st.sidebar.selectbox("Жил сонгох:", years)
            start_dt = pd.Timestamp(sel_year, 1, 1)
            end_dt = pd.Timestamp(sel_year, 12, 31)
        elif period_type == "Улирлаар":
            sel_year = st.sidebar.selectbox("Жил сонгох:", years)
            sel_quarter = st.sidebar.selectbox("Улирал сонгох:", ["1-р улирал (Q1)", "2-р улирал (Q2)", "3-р улирал (Q3)", "4-р улирал (Q4)"])
            if "Q1" in sel_quarter:
                start_dt = pd.Timestamp(sel_year, 1, 1)
                end_dt = pd.Timestamp(sel_year, 3, 31)
            elif "Q2" in sel_quarter:
                start_dt = pd.Timestamp(sel_year, 4, 1)
                end_dt = pd.Timestamp(sel_year, 6, 30)
            elif "Q3" in sel_quarter:
                start_dt = pd.Timestamp(sel_year, 7, 1)
                end_dt = pd.Timestamp(sel_year, 9, 30)
            else:
                start_dt = pd.Timestamp(sel_year, 10, 1)
                end_dt = pd.Timestamp(sel_year, 12, 31)
        elif period_type == "Сараар":
            sel_year = st.sidebar.selectbox("Жил сонгох:", years)
            sel_month = st.sidebar.selectbox(
                "Сар сонгох:",
                [f"{i}-р сар" for i in range(1, 13)],
                index=max_date.month - 1 if not sales_df.empty else 7
            )
            m_num = int(sel_month.split("-")[0])
            start_dt = pd.Timestamp(sel_year, m_num, 1)
            end_dt = start_dt + pd.offsets.MonthEnd(0)
        elif period_type == "Өдрөөр":
            sel_day = st.sidebar.date_input("Өдөр сонгох:", value=max_date.date(), min_value=min_date.date(), max_value=max_date.date())
            start_dt = pd.to_datetime(sel_day)
            end_dt = pd.to_datetime(sel_day)
        else:
            # Custom range
            custom_range = st.sidebar.date_input(
                "Хугацааны муж:",
                value=(pd.Timestamp(max_date.year, max_date.month, 1).date(), max_date.date()),
                min_value=min_date.date(),
                max_value=max_date.date()
            )
            if isinstance(custom_range, tuple) and len(custom_range) == 2:
                start_dt = pd.to_datetime(custom_range[0])
                end_dt = pd.to_datetime(custom_range[1])
            else:
                start_dt = pd.Timestamp(max_date.year, max_date.month, 1)
                end_dt = max_date
            
        # Filter Data
        filtered_sales = sales_df[(sales_df['date'] >= start_dt) & (sales_df['date'] <= end_dt)]
        filtered_expenses = expense_df[(expense_df['Огноо'] >= start_dt) & (expense_df['Огноо'] <= end_dt)]
        
        # Roll back warehouses dynamically to end_dt
        rolled_prod_warehouse = roll_back_prod_warehouse(end_dt, prod_warehouse, sales_df, purchases_df, product_master)
        rolled_mat_warehouse = roll_back_mat_warehouse(end_dt, mat_warehouse, sales_df, purchases_df, recipe_bom)
        
        # Build unit cost mapping for products
        product_cost_map = {}
        for idx, row in product_master.iterrows():
            name = row['Материалын нэр_clean']
            product_cost_map[name] = safe_float(row['Худалдан авах өртөг үнэ']) if 'Худалдан авах өртөг үнэ' in row else safe_float(row.get('Худалдан авсан үнэ', 0.0))

        # Title Block
        st.markdown(f"<h1 class='main-title'>💅 BAEKSEOL BEAUTY Дашборд</h1>", unsafe_allow_html=True)
        st.markdown(f"**Хугацаа:** `{start_dt.strftime('%Y-%m-%d')}` -оос `{end_dt.strftime('%Y-%m-%d')}` хүртэл", unsafe_allow_html=True)
        st.markdown("---")
        
        # Configure Gemini
        default_key = st.secrets.get("GEMINI_API_KEY", "")
        has_ai = False
        
        if default_key:
            # Key is already configured in secrets, hide UI to keep sidebar clean
            try:
                genai.configure(api_key=default_key.strip())
                has_ai = True
            except Exception as e:
                st.sidebar.error(f"Хадгалагдсан API Key алдаатай байна: {e}")
        else:
            # Key is not in secrets, show config UI
            st.sidebar.markdown("---")
            st.sidebar.markdown("### 🤖 AI Туслахын тохиргоо")
            st.sidebar.markdown("[Энд дарж](https://aistudio.google.com/) үнэгүй Gemini API Key авна уу.")
            gemini_api_key = st.sidebar.text_input("Gemini API Key:", type="password", help="AI-тай чатлах болон тайлан автоматаар тайлбарлуулахад ашиглагдана.")
            if gemini_api_key.strip():
                try:
                    genai.configure(api_key=gemini_api_key.strip())
                    has_ai = True
                except Exception as e:
                    st.sidebar.error(f"API Key алдаатай байна: {e}")
        
        # CALCULATIONS
        # 1. Revenue
        total_cash_rev = filtered_sales['grand_total'].sum()
        total_accrual_rev = filtered_sales['recognized_service_rev'].sum() + filtered_sales['product_cash'].sum()
        service_cash_rev_period = filtered_sales['service_cash'].sum() if not filtered_sales.empty else 0.0
        product_cash_rev_period = filtered_sales['product_cash'].sum() if not filtered_sales.empty else 0.0
        service_accrual_rev_period = filtered_sales['recognized_service_rev'].sum() if not filtered_sales.empty else 0.0
        
        # 2. Wage and Materials Cost from Services
        total_labor_cost = filtered_sales['service_labor'].sum()
        total_materials_cost = filtered_sales['service_material'].sum()
        
        # 3. Product Cost of Goods Sold (COGS)
        total_product_cogs = 0.0
        for idx, row in filtered_sales.iterrows():
            for p_name, qty in row['product_qtys'].items():
                unit_cost = product_cost_map.get(p_name, 0.0)
                total_product_cogs += qty * unit_cost
                
        # 4. Operating Expenses (OpEx)
        # Exclude "Бараа материал" to prevent double counting with product COGS,
        # and exclude "Дотоод шилжүүлэг" / "Дотоод гүйлгээ" to ignore cash-to-bank or account transfers.
        operating_expenses_df = filtered_expenses[
            ~filtered_expenses['Үндсэн ангилал'].isin(['Бараа материал', 'Дотоод шилжүүлэг', 'Дотоод гүйлгээ'])
        ]
        total_opex = operating_expenses_df['Мөнгөн дүн'].sum()
        total_cash_expenses = filtered_expenses[
            ~filtered_expenses['Үндсэн ангилал'].isin(['Дотоод шилжүүлэг', 'Дотоод гүйлгээ'])
        ]['Мөнгөн дүн'].sum()
        
        # Calculate Total Accrual Expenses:
        # Salaries in total_opex (from ЗАРЛАГЫН_БҮРТГЭЛ) already include base and bonus commissions.
        # Therefore, we do NOT add the service-calculated total_labor_cost here to prevent double counting.
        total_accrual_expenses = total_materials_cost + total_product_cogs + total_opex
        accrual_net_profit = total_accrual_rev - total_accrual_expenses
        
        # Calculate new prepayments received via QPay (Column E) in PAYMENT_MASTER for the selected period
        new_prepays_received_period = 0.0
        if not payment_master.empty:
            pm_df = payment_master.copy()
            pm_df['Огноо'] = pd.to_datetime(pm_df['Огноо'], errors='coerce')
            pm_filtered = pm_df[(pm_df['Огноо'] >= start_dt) & (pm_df['Огноо'] <= end_dt)]
            new_prepays_received_period = pm_filtered['Орсон мөнгө'].sum()
            
        # Commissions and Actual Payments Received
        total_commissions = 0.0
        barter_amt = 0.0
        for idx, row in filtered_sales.iterrows():
            pos_company = row['payments'].get("POS — Компани", 0.0) + row['payments'].get("POS - Компани", 0.0)
            pos_unda = row['payments'].get("POS — Ундармаа", 0.0) + row['payments'].get("POS - Ундармаа", 0.0)
            qpay = row['payments'].get("QPay", 0.0)
            pocket = row['payments'].get("Pocket", 0.0)
            omni = row['payments'].get("Omni", 0.0)
            total_commissions += (pos_company + pos_unda + qpay) * 0.01 + pocket * 0.065 + omni * 0.06
            barter_amt += row['payments'].get("Бартер", 0.0)
            
        total_prepays_used_period = filtered_sales['hourly_prepay_used'].sum() + filtered_sales['course_prepay_used'].sum() if not filtered_sales.empty else 0.0
        total_customer_debt = filtered_sales['customer_debt'].sum() if not filtered_sales.empty else 0.0
        
        # Calculate actual cash payments total (ТӨЛБӨРИЙН НИЙТ / НИЙТ ОРСОН ОРЛОГО)
        sheet_total_payments = total_cash_rev - total_prepays_used_period + new_prepays_received_period - barter_amt - total_customer_debt
        
        # Cash-basis net profit matching Google Sheet's "ЦЭВЭР АШИГ" exactly
        cash_profit = total_cash_rev - total_prepays_used_period - total_customer_debt - total_cash_expenses - total_commissions
        
        cash_flow_net = sheet_total_payments - total_cash_expenses - total_commissions
        
        # Calculate total outstanding supplier credit debt (Барааны зээлийн өр) from БАРАА_БҮРТГЭЛ
        total_unpaid_debt = 0.0
        if not purchases_df.empty:
            status_col = None
            for c in purchases_df.columns:
                if any(x in str(c).lower() for x in ['төлөв', 'тайлбар', 'status', 'төлөв']):
                    status_col = c
                    break
            cost_col = None
            for c in purchases_df.columns:
                if any(x in str(c).lower() for x in ['үнэ', 'дүн', 'өртөг', 'үнэ']):
                    cost_col = c
                    break
            if cost_col is None and len(purchases_df.columns) > 5:
                cost_col = purchases_df.columns[5]
                
            if status_col is not None and cost_col is not None:
                unpaid_rows = purchases_df[
                    purchases_df[status_col].astype(str).str.contains('Төлөгдөөгүй', case=False, na=False) |
                    purchases_df[status_col].astype(str).str.contains('Зээл', case=False, na=False)
                ]
                for idx, row in unpaid_rows.iterrows():
                    total_unpaid_debt += safe_float(row[cost_col])
        
        # Calculate Cost Value of Course Liability
        service_cost_map = {}
        if not service_master.empty:
            for idx, s_row in service_master.iterrows():
                name = str(s_row['Үйлчилгээний нэр']).strip()
                labor = float(s_row['Ажлын хөлс (₮)']) if not pd.isna(s_row['Ажлын хөлс (₮)']) else 0.0
                material = float(s_row['Материалын өртөг (₮)']) if not pd.isna(s_row['Материалын өртөг (₮)']) else 0.0
                service_cost_map[name] = labor + material
                
        total_course_cost_liability = 0.0
        if not course_master.empty:
            for idx, c_row in course_master.iterrows():
                srv = str(c_row['Үйлчилгээ']).strip()
                rem_sessions = float(c_row['Үлдсэн оролт']) if not pd.isna(c_row['Үлдсэн оролт']) else 0.0
                cost = service_cost_map.get(srv, None)
                if cost is None:
                    for k, v in service_cost_map.items():
                        if k in srv or srv in k:
                            cost = v
                            break
                if cost is not None:
                    total_course_cost_liability += rem_sessions * cost
                    

        
        # Generate context for AI
        def get_current_data_summary():
            # Build summary tables
            # Service counts
            service_counts = filtered_sales[filtered_sales['service_name'] != ""].groupby('service_name').agg(
                count=('service_name', 'count'),
                cash_rev=('service_cash', 'sum'),
                accrual_rev=('recognized_service_rev', 'sum'),
                labor_cost=('service_labor', 'sum'),
                material_cost=('service_material', 'sum')
            ).reset_index()
            
            prod_sold_sums = {}
            for idx, r_row in filtered_sales.iterrows():
                for p_name, qty in r_row['product_qtys'].items():
                    prod_sold_sums[p_name] = prod_sold_sums.get(p_name, 0.0) + qty
            
            summary_str = f"""
Хугацаа: {start_dt.strftime('%Y-%m-%d')} -оос {end_dt.strftime('%Y-%m-%d')} хүртэл
---
1. Нэгдсэн тоонууд:
   - Хэрэгжсэн Бодит Орлого: {total_accrual_rev:,.0f} MNT
   - Хэрэгжсэн Бодит Цэвэр Ашиг (P&L): {accrual_net_profit:,.0f} MNT
   - Бэлэн Мөнгөний Орлого: {total_cash_rev:,.0f} MNT
   - Цэвэр Мөнгөн Урсгал (Кассны үлдэгдэл зөрүү): {cash_flow_net:,.0f} MNT
   - Нийт үйлчилгээний ажлын хөлс бонус (тооцоолсон): {total_labor_cost:,.0f} MNT
   - Нийт үйлчилгээний материалын өртөг (BOM): {total_materials_cost:,.0f} MNT
   - Нийт зарагдсан бүтээгдэхүүний өртөг (COGS): {total_product_cogs:,.0f} MNT
   - Үйл ажиллагааны зардлууд (байр, цалин, маркетинг гэх мэт): {total_opex:,.0f} MNT
   - Гарсан шимтгэл хураамж: {total_commissions:,.0f} MNT

2. Үйлчилгээний жагсаалт:
{service_counts.to_string(index=False) if not service_counts.empty else "Байхгүй"}

3. Зарагдсан бүтээгдэхүүнүүд:
{str(prod_sold_sums) if prod_sold_sums else "Байхгүй"}

4. Зардлын дэлгэрэнгүй жагсаалт:
{filtered_expenses[['Огноо', 'Үндсэн ангилал', 'Зарлагын нэр (Дэд ангилал)', 'Мөнгөн дүн', 'Тайлбар']].to_string(index=False) if not filtered_expenses.empty else "Байхгүй"}

5. Агуулахын бүтээгдэхүүний үлдэгдэл:
{rolled_prod_warehouse[['Материалын код', 'Материалын нэр', 'Одоогийн үлдэгдэл', 'Нийт хөрөнгийн дүн']].to_string(index=False) if not rolled_prod_warehouse.empty else "Байхгүй"}
"""
            return summary_str

        # Multi-tab layout
        tab_summary, tab_services, tab_products, tab_inventory, tab_expenses, tab_ai = st.tabs([
            "📊 Ерөнхий тойм", "💇 Үйлчилгээний шинжилгээ", "📦 Бүтээгдэхүүний борлуулалт", 
            "🏢 Агуулах & Өр төлбөр", "💸 Зардлын шинжилгээ", "🤖 AI Туслах"
        ])
        
        # TAB 1: EXECUTIVE SUMMARY
        with tab_summary:
            st.markdown("### 🎯 Борлуулалтын зорилтот KPIs (Төлөвлөгөө ба Биелэлт)")
            
            # Actual values for targets
            act_total_rev = total_cash_rev + new_prepays_received_period
            act_service_rev = filtered_sales['service_cash'].sum() if not filtered_sales.empty else 0.0
            act_product_rev = filtered_sales['product_cash'].sum() if not filtered_sales.empty else 0.0
            
            # Clean asset value
            asset_val_clean = 0.0
            if not rolled_prod_warehouse.empty and 'Нийт хөрөнгийн дүн' in rolled_prod_warehouse.columns:
                asset_val_clean = pd.to_numeric(rolled_prod_warehouse['Нийт хөрөнгийн дүн'], errors='coerce').fillna(0.0).sum()
                
            # Build target dataset
            targets_data = [
                {"Үзүүлэлт": "Нийт Орлого (Cash)", "Зорилт": 150000000, "Гүйцэтгэл": act_total_rev},
                {"Үзүүлэлт": "Үйлчилгээний Орлого", "Зорилт": 80000000, "Гүйцэтгэл": act_service_rev},
                {"Үзүүлэлт": "Бүтээгдэхүүний Орлого", "Зорилт": 70000000, "Гүйцэтгэл": act_product_rev}
            ]
            
            targets_df = pd.DataFrame(targets_data)
            targets_df["Биелэлт %"] = (targets_df["Гүйцэтгэл"] / targets_df["Зорилт"] * 100).fillna(0.0)
            targets_df["Дутуу дүн"] = (targets_df["Зорилт"] - targets_df["Гүйцэтгэл"]).apply(lambda x: max(0.0, x))
            
            # Formatting
            disp_targets = targets_df.copy()
            for col in ["Зорилт", "Гүйцэтгэл", "Дутуу дүн"]:
                disp_targets[col] = disp_targets[col].map('{:,.0f} ₮'.format)
            disp_targets["Биелэлт %"] = disp_targets["Биелэлт %"].map('{:.2f}%'.format)
            
            # Display target table
            st.dataframe(disp_targets, use_container_width=True, hide_index=True)
            st.info(f"🏢 **Агуулахын нийт бүтээгдэхүүний хөрөнгө:** `{asset_val_clean:,.0f} ₮`")
            st.markdown("<br>", unsafe_allow_html=True)
            
            st.subheader("🔥 Гол үзүүлэлтүүд (KPIs)")
            report_basis = st.radio(
                "📊 Тайлан харуулах суурь сонгох:",
                ["Кассын сууриар (Google Sheet-тэй 100% тулгах горим)", "Аккруэл сууриар (Салоны бодит ашиг тооцох горим)"],
                index=0,
                horizontal=True
            )
            st.markdown("<br>", unsafe_allow_html=True)
            
            col1, col2, col3, col4, col5 = st.columns(5)
            
            if report_basis == "Кассын сууриар (Google Sheet-тэй 100% тулгах горим)":
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">💰 Нийт Борлуулалтын Орлого</div>
                        <div class="metric-value">{total_cash_rev:,.0f} ₮</div>
                        <div style="font-size:11px; color:#666; margin-top:5px;">(Google Sheet B5 нүдний дүн)</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">💸 Нийт Зарлага (Ledger)</div>
                        <div class="metric-value" style="color: #C0392B;">{total_cash_expenses:,.0f} ₮</div>
                        <div style="font-size:11px; color:#666; margin-top:5px;">(Зарлагын бүртгэлийн бодит гаралт)</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col3:
                    color = "green" if cash_profit >= 0 else "red"
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">📈 Кассын Цэвэр Ашиг</div>
                        <div class="metric-value" style="color: {color}; font-weight: bold;">{cash_profit:,.0f} ₮</div>
                        <div style="font-size:11px; color:#666; margin-top:5px;">(Борлуулалт - Өр - Шимтгэл - Зардал)</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col4:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">📥 Нийт Цэвэр Орлого</div>
                        <div class="metric-value">{sheet_total_payments:,.0f} ₮</div>
                        <div style="font-size:11px; color:#27AE60; margin-top:5px;">(Бартер хасагдсан цэвэр дүн)</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col5:
                    cf_color = "green" if cash_flow_net >= 0 else "red"
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">💵 Цэвэр Мөнгөн Урсгал</div>
                        <div class="metric-value" style="color: {cf_color};">{cash_flow_net:,.0f} ₮</div>
                        <div style="font-size:11px; color:#666; margin-top:5px;">(Орсон мөнгө - Зарлага - Шимтгэл)</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                with col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">📈 Хэрэгжсэн Бодит Орлого</div>
                        <div class="metric-value">{total_accrual_rev:,.0f} ₮</div>
                        <div style="font-size:11px; color:green; margin-top:5px;">(Үзүүлсэн үйлчилгээ + бараа)</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">💸 Нийт Зарлага (Expenses)</div>
                        <div class="metric-value" style="color: #C0392B;">{total_accrual_expenses:,.0f} ₮</div>
                        <div style="font-size:11px; color:#666; margin-top:5px;">(Өртөг + Үйл ажиллагааны зардал)</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col3:
                    color = "green" if accrual_net_profit >= 0 else "red"
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">📊 Хэрэгжсэн Бодит Цэвэр Ашиг</div>
                        <div class="metric-value" style="color: {color}; font-weight: bold;">{accrual_net_profit:,.0f} ₮</div>
                        <div style="font-size:11px; color:#666; margin-top:5px;">(Бодит Орлого - Нийт Зарлага)</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col4:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">💰 Бэлэн Мөнгөний Орлого</div>
                        <div class="metric-value">{total_cash_rev:,.0f} ₮</div>
                        <div style="font-size:11px; color:#666; margin-top:5px;">(Касс болон дансанд орсон дүн)</div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with col5:
                    cf_color = "green" if cash_flow_net >= 0 else "red"
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-label">💵 Цэвэр Мөнгөн Урсгал</div>
                        <div class="metric-value" style="color: {cf_color};">{cash_flow_net:,.0f} ₮</div>
                        <div style="font-size:11px; color:#666; margin-top:5px;">(Орсон мөнгө - Зарлага - Шимтгэл)</div>
                    </div>
                    """, unsafe_allow_html=True)
            # Product and Service Revenue split
            st.markdown("<br>", unsafe_allow_html=True)
            col_split1, col_split2 = st.columns(2)
            
            if report_basis == "Кассын сууриар (Google Sheet-тэй 100% тулгах горим)":
                with col_split1:
                    st.markdown(f"""
                    <div style="background-color: #F8F9FA; padding: 12px; border-radius: 6px; border: 1px solid #E9ECEF; text-align: center; font-family: 'DM Sans', sans-serif;">
                        <div style="font-size: 13px; color: #7F8C8D; font-weight: 500;">💇 Үйлчилгээний Кассын Орлого</div>
                        <div style="font-size: 20px; font-weight: bold; color: #16A085; margin-top: 5px;">{service_cash_rev_period:,.0f} ₮</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_split2:
                    st.markdown(f"""
                    <div style="background-color: #F8F9FA; padding: 12px; border-radius: 6px; border: 1px solid #E9ECEF; text-align: center; font-family: 'DM Sans', sans-serif;">
                        <div style="font-size: 13px; color: #7F8C8D; font-weight: 500;">📦 Бүтээгдэхүүний Кассын Орлого</div>
                        <div style="font-size: 20px; font-weight: bold; color: #2980B9; margin-top: 5px;">{product_cash_rev_period:,.0f} ₮</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                with col_split1:
                    st.markdown(f"""
                    <div style="background-color: #F8F9FA; padding: 12px; border-radius: 6px; border: 1px solid #E9ECEF; text-align: center; font-family: 'DM Sans', sans-serif;">
                        <div style="font-size: 13px; color: #7F8C8D; font-weight: 500;">💇 Хэрэгжсэн Үйлчилгээний Орлого (Accrual)</div>
                        <div style="font-size: 20px; font-weight: bold; color: #16A085; margin-top: 5px;">{service_accrual_rev_period:,.0f} ₮</div>
                    </div>
                    """, unsafe_allow_html=True)
                with col_split2:
                    st.markdown(f"""
                    <div style="background-color: #F8F9FA; padding: 12px; border-radius: 6px; border: 1px solid #E9ECEF; text-align: center; font-family: 'DM Sans', sans-serif;">
                        <div style="font-size: 13px; color: #7F8C8D; font-weight: 500;">📦 Хэрэгжсэн Бүтээгдэхүүний Орлого (Accrual)</div>
                        <div style="font-size: 20px; font-weight: bold; color: #2980B9; margin-top: 5px;">{product_cash_rev_period:,.0f} ₮</div>
                    </div>
                    """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Calculate Liabilities rolled back to end_dt!
            total_course_liability, total_course_cost_liability = get_course_liabilities_as_of(end_dt, course_master, sales_df, service_master)
            
            st.markdown("### 🏦 Урьдчилгаа ба Багц Үйлчилгээний Өр төлбөр (Deferred Revenue)")
            col_l1, col_l2, col_l3 = st.columns(3)
            with col_l1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">⏳ Эргэн Төлөх Үлдэгдэл Курс</div>
                    <div class="metric-value" style="color: #E28743;">{total_course_liability:,.0f} ₮</div>
                    <div style="font-size:11px; color:#666; margin-top:5px;">(Үлдэгдэл курсуудын борлуулах үнээрх дүн)</div>
                </div>
                """, unsafe_allow_html=True)
            with col_l2:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">📊 Өр Төлөх Бодит Өртөг</div>
                    <div class="metric-value" style="color: #C0392B; font-weight: bold;">{total_course_cost_liability:,.0f} ₮</div>
                    <div style="font-size:11px; color:#666; margin-top:5px;">(Үлдэгдэл курсыг үзүүлэх бодит өртөг/зардал)</div>
                </div>
                """, unsafe_allow_html=True)
            with col_l3:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">📥 Орсон Шинэ Урьдчилгаа</div>
                    <div class="metric-value" style="color: #27AE60; font-weight: bold;">{new_prepays_received_period:,.0f} ₮</div>
                    <div style="font-size:11px; color:#27AE60; margin-top:5px;">(Сонгосон хугацаанд вэбээр орсон дүн)</div>
                </div>
                """, unsafe_allow_html=True)
                
            st.markdown(f"""
            <div style="background-color: #FFF3CD; color: #856404; padding: 12px; border-radius: 5px; font-size: 13px; border: 1px solid #FFEBAA; margin-top: 15px; margin-bottom: 15px;">
                ⚠️ <b>Зохистой нөөцийн санамж:</b> Салоны үлдсэн курсыг үзүүлэхэд шаардлагатай бодит өртөг болох <b>{total_course_cost_liability:,.0f} ₮</b>-ийг дансандаа заавал <b>хуримтлал/нөөц</b> болгон үлдээхийг зөвлөж байна. Хэрэв урьдчилж орсон мөнгөнүүдийг орлого гэж андууран үрвэл ирээдүйд цалин ба материалын өртөг төлөх мөнгөгүйдэж, төлбөрийн чадваргүй болох эрсдэлтэй.
            </div>
            """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Cash Flow Details Table
            st.markdown("### 💵 Мөнгөний Бодит Урсгал (Төлбөрийн хэлбэр ба Шимтгэлүүд)")
            payment_sums = {}
            for idx, row in filtered_sales.iterrows():
                for pay_type, val in row['payments'].items():
                    payment_sums[pay_type] = payment_sums.get(pay_type, 0.0) + val
                    
            # Add prepayment received to cash flow table
            payment_sums["Урьдчилж орсон орлого (Prepayment Received)"] = new_prepays_received_period
            
            commission_rates = {
                "Данс — Компани": 0.0,
                "Данс — Ундармаа": 0.0,
                "POS — Компани": 0.01,
                "POS — Ундармаа": 0.01,
                "QPay": 0.01,
                "Бэлэн": 0.0,
                "Pocket": 0.065,
                "Omni": 0.06,
                "Бартер": 0.0,
                "Урьдчилж орсон орлого (Prepayment Received)": 0.0
            }
            
            cf_rows = []
            total_cf_amt = 0.0
            total_cf_comm = 0.0
            total_cf_net = 0.0
            
            for pay_type, rate in commission_rates.items():
                # support both formats of key lookup
                alt_pay_type = pay_type.replace("—", "-")
                amt = payment_sums.get(pay_type, 0.0)
                if alt_pay_type != pay_type:
                    amt += payment_sums.get(alt_pay_type, 0.0)
                comm = amt * rate
                net = amt - comm
                
                total_cf_amt += amt
                total_cf_comm += comm
                total_cf_net += net
                
                cf_rows.append({
                    "Төлбөрийн хэлбэр": pay_type,
                    "Нийт төлбөр": amt,
                    "Шимтгэл %": f"{rate*100:.1f}%" if rate > 0 else "0%",
                    "Хасагдах шимтгэл": comm,
                    "Цэвэр авах дүн": net,
                    "Мөнгөн төлөв": "🟢 Зардалгүй" if rate == 0 else ("🟡 1% Шимтгэл" if rate <= 0.01 else "🔴 Өндөр шимтгэл")
                })
                
            cf_df = pd.DataFrame(cf_rows)
            disp_cf = cf_df.copy()
            for col in ["Нийт төлбөр", "Хасагдах шимтгэл", "Цэвэр авах дүн"]:
                disp_cf[col] = disp_cf[col].map('{:,.0f} ₮'.format)
                
            # Add TOTAL row
            disp_cf.loc[len(disp_cf)] = [
                "🔥 ТӨЛБӨРИЙН НИЙТ (Касс+Дансны орсон дүн)", 
                f"{total_cf_amt:,.0f} ₮", 
                "-", 
                f"{total_cf_comm:,.0f} ₮", 
                f"{total_cf_net:,.0f} ₮",
                "📈"
            ]
            
            st.dataframe(disp_cf, use_container_width=True, hide_index=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 1. Bank Transfer Helper Block
            st.markdown("### 🏦 Дансны шилжүүлгийн тооцоолуур")
            
            tot_service_cash = filtered_sales['service_cash'].sum() if not filtered_sales.empty else 0.0
            tot_product_cash = filtered_sales['product_cash'].sum() if not filtered_sales.empty else 0.0
            tot_cash_sales = 0.0
            if not filtered_sales.empty:
                for idx, row in filtered_sales.iterrows():
                    tot_cash_sales += row['payments'].get("Бэлэн", 0.0)
                    
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                st.markdown(f"""
                <div class="metric-card" style="border-left: 5px solid #27AE60;">
                    <div class="metric-label">💵 Компани данс руу тушаах бэлэн мөнгө</div>
                    <div class="metric-value" style="color: #27AE60; font-size: 20px;">{tot_cash_sales:,.0f} ₮</div>
                    <div style="font-size:11px; color:#666; margin-top:5px;">(Кассаас MN92 0005 00 5175343431 руу тушаах)</div>
                </div>
                """, unsafe_allow_html=True)
                
            with col_b2:
                st.markdown(f"""
                <div class="metric-card" style="border-left: 5px solid #2980B9;">
                    <div class="metric-label">💇 Үйлчилгээний данс руу шилжүүлэх</div>
                    <div class="metric-value" style="color: #2980B9; font-size: 20px;">{tot_service_cash:,.0f} ₮</div>
                    <div style="font-size:11px; color:#666; margin-top:5px;">(Үндсэн данснаас MN66 0005 00 5079172279 руу)</div>
                </div>
                """, unsafe_allow_html=True)
                
            with col_b3:
                st.markdown(f"""
                <div class="metric-card" style="border-left: 5px solid #8E44AD;">
                    <div class="metric-label">📦 Бүтээгдэхүүний данс руу шилжүүлэх</div>
                    <div class="metric-value" style="color: #8E44AD; font-size: 20px;">{tot_product_cash:,.0f} ₮</div>
                    <div style="font-size:11px; color:#666; margin-top:5px;">(Үндсэн данснаас MN46 0005 00 5175433596 руу)</div>
                </div>
                """, unsafe_allow_html=True)
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 2. Sales vs Payments Reconciliation Block (Downward step-by-step layout)
            st.markdown("### 🔄 Борлуулалтаас Касс/Дансанд орсон мөнгөний тохируулга")
            sales_plus_prepayment = total_cash_rev + new_prepays_received_period
            
            st.markdown(f"""
            <div style="background-color: #F8F9FA; padding: 15px; border-radius: 8px; border: 1px solid #E9ECEF; font-family: 'DM Sans', sans-serif; font-size: 14px;">
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #DEE2E6; padding-bottom: 6px;">
                    <span><b>1. Нийт Борлуулалт (Google Sheet Z багана):</b></span>
                    <span><b>{total_cash_rev:,.0f} ₮</b></span>
                </div>
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #DEE2E6; padding: 6px 0; color: #27AE60;">
                    <span>(+) Шинээр орсон урьдчилгаа (PAYMENT_MASTER):</span>
                    <span>+{new_prepays_received_period:,.0f} ₮</span>
                </div>
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #DEE2E6; padding: 6px 0; font-weight: bold; color: #2C3E50;">
                    <span>Нийт Орлого (Борлуулалт + Шинэ урьдчилгаа):</span>
                    <span>{sales_plus_prepayment:,.0f} ₮</span>
                </div>
                <div style="display: flex; justify-content: space-between; border-bottom: 1px solid #DEE2E6; padding: 6px 0; color: #C0392B;">
                    <span>(-) Урьдчилгаанаас хасагдсан дүн (Ашигласан курс):</span>
                    <span>-{total_prepays_used_period:,.0f} ₮</span>
                </div>
                <div style="display: flex; justify-content: space-between; border-bottom: 2px solid #ADB5BD; padding: 6px 0; color: #C0392B;">
                    <span>(-) Харилцагчийн өр (Хийлгээд мөнгөө өгөөгүй):</span>
                    <span>-{total_customer_debt:,.0f} ₮</span>
                </div>
                <div style="display: flex; justify-content: space-between; border-bottom: 2px solid #34495E; padding: 8px 0; font-size: 15px; font-weight: bold; color: #27AE60;">
                    <span>🔥 НИЙТ ОРСОН ОРЛОГО (Бүх төлбөрийн хэлбэрүүд):</span>
                    <span>{(sheet_total_payments + barter_amt):,.0f} ₮</span>
                </div>
                <div style="display: flex; justify-content: space-between; border-bottom: 2px solid #ADB5BD; padding: 6px 0; color: #C0392B;">
                    <span>(-) Хасах орлого бартер:</span>
                    <span>-{barter_amt:,.0f} ₮</span>
                </div>
                <div style="display: flex; justify-content: space-between; padding-top: 8px; font-size: 16px; font-weight: bold; color: #2E86C1;">
                    <span>💎 НИЙТ ЦЭВЭР ОРЛОГО (Бодит бэлэн мөнгөн орлого):</span>
                    <span>{sheet_total_payments:,.0f} ₮</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Show supplier credit debt
            st.markdown("### 🔌 Бэлтгэн нийлүүлэгчийн Зээлийн Өр төлбөр (Accounts Payable)")
            st.markdown(f"""
            <div style="background-color: #FFF5F5; padding: 15px; border-radius: 8px; border: 1px solid #FFE3E3; font-family: 'DM Sans', sans-serif; font-size: 14px;">
                <div style="display: flex; justify-content: space-between; font-weight: bold; color: #C0392B;">
                    <span>🚨 Нийт Төлөгдөөгүй байгаа Барааны Зээл:</span>
                    <span>{total_unpaid_debt:,.0f} ₮</span>
                </div>
                <div style="font-size: 12px; color: #7F8C8D; margin-top: 5px; font-family: 'DM Sans', sans-serif;">
                    (БАРАА_БҮРТГЭЛ хуудсан дээр 'Орлого (Зээлээр авсан)' гэж тэмдэглэгдсэн бөгөөд 'Төлөгдөөгүй' төлөвтэй байгаа барааны нийлбэр дүн)
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Graphs
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                st.subheader("📈 Өдрийн орлогын хандлага")
                daily_sales = filtered_sales.groupby(filtered_sales['date'].dt.date).agg(
                    cash_revenue=('grand_total', 'sum'),
                    accrual_revenue=('recognized_service_rev', lambda x: x.sum())
                ).reset_index()
                prod_daily = filtered_sales.groupby(filtered_sales['date'].dt.date)['product_cash'].sum().reset_index()
                daily_sales = pd.merge(daily_sales, prod_daily, on='date', how='left')
                daily_sales['accrual_revenue'] = daily_sales['accrual_revenue'] + daily_sales['product_cash'].fillna(0)
                
                fig_daily = go.Figure()
                fig_daily.add_trace(go.Scatter(
                    x=daily_sales['date'], y=daily_sales['accrual_revenue'],
                    mode='lines+markers', name='Хэрэгжсэн бодит орлого',
                    line=dict(color='#2B8C7F', width=3)
                ))
                fig_daily.add_trace(go.Scatter(
                    x=daily_sales['date'], y=daily_sales['cash_revenue'],
                    mode='lines+markers', name='Кассын мөнгөн орлого',
                    line=dict(color='#A8A8A8', width=2, dash='dash')
                ))
                fig_daily.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(showgrid=True, gridcolor='#E9ECEF'),
                    yaxis=dict(showgrid=True, gridcolor='#E9ECEF')
                )
                st.plotly_chart(fig_daily, use_container_width=True)
                
            with col_chart2:
                st.subheader("💳 Төлбөрийн хэлбэрүүд (Орлого)")
                payment_sums = {}
                for idx, row in filtered_sales.iterrows():
                    for pay_type, val in row['payments'].items():
                        payment_sums[pay_type] = payment_sums.get(pay_type, 0.0) + val
                
                pay_df = pd.DataFrame(list(payment_sums.items()), columns=["Төрөл", "Дүн"]).sort_values(by="Дүн", ascending=True)
                pay_df = pay_df[pay_df['Дүн'] > 0]
                
                fig_pay = px.bar(
                    pay_df, x="Дүн", y="Төрөл", orientation="h",
                    color_discrete_sequence=['#2B8C7F']
                )
                fig_pay.update_layout(
                    margin=dict(l=10, r=10, t=10, b=10),
                    paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                    xaxis=dict(showgrid=True, gridcolor='#E9ECEF'),
                    yaxis=dict(showgrid=False)
                )
                st.plotly_chart(fig_pay, use_container_width=True)
                
        # TAB 2: SERVICE ANALYSIS
        with tab_services:
            st.subheader("💇 Үйлчилгээний бодит ашиг ба борлуулалт")
            
            service_counts = filtered_sales[filtered_sales['service_name'] != ""].groupby('service_name').agg(
                count=('service_name', 'count'),
                cash_rev=('service_cash', 'sum'),
                accrual_rev=('recognized_service_rev', 'sum'),
                labor_cost=('service_labor', 'sum'),
                material_cost=('service_material', 'sum')
            ).reset_index()
            
            service_counts['total_cost'] = service_counts['labor_cost'] + service_counts['material_cost']
            service_counts['booit_profit'] = service_counts['accrual_rev'] - service_counts['total_cost']
            service_counts['margin_pct'] = (service_counts['booit_profit'] / service_counts['accrual_rev'] * 100).fillna(0)
            
            # Average Service Profit Calculation & Display
            total_service_visits = service_counts['count'].sum() if not service_counts.empty else 0
            total_service_profit = service_counts['booit_profit'].sum() if not service_counts.empty else 0.0
            avg_service_profit = total_service_profit / total_service_visits if total_service_visits > 0 else 0.0
            avg_service_margin = (total_service_profit / service_counts['accrual_rev'].sum() * 100) if not service_counts.empty and service_counts['accrual_rev'].sum() > 0 else 0.0
            
            st.markdown(f"""
            <div style="background-color: #E8F8F5; padding: 15px; border-radius: 8px; border: 1px solid #A3E4D7; margin-bottom: 20px; font-family: 'DM Sans', sans-serif;">
                <div style="font-weight: bold; color: #16A085; font-size: 15px;">💇 Үйлчилгээний дундаж ашиг (Average Service Profit)</div>
                <div style="font-size: 26px; font-weight: bold; margin-top: 5px; color: #117864;">{avg_service_profit:,.0f} ₮ <span style="font-size: 14px; font-weight: normal; color: #7F8C8D;">/ нэг үйлчилгээ тутамд</span></div>
                <div style="font-size: 12px; color: #7F8C8D; margin-top: 5px;">
                    (Нийт үйлчилгээний ашиг: <b>{total_service_profit:,.0f} ₮</b> | Нийт үзүүлсэн: <b>{total_service_visits} удаа</b> | Ашгийн дундаж марж: <b>{avg_service_margin:.1f}%</b>)
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            service_counts = service_counts.sort_values(by="count", ascending=False)
            
            display_services = service_counts.copy()
            for col in ['cash_rev', 'accrual_rev', 'labor_cost', 'material_cost', 'total_cost', 'booit_profit']:
                display_services[col] = display_services[col].map('{:,.0f} ₮'.format)
            display_services['margin_pct'] = display_services['margin_pct'].map('{:.1f}%'.format)
            
            display_services.columns = [
                "Үйлчилгээний нэр", "Тоо хэмжээ", "Кассын Орлого (Cash)", "Хэрэгжсэн Орлого (Accrual)",
                "Гоо сайханчийн ажлын хөлс", "Материалын өртөг (BOM)", "Нийт Өртөг", "Бодит Цэвэр Ашиг", "Ашгийн марж"
            ]
            
            with st.expander("🔍 Үйлчилгээний бодит ашиг, зарлагын дэлгэрэнгүй жагсаалт"):
                st.dataframe(display_services, use_container_width=True, hide_index=True)
            
            # Beautician Performance
            st.markdown("<br>", unsafe_allow_html=True)
            st.subheader("👩‍⚕️ Гоо сайханчдын гүйцэтгэл")
            beautician_perf = filtered_sales[filtered_sales['beautician'] != ""].groupby('beautician').agg(
                sessions_done=('beautician', 'count'),
                total_labor_earned=('service_labor', 'sum'),
                total_rev_generated=('recognized_service_rev', 'sum')
            ).reset_index().sort_values(by="sessions_done", ascending=False)
            
            beautician_perf['total_labor_earned'] = beautician_perf['total_labor_earned'].map('{:,.0f} ₮'.format)
            beautician_perf['total_rev_generated'] = beautician_perf['total_rev_generated'].map('{:,.0f} ₮'.format)
            
            beautician_perf.columns = ["Гоо сайханч", "Үйлчилгээний тоо", "Бодогдсон ажлын хөлс", "Үүсгэсэн Орлого"]
            st.dataframe(beautician_perf, use_container_width=True, hide_index=True)
            
        # TAB 3: PRODUCT SALES
        with tab_products:
            st.subheader("📦 Бүтээгдэхүүний борлуулалтын ашиг")
            
            prod_sold_sums = {}
            for idx, row in filtered_sales.iterrows():
                for p_name, qty in row['product_qtys'].items():
                    prod_sold_sums[p_name] = prod_sold_sums.get(p_name, 0.0) + qty
                    
            if prod_sold_sums:
                prod_sold_df = pd.DataFrame(list(prod_sold_sums.items()), columns=["Бүтээгдэхүүн", "Зарагдсан тоо"])
                
                prod_details = []
                for idx, row in prod_sold_df.iterrows():
                    p_name = row['Бүтээгдэхүүн']
                    qty = row['Зарагдсан тоо']
                    
                    unit_cost = product_cost_map.get(p_name, 0.0)
                    matching_master = product_master[product_master['Материалын нэр_clean'] == p_name]
                    unit_price = 0.0
                    if not matching_master.empty:
                        unit_price = float(matching_master.iloc[0]['Борлуулах үнэ']) if not pd.isna(matching_master.iloc[0]['Борлуулах үнэ']) else 0.0
                        
                    total_revenue = qty * unit_price
                    total_cogs = qty * unit_cost
                    profit = total_revenue - total_cogs
                    margin = (profit / total_revenue * 100) if total_revenue > 0 else 0
                    
                    prod_details.append({
                        "Бүтээгдэхүүн": p_name,
                        "Зарагдсан тоо": qty,
                        "Нэгжийн өртөг": unit_cost,
                        "Борлуулах нэгж үнэ": unit_price,
                        "Нийт Борлуулалт": total_revenue,
                        "Нийт Өртөг (COGS)": total_cogs,
                        "Цэвэр ашиг": profit,
                        "Ашгийн марж": margin
                    })
                    
                prod_details_df = pd.DataFrame(prod_details).sort_values(by="Зарагдсан тоо", ascending=False)
                
                # Average Product Profit Calculation & Display
                total_products_sold = prod_details_df['Зарагдсан тоо'].sum() if not prod_details_df.empty else 0
                total_product_profit = prod_details_df['Цэвэр ашиг'].sum() if not prod_details_df.empty else 0.0
                avg_product_profit = total_product_profit / total_products_sold if total_products_sold > 0 else 0.0
                avg_product_margin = (total_product_profit / prod_details_df['Нийт Борлуулалт'].sum() * 100) if not prod_details_df.empty and prod_details_df['Нийт Борлуулалт'].sum() > 0 else 0.0
                
                st.markdown(f"""
                <div style="background-color: #EBF5FB; padding: 15px; border-radius: 8px; border: 1px solid #AED6F1; margin-bottom: 20px; font-family: 'DM Sans', sans-serif;">
                    <div style="font-weight: bold; color: #2980B9; font-size: 15px;">📦 Бүтээгдэхүүний дундаж ашиг (Average Product Profit)</div>
                    <div style="font-size: 26px; font-weight: bold; margin-top: 5px; color: #1B4F72;">{avg_product_profit:,.0f} ₮ <span style="font-size: 14px; font-weight: normal; color: #7F8C8D;">/ нэг бүтээгдэхүүн тутамд</span></div>
                    <div style="font-size: 12px; color: #7F8C8D; margin-top: 5px;">
                        (Нийт бүтээгдэхүүний ашиг: <b>{total_product_profit:,.0f} ₮</b> | Нийт зарагдсан: <b>{total_products_sold} ширхэг</b> | Ашгийн дундаж марж: <b>{avg_product_margin:.1f}%</b>)
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                disp_prod = prod_details_df.copy()
                for col in ["Нэгжийн өртөг", "Борлуулах нэгж үнэ", "Нийт Борлуулалт", "Нийт Өртөг (COGS)", "Цэвэр ашиг"]:
                    disp_prod[col] = disp_prod[col].map('{:,.0f} ₮'.format)
                disp_prod["Ашгийн марж"] = disp_prod["Ашгийн марж"].map('{:.1f}%'.format)
                
                with st.expander("🔍 Бүтээгдэхүүн бүрийн борлуулалт, ашгийн дэлгэрэнгүй жагсаалт"):
                    st.dataframe(disp_prod, use_container_width=True, hide_index=True)
            else:
                st.info("Сонгосон хугацаанд бүтээгдэхүүний борлуулалт байхгүй байна.")
                
        # TAB 4: INVENTORY STATUS
        with tab_inventory:
            st.subheader("🏢 Агуулахын одоогийн үлдэгдлийн хяналт")
            
            col_inv1, col_inv2 = st.columns(2)
            
            with col_inv1:
                st.markdown("### 🧴 Борлуулах бүтээгдэхүүний үлдэгдэл")
                if not rolled_prod_warehouse.empty:
                    disp_pw = rolled_prod_warehouse[['Материалын код', 'Материалын нэр', 'Төрөл', 'Эхний үлдэгдэл', 'Нийт орлого', 'Борлуулалтын зарлага', 'Салонд задласан', 'Одоогийн үлдэгдэл', 'Нийт хөрөнгийн дүн']].copy()
                    disp_pw['Нийт хөрөнгийн дүн'] = disp_pw['Нийт хөрөнгийн дүн'].map('{:,.0f} ₮'.format)
                    with st.expander("🧴 Дэлгэрэнгүй жагсаалт харах"):
                        st.dataframe(disp_pw, use_container_width=True, hide_index=True)
                else:
                    st.info("Агуулахын бүтээгдэхүүний мэдээлэл олдсонгүй.")
                    
            with col_inv2:
                st.markdown("### 🔬 Үйлчилгээний материалын үлдэгдэл")
                if not rolled_mat_warehouse.empty:
                    disp_mw = rolled_mat_warehouse[['Материалын код', 'Материалын нэр', 'Төрөл', 'Нэгж', 'Эхний үлдэгдэл', 'Нийт орлого', 'Үйлчилгээний зарлага', 'Нийт зарлага', 'Одоогийн үлдэгдэл']].copy()
                    with st.expander("🔬 Дэлгэрэнгүй жагсаалт харах"):
                        st.dataframe(disp_mw, use_container_width=True, hide_index=True)
                else:
                    st.info("Агуулахын материалын мэдээлэл олдсонгүй.")
            
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown("### 💳 Идэвхтэй урьдчилгаа төлбөр бүхий үйлчлүүлэгчид (Prepayments)")
            
            if not payment_master.empty:
                # Filter for rows where remaining balance (Үлдэгдэл) > 0
                active_prepayments = payment_master[payment_master['Үлдэгдэл'] > 0].copy()
                if not active_prepayments.empty:
                    # Sort by balance descending
                    active_prepayments = active_prepayments.sort_values(by='Үлдэгдэл', ascending=False)
                    # Format dates
                    if 'Огноо' in active_prepayments.columns:
                        active_prepayments['Огноо'] = pd.to_datetime(active_prepayments['Огноо']).dt.strftime('%Y-%m-%d')
                    
                    # Format currency columns
                    for col in ['Орсон мөнгө', 'Ашигласан мөнгө', 'Үлдэгдэл']:
                        if col in active_prepayments.columns:
                            active_prepayments[col] = active_prepayments[col].map('{:,.0f} ₮'.format)
                            
                    cols_to_show = ['Огноо', 'Нэр', 'Утас', 'Гүйлгээний төрөл', 'Орсон мөнгө', 'Ашигласан мөнгө', 'Үлдэгдэл', 'Тайлбар']
                    cols_to_show = [c for c in cols_to_show if c in active_prepayments.columns]
                    with st.expander("💳 Идэвхтэй урьдчилгаатай хэрэглэгчдийн жагсаалт харах"):
                        st.dataframe(active_prepayments[cols_to_show], use_container_width=True, hide_index=True)
                else:
                    st.info("Идэвхтэй урьдчилгаа төлбөрийн үлдэгдэлтэй хэрэглэгч байхгүй байна.")
            else:
                st.info("Урьдчилгаа төлбөрийн мэдээлэл олдсонгүй.")
                
        # TAB 5: EXPENSE ANALYSIS
        with tab_expenses:
            st.subheader("💸 Үйл ажиллагааны зардлын задаргаа")
            
            if not filtered_expenses.empty:
                exp_cat = filtered_expenses.groupby('Үндсэн ангилал')['Мөнгөн дүн'].sum().reset_index().sort_values(by="Мөнгөн дүн", ascending=False)
                
                col_exp1, col_exp2 = st.columns([1, 1])
                
                with col_exp1:
                    st.markdown("### 📊 Ангиллаар")
                    fig_exp = px.pie(
                        exp_cat, values="Мөнгөн дүн", names="Үндсэн ангилал",
                        color_discrete_sequence=px.colors.qualitative.Set2
                    )
                    fig_exp.update_layout(margin=dict(l=10, r=10, t=10, b=10))
                    st.plotly_chart(fig_exp, use_container_width=True)
                    
                with col_exp2:
                    st.markdown("### 📊 Зарлагын Хүснэгт")
                    disp_exp_cat = exp_cat.copy()
                    disp_exp_cat['Мөнгөн дүн'] = disp_exp_cat['Мөнгөн дүн'].map('{:,.0f} ₮'.format)
                    disp_exp_cat.columns = ["Зардлын ангилал", "Нийт Дүн"]
                    st.dataframe(disp_exp_cat, use_container_width=True, hide_index=True)
                    
                with st.expander("🔍 Бүх зарлагын дэлгэрэнгүй жагсаалт харах"):
                    detailed_exp = filtered_expenses.copy().sort_values(by="Огноо", ascending=False).head(50)
                    if not detailed_exp.empty:
                        detailed_exp['Огноо'] = detailed_exp['Огноо'].dt.strftime('%Y-%m-%d')
                        detailed_exp['Мөнгөн дүн'] = detailed_exp['Мөнгөн дүн'].map('{:,.0f} ₮'.format)
                        st.dataframe(detailed_exp[['Огноо', 'Үндсэн ангилал', 'Зарлагын нэр (Дэд ангилал)', 'Мөнгөн дүн', 'Хаанаас төлсөн / Касс', 'Тайлбар']], use_container_width=True, hide_index=True)
                    else:
                        st.info("Сонгосон хугацаанд зардлын мэдээлэл байхгүй байна.")
            else:
                st.info("Сонгосон хугацаанд зардлын бүртгэл байхгүй байна.")
                
        # TAB 6: AI CONSULTANT (AI Зөвлөх)
        with tab_ai:
            st.subheader("🤖 AI Бизнес Зөвлөх")
            
            sub_tab_chat, sub_tab_strategy = st.tabs(["💬 AI Нягтлан бодогч (Чат)", "📈 Маркетингийн стратеги & Зардал оновчлол"])
            
            with sub_tab_chat:
                st.markdown("Салоны санхүү, орлого, ашиг алдагдал болон агуулахын талаар асуух зүйлээ доор бичнэ үү.")
                
                if not has_ai:
                    st.warning("⚠️ **Анхааруулга:** AI-тай чатлахын тулд зүүн талын цэсэнд **Gemini API Key**-ээ оруулах шаардлагатай.")
                else:
                    # Chat logic
                    if "messages" not in st.session_state:
                        st.session_state.messages = []
                    
                    # Display chat messages from history
                    for message in st.session_state.messages:
                        with st.chat_message(message["role"]):
                            st.markdown(message["content"])
                    
                    # Input box
                    if user_prompt := st.chat_input("Энд асуултаа бичнэ үү (Жишээ нь: Өнөөдрийн бодит ашиг хэд байна?):"):
                        # Display user message
                        with st.chat_message("user"):
                            st.markdown(user_prompt)
                        # Add to history
                        st.session_state.messages.append({"role": "user", "content": user_prompt})
                        
                        # Generate live data summary to inject into prompt context
                        context_data = get_current_data_summary()
                        
                        system_instructions = f"""
    Та Baekseol Beauty салоны ухаалаг "AI Нягтлан бодогч" юм. Таны зорилго бол хэрэглэгчид өөрийнх нь өгөгдөл дээр үндэслэн санхүүгийн бодит мэдээлэл, ашиг алдагдал, үлдэгдлийг тодорхойлж тайлбарлахад туслах юм.
    Маш чухал: Ухаалаг, цэгцтэй, Монгол хэлээр хариулна. Хэрэв тодорхой хугацаа эсвэл өдрийн тухай асуувал доорх өгөгдөл дотроос тухайн өдрийн орлого зардлыг шүүж аваад тоо бодож тайлбарлана.
    
    Одоогийн дашбордын өгөгдлийн хураангуй:
    {context_data}
    """
                        
                        # Call Gemini streaming
                        with st.chat_message("assistant"):
                            message_placeholder = st.empty()
                            
                            try:
                                # Reconstruct conversation structure for API
                                # Gather last 5 messages for history
                                history_messages = st.session_state.messages[-6:-1]
                                formatted_history = ""
                                for m in history_messages:
                                    formatted_history += f"{m['role'].capitalize()}: {m['content']}\n"
                                    
                                full_prompt = f"""
    {system_instructions}
    
    Өмнөх харилцан яриа:
    {formatted_history}
    
    Хэрэглэгчийн асуулт: {user_prompt}
    
    AI хариулт:
    """
                                model = genai.GenerativeModel("gemini-3.6-flash")
                                response = model.generate_content(full_prompt, stream=True)
                                
                                full_response = ""
                                for chunk in response:
                                    full_response += chunk.text
                                    message_placeholder.markdown(full_response + "▌")
                                
                                message_placeholder.markdown(full_response)
                                # Add assistant response to history
                                st.session_state.messages.append({"role": "assistant", "content": full_response})
                            except Exception as e:
                                st.error(f"Алдаа гарлаа: {e}")
                                
            with sub_tab_strategy:
                st.markdown("### 📈 Өгөгдөлд суурилсан маркетингийн төлөвлөгөө ба алдагдлыг бууруулах зөвлөмжүүд")
                
                if not has_ai:
                    st.warning("⚠️ **Анхааруулга:** AI зөвлөмжийг авахын тулд зүүн талын цэсэнд **Gemini API Key**-ээ оруулах шаардлагатай.")
                else:
                    @st.cache_data(ttl=1800)  # Cache for 30 minutes
                    def generate_marketing_strategy(data_summary_str):
                        try:
                            model = genai.GenerativeModel("gemini-3.6-flash")
                            prompt = f"""
Та гоо сайхны салоны бизнесийн стратеги хариуцсан AI Зөвлөх юм. Доор өгөгдсөн санхүү, борлуулалт, зардлын бодит өгөгдөлд дүн шинжилгээ хийж, удирдлагын хэмжээний зөвлөмж бэлтгэж өгнө үү.
Ялангуяа:
1. **Алдагдал бууруулах зөвлөмж:** Төлбөрийн хэлбэрүүдийн шимтгэл (POS 1%, QPay 1%, Pocket 6.5%, Omni 6% г.м)-д дүн шинжилгээ хийж, шимтгэлийн зардлыг хэрхэн бууруулах зөвлөмж. Мөн одоогийн ашиг алдагдлыг эерэг болгох зардлын хэмнэлтийн боломжууд.
2. **Маркетингийн төлөвлөгөө ба контент стратеги:** Аль үйлчилгээ болон бүтээгдэхүүнийг түлхүү зарах хэрэгтэй вэ? (Хамгийн өндөр борлуулалттай эсвэл хамгийн өндөр ашгийн маржинтай байгаагаар нь уялдуулах). Харилцагч татах ямар контент, урамшуулал хийх вэ?
3. **Өр төлбөрийн менежмент:** 6.8 сая ₮-ний үлдэгдэл курс үйлчилгээний өр төлбөрийг хэрхэн зөв удирдаж, ажлын ачааллыг төлөвлөх вэ?

Өгөгдөл:
{data_summary_str}

Хариултыг Монгол хэлээр, маш ойлгомжтой, цэгцтэй Markdown форматтай, гарчиг дэд хэсэгтэйгээр бэлтгэж өгнө үү.
"""
                            response = model.generate_content(prompt)
                            return response.text
                        except Exception as e:
                            if "429" in str(e) or "quota" in str(e).lower():
                                return "⚠️ **AI-ийн ачаалал хэтэрлээ:** Google Gemini API-ийн үнэгүй эрхийн хязгаар (Rate Limit) хэтэрсэн байна. Та 30 секунд хүлээгээд хуудсыг дахин ачаална үү (Refresh / Rerun)."
                            return f"AI-аар зөвлөмж бэлтгэхэд алдаа гарлаа: {e}"
                            
                    if "strategy_report" not in st.session_state:
                        st.session_state.strategy_report = ""
                        
                    col_st1, col_st2 = st.columns([1, 2])
                    with col_st1:
                        if st.button("📈 Стратеги зөвлөмж шинээр бэлтгэх", use_container_width=True):
                            with st.spinner("AI зөвлөх борлуулалтын стратеги, зардлын оновчлолыг тооцоолж байна..."):
                                st.session_state.strategy_report = generate_marketing_strategy(get_current_data_summary())
                                
                    if st.session_state.strategy_report:
                        st.markdown(st.session_state.strategy_report)
                    else:
                        st.info("Дээрх товчлуур дээр дарж AI маркетингийн стратеги болон зардлын зөвлөмжийг ажиллуулна уу. (Энэ нь API лимитийг хэмнэхэд тусална)")
    else:
        st.error("Google Sheets-ээс мэдээллийг татаж чадсангүй. Та сүлжээний холболтоо эсвэл Google Sheets-ийн холбоосыг шалгана уу.")
