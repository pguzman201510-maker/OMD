
import streamlit as st
import pandas as pd
from logic import PDFParser, BondLogic
from data_manager import DataManager
from pdf_generator import PDFGenerator
import io
import os
from datetime import datetime

st.set_page_config(layout="wide", page_title="Calculadora OMD")

st.title("Gestión de Operaciones de Manejo de Deuda (OMD)")

# Sidebar for Config/Files
with st.sidebar:
    st.header("Carga de Archivos")

    # PDF Input
    pdf_file = st.file_uploader("Memorando OMD (PDF)", type="pdf")

    # Reference Files (Defaults from repo if available)
    st.subheader("Archivos de Referencia")

    def get_file_path(name):
        if os.path.exists(name): return name
        return None

    uvr_path = get_file_path("UVR_Unidad de valor real.xlsx")
    inf_path = get_file_path("Inflación y meta.xlsx")
    cons_path = get_file_path("Consolidado (desagregado_nodesagregado) 2025.xlsx")

    uvr_file = st.file_uploader("Histórico UVR", type="xlsx") or uvr_path
    inf_file = st.file_uploader("Inflación", type="xlsx") or inf_path
    cons_file = st.file_uploader("Consolidado", type="xlsx") or cons_path

# Main Area
if pdf_file:
    parser = PDFParser()

    # Step 1: Parse
    with st.spinner("Leyendo PDF..."):
        settlement_date, recogidos_raw, entregados_raw = parser.parse_omd(pdf_file)

    st.success(f"Fecha de Liquidación detectada: {settlement_date}")

    # Operation ID Input
    default_id = f"OMD_{settlement_date.strftime('%d%m%y')}" if settlement_date else "OMD_010125"
    operation_id = st.text_input("ID de Operación", value=default_id)

    # Step 2: Data Editor for Bonds
    st.subheader("Detalle de Títulos")

    columns = ["Tipo", "ISIN", "Vencimiento", "Denom (COP/UVR)", "Cupón %", "Tasa %", "Precio (Sucio) %", "Valor Nominal Orig", "Nominal COP (Calc)"]

    data = []

    def parse_raw(rows, type_label):
        for r in rows:
            # Map fields from logic.py parser
            data.append({
                "Tipo": type_label,
                "ISIN": r.get("ISIN", ""),
                "Vencimiento": r.get("Maturity"), # Might be None or string
                "Denom (COP/UVR)": r.get("Denom", "COP"),
                "Cupón %": r.get("Coupon", 0.0),
                "Tasa %": r.get("Yield", 0.0),
                "Precio (Sucio) %": r.get("Price", 0.0),
                "Valor Nominal Orig": r.get("Nominal", 0.0),
                "Nominal COP (Calc)": 0.0 # Calc field
            })

    if recogidos_raw:
        parse_raw(recogidos_raw, "Recogido")
    else:
        data.append({"Tipo": "Recogido", "ISIN": "", "Denom (COP/UVR)": "COP", "Valor Nominal Orig": 0.0})

    if entregados_raw:
        parse_raw(entregados_raw, "Entregado")
    else:
        data.append({"Tipo": "Entregado", "ISIN": "", "Denom (COP/UVR)": "COP", "Valor Nominal Orig": 0.0})

    df_input = pd.DataFrame(data, columns=columns)

    edited_df = st.data_editor(df_input, num_rows="dynamic", use_container_width=True)

    # Step 3: Calculate
    if st.button("Calcular Operación"):
        logic = BondLogic()
        dm = DataManager(uvr_file, inf_file, cons_file)

        results = []

        inflation = dm.get_inflation(settlement_date.year if settlement_date else 2025)
        uvr_spot = dm.get_uvr(settlement_date) if settlement_date else 100.0

        st.write(f"Parámetros usados: UVR={uvr_spot}, Inflación={inflation:.2%}")

        monto_canjeado = 0.0
        cfn = 0.0
        saldo_deuda = 0.0
        indexaciones_total = 0.0
        efectos_cupones = 0.0
        valor_giro_total = 0.0

        for index, row in edited_df.iterrows():
            try:
                bond_type = row["Tipo"]
                denom = row["Denom (COP/UVR)"]
                maturity = pd.to_datetime(row["Vencimiento"])
                coupon = float(row["Cupón %"]) / 100.0
                yield_rate = float(row["Tasa %"]) / 100.0
                dirty_price_pct = float(row["Precio (Sucio) %"]) / 100.0

                nominal_orig = float(row["Valor Nominal Orig"])

                if bond_type == "Recogido" and nominal_orig > 0:
                    nominal_orig = -nominal_orig
                elif bond_type == "Entregado" and nominal_orig < 0:
                    nominal_orig = abs(nominal_orig)

                _, acc_int_val, _ = logic.calculate_clean_price_formula(yield_rate, coupon, maturity, settlement_date)
                acc_int_pct = acc_int_val / 100.0
                clean_price_pct = dirty_price_pct - acc_int_pct

                uvr_val = uvr_spot

                nominal_cop = 0.0
                if denom == "UVR":
                    nominal_cop = nominal_orig * uvr_val
                else:
                    nominal_cop = nominal_orig

                valor_costo = nominal_cop * dirty_price_pct

                effect = logic.calculate_coupon_effect(settlement_date, maturity, coupon, nominal_cop, bond_type)

                uvr_end = logic.calculate_uvr_forward(uvr_val, inflation, settlement_date)
                indexation = 0.0
                if denom == "UVR":
                    indexation = (nominal_orig * uvr_end) - (nominal_orig * uvr_val)

                if bond_type == "Recogido":
                    monto_canjeado += abs(nominal_cop)

                saldo_deuda += nominal_cop
                efectos_cupones += effect
                indexaciones_total += indexation
                valor_giro_total += valor_costo

                results.append({
                    "Tipo": bond_type,
                    "ISIN": row["ISIN"],
                    "Vencimiento": maturity.date(),
                    "Cupón %": coupon * 100,
                    "Tasa %": yield_rate * 100,
                    "Nominal Orig": nominal_orig,
                    "Nominal COP": nominal_cop,
                    "Precio Sucio %": dirty_price_pct * 100,
                    "Precio Limpio %": clean_price_pct * 100,
                    "Intereses (AccInt)": acc_int_pct * 100,
                    "Valor Costo": valor_costo,
                    "Efecto Cupón": effect,
                    "Indexaciones": indexation,
                    "Denom (COP/UVR)": denom,
                    "Fecha Liq": settlement_date
                })

            except Exception as e:
                st.error(f"Error calculating row {index}: {e}")

        valor_giro_final = -(valor_giro_total)
        cfn = valor_giro_final + efectos_cupones
        resultado_general = saldo_deuda + (cfn + indexaciones_total)

        st.subheader("Resultados Detallados")
        df_results = pd.DataFrame(results)

        if not df_results.empty:
            st.dataframe(df_results.style.format({
                "Nominal Orig": "{:,.2f}",
                "Nominal COP": "{:,.2f}",
                "Valor Costo": "{:,.2f}",
                "Efecto Cupón": "{:,.2f}",
                "Indexaciones": "{:,.2f}"
            }))

        st.subheader("Resumen de Operación")
        col1, col2, col3 = st.columns(3)
        col1.metric("Monto Canjeado", f"{monto_canjeado:,.2f}")
        col2.metric("Costo Fiscal Neto (CFN)", f"{cfn:,.2f}")
        col3.metric("Resultado General", f"{resultado_general:,.2f}")

        # Prepare Stats for Export
        stats = {
            "operation_id": operation_id,
            "fecha_liq": settlement_date,
            "monto_canjeado": monto_canjeado,
            "valor_giro": valor_giro_final,
            "efectos_cupones": efectos_cupones,
            "cfn": cfn,
            "indexaciones": indexaciones_total,
            "saldo_deuda": saldo_deuda,
            "resultado_general": resultado_general,
            "ahorro": resultado_general
        }

        st.subheader("Descargas")
        col_down1, col_down2 = st.columns(2)

        # 1. Excel
        if cons_file:
            with st.spinner("Generando Excel actualizado..."):
                try:
                    excel_bytes = dm.save_results(df_results, stats)
                    col_down1.download_button(
                        "Descargar Consolidado (Excel)",
                        data=excel_bytes,
                        file_name=f"Consolidado_OMD_{operation_id}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                except Exception as e:
                    col_down1.error(f"Error generando Excel: {e}")
        else:
            col_down1.warning("No se ha cargado el archivo Consolidado.")

        # 2. PDF
        pdf_gen = PDFGenerator()
        df_rec = df_results[df_results["Tipo"] == "Recogido"] if not df_results.empty else pd.DataFrame()
        df_ent = df_results[df_results["Tipo"] == "Entregado"] if not df_results.empty else pd.DataFrame()

        try:
            pdf_bytes = pdf_gen.generate_report(settlement_date, operation_id, df_rec, df_ent, stats)
            col_down2.download_button(
                "Descargar Informe (PDF)",
                data=pdf_bytes,
                file_name=f"Informe_{operation_id}.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            col_down2.error(f"Error generando PDF: {e}")
