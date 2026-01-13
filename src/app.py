import streamlit as st
import pandas as pd
from logic import process_pdf_files
from io import BytesIO

st.set_page_config(page_title="Consolidación de Memorandos OMD", layout="wide")

st.title("Consolidación de Memorandos OMD")
st.write("Carga los archivos PDF (Memorandos) para extraer y consolidar las tablas.")

uploaded_files = st.file_uploader("Seleccionar archivos PDF", type="pdf", accept_multiple_files=True)

if uploaded_files:
    if st.button("Procesar Archivos"):
        with st.spinner("Procesando archivos..."):
            try:
                consolidated_df = process_pdf_files(uploaded_files)

                if not consolidated_df.empty:
                    st.success("Archivos procesados correctamente.")
                    st.write("### Vista Previa de Datos Consolidados")
                    st.dataframe(consolidated_df)

                    # Convert to Excel
                    output = BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        consolidated_df.to_excel(writer, index=False, sheet_name='Consolidado')
                    output.seek(0)

                    st.download_button(
                        label="Descargar Excel",
                        data=output,
                        file_name="Consolidado_OMD.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("No se encontraron tablas validas en los archivos proporcionados.")
            except Exception as e:
                st.error(f"Ocurrió un error al procesar los archivos: {e}")
