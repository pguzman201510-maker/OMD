import streamlit as st
import pandas as pd
import os
import tempfile
from pdf_processor import extract_date, process_tables

st.set_page_config(page_title="Extractor OMD", layout="wide")

st.title("Extractor de Operaciones de Manejo de Deuda (OMD)")

st.markdown("""
Esta aplicación permite extraer información de los memorandos OMD (PDF) y generar un archivo de Excel para el consolidado.
""")

# User Input
tipo_operacion = st.radio("Seleccione el Tipo de Operación:", ("Tesorería", "Mercado"))

uploaded_files = st.file_uploader("Cargar Memorandos (PDF)", type=["pdf"], accept_multiple_files=True)

if st.button("Procesar Archivos"):
    if not uploaded_files:
        st.warning("Por favor cargue al menos un archivo PDF.")
    else:
        all_data = []

        progress_bar = st.progress(0)

        for i, uploaded_file in enumerate(uploaded_files):
            # Save temp file securely
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
                tmp_file.write(uploaded_file.getbuffer())
                temp_path = tmp_file.name

            try:
                # Extract Data
                st.subheader(f"Procesando: {uploaded_file.name}")
                date = extract_date(temp_path)
                st.write(f"**Fecha de Cumplimiento:** {date}")

                df_recibidos, df_entregados = process_tables(temp_path)

                if df_recibidos.empty and df_entregados.empty:
                    st.error("No se encontraron tablas legibles. Puede que el PDF sea una imagen.")
                else:
                    st.write("Títulos Recibidos:")
                    st.dataframe(df_recibidos)

                    st.write("Títulos Entregados:")
                    st.dataframe(df_entregados)

                    # Add metadata for Excel generation
                    # We need to store this data
                    file_data = {
                        "filename": uploaded_file.name,
                        "date": date,
                        "tipo": tipo_operacion,
                        "recibidos": df_recibidos,
                        "entregados": df_entregados
                    }
                    all_data.append(file_data)

            except Exception as e:
                st.error(f"Error procesando {uploaded_file.name}: {e}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

            progress_bar.progress((i + 1) / len(uploaded_files))

        if all_data:
            st.success("Procesamiento completado.")

            # Store data in session state to persist for download button
            st.session_state['extracted_data'] = all_data

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
