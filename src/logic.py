
import pandas as pd
import numpy as np
from datetime import datetime, date
import re
import math

class BondLogic:
    def __init__(self):
        pass

    @staticmethod
    def parse_date(date_str):
        """Parses date string to datetime object."""
        try:
            return pd.to_datetime(date_str, format='%Y-%m-%d')
        except:
            return pd.to_datetime(date_str)

    @staticmethod
    def calculate_clean_price_formula(yield_rate, coupon_rate, maturity_date, settlement_date, redemption=100):
        """
        Calculates Clean Price (P) and Accrued Interest (AccInt).
        Formula: P = [Sum(C/(1+y)^(i-1+f))] + M/(1+y)^(n-1+f) - AccInt

        Using simplified annuity formula if coupon dates align, but here we likely need the general case.
        However, the prompt suggests a specific formula structure.

        Params:
        - yield_rate (y): float (e.g., 0.12375 for 12.375%)
        - coupon_rate (c_percent): float (e.g., 0.11 for 11%)
        - maturity_date: datetime
        - settlement_date: datetime
        - redemption (M): 100
        """
        # Ensure dates are datetime objects
        mat_date = pd.to_datetime(maturity_date)
        set_date = pd.to_datetime(settlement_date)

        if set_date >= mat_date:
            return 0.0, 0.0

        # Frequency: Assuming annual coupons as per prompt (n=years)
        # But commonly TES are annual. "C: Valor del cupón anual".

        # Calculate full years and fraction
        # This is a simplification. Real bond math uses exact days conventions (Actual/Actual, etc.)
        # The prompt says: "f: Fracción de año que falta para el próximo cupón (días desde liquidación al próximo cupón dividido por los días del periodo)"

        # Find next coupon date
        # Assuming coupons pay on the anniversary of maturity each year?
        # Or fixed dates? "TES" usually pay annually.

        # 1. Determine Next Coupon Date
        next_coupon = mat_date
        while next_coupon > set_date:
            prev_coupon = next_coupon
            next_coupon = next_coupon.replace(year=next_coupon.year - 1)

        # Now 'next_coupon' is strictly <= set_date. This is wrong.
        # We want the first coupon date > set_date.

        coupon_date = mat_date
        while coupon_date > set_date:
            next_coupon_date = coupon_date
            coupon_date = coupon_date.replace(year=coupon_date.year - 1)

        # next_coupon_date is the first coupon date after settlement
        # previous_coupon_date is the last coupon date before settlement (or issue date)

        prev_coupon_date = next_coupon_date.replace(year=next_coupon_date.year - 1)

        days_in_period = 365 # or 366? Standard in Colombia TES is often 365 or 360/360.
        # Prompt says: "días desde liquidación al próximo cupón dividido por los días del periodo"
        # Let's assume Actual/365 or 365 fixed as per "365" usage in prompt formulas.

        days_to_next = (next_coupon_date - set_date).days
        days_period = 365 # Prompt uses 365 in other formulas

        f = days_to_next / days_period

        # n: Number of coupons pending (including the next one)
        # Count years from next_coupon_date to maturity_date + 1
        n = next_coupon_date.year - set_date.year # Initial guess? No.

        # If next coupon is maturity, n=1.
        # If next coupon is 2026 and maturity is 2031, n = 2031-2026 + 1 = 6.
        n = (mat_date.year - next_coupon_date.year) + 1

        C = redemption * coupon_rate
        y = yield_rate
        M = redemption

        # Calculate Summation for Dirty Price
        # P_dirty = Sum( C / (1+y)^(i-1+f) ) + M / (1+y)^(n-1+f)
        # i goes from 1 to n

        sum_coupons = 0.0
        for i in range(1, int(n) + 1):
            term = C / ((1 + y) ** (i - 1 + f))
            sum_coupons += term

        redemption_term = M / ((1 + y) ** (n - 1 + f))

        dirty_price = sum_coupons + redemption_term

        # Accrued Interest (AccInt)
        # "Interés Corrido (interés devengado desde el último cupón)."
        # Days accrued = Days since prev coupon
        days_accrued = (set_date - prev_coupon_date).days

        # "Se resta al final porque la sumatoria nos da el Precio Sucio"
        # AccInt = C * (days_accrued / days_period)?
        # Or implies linear accrual? Standard is Linear.
        acc_int = C * (days_accrued / days_period)

        clean_price = dirty_price - acc_int

        return clean_price, acc_int, dirty_price

    @staticmethod
    def calculate_coupon_effect(settlement_date, maturity_date, rate, nominal, bond_type):
        """
        Calculates Coupon Effect.

        Logic:
        1. Extract day and month of settlement and maturity.
        2. Standardize to year 2000.
        3. Compare: If settlement < anniversary in that year, calculation triggers.
           Else 0.
        4. Calculation: Rate * Abs(Nominal).
        5. Sign: Recogidos (-) -> Negative result. Entregados (+) -> Positive result.
        """
        set_date = pd.to_datetime(settlement_date)
        mat_date = pd.to_datetime(maturity_date)

        # Standardize
        try:
            date_set_std = date(2000, set_date.month, set_date.day)
            date_mat_std = date(2000, mat_date.month, mat_date.day)
        except ValueError:
            # Handle leap years if 2000 doesn't work (2000 is leap, so Feb 29 is fine)
            # If original was Feb 29 and mapped to non-leap, could fail. 2000 is safe.
            date_set_std = date(2000, set_date.month, set_date.day)
            date_mat_std = date(2000, mat_date.month, mat_date.day)

        effect = 0.0

        # "Si la liquidación es cronológicamente anterior al aniversario del vencimiento en ese año, se dispara el cálculo."
        if date_set_std < date_mat_std:
            effect = rate * abs(nominal) # Rate here is Coupon Rate? Or Yield?
            # Prompt says "Cálculo: Se multiplica la tasa por el valor absoluto del nominal."
            # Usually "tasa" implies the coupon rate here for "Effect Coupon".

        # Apply sign based on bond type (Recogido vs Entregado)
        # Bond type check: If nominal is negative -> Recogido.

        # "títulos recogidos su valor nominal moneda orig debe ser negativo" -> result negative
        # "entregados debe ser positivos" -> result positive

        if nominal < 0:
            return -abs(effect)
        else:
            return abs(effect)

    @staticmethod
    def calculate_uvr_forward(uvr_val, inflation, settlement_date):
        """
        UVR (fin de periodo) = UVR * (1+Inflación)^((last_day_year - settlement)/365)
        """
        set_date = pd.to_datetime(settlement_date)
        last_day = pd.Timestamp(year=set_date.year, month=12, day=31)

        days_remaining = (last_day - set_date).days

        # Inflation is in percent? Prompt: "1+Inflación Observada". usually input as 0.0X

        uvr_forward = uvr_val * ((1 + inflation) ** (days_remaining / 365))
        return uvr_forward

    @staticmethod
    def calculate_indexation(nominal, uvr_forward, is_uvr_bond):
        """
        Si es UVR: Valor nominal * UVR (fin de periodo) - Nominal
        Else: 0? Prompt implies indexation logic for UVR.
        Wait, "Valor nominal" in formula... is this Nominal in UVR or COP?
        "Valor nominal * UVR" -> Implies Nominal is in UVR units.
        So: Nominal_UVR * UVR_Final_COP - Nominal_COP_Initial?
        Prompt: "Valor nominal * UVR (fin de periodo) - Nominal"
        Usually: Nominal_COP_End - Nominal_COP_Start
        Nominal_COP_End = Nominal_UVR * UVR_Forward
        Nominal_COP_Start = Nominal_UVR * UVR_Spot (at issuance?) Or just the Nominal input?

        Let's interpret: "Valor nominal [en UVR] * UVR (fin de periodo) - Nominal [en COP?]"
        Usually Nominal input for UVR bonds is in UVR units.
        But prompt says: "Valor nominal COP" is calculated separately.

        Let's assume: Indexation = (Nominal_UVR * UVR_Forward) - (Nominal_UVR * UVR_Spot)?
        OR: Indexation = Nominal_UVR * UVR_Forward - Nominal_COP_Transaction?

        Prompt: "Si el titulo es en UVR, entonces: Valor nominal * UVR (fin de periodo) - Nominal"
        This 'Nominal' at the end likely refers to the COP equivalent at the start OR just the UVR nominal?
        Dimensionality: UVR * COP/UVR = COP. Nominal (UVR) * COP/UVR = COP.
        So "Nominal" at the end must be in COP.

        Likely: Indexation = (Nominal_UVR * UVR_Forward) - (Nominal_UVR * UVR_Transaction)

        Ref: "Valor Costo" for UVR = UVR_t * Nominal_COP * (DirtyPrice/100)??
        Wait, earlier: "Si es en UVR, entonces: UVR_t * Valor Nominal COP * (Precio Sucio/100)"
        This sounds like "Valor Nominal COP" is actually Nominal in UVR Units?
        Because UVR_t * Nominal_UVR * Price% = Cost in COP.
        If Nominal was already COP, why multiply by UVR_t?

        Assumption: The input "Valor Nominal Moneda Original" for UVR bonds is in UVR units.
        "Valor Nominal COP" (calculated) = Nominal_Original * UVR_Spot?

        Prompt: "Se calcula la UVR que es: (valor nominal cop)/(valor nominal moneda original)"
        This implies we derive the UVR spot from the inputs if provided, or vice versa.

        Let's stick to the Indexation formula:
        Indexation = (Nominal_Original_UVR * UVR_Forward) - (Nominal_Original_UVR * UVR_Spot)
        Which simplifies to Nominal_Original_UVR * (UVR_Forward - UVR_Spot).

        But the prompt says: "Valor nominal * UVR (fin de periodo) - Nominal"
        If "Nominal" refers to Nominal COP Value at Transaction (Nominal_Original * UVR_Spot).
        Then yes.
        """
        if not is_uvr_bond:
            return 0.0

        # See logic in method calculate_row
        return 0.0

