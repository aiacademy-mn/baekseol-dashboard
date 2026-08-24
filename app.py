import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import data_loader
import google.generativeai as genai
import os

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
        
        # Quick Filters
        quick_select = st.sidebar.selectbox(
            "Хурдан сонголт:",
            ["Бүх хугацаа", "Сүүлийн 7 хоног", "Сүүлийн 14 хоног", "Сүүлийн 30 хоног", "Энэ сар"]
        )
        
        if quick_select == "Сүүлийн 7 хоног":
            start_date = max_date - pd.Timedelta(days=6)
            end_date = max_date
        elif quick_select == "Сүүлийн 14 хоног":
            start_date = max_date - pd.Timedelta(days=13)
            end_date = max_date
        elif quick_select == "Сүүлийн 30 хоног":
            start_date = max_date - pd.Timedelta(days=29)
            end_date = max_date
        elif quick_select == "Энэ сар":
            start_date = pd.Timestamp(max_date.year, max_date.month, 1)
            end_date = max_date
        else:
            start_date = min_date
            end_date = max_date
            
        custom_range = st.sidebar.date_input(
            "Сонгосон хугацаа:",
            value=(start_date, end_date),
            min_value=min_date.date(),
            max_value=max_date.date()
        )
        
        if isinstance(custom_range, tuple) and len(custom_range) == 2:
            start_dt = pd.to_datetime(custom_range[0])
            end_dt = pd.to_datetime(custom_range[1])
        else:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            
        # Filter Data
        filtered_sales = sales_df[(sales_df['date'] >= start_dt) & (sales_df['date'] <= end_dt)]
        filtered_expenses = expense_df[(expense_df['Огноо'] >= start_dt) & (expense_df['Огноо'] <= end_dt)]
        
        # Build unit cost mapping for products
        product_cost_map = {}
        for idx, row in product_master.iterrows():
            name = row['Материалын нэр_clean']
            product_cost_map[name] = float(row['Худалдан авсан үнэ']) if not pd.isna(row['Худалдан авсан үнэ']) else 0.0

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
        # We keep the "Цалин" category from the ledger (ЗАРЛАГЫН_БҮРТГЭЛ) to match actual paid wages,
        # but exclude "Бараа материал" to prevent double counting with product COGS.
        operating_expenses_df = filtered_expenses[filtered_expenses['Үндсэн ангилал'] != 'Бараа материал']
        total_opex = operating_expenses_df['Мөнгөн дүн'].sum()
        total_cash_expenses = filtered_expenses['Мөнгөн дүн'].sum()
        
        # Calculate Total Accrual Expenses:
        # Salaries in total_opex (from ЗАРЛАГЫН_БҮРТГЭЛ) already include base and bonus commissions.
        # Therefore, we do NOT add the service-calculated total_labor_cost here to prevent double counting.
        total_accrual_expenses = total_materials_cost + total_product_cogs + total_opex
        accrual_net_profit = total_accrual_rev - total_accrual_expenses
        
        # Commissions
        total_commissions = 0.0
        for idx, row in filtered_sales.iterrows():
            pos_company = row['payments'].get("POS - Компани", 0.0)
            pos_unda = row['payments'].get("POS - Ундармаа", 0.0)
            qpay = row['payments'].get("QPay", 0.0)
            pocket = row['payments'].get("Pocket", 0.0)
            omni = row['payments'].get("Omni", 0.0)
            total_commissions += (pos_company + pos_unda + qpay) * 0.01 + pocket * 0.065 + omni * 0.06
            
        cash_flow_net = total_cash_rev - total_cash_expenses - total_commissions
        
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
{prod_warehouse[['Материалын код', 'Материалын нэр', 'Одоогийн үлдэгдэл', 'Нийт хөрөнгийн дүн']].to_string(index=False) if not prod_warehouse.empty else "Байхгүй"}
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
            act_total_rev = total_cash_rev
            act_service_rev = filtered_sales['service_cash'].sum() if not filtered_sales.empty else 0.0
            act_product_rev = filtered_sales['product_cash'].sum() if not filtered_sales.empty else 0.0
            
            # Clean asset value
            asset_val_clean = 0.0
            if not prod_warehouse.empty and 'Нийт хөрөнгийн дүн' in prod_warehouse.columns:
                asset_val_clean = pd.to_numeric(prod_warehouse['Нийт хөрөнгийн дүн'], errors='coerce').fillna(0.0).sum()
                
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
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">📊 Хэрэгжсэн Бодит Орлого</div>
                    <div class="metric-value">{total_accrual_rev:,.0f} ₮</div>
                    <div style="font-size:12px; color:green; margin-top:5px;">(Үзүүлсэн үйлчилгээний бодит дүн)</div>
                </div>
                """, unsafe_allow_html=True)
                
            with col2:
                color = "green" if accrual_net_profit >= 0 else "red"
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">📈 Хэрэгжсэн Бодит Цэвэр Ашиг (P&L)</div>
                    <div class="metric-value" style="color: {color};">{accrual_net_profit:,.0f} ₮</div>
                    <div style="font-size:12px; color:#666; margin-top:5px;">(Орлого - Өртөг - Үйл ажиллагааны зардал)</div>
                </div>
                """, unsafe_allow_html=True)
                
            with col3:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">💰 Бэлэн Мөнгөний Орлого</div>
                    <div class="metric-value">{total_cash_rev:,.0f} ₮</div>
                    <div style="font-size:12px; color:#666; margin-top:5px;">(Касс болон дансанд орсон дүн)</div>
                </div>
                """, unsafe_allow_html=True)
                
            with col4:
                cf_color = "green" if cash_flow_net >= 0 else "red"
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">💵 Цэвэр Мөнгөн Урсгал</div>
                    <div class="metric-value" style="color: {cf_color};">{cash_flow_net:,.0f} ₮</div>
                    <div style="font-size:12px; color:#666; margin-top:5px;">(Орсон мөнгө - Зарлага - Шимтгэл)</div>
                </div>
                """, unsafe_allow_html=True)
                
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Calculate Liabilities
            col_name = course_master.columns[13] if len(course_master.columns) > 13 else "Байгууллагын өр"
            total_course_liability = course_master[col_name].sum() if not course_master.empty else 0.0
            total_prepayment_liability = payment_master['Үлдэгдэл'].sum() if not payment_master.empty else 0.0
            total_deferred_liabilities = total_course_liability + total_prepayment_liability
            
            st.markdown("### 🏦 Урьдчилгаа ба Багц Үйлчилгээний Өр төлбөр (Deferred Revenue)")
            col_l1, col_l2, col_l3 = st.columns(3)
            with col_l1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">⏳ Эргэн Төлөх Үлдэгдэл Курс (Байгууллагын Өр)</div>
                    <div class="metric-value" style="color: #E28743;">{total_course_liability:,.0f} ₮</div>
                    <div style="font-size:12px; color:#666; margin-top:5px;">(Худалдаж авсан боловч ороогүй үлдсэн курсын дүн)</div>
                </div>
                """, unsafe_allow_html=True)
            with col_l2:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">💳 Урьдчилгаа Төлбөрийн Үлдэгдэл</div>
                    <div class="metric-value" style="color: #E28743;">{total_prepayment_liability:,.0f} ₮</div>
                    <div style="font-size:12px; color:#666; margin-top:5px;">(Цагийн болон бусад урьдчилж орсон ашиглаагүй дүн)</div>
                </div>
                """, unsafe_allow_html=True)
            with col_l3:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-label">📊 Нийт Үйлчилгээ Хариуцах Өр (Total Liabilities)</div>
                    <div class="metric-value" style="color: #C0392B; font-weight: bold;">{total_deferred_liabilities:,.0f} ₮</div>
                    <div style="font-size:12px; color:#666; margin-top:5px;">(Байгууллагын нийт үзүүлэх өртэй үйлчилгээний дүн)</div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            # Cash Flow Details Table
            st.markdown("### 💵 Мөнгөний Бодит Урсгал (Төлбөрийн хэлбэр ба Шимтгэлүүд)")
            payment_sums = {}
            for idx, row in filtered_sales.iterrows():
                for pay_type, val in row['payments'].items():
                    payment_sums[pay_type] = payment_sums.get(pay_type, 0.0) + val
                    
            commission_rates = {
                "Данс — Компани": 0.0,
                "Данс — Ундармаа": 0.0,
                "POS — Компани": 0.01,
                "POS — Ундармаа": 0.01,
                "QPay": 0.01,
                "Бэлэн": 0.0,
                "Pocket": 0.065,
                "Omni": 0.06,
                "Бартер": 0.0
            }
            
            cf_rows = []
            total_cf_amt = 0.0
            total_cf_comm = 0.0
            total_cf_net = 0.0
            
            for pay_type, rate in commission_rates.items():
                amt = payment_sums.get(pay_type, 0.0)
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
            
            # Format numbers for display
            disp_cf = cf_df.copy()
            for col in ["Нийт төлбөр", "Хасагдах шимтгэл", "Цэвэр авах дүн"]:
                disp_cf[col] = disp_cf[col].map('{:,.0f} ₮'.format)
                
            # Add TOTAL row
            disp_cf.loc[len(disp_cf)] = [
                "🔥 НИЙТ", 
                f"{total_cf_amt:,.0f} ₮", 
                "-", 
                f"{total_cf_comm:,.0f} ₮", 
                f"{total_cf_net:,.0f} ₮",
                "📈"
            ]
            
            st.dataframe(disp_cf, use_container_width=True, hide_index=True)
            st.markdown("<br>", unsafe_allow_html=True)
            
            # AI or Static Summary Note
            st.markdown("### 📝 Санхүүгийн дүн шинжилгээ ба тайлбар")
            
            if has_ai:
                @st.cache_data(ttl=3600)  # Cache for 1 hour to save API calls
                def generate_ai_analysis(data_summary_str):
                    try:
                        model = genai.GenerativeModel("gemini-3.6-flash")
                        prompt = f"""
Та Baekseol Beauty гоо сайхны салоны AI Санхүүгийн шинжээч юм. Доор өгөгдсөн санхүүгийн өгөгдлийг ашиглан удирдлагын тайланг бэлтгэж, тоонууд хэрхэн бодогдсон логикийг маш ойлгомжтойгоор тайлбарлаж өгнө үү.
Ялангуяа:
1. Хэрэгжсэн бодит орлого болон Бэлэн мөнгөний орлого хоёрын зөрүүг тоо бодож, хэрэглэгчид жишээгээр тайлбарлаж өгөх (Жишээлбэл, курс худалдан авалт болон курс ашиглалт хэрхэн нөлөөлсөн).
2. Хэрэгжсэн бодит цэвэр ашиг болон Цэвэр мөнгөн урсгал хоёрын зөрүүг тайлбарлах.
3. Хамгийн ашигтай үйлчилгээ болон бүтээгдэхүүнийг зааж өгөх.
4. Зардлын гол ангиллыг харуулах.

Өгөгдөл:
{data_summary_str}

Хариултыг зөвхөн Монгол хэлээр, маш цэгцтэй, Markdown форматтайгаар бэлтгэнэ үү.
"""
                        response = model.generate_content(prompt)
                        return response.text
                    except Exception as e:
                        return f"AI-аар тайлан бэлтгэхэд алдаа гарлаа: {e}"
                
                with st.spinner("AI тайлан бэлтгэж байна..."):
                    ai_analysis_text = generate_ai_analysis(get_current_data_summary())
                st.markdown(ai_analysis_text)
            else:
                st.info("💡 **Зөвлөмж:** Зүүн талын цэсэнд **Gemini API Key**-ээ оруулбал өдөр бүрийн санхүүгийн дүн шинжилгээний тайлбар болон тооцооллын задргааг AI автоматаар бодож энд харуулах болно.")
                st.markdown("""
                #### 💡 Бодит ашиг ба Бэлэн мөнгөний зөрүүг хэрхэн боддог вэ?
                * **Курсийн урьдчилгаа төлбөр:** Үйлчлүүлэгч 500,000₮-ийн курс авахад тухайн өдрийн **Бэлэн мөнгөний орлого 500,000₮**-өөр нэмэгдэх ч **Хэрэгжсэн бодит орлогод зөвхөн 1 удаагийн үйлчилгээний үнэ (100,000₮)** очно. Үлдэх 400,000₮ нь дараагийн удаа үйлчилгээ авахад хэрэгжинэ.
                * **Курс ашиглалт:** Үйлчлүүлэгч курсээсээ 1 удаа ашиглахад **Бэлэн мөнгөний орлого 0₮** байх ч үйлчилгээ үзүүлсэн тул дашборд дээр **Хэрэгжсэн орлого нь 100,000₮** гэж бүртгэгдэнэ. Түүнээс гоо сайханчийн хөлс ба материалын өртөг хасагдан бодит ашгийг зөв тооцдог.
                * **Бараа татан авалт:** Агуулахад зориулж 10,000,000₮-ний бараа татахад **Бэлэн мөнгөний урсгалаас 10 сая хасагдах** боловч бодит ашгаас хасахгүй. Бараа зарагдах эсвэл үйлчилгээнд ашиглагдах бүрд л өөрийн өртөг нь бодит ашгаас хасагдаж бодогдоно.
                """)
                
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
            
            service_counts = service_counts.sort_values(by="count", ascending=False)
            
            display_services = service_counts.copy()
            for col in ['cash_rev', 'accrual_rev', 'labor_cost', 'material_cost', 'total_cost', 'booit_profit']:
                display_services[col] = display_services[col].map('{:,.0f} ₮'.format)
            display_services['margin_pct'] = display_services['margin_pct'].map('{:.1f}%'.format)
            
            display_services.columns = [
                "Үйлчилгээний нэр", "Тоо хэмжээ", "Кассын Орлого (Cash)", "Хэрэгжсэн Орлого (Accrual)",
                "Гоо сайханчийн ажлын хөлс", "Материалын өртөг (BOM)", "Нийт Өртөг", "Бодит Цэвэр Ашиг", "Ашгийн марж"
            ]
            
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
                
                disp_prod = prod_details_df.copy()
                for col in ["Нэгжийн өртөг", "Борлуулах нэгж үнэ", "Нийт Борлуулалт", "Нийт Өртөг (COGS)", "Цэвэр ашиг"]:
                    disp_prod[col] = disp_prod[col].map('{:,.0f} ₮'.format)
                disp_prod["Ашгийн марж"] = disp_prod["Ашгийн марж"].map('{:.1f}%'.format)
                
                st.dataframe(disp_prod, use_container_width=True, hide_index=True)
            else:
                st.info("Сонгосон хугацаанд бүтээгдэхүүний борлуулалт байхгүй байна.")
                
        # TAB 4: INVENTORY STATUS
        with tab_inventory:
            st.subheader("🏢 Агуулахын одоогийн үлдэгдлийн хяналт")
            
            col_inv1, col_inv2 = st.columns(2)
            
            with col_inv1:
                st.markdown("### 🧴 Борлуулах бүтээгдэхүүний үлдэгдэл")
                if not prod_warehouse.empty:
                    disp_pw = prod_warehouse[['Материалын код', 'Материалын нэр', 'Төрөл', 'Эхний үлдэгдэл', 'Нийт орлого', 'Борлуулалтын зарлага', 'Салонд задласан', 'Одоогийн үлдэгдэл', 'Нийт хөрөнгийн дүн']].copy()
                    disp_pw['Нийт хөрөнгийн дүн'] = disp_pw['Нийт хөрөнгийн дүн'].map('{:,.0f} ₮'.format)
                    st.dataframe(disp_pw, use_container_width=True, hide_index=True)
                else:
                    st.info("Агуулахын бүтээгдэхүүний мэдээлэл олдсонгүй.")
                    
            with col_inv2:
                st.markdown("### 🔬 Үйлчилгээний материалын үлдэгдэл")
                if not mat_warehouse.empty:
                    disp_mw = mat_warehouse[['Материалын код', 'Материалын нэр', 'Төрөл', 'Нэгж', 'Эхний үлдэгдэл', 'Нийт орлого', 'Үйлчилгээний зарлага', 'Нийт зарлага', 'Одоогийн үлдэгдэл']].copy()
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
                    
                st.markdown("### 📜 Бүх зарлагын жагсаалт (Сүүлийн 50 бичилт)")
                detailed_exp = filtered_expenses.copy().sort_values(by="Огноо", ascending=False).head(50)
                detailed_exp['Огноо'] = detailed_exp['Огноо'].dt.strftime('%Y-%m-%d')
                detailed_exp['Мөнгөн дүн'] = detailed_exp['Мөнгөн дүн'].map('{:,.0f} ₮'.format)
                st.dataframe(detailed_exp[['Огноо', 'Үндсэн ангилал', 'Зарлагын нэр (Дэд ангилал)', 'Мөнгөн дүн', 'Хаанаас төлсөн / Касс', 'Тайлбар']], use_container_width=True, hide_index=True)
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
                            return f"AI-аар зөвлөмж бэлтгэхэд алдаа гарлаа: {e}"
                            
                    with st.spinner("AI зөвлөх борлуулалтын стратеги, зардлын оновчлолыг тооцоолж байна..."):
                        strategy_report = generate_marketing_strategy(get_current_data_summary())
                    st.markdown(strategy_report)
    else:
        st.error("Google Sheets-ээс мэдээллийг татаж чадсангүй. Та сүлжээний холболтоо эсвэл Google Sheets-ийн холбоосыг шалгана уу.")
