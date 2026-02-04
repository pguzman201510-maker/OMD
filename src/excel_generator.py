import pandas as pd
import io

def generate_excel(all_data):
    # Define target columns based on "Consolidado" file
    columns = [
        "Operación", "Fecha Cumplimiento y/ liquidacion", "Canje", "Concepto",
        "Nemotécnico", "Denom", "Plazo", "Fecha Emision", "Fecha Vto",
        "Cupon", "Tasa de Corte (%)", "Precio sucio", "Precio Limpio",
        "Valor Nominal", "Valor Costo", "Nominal COP", "Costo COP",
        "UVR", "Efectos cupón", "Efecto Cupón (Signo)", "UVR (Fin de periodo)", "Indexaciones"
    ]

    rows = []

    op_counter = 1

    for file_data in all_data:
        date = file_data['date']
        tipo_operacion = file_data['tipo'] # Tesorería / Mercado

        # Process Recibidos
        if not file_data['recibidos'].empty:
            for _, row in file_data['recibidos'].iterrows():
                rows.append({
                    "Operación": op_counter,
                    "Fecha Cumplimiento y/ liquidacion": date,
                    "Canje": tipo_operacion,
                    "Concepto": "Títulos Recibidos por la Nación",
                    "Nemotécnico": row.get('ISIN'),
                    "Denom": row.get('Moneda'),
                    "Plazo": None,
                    "Fecha Emision": None,
                    "Fecha Vto": row.get('Vencimiento'),
                    "Cupon": row.get('Cupón') / 100 if row.get('Cupón') else None, # Assume % stored as 7.5 not 0.075? Input parser stripped %.
                    "Tasa de Corte (%)": row.get('Tasa') / 100 if row.get('Tasa') else None,
                    "Precio sucio": row.get('Precio'),
                    "Precio Limpio": None,
                    "Valor Nominal": row.get('Valor Nominal'),
                    "Valor Costo": row.get('Valor Costo COP'), # Assuming Costo is Costo COP for now
                    "Nominal COP": row.get('Valor Nominal COP'),
                    "Costo COP": row.get('Valor Costo COP'),
                    "UVR": None,
                    "Efectos cupón": None,
                    "Efecto Cupón (Signo)": None,
                    "UVR (Fin de periodo)": None,
                    "Indexaciones": None
                })

        # Process Entregados
        if not file_data['entregados'].empty:
            for _, row in file_data['entregados'].iterrows():
                rows.append({
                    "Operación": op_counter,
                    "Fecha Cumplimiento y/ liquidacion": date,
                    "Canje": tipo_operacion,
                    "Concepto": "Títulos Entregados por la Nación",
                    "Nemotécnico": row.get('ISIN'),
                    "Denom": row.get('Moneda'),
                    "Plazo": None,
                    "Fecha Emision": None,
                    "Fecha Vto": row.get('Vencimiento'),
                    "Cupon": row.get('Cupón') / 100 if row.get('Cupón') else None,
                    "Tasa de Corte (%)": row.get('Tasa') / 100 if row.get('Tasa') else None,
                    "Precio sucio": row.get('Precio'),
                    "Precio Limpio": None,
                    "Valor Nominal": row.get('Valor Nominal'),
                    "Valor Costo": row.get('Valor Costo COP'),
                    "Nominal COP": row.get('Valor Nominal COP'),
                    "Costo COP": row.get('Valor Costo COP'),
                    "UVR": None,
                    "Efectos cupón": None,
                    "Efecto Cupón (Signo)": None,
                    "UVR (Fin de periodo)": None,
                    "Indexaciones": None
                })

        op_counter += 1

    df = pd.DataFrame(rows, columns=columns)

    output = io.BytesIO()
    # Write to Excel
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Canjes')

        # Auto-adjust column width? (Optional)

    return output.getvalue()
