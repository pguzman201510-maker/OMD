import streamlit as st
import pandas as pd
import os
import tempfile
from pdf_processor import extract_date, process_tables, process_manual_text

st.set_page_config(page_title="Extractor OMD", layout="wide")

st.title("Extractor de Operaciones de Manejo de Deuda (OMD)")

st.markdown("""
Esta aplicación permite extraer información de los memorandos OMD (PDF) y generar un archivo de Excel para el consolidado.
""")

# User Input
tipo_operacion = st.radio("Seleccione el Tipo de Operación:", ("Tesorería", "Mercado"))

uploaded_files = st.file_uploader("Cargar Memorandos (PDF)", type=["pdf"], accept_multiple_files=True)

if 'processed_files' not in st.session_state:
    st.session_state['processed_files'] = {}

def process_files():
    if not uploaded_files:
        st.warning("Por favor cargue al menos un archivo PDF.")
        return

    progress_bar = st.progress(0)

    for i, uploaded_file in enumerate(uploaded_files):
        file_id = uploaded_file.name

        # Skip if already processed successfully unless re-triggered?
        # For simplicity, we process fresh every time button is clicked.

        # Save temp file securely
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            tmp_file.write(uploaded_file.getbuffer())
            temp_path = tmp_file.name

        try:
            # Extract Data
            date = extract_date(temp_path)
            df_recibidos, df_entregados = process_tables(temp_path)

            # Store in session state
            st.session_state['processed_files'][file_id] = {
                'date': date,
                'recibidos': df_recibidos,
                'entregados': df_entregados,
                'temp_path': temp_path, # Keep tracking just in case
                'manual_needed': df_recibidos.empty and df_entregados.empty,
                'manual_text': ""
            }

        except Exception as e:
            st.error(f"Error procesando {uploaded_file.name}: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

        progress_bar.progress((i + 1) / len(uploaded_files))

if st.button("Procesar Archivos"):
    process_files()

# Display results and handle manual input
all_data_for_excel = []

if uploaded_files:
    for uploaded_file in uploaded_files:
        file_id = uploaded_file.name
        if file_id in st.session_state['processed_files']:
            data = st.session_state['processed_files'][file_id]

            st.subheader(f"Archivo: {file_id}")
            st.write(f"**Fecha de Cumplimiento:** {data['date']}")

            df_recibidos = data['recibidos']
            df_entregados = data['entregados']

            if data['manual_needed']:
                st.warning("No se encontraron tablas legibles. Por favor pegue el texto a continuación:")

                # Use a form to capture manual input without rerun issues
                with st.form(key=f"manual_form_{file_id}"):
                    manual_text = st.text_area("Texto del PDF", height=200)
                    submit_manual = st.form_submit_button("Procesar Texto Manual")

                    if submit_manual:
                        # Update the data in session state
                         df_rec, df_ent = process_manual_text(manual_text)
                         data['recibidos'] = df_rec
                         data['entregados'] = df_ent
                         data['manual_needed'] = False # Mark as resolved?
                         # Actually we just update the dfs, next rerun will show tables
                         st.rerun()

            if not df_recibidos.empty or not df_entregados.empty:
                st.write("Títulos Recibidos:")
                st.dataframe(df_recibidos)
                st.write("Títulos Entregados:")
                st.dataframe(df_entregados)

                all_data_for_excel.append({
                    "filename": file_id,
                    "date": data['date'],
                    "tipo": tipo_operacion,
                    "recibidos": df_recibidos,
                    "entregados": df_entregados
                })

if all_data_for_excel:
    st.session_state['extracted_data'] = all_data_for_excel

# Excel Generation Trigger
if 'extracted_data' in st.session_state:
    from excel_generator import generate_excel

    excel_data = generate_excel(st.session_state['extracted_data'])

    st.download_button(
        label="Descargar Excel Consolidado",
        data=excel_data,
        file_name="Consolidado_OMD_Extracted.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
