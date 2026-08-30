import streamlit as st
import pandas as pd
import numpy as np
import requests
import io
import os

SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1WUhSE3SZJkUK03XwGZd77bQL7eBoVeXTnTizBCOOm3Y/export?format=xlsx"

@st.cache_data(ttl=600)  # Cache for 10 minutes by default
def fetch_excel_bytes(url):
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print(f"Network error downloading spreadsheet: {e}")
    return None

def load_workbook_data():
    content = fetch_excel_bytes(SPREADSHEET_URL)
    if content is not None:
        try:
            with open("local_fallback.xlsx", "wb") as f:
                f.write(content)
        except:
            pass
        return pd.ExcelFile(io.BytesIO(content))
    
    if os.path.exists("local_fallback.xlsx"):
        try:
            return pd.ExcelFile("local_fallback.xlsx")
        except:
            pass
    return None

def parse_service_master(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="SERVICE_MASTER")
        df['Үйлчилгээний нэр_clean'] = df['Үйлчилгээний нэр'].astype(str).str.strip()
        df['Service Code'] = df['Service Code'].astype(str).str.strip()
        return df
    except Exception as e:
        st.warning(f"Error reading SERVICE_MASTER: {e}")
        return pd.DataFrame()

def parse_product_master(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="PRODUCT_MASTER", header=1)
        df['Материалын нэр_clean'] = df['Материалын нэр'].astype(str).str.strip()
        df['Материалын код'] = df['Материалын код'].astype(str).str.strip()
        return df
    except Exception as e:
        st.warning(f"Error reading PRODUCT_MASTER: {e}")
        return pd.DataFrame()

def parse_recipe_bom(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="RECIPE_BOM")
        return df
    except Exception as e:
        st.warning(f"Error reading RECIPE_BOM: {e}")
        return pd.DataFrame()

def parse_expense_registry(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="ЗАРЛАГЫН_БҮРТГЭЛ")
        df['Огноо'] = pd.to_datetime(df['Огноо'], errors='coerce')
        df = df.dropna(subset=['Огноо'])
        df['Мөнгөн дүн'] = pd.to_numeric(df['Мөнгөн дүн'], errors='coerce').fillna(0.0)
        return df
    except Exception as e:
        st.warning(f"Error reading ЗАРЛАГЫН_БҮРТГЭЛ: {e}")
        return pd.DataFrame()

def parse_product_warehouse(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="БҮТ_АГУУЛАХ_ҮЛДЭГДЭЛ", header=1)
        # Drop rows where material code is NaN
        df = df.dropna(subset=['Материалын код'])
        df['Материалын код'] = df['Материалын код'].astype(str).str.strip()
        df['Материалын нэр'] = df['Материалын нэр'].astype(str).str.strip()
        return df
    except Exception as e:
        st.warning(f"Error reading БҮТ_АГУУЛАХ_ҮЛДЭГДЭЛ: {e}")
        return pd.DataFrame()

def parse_material_warehouse(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="МАТ_АГУУЛАХ_ҮЛДЭГДЭЛ", header=1)
        df = df.dropna(subset=['Материалын код'])
        df['Материалын код'] = df['Материалын код'].astype(str).str.strip()
        df['Материалын нэр'] = df['Материалын нэр'].astype(str).str.strip()
        return df
    except Exception as e:
        st.warning(f"Error reading МАТ_АГУУЛАХ_ҮЛДЭГДЭЛ: {e}")
        return pd.DataFrame()

