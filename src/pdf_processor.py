import tabula
import pandas as pd
import pypdf
import re
import numpy as np

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
    # Remove % if present
    val_str = val_str.replace('%', '')
    try:
        return float(val_str)
    except:
        return 0.0

def is_header_row(row):
    # Convert row to string
    row_str = " ".join([str(x) for x in row if pd.notna(x)])
    keywords = ["ISIN", "Vencimiento", "Valor Nominal", "Precio", "Tasa", "Cupón"]
    matches = sum(1 for k in keywords if k.lower() in row_str.lower())
    return matches >= 2

def is_total_row(row):
    row_str = " ".join([str(x) for x in row if pd.notna(x)])
    return "TOTAL" in row_str.upper() or "VALOR A GIRAR" in row_str.upper()

def extract_row_data(row):
    # Attempt to extract fields based on patterns
    data = {}

    # Clean row: remove NaNs and split merged strings (like "COL123 2-jun-26")
    raw_items = [str(x).strip() for x in row if pd.notna(x) and str(x).strip() != ""]
    items = []
    for item in raw_items:
        # Split by space if it looks like multiple valid tokens
        # But be careful not to split "100.000,00"
        # Split only if space separates clear concepts?
        # E.g. "COL... 2-jun..."
        parts = item.split()
        if len(parts) > 1:
            # Check if any part looks like ISIN or Date
            if any(x.startswith("COL") for x in parts) or any(re.search(r'\d{1,2}-[a-zA-Z]{3}-\d{2}', x) for x in parts):
                 items.extend(parts)
            else:
                 items.append(item)
        else:
            items.append(item)

    # 1. ISIN: Starts with COL, length usually 12
    # Regex search because sometimes it might be attached to something else?
    # But splitting should handle space-separated.
    isin_candidates = [x for x in items if x.startswith("COL") and len(x) >= 10]
    # Clean up ISIN (remove trailing non-alphanumeric if needed)
    if isin_candidates:
        data['ISIN'] = isin_candidates[0].strip()
    else:
        data['ISIN'] = None

    # 2. Date (Vencimiento): Looks like "2-jun-26" or "26-ago-26"
    date_candidates = [x for x in items if re.search(r'^\d{1,2}-[a-zA-Z]{3}-\d{2}$', x)]
    data['Vencimiento'] = date_candidates[0] if date_candidates else None

    # 3. Moneda: COP or UVR
    moneda_candidates = [x for x in items if x in ["COP", "UVR"]]
    data['Moneda'] = moneda_candidates[0] if moneda_candidates else "COP" # Default to COP?

    # 4. Numerics
    # We expect: Cupón (%), Tasa (%), Precio, ValNominal, ValNominalCOP, ValCosto
    # This is tricky because order matters.
    # Usually: Cupón -> Tasa -> Precio -> Nominal -> NominalCOP -> Costo

    # Filter out ISIN, Date, Moneda from items to process numerics
    remaining = [x for x in items if x not in isin_candidates and x not in date_candidates and x not in moneda_candidates]

    # Identify Percentages
    percentages = [x for x in remaining if '%' in x]

    # Identify Numbers (non-percentages)
    numbers = []
    for x in remaining:
        if '%' not in x:
            # Check if it looks like a number
            if re.match(r'^[\d\.,]+$', x):
                numbers.append(x)

    # Assign based on count
    # Percentages:
    if len(percentages) == 2:
        data['Cupón'] = parse_currency(percentages[0])
        data['Tasa'] = parse_currency(percentages[1])
    elif len(percentages) == 1:
        # Ambiguous. Usually Tasa is the yield, Cupon is fixed.
        # Check context or assume Tasa if only one?
        data['Tasa'] = parse_currency(percentages[0])
        data['Cupón'] = 0.0 # Or NaN
    else:
        data['Cupón'] = 0.0
        data['Tasa'] = 0.0

    # Numbers:
    # Expected: Precio (smallish, ~80-120), Nominal (Huge), NominalCOP (Huge), Costo (Huge)
    # Sort numbers by value to guess?
    # Precio is usually < 200.
    # Nominal is integer-like (lots of zeros).

    parsed_nums = []
    for n in numbers:
        parsed_nums.append(parse_currency(n))

    # Filter out small numbers that might be Precio
    prices = [n for n in parsed_nums if n < 1000] # threshold for price
    large_nums = [n for n in parsed_nums if n >= 1000]

    if prices:
        data['Precio'] = prices[0] # Assume first small num is price
    else:
        data['Precio'] = 0.0

    # Large numbers assignment
    # If 3 large numbers: Nominal, NominalCOP, Costo
    # If 2: Nominal, Costo (maybe NominalCOP is missing or same as Nominal)
    # If 1: Nominal

    if len(large_nums) >= 3:
        data['Valor Nominal'] = large_nums[0]
        data['Valor Nominal COP'] = large_nums[1]
        data['Valor Costo COP'] = large_nums[2]
    elif len(large_nums) == 2:
        data['Valor Nominal'] = large_nums[0]
        data['Valor Nominal COP'] = large_nums[0] # Assumption for COP
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

            # Split logic
            recibidos_mask = df_str.apply(lambda x: x.str.contains('TES RECIBIDOS', case=False, na=False)).any(axis=1)
            entregados_mask = df_str.apply(lambda x: x.str.contains('TES ENTREGADOS', case=False, na=False)).any(axis=1)

            rows_to_process = []

            if entregados_mask.any():
                split_idx = entregados_mask.idxmax()

                # Part 1: Before split
                part1 = df.iloc[:split_idx]
                if current_category == "Recibidos":
                    # Process rows
                    for _, row in part1.iterrows():
                        if not is_header_row(row) and not is_total_row(row):
                            d = extract_row_data(row)
                            if d['ISIN']: recibidos.append(d)
                else:
                    for _, row in part1.iterrows():
                        if not is_header_row(row) and not is_total_row(row):
                            d = extract_row_data(row)
                            if d['ISIN']: entregados.append(d)

                current_category = "Entregados"

                # Part 2: After split
                part2 = df.iloc[split_idx+1:]
                for _, row in part2.iterrows():
                    if not is_header_row(row) and not is_total_row(row):
                        d = extract_row_data(row)
                        if d['ISIN']: entregados.append(d)
            else:
                # No split
                for _, row in df.iterrows():
                    # Check if category switch happened in previous block? No, assumed sequential.
                    # But wait, "TES RECIBIDOS" might be in this block too.
                    if recibidos_mask.any():
                         # Reset to Recibidos? Usually it starts with Recibidos.
                         current_category = "Recibidos"

                    if not is_header_row(row) and not is_total_row(row):
                        d = extract_row_data(row)
                        if d['ISIN']:
                            if current_category == "Recibidos":
                                recibidos.append(d)
                            else:
                                entregados.append(d)

        return pd.DataFrame(recibidos), pd.DataFrame(entregados)

    except Exception as e:
        print(f"Error processing tables: {e}")
        return pd.DataFrame(), pd.DataFrame()
