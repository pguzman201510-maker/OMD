import tabula
import pandas as pd
import pypdf
import re
import numpy as np
import io
import tempfile

def extract_date(pdf_path):
    try:
        reader = pypdf.PdfReader(pdf_path)
        full_text = ""
        for page in reader.pages:
            full_text += page.extract_text() or ""

        match = re.search(r"fecha de cumplimiento\s+(.*?)(?:\.|\n|$)", full_text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        match_header = re.search(r"Bogotá D\. ?C\.,\s+(.*?)(?:\n|$)", full_text, re.IGNORECASE)
        if match_header:
            return match_header.group(1).strip()

        return "Fecha no encontrada"
    except Exception as e:
        return f"Error extrayendo fecha: {str(e)}"

def parse_currency(val):
    if pd.isna(val) or val == "":
        return 0.0
    val_str = str(val).strip().replace('.', '').replace(',', '.')
    val_str = val_str.replace('%', '')
    try:
        return float(val_str)
    except:
        return 0.0

def is_header_row(row):
    row_str = " ".join([str(x) for x in row if pd.notna(x)])
    keywords = ["ISIN", "Vencimiento", "Valor Nominal", "Precio", "Tasa", "Cupón"]
    matches = sum(1 for k in keywords if k.lower() in row_str.lower())
    return matches >= 2

def is_total_row(row):
    row_str = " ".join([str(x) for x in row if pd.notna(x)])
    return "TOTAL" in row_str.upper() or "VALOR A GIRAR" in row_str.upper()

def extract_row_data(row):
    data = {}

    # Handle both list (from PDF table) and string (from manual text) input
    if isinstance(row, str):
        # Raw string parsing
        raw_items = row.split()
    else:
        # Pandas Series or list processing
        raw_items = [str(x).strip() for x in row if pd.notna(x) and str(x).strip() != ""]

    items = []
    for item in raw_items:
        # Split merged tokens unless it breaks currency (e.g. 100.000,00)
        # We split by space
        parts = item.split()
        if len(parts) > 1:
             items.extend(parts)
        else:
            items.append(item)

    # 1. ISIN
    isin_candidates = [x for x in items if x.startswith("COL") and len(x) >= 10]
    data['ISIN'] = isin_candidates[0].strip() if isin_candidates else None

    # 2. Date
    date_candidates = [x for x in items if re.search(r'^\d{1,2}-[a-zA-Z]{3}-\d{2}$', x)]
    data['Vencimiento'] = date_candidates[0] if date_candidates else None

    # 3. Moneda
    moneda_candidates = [x for x in items if x in ["COP", "UVR"]]
    data['Moneda'] = moneda_candidates[0] if moneda_candidates else "COP"

    # 4. Numerics
    remaining = [x for x in items if x not in isin_candidates and x not in date_candidates and x not in moneda_candidates]

    percentages = [x for x in remaining if '%' in x]
    numbers = [x for x in remaining if '%' not in x and re.match(r'^[\d\.,]+$', x)]

    if len(percentages) == 2:
        data['Cupón'] = parse_currency(percentages[0])
        data['Tasa'] = parse_currency(percentages[1])
    elif len(percentages) == 1:
        data['Tasa'] = parse_currency(percentages[0])
        data['Cupón'] = 0.0
    else:
        data['Cupón'] = 0.0
        data['Tasa'] = 0.0

    parsed_nums = [parse_currency(n) for n in numbers]
    prices = [n for n in parsed_nums if n < 1000]
    large_nums = [n for n in parsed_nums if n >= 1000]

    data['Precio'] = prices[0] if prices else 0.0

    if len(large_nums) >= 3:
        data['Valor Nominal'] = large_nums[0]
        data['Valor Nominal COP'] = large_nums[1]
        data['Valor Costo COP'] = large_nums[2]
    elif len(large_nums) == 2:
        data['Valor Nominal'] = large_nums[0]
        data['Valor Nominal COP'] = large_nums[0]
        data['Valor Costo COP'] = large_nums[1]
    elif len(large_nums) == 1:
        data['Valor Nominal'] = large_nums[0]
        data['Valor Nominal COP'] = large_nums[0]
        data['Valor Costo COP'] = 0.0
    else:
        data['Valor Nominal'] = 0.0
        data['Valor Nominal COP'] = 0.0
        data['Valor Costo COP'] = 0.0

    return data

def process_tables(pdf_path):
    try:
        tables = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True, lattice=False, stream=True)
        recibidos = []
        entregados = []
        current_category = "Recibidos"

        for df in tables:
            df_str = df.astype(str)

            recibidos_mask = df_str.apply(lambda x: x.str.contains('TES RECIBIDOS', case=False, na=False)).any(axis=1)
            entregados_mask = df_str.apply(lambda x: x.str.contains('TES ENTREGADOS', case=False, na=False)).any(axis=1)

            if entregados_mask.any():
                split_idx = entregados_mask.idxmax()

                # Part 1
                part1 = df.iloc[:split_idx]
                target_list = recibidos if current_category == "Recibidos" else entregados
                for _, row in part1.iterrows():
                    if not is_header_row(row) and not is_total_row(row):
                        d = extract_row_data(row)
                        if d['ISIN']: target_list.append(d)

                current_category = "Entregados"

                # Part 2
                part2 = df.iloc[split_idx+1:]
                for _, row in part2.iterrows():
                    if not is_header_row(row) and not is_total_row(row):
                        d = extract_row_data(row)
                        if d['ISIN']: entregados.append(d)
            else:
                if recibidos_mask.any(): current_category = "Recibidos"
                target_list = recibidos if current_category == "Recibidos" else entregados
                for _, row in df.iterrows():
                    if not is_header_row(row) and not is_total_row(row):
                        d = extract_row_data(row)
                        if d['ISIN']: target_list.append(d)

        return pd.DataFrame(recibidos), pd.DataFrame(entregados)

    except Exception as e:
        print(f"Error processing tables: {e}")
        return pd.DataFrame(), pd.DataFrame()

def process_manual_text(text):
    recibidos = []
    entregados = []
    current_list = recibidos # Start with Recibidos by default

    lines = text.split('\n')
    for line in lines:
        clean_line = line.strip()
        if not clean_line: continue

        upper_line = clean_line.upper()

        if "TES RECIBIDOS" in upper_line:
            current_list = recibidos
            continue
        if "TES ENTREGADOS" in upper_line:
            current_list = entregados
            continue

        # Skip headers and totals
        if "CODIGO ISIN" in upper_line or "VALOR NOMINAL" in upper_line: continue
        if "TOTAL" in upper_line: continue

        # Parse data row
        d = extract_row_data(clean_line)
        if d['ISIN']:
            current_list.append(d)

    return pd.DataFrame(recibidos), pd.DataFrame(entregados)
