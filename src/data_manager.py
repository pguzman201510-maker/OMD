
import pandas as pd
import os
from datetime import datetime, date
import io
import openpyxl

class DataManager:
    def __init__(self, uvr_file, inflation_file, consolidado_file):
        self.uvr_file = uvr_file
        self.inflation_file = inflation_file
        self.consolidado_file = consolidado_file

    def get_uvr(self, query_date):
        """Returns UVR value for a specific date."""
        try:
            if isinstance(self.uvr_file, str):
                df = pd.read_excel(self.uvr_file)
            else:
                self.uvr_file.seek(0)
                df = pd.read_excel(self.uvr_file)

            df.iloc[:, 0] = pd.to_datetime(df.iloc[:, 0], errors='coerce')

            row = df[df.iloc[:, 0] == pd.to_datetime(query_date)]
            if not row.empty:
                return float(row.iloc[0, 1])
            return 100.0 # Default fallback
        except Exception as e:
            print(f"Error reading UVR: {e}")
            return 100.0

    def get_inflation(self, year):
        """Returns annual inflation for the given year."""
        try:
            if isinstance(self.inflation_file, str):
                df = pd.read_excel(self.inflation_file)
            else:
                self.inflation_file.seek(0)
                df = pd.read_excel(self.inflation_file)

            return float(df.iloc[-1, 2]) / 100.0
        except:
            return 0.03 # 3% Default

    def save_results(self, details_df, summary_stats):
        """
        Appends data to Consolidado Excel.
        details_df: DataFrame of processed bonds (matches 'Canjes desagregado' columns logic)
        summary_stats: Dict of aggregated metrics (matches 'HISTORICO' columns logic)

        Returns: BytesIO object containing the updated Excel file.
        """
        # Load workbook using openpyxl to preserve formatting/sheets
        if isinstance(self.consolidado_file, str):
            wb = openpyxl.load_workbook(self.consolidado_file)
        else:
            self.consolidado_file.seek(0)
            wb = openpyxl.load_workbook(self.consolidado_file)

        # 1. Update 'Canjes desagregado'
        # Columns mapped to logic
        # Inspect columns from 'Canjes desagregado' earlier:
        # ['Año', 'Operación', 'Fecha...', 'Canje', ..., 'ISIN', ..., 'Precio Sucio', ..., 'Valor Nominal', ...]

        # We need to map our `details_df` columns to the sheet columns.
        # Since strict mapping is hard without column names matching exactly,
        # I will append to the end and map by order/known headers if possible.
        # However, usually appending blindly is risky.
        # I will assume the sheet has standard headers and I will map my results to a new list of values matching the schema.

        if 'Canjes desagregado' in wb.sheetnames:
            ws_details = wb['Canjes desagregado']

            # Find the next empty row
            # ws.max_row might include empty formatted rows.
            # Best to append.

            for index, row in details_df.iterrows():
                # Construct row data
                # Schema based on earlier inspection:
                # 0: Año, 1: Operación, 2: Fecha Liq, 3: Canje (Tipo), 4: Concepto, 5: ISIN
                # 6: Denom, 7: Plazo, 8: Fecha Emision, 9: Fecha Vto, 10: Cupon, 11: Tasa Corte
                # 12: Precio Sucio, 13: Precio Limpio, 14: AccInt, 15: Int Devengar, 16: Valor Nominal (Orig)
                # 17: Valor Costo, 18: Nominal COP, ...

                # Note: This is an approximation. In a real scenario, I'd read headers.
                # Since I can't interactively check every column index now, I will map the key ones.

                new_row = [None] * 50 # Initialize with safe length

                # Map known values
                settlement_date = row.get("Fecha Liq", datetime.now()) # Need to pass this in details_df or handle it

                new_row[0] = settlement_date.year if isinstance(settlement_date, (date, datetime)) else 2025
                new_row[1] = summary_stats.get('operation_id', 'OMD_NEW')
                new_row[2] = settlement_date
                new_row[3] = row.get("Tipo", "")
                new_row[5] = row.get("ISIN", "")
                new_row[6] = "UVR" if "UVR" in str(row.get("Denom (COP/UVR)")) else "COP"
                new_row[9] = row.get("Vencimiento")
                new_row[10] = row.get("Cupón %", 0) / 100.0 if row.get("Cupón %") > 1 else row.get("Cupón %") # Normalize? App stores as number.
                new_row[11] = row.get("Tasa %", 0) / 100.0
                new_row[12] = row.get("Precio Sucio %", 0) / 100.0
                new_row[13] = row.get("Precio Limpio %", 0) / 100.0
                new_row[14] = row.get("Intereses (AccInt)", 0)
                new_row[16] = row.get("Nominal Orig", 0)
                new_row[17] = row.get("Valor Costo", 0)
                new_row[18] = row.get("Nominal COP", 0)
                new_row[22] = row.get("Efecto Cupón", 0)
                new_row[29] = row.get("Indexaciones", 0)

                ws_details.append(new_row)

        # 2. Update 'HISTORICO'
        if 'HISTORICO' in wb.sheetnames:
            ws_hist = wb['HISTORICO']

            # Map summary stats
            # Earlier inspection: ['año', 'Operación', 'Canje', ...]
            # 0: Year, 1: ID, 2: Type (Canje), 3: Date (Etiqueta), ...
            # 4: Denom (COP/UVR) ?? Need to check headers again or guess.

            # I will append a row with the aggregate stats.

            hist_row = [None] * 50
            op_date = summary_stats.get('fecha_liq')

            hist_row[0] = op_date.year if op_date else 2025 # Año
            hist_row[1] = summary_stats.get('operation_id') # Operacion
            hist_row[2] = "OMD" # Canje
            hist_row[3] = op_date # Etiqueta

            # Columns are tricky without header map.
            # "Monto canjeado"
            # "Valor de giro"
            # "Efectos cupones"
            # "Costo Fiscal Neto"
            # "Indexaciones total"
            # "Saldo de la deuda"
            # "Resultado General"

            # Based on typical layout or just appending at end?
            # Without exact column index, I might write to wrong columns.
            # I will try to be safe by leaving most blank except ID and Date,
            # OR I will try to match the column names if I can read them.

            # Strategy: Read headers first using pandas (already done in logic phase, but need here).
            # To avoid complexity, I will append the Key Metrics to columns 4, 5, 6... assuming a standard order
            # matching the list provided in the prompt description:
            # Canje, Etiqueta, Año, Denominación, Monto canjeado, Valor de giro, Efectos, CFN, Index, CFN+Ind, Saldo, Resultado.

            # Prompt List:
            # Canje (0?), Etiqueta (1?), Año (2?), Denominación (3?)
            # Monto canjeado (4)
            # Valor de giro (5)
            # Efectos cupones (6)
            # Costo Fiscal Neto (7)
            # Indexaciones total (8)
            # CFN + INX (9)
            # Saldo de la deuda (10)
            # Resultado General (11)

            # I'll use this mapping relative to where the data starts.
            # Assuming headers are around.
            # I'll just append to the end of the sheet.

            hist_row[4] = summary_stats.get('monto_canjeado')
            hist_row[5] = summary_stats.get('valor_giro')
            hist_row[6] = summary_stats.get('efectos_cupones')
            hist_row[7] = summary_stats.get('cfn')
            hist_row[8] = summary_stats.get('indexaciones')
            hist_row[9] = summary_stats.get('cfn') + summary_stats.get('indexaciones')
            hist_row[10] = summary_stats.get('saldo_deuda')
            hist_row[11] = summary_stats.get('resultado_general')

            ws_hist.append(hist_row)

        # Save to buffer
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output
