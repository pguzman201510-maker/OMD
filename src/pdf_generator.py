
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
import io

class PDFGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self.style_header = ParagraphStyle(
            'Header',
            parent=self.styles['Heading1'],
            fontSize=14,
            alignment=1 # Center
        )
        self.style_normal = self.styles['Normal']
        self.style_normal.fontSize = 8

    def generate_report(self, settlement_date, operation_id, df_recogidos, df_entregados, summary_stats):
        """
        Generates the PDF report.
        df_recogidos, df_entregados: Pandas DataFrames with calculated columns.
        summary_stats: Dict of aggregated metrics.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=landscape(letter),
                                rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)

        elements = []

        # Header
        # Replicating "Seguimiento OMD" header style roughly
        # Usually contains logo (skipped), title, date

        elements.append(Paragraph(f"SEGUIMIENTO DE OPERACIONES DE MANEJO DE DEUDA (OMD)", self.style_header))
        elements.append(Paragraph(f"Fecha de Liquidación: {settlement_date}", self.style_header))
        elements.append(Spacer(1, 0.2*inch))

        # Summary Section (Table)
        # CFN, Savings, etc.
        # "Cuadro Resumen"

        summary_data = [
            ["Indicador", "Valor (COP)"],
            ["Monto Canjeado (Recogido)", f"{summary_stats.get('monto_canjeado', 0):,.2f}"],
            ["Costo Fiscal Neto (CFN)", f"{summary_stats.get('cfn', 0):,.2f}"],
            ["Ahorro Generado", f"{summary_stats.get('ahorro', 0):,.2f}"], # Assuming Ahorro is calculated
            ["Saldo de Deuda", f"{summary_stats.get('saldo_deuda', 0):,.2f}"]
        ]

        t_summary = Table(summary_data, colWidths=[3*inch, 2*inch])
        t_summary.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        elements.append(t_summary)
        elements.append(Spacer(1, 0.3*inch))

        # Detailed Tables
        # Need to format DataFrame to List of Lists

        def df_to_table(df, title):
            if df.empty:
                return

            elements.append(Paragraph(title, self.styles['Heading2']))

            # Select columns to show
            cols_show = ['ISIN', 'Vencimiento', 'Tasa %', 'Valor Nominal Orig', 'Valor Costo', 'Efecto Cupón']
            # Add headers
            data = [cols_show]

            for index, row in df.iterrows():
                r = []
                for c in cols_show:
                    val = row.get(c, "")
                    if isinstance(val, (float, int)):
                        r.append(f"{val:,.2f}")
                    else:
                        r.append(str(val))
                data.append(r)

            t = Table(data)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                ('FONTSIZE', (0, 0), (-1, -1), 7)
            ]))
            elements.append(t)
            elements.append(Spacer(1, 0.2*inch))

        df_recogidos_display = df_recogidos
        df_entregados_display = df_entregados

        df_to_table(df_recogidos_display, "Títulos Recogidos (Tesorería / Mercado)")
        df_to_table(df_entregados_display, "Títulos Entregados")

        # Build
        doc.build(elements)
        buffer.seek(0)
        return buffer