def parse_daily_sales(excel_file, service_master, product_master):
    try:
        df = pd.read_excel(excel_file, sheet_name="ӨДӨР БҮРИЙН ОРЛОГО", header=[0, 1])
        
        service_map = {}
        if not service_master.empty:
            for idx, row in service_master.iterrows():
                name = row['Үйлчилгээний нэр_clean']
                service_map[name] = {
                    "code": row['Service Code'],
                    "labor_cost": float(row['Ажлын хөлс (₮)']) if not pd.isna(row['Ажлын хөлс (₮)']) else 0.0,
                    "material_cost": float(row['Материалын өртөг (₮)']) if not pd.isna(row['Материалын өртөг (₮)']) else 0.0,
                    "selling_price": float(row['Борлуулах үнэ']) if not pd.isna(row['Борлуулах үнэ']) else 0.0
                }
        
        parsed_records = []
        for idx, row in df.iterrows():
            date_val = row.iloc[1]
            if pd.isna(date_val) or str(date_val).strip() == "" or "Огноо" in str(date_val):
                continue
            
            col5_val = str(row.iloc[5]).strip() if not pd.isna(row.iloc[5]) else ""
            col6_val = str(row.iloc[6]).strip() if not pd.isna(row.iloc[6]) else ""
            service_name = col5_val if col5_val != "" else col6_val
            
            try:
                service_cash = float(row.iloc[7]) if not pd.isna(row.iloc[7]) else 0.0
            except:
                service_cash = 0.0
                
            try:
                baekseol_discount = float(row.iloc[16]) if not pd.isna(row.iloc[16]) else 0.0
            except:
                baekseol_discount = 0.0

            try:
                baekseol_cash = float(row.iloc[17]) if not pd.isna(row.iloc[17]) else 0.0
            except:
                baekseol_cash = 0.0

            try:
                healthy_cell_discount = float(row.iloc[22]) if not pd.isna(row.iloc[22]) else 0.0
            except:
                healthy_cell_discount = 0.0
                
            try:
                healthy_cell_cash = float(row.iloc[23]) if not pd.isna(row.iloc[23]) else 0.0
            except:
                healthy_cell_cash = 0.0
                
            try:
                grand_total = float(row.iloc[25]) if not pd.isna(row.iloc[25]) else 0.0
            except:
                grand_total = 0.0
                
            beautician = str(row.iloc[4]).strip() if not pd.isna(row.iloc[4]) else ""
            customer_name = str(row.iloc[2]).strip() if not pd.isna(row.iloc[2]) else ""
            
            matched_service_name = service_name.strip()
            service_details = service_map.get(matched_service_name, None)
            if service_details is None and matched_service_name != "":
                for k, v in service_map.items():
                    if k in matched_service_name or matched_service_name in k:
                        service_details = v
                        matched_service_name = k
                        break
            
            service_labor = 0.0
            service_material = 0.0
            service_selling_price = 0.0
            service_code = "Unknown"
            
            if service_details is not None:
                service_labor = service_details["labor_cost"]
                service_material = service_details["material_cost"]
                service_selling_price = service_details["selling_price"]
                service_code = service_details["code"]
            
            recognized_service_rev = 0.0
            if matched_service_name != "":
                if service_cash == 0.0:
                    recognized_service_rev = service_selling_price
                elif service_selling_price > 0.0 and service_cash >= service_selling_price:
                    recognized_service_rev = service_selling_price
                else:
                    recognized_service_rev = service_cash
            
            payments = {}
            payment_cols = [
                "Данс — Компани", "Данс — Ундармаа", "POS — Компани", 
                "POS — Ундармаа", "QPay", "Бэлэн", "Pocket", "Omni", "Бартер"
            ]
            for i, col_name in enumerate(payment_cols):
                try:
                    val = float(row.iloc[27 + i]) if not pd.isna(row.iloc[27 + i]) else 0.0
                    payments[col_name] = val
                except:
                    payments[col_name] = 0.0
            
            product_qtys = {}
            baekseol_col_names = [
                "Baekseol тос", "Baekseol мист", "Baekseol хөөс", 
                "Baekseol крем", "Baekseol ампуль", "Baekseol хал/хүйт", "Baekseol нарны тос"
            ]
            for i, p_name in enumerate(baekseol_col_names):
                try:
                    val = float(row.iloc[8 + i]) if not pd.isna(row.iloc[8 + i]) else 0.0
                    if val > 0:
                        product_qtys[p_name] = val
                except:
                    pass
                    
            hc_col_names = [
                "Эрүүл эс уураг", "Эрүүл эс мист", "Эрүүл эс маск", "Эрүүл эс х/тос"
            ]
            for i, p_name in enumerate(hc_col_names):
                try:
                    val = float(row.iloc[18 + i]) if not pd.isna(row.iloc[18 + i]) else 0.0
                    if val > 0:
                        product_qtys[p_name] = val
                except:
                    pass

            try:
                hourly_prepay_used = float(row.iloc[36]) if not pd.isna(row.iloc[36]) else 0.0
            except:
                hourly_prepay_used = 0.0
                
            try:
                course_prepay_used = float(row.iloc[37]) if not pd.isna(row.iloc[37]) else 0.0
            except:
                course_prepay_used = 0.0
                
            try:
                course_sessions_used = float(row.iloc[38]) if not pd.isna(row.iloc[38]) else 0.0
            except:
                course_sessions_used = 0.0
                
            try:
                customer_debt = float(row.iloc[40]) if not pd.isna(row.iloc[40]) else 0.0
            except:
                customer_debt = 0.0

            parsed_records.append({
                "date": pd.to_datetime(str(date_val).strip()),
                "customer": customer_name,
                "beautician": beautician,
                "service_name": matched_service_name,
                "service_code": service_code,
                "service_cash": service_cash,
                "recognized_service_rev": recognized_service_rev,
                "product_cash": baekseol_cash + healthy_cell_cash,
                "baekseol_discount": baekseol_discount,
                "healthy_cell_discount": healthy_cell_discount,
                "product_discount": baekseol_discount + healthy_cell_discount,
                "grand_total": grand_total,
                "service_labor": service_labor if matched_service_name != "" else 0.0,
                "service_material": service_material if matched_service_name != "" else 0.0,
                "payments": payments,
                "product_qtys": product_qtys,
                "hourly_prepay_used": hourly_prepay_used,
                "course_prepay_used": course_prepay_used,
                "course_sessions_used": course_sessions_used,
                "customer_debt": customer_debt
            })
            
        sales_df = pd.DataFrame(parsed_records)
        sales_df = sales_df.dropna(subset=['date'])
        return sales_df
    except Exception as e:
        st.warning(f"Error reading ӨДӨР БҮРИЙН ОРЛОГО: {e}")
        return pd.DataFrame()