import pypdf
import io

class PDFParser:
    def __init__(self):
        pass

    def extract_text(self, pdf_file):
        reader = pypdf.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text

    def parse_omd(self, pdf_file):
        """
        Parses the OMD PDF to extract:
        1. Settlement Date
        2. Tables for Recogidos and Entregados
        """
        text = self.extract_text(pdf_file)

        # 1. Date
        # "Bogotá D. C., 19 de diciembre de 2025"
        date_pattern = r"Bogotá D\.?\s*C\.?,\s*(\d{1,2})\s+de\s+([A-Za-z]+)\s+de\s+(\d{4})"
        match = re.search(date_pattern, text)

        settlement_date = None
        if match:
            day, month_str, year = match.groups()
            months = {
                "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
            }
            try:
                settlement_date = date(int(year), months[month_str.lower()], int(day))
            except:
                pass

        # 2. Extract Tables
        # Strategy: Split text by "TES RECIBIDOS" and "TES ENTREGADOS"
        # Then look for lines that look like bond rows
        # Row Format: ISIN | Vencimiento | Den | Cupon | Tasa | Precio | Nominal Orig | Nominal COP

        # Normalize text
        lines = text.split('\n')

        recogidos_rows = []
        entregados_rows = []

        current_section = None

        # Regex to match a bond line
        # COL17... 2031-05-21 UVR 3.00% 4.500% 102.34 ...
        # This is hard due to varying whitespace.
        # But we know the columns.

        for line in lines:
            line = line.strip()
            if "TES RECIBIDOS POR LA NACIÓN" in line or "TÍTULOS RECOGIDOS" in line.upper():
                current_section = "RECOGIDOS"
                continue
            if "TES ENTREGADOS POR LA NACIÓN" in line or "TÍTULOS ENTREGADOS" in line.upper():
                current_section = "ENTREGADOS"
                continue

            # Skip headers
            if "CÓDIGO ISIN" in line or "VENCIMIENTO" in line:
                continue

            # Attempt to parse row
            # Look for ISIN (starts with CO or similar, alphanumeric)
            # CO12TE000000
            if re.match(r'^[A-Z0-9]{10,12}', line):
                row_data = self.extract_bond_row_data(line)
                row_data["Type"] = current_section
                row_data["Raw"] = line

                if current_section == "RECOGIDOS":
                    recogidos_rows.append(row_data)
                elif current_section == "ENTREGADOS":
                    entregados_rows.append(row_data)

        return settlement_date, recogidos_rows, entregados_rows

    def extract_bond_row_data(self, line):
        """
        Heuristic extraction of bond data from a line.
        Expected columns: ISIN, Vencimiento, Den, Cupon, Tasa, Precio, Nom Orig, Nom COP
        Example: COL17CT04134 15-dic-26 COP 0,00% 10,655% 90,471 9.716.595.800.000 ...
        """
        parts = line.split()
        data = {
            "ISIN": "",
            "Maturity": None,
            "Denom": "COP",
            "Coupon": 0.0,
            "Yield": 0.0,
            "Price": 0.0,
            "Nominal": 0.0
        }

        if not parts:
            return data

        # 1. ISIN
        if re.match(r'^[A-Z0-9]{10,12}$', parts[0]):
            data["ISIN"] = parts[0]

        # Helper for Spanish Month Date
        def parse_spanish_date(d_str):
            # 15-dic-26 or 15-Dic-26
            match = re.match(r'(\d{1,2})-([a-zA-Z]{3})-(\d{2,4})', d_str)
            if match:
                d, m, y = match.groups()
                months = {
                    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
                    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12
                }
                m_num = months.get(m.lower()[:3], 0)
                if m_num == 0: return None

                y_num = int(y)
                if y_num < 100: y_num += 2000 # Assume 20xx

                try:
                    return date(y_num, m_num, int(d))
                except:
                    return None
            return None

        # Helper for Number
        def parse_number(n_str):
            # Remove %
            n = n_str.replace('%', '')
            # Handle dots as thousand, comma as decimal (Spanish format)
            # 9.716.595.800.000 -> 9716595800000
            # 90,471 -> 90.471
            # 0,00 -> 0.00
            if ',' in n and '.' in n:
                # Both used. Assume dot is thousand, comma is decimal
                n = n.replace('.', '').replace(',', '.')
            elif ',' in n:
                # Comma only. Likely decimal (European)
                n = n.replace(',', '.')
            # If dot only, ambiguous. But in this PDF, dot seems to be thousand (nominal) OR decimal (price?)
            # Wait, Price 90,471 (comma).
            # Nominal 9.716.595 (dot).
            # So DOT is Thousand, COMMA is Decimal.
            elif '.' in n:
                # 10.000 -> 10000? Or 10.00?
                # Usually nominals are large, so 10.000 is 10k.
                # Yields are small. 10.5.
                # But here yields are 10,655%. So comma.
                # So dot is purely thousand separator.
                n = n.replace('.', '')

            try:
                return float(n)
            except:
                return None

        nums = []
        denom = "COP"

        for p in parts[1:]:
            # Check Denom
            if p.upper() in ["UVR", "COP", "PESOS"]:
                denom = "UVR" if p.upper() == "UVR" else "COP"
                continue

            # Check Date
            d = parse_spanish_date(p)
            if d:
                data["Maturity"] = d
                continue

            # Check Number
            val = parse_number(p)
            if val is not None:
                nums.append(val)

        data["Denom"] = denom

        # Heuristic Assignment
        # Columns in PDF: Cupón, Tasa, Precio, Valor Nominal Original, ...
        # Strategy: Pivot around Price (typically 40-160)

        price_idx = -1
        for i, n in enumerate(nums):
            # Price typically between 40 and 160%
            # Yield/Coupon typically < 30%
            if 40 <= n <= 160:
                price_idx = i
                break

        if price_idx != -1:
            data["Price"] = nums[price_idx]

            # Nominal is usually immediately after Price
            if len(nums) > price_idx + 1:
                data["Nominal"] = nums[price_idx + 1]

            # Values before Price are Yield and Coupon
            if price_idx == 1:
                # [Yield, Price, ...] -> Coupon is missing (0)
                data["Yield"] = nums[0]
                data["Coupon"] = 0.0
            elif price_idx >= 2:
                # [Coupon, Yield, Price, ...]
                data["Yield"] = nums[price_idx - 1]
                data["Coupon"] = nums[price_idx - 2]
            elif price_idx == 0:
                # [Price, Nominal...] -> Missing Yield/Coupon? Unlikely structure but safe default
                data["Coupon"] = 0.0
                data["Yield"] = 0.0

        else:
            # Fallback if Price not identified (e.g. Price < 40? Distress?)
            # Use strict position if len >= 3
            if len(nums) >= 4:
                data["Coupon"] = nums[0]
                data["Yield"] = nums[1]
                data["Price"] = nums[2]
                data["Nominal"] = nums[3]
            elif len(nums) == 3:
                data["Coupon"] = 0.0
                data["Yield"] = nums[0]
                data["Price"] = nums[1]
                data["Nominal"] = nums[2]

        return data

        return settlement_date, recogidos_rows, entregados_rows
