import pandas as pd
import tabula
from pypdf import PdfReader
import re
import tempfile
import os

def extract_date_from_text(text):
    # Pattern to find date in format "Bogotá D. C., DD de MM de YYYY"
    match = re.search(r'Bogotá D\.? ?C\.?,? (\d+ de [a-zA-Z]+ de \d{4})', text)
    if match:
        return match.group(1)

    match = re.search(r'(\d{1,2} de [a-zA-Z]+ de \d{4})', text)
    if match:
        return match.group(1)

    return "Fecha no encontrada"

def clean_tabula_df(df):
    """
    Cleans a dataframe extracted by Tabula.
    """
    # Remove empty rows/cols
    df = df.dropna(how='all', axis=0)
    df = df.dropna(how='all', axis=1)

    # Check if header is inside the rows (common in stream mode)
    # Look for row containing "ISIN"
    header_idx = -1
    for i, row in df.iterrows():
        row_str = " ".join([str(x) for x in row.values])
        if "ISIN" in row_str and "Vencimiento" in row_str:
            header_idx = i
            break

    if header_idx != -1:
        # Set header
        df.columns = df.iloc[header_idx]
        df = df[header_idx+1:]
        df = df.reset_index(drop=True)

    # Filter for valid data rows (must contain 'COL')
    # If columns are not named correctly yet, check values
    valid_rows = []
    for i, row in df.iterrows():
        row_str = str(row.values)
        if "COL" in row_str:
            valid_rows.append(i)

    if valid_rows:
        df = df.loc[valid_rows]
    else:
        return pd.DataFrame() # Empty if no valid data rows

    return df

def parse_text_fallback(text, date_str, filename):
    """
    Fallback function to parse text directly when tabula fails.
    """
    rows = []
    current_type = None

    lines = text.split('\n')
    for line in lines:
        line = line.strip()

        # Identify section
        if "TES RECIBIDOS POR LA NACIÓN" in line:
            current_type = "Recibidos"
            continue
        elif "TES ENTREGADOS POR LA NACIÓN" in line:
            current_type = "Entregados"
            continue

        if line.startswith("COL") and current_type:
            # Parse row
            parts = re.split(r'\s+', line)
            if len(parts) >= 8:
                entry = {}
                entry['Codigo ISIN'] = parts[0]
                entry['Vencimiento'] = parts[1]
                entry['Den'] = parts[2]
                entry['Cupón'] = parts[3]

                if '%' in parts[4]:
                    entry['Tasa'] = parts[4]
                    idx_offset = 1
                else:
                    entry['Tasa'] = ""
                    idx_offset = 0

                if len(parts) >= 8 + idx_offset:
                    entry['Precio'] = parts[4 + idx_offset]
                    entry['Valor Nominal Moneda Original'] = parts[5 + idx_offset]
                    entry['Valor Nominal COP'] = parts[6 + idx_offset]
                    entry['Valor Costo COP'] = parts[7 + idx_offset]

                    entry['Fecha'] = date_str
                    entry['Tipo'] = current_type
                    entry['Archivo'] = filename

                    rows.append(entry)

    return pd.DataFrame(rows)

def process_pdf_files(uploaded_files):
    all_dfs = []

    for uploaded_file in uploaded_files:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getvalue())
            tmp_path = tmp_file.name

        try:
            reader = PdfReader(tmp_path)
            full_text = ""
            for page in reader.pages:
                full_text += page.extract_text() + "\n"

            date_str = extract_date_from_text(full_text)

            # --- Tabula Extraction ---
            tabula_success = False
            try:
                # Use stream=True as it fits the layout better
                dfs = tabula.read_pdf(tmp_path, pages='all', stream=True, pandas_options={'header': None})

                valid_tabula_dfs = []
                if dfs:
                    for df in dfs:
                        cleaned = clean_tabula_df(df)
                        if not cleaned.empty:
                            valid_tabula_dfs.append(cleaned)

                if valid_tabula_dfs:
                    # Identify types based on text positions
                    pos_recibidos = full_text.find("TES RECIBIDOS POR LA NACIÓN")
                    pos_entregados = full_text.find("TES ENTREGADOS POR LA NACIÓN")

                    # Logic:
                    # If both exist and Recibidos < Entregados:
                    #   First table(s) -> Recibidos
                    #   Second table(s) -> Entregados
                    # This is imperfect if there are multiple tables per section,
                    # but assumes 1 table per section usually.

                    # Better Logic:
                    # Since we have the DF content, we can't really know the type from the DF content itself easily
                    # without the surrounding text context which tabula loses.
                    # HOWEVER, since the structure is simple (Recibidos then Entregados), we map by order.

                    current_idx = 0
                    if pos_recibidos != -1:
                        # Assign first table to Recibidos
                        if current_idx < len(valid_tabula_dfs):
                            valid_tabula_dfs[current_idx]['Tipo'] = "Recibidos"
                            current_idx += 1

                    if pos_entregados != -1:
                         # Assign next table to Entregados
                         if current_idx < len(valid_tabula_dfs):
                            valid_tabula_dfs[current_idx]['Tipo'] = "Entregados"
                            current_idx += 1

                    # Add common metadata
                    for df in valid_tabula_dfs:
                        df['Fecha'] = date_str
                        df['Archivo'] = uploaded_file.name
                        # Ensure columns match expected standard if needed, or leave as is.
                        # Fallback uses standard keys.
                        all_dfs.append(df)

                    tabula_success = True

            except Exception as e:
                print(f"Tabula error: {e}")

            # --- Fallback Extraction ---
            if not tabula_success:
                # Only use fallback if Tabula failed to produce valid dataframes
                # This respects the requirement to use Tabula, but ensures reliability
                df_text = parse_text_fallback(full_text, date_str, uploaded_file.name)
                if not df_text.empty:
                    all_dfs.append(df_text)

        except Exception as e:
            print(f"Error processing {uploaded_file.name}: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    if all_dfs:
        final_df = pd.concat(all_dfs, ignore_index=True)
        # Ensure column order/existence if mixed sources (unlikely)
        return final_df
    else:
        return pd.DataFrame()