def parse_product_inventory_purchases(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="БАРАА_БҮРТГЭЛ")
        df['Огноо'] = pd.to_datetime(df['Огноо'], errors='coerce')
        df = df.dropna(subset=['Огноо'])
        df['Тоо хэмжээ'] = pd.to_numeric(df['Тоо хэмжээ'], errors='coerce').fillna(0.0)
        return df
    except Exception as e:
        st.warning(f"Error reading БАРАА_БҮРТГЭЛ: {e}")
        return pd.DataFrame()

def parse_salary_calculation(excel_file):
    try:
        # Read dates from first two rows
        df_dates = pd.read_excel(excel_file, sheet_name="ЦАЛИН_БОДОЛТ", header=None, nrows=2)
        start_date = pd.to_datetime(df_dates.iloc[1, 0], errors='coerce')
        end_date = pd.to_datetime(df_dates.iloc[1, 1], errors='coerce')
        
        df = pd.read_excel(excel_file, sheet_name="ЦАЛИН_БОДОЛТ", header=3)
        df = df.dropna(subset=["Овог нэр"])
        df["Олгох цалин"] = pd.to_numeric(df["Олгох цалин"], errors="coerce").fillna(0.0)
        df["Хийсэн ажлын бонус"] = pd.to_numeric(df["Хийсэн ажлын бонус"], errors="coerce").fillna(0.0)
        df["Хугацааны үндсэн цалин (50%)"] = pd.to_numeric(df["Хугацааны үндсэн цалин (50%)"], errors="coerce").fillna(0.0)
        df["Нэмэгдэл"] = pd.to_numeric(df["Нэмэгдэл"], errors="coerce").fillna(0.0)
        df["Суутгал/Өр"] = pd.to_numeric(df["Суутгал/Өр"], errors="coerce").fillna(0.0)
        
        # Save metadata
        df.attrs["start_date"] = start_date
        df.attrs["end_date"] = end_date
        return df
    except Exception as e:
        st.warning(f"Error reading ЦАЛИН_БОДОЛТ: {e}")
        return pd.DataFrame()

def parse_course_master(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="COURSE_MASTER")
        col_name = df.columns[13] if len(df.columns) > 13 else "Байгууллагын өр"
        df[col_name] = pd.to_numeric(df[col_name], errors='coerce').fillna(0.0)
        return df
    except Exception as e:
        st.warning(f"Error reading COURSE_MASTER: {e}")
        return pd.DataFrame()

def parse_payment_master(excel_file):
    try:
        df = pd.read_excel(excel_file, sheet_name="PAYMENT_MASTER")
        df['Үлдэгдэл'] = pd.to_numeric(df['Үлдэгдэл'], errors='coerce').fillna(0.0)
        df['Орсон мөнгө'] = pd.to_numeric(df['Орсон мөнгө'], errors='coerce').fillna(0.0)
        df['Ашигласан мөнгө'] = pd.to_numeric(df['Ашигласан мөнгө'], errors='coerce').fillna(0.0)
        return df
    except Exception as e:
        st.warning(f"Error reading PAYMENT_MASTER: {e}")
        return pd.DataFrame()

def get_processed_data():
    excel_file = load_workbook_data()
    if excel_file is None:
        st.error("No data workbook could be loaded (neither online nor fallback local_fallback.xlsx).")
        return None
    
    service_master = parse_service_master(excel_file)
    product_master = parse_product_master(excel_file)
    recipe_bom = parse_recipe_bom(excel_file)
    expenses = parse_expense_registry(excel_file)
    sales = parse_daily_sales(excel_file, service_master, product_master)
    purchases = parse_product_inventory_purchases(excel_file)
    prod_warehouse = parse_product_warehouse(excel_file)
    mat_warehouse = parse_material_warehouse(excel_file)
    salary_calc = parse_salary_calculation(excel_file)
    course_master = parse_course_master(excel_file)
    payment_master = parse_payment_master(excel_file)
    
    return {
        "service_master": service_master,
        "product_master": product_master,
        "recipe_bom": recipe_bom,
        "expenses": expenses,
        "sales": sales,
        "purchases": purchases,
        "product_warehouse": prod_warehouse,
        "material_warehouse": mat_warehouse,
        "salary_calc": salary_calc,
        "course_master": course_master,
        "payment_master": payment_master
    }
