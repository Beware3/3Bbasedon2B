from __future__ import annotations

from io import BytesIO
import re
from typing import Callable

import pandas as pd


EXPECTED_HEADERS = [
    "Section",
    "ITC Reduction Required",
    "Invoice Status (My Action)",
    "GSTR-2B Year",
    "GSTR-2B Period",
    "GSTR-2B Original Year",
    "GSTR-2B Original Period",
    "Declared IGST",
    "Declared CGST",
    "Declared SGST",
    "Declared Cess",
    "Original and Amendment in same month",
    "Amendment moved",
    "Company Description",
    "State Description",
    "GSTIN",
    "IGST (Amt)",
    "CGST (Amt)",
    "SGST/UTGST (Amt)",
    "Cess (Amt)",
    "4B1 IGST (Amt)",
    "4B1 CGST (Amt)",
    "4B1 SGST (Amt)",
    "4B1 CESS (Amt)",
    "4B2 IGST (Amt)",
    "4B2 CGST (Amt)",
    "4B2 SGST (Amt)",
    "4B2 CESS (Amt)",
    "Delta IGST Amount",
    "Delta CGST Amount",
    "Delta SGST/UTGST Amount",
    "Delta CESS Amount",
    "Reverse Charge",
    "ITC Availability",
    "Note Type (Credit/Debit)",
]

REQUIRED_COLUMNS = [
    "Section",
    "ITC Reduction Required",
    "Invoice Status (My Action)",
    "GSTR-2B Year",
    "GSTR-2B Period",
    "GSTR-2B Original Year",
    "GSTR-2B Original Period",
    "Declared IGST",
    "Declared CGST",
    "Declared SGST",
    "Declared Cess",
]

OUT_COLS = [
    "4A1_Original",
    "4A3_Original",
    "4A4_Original",
    "4A5_Original",
    "4B1_Original",
    "4B2_Original",
    "4D1_Original",
    "4D2_Original",
    "4A1_Tax",
    "4A3_Tax",
    "4A4_Tax",
    "4A5_Tax",
    "4B1_Tax",
    "4B2_Tax",
    "4D1_Tax",
    "4D2_Tax",
    "Rule Applied",
]


def normalize_header(name: str) -> str:
    cleaned = re.sub(r"[?]+", "", str(name).strip().lower())
    cleaned = re.sub(r"\s*\(\s*", "(", cleaned)
    cleaned = re.sub(r"\s*\)\s*", ")", cleaned)
    return " ".join(cleaned.split())


def canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.map(lambda col: str(col).strip())
    canonical_headers = {normalize_header(col): col for col in EXPECTED_HEADERS}
    rename_map = {}

    for col in df.columns:
        normalized = normalize_header(col)
        if normalized in canonical_headers:
            rename_map[col] = canonical_headers[normalized]

    return df.rename(columns=rename_map)


def validate_required_columns(df: pd.DataFrame) -> list[str]:
    return [col for col in REQUIRED_COLUMNS if col not in df.columns]


def norm_itc(value) -> str:
    if str(value).strip().upper() in ["Y", "YES"]:
        return "Y"
    if str(value).strip() == "" or pd.isna(value):
        return "BLANK"
    return "N"


def norm_flag(value) -> str:
    return "Y" if str(value).strip().upper() == "Y" else "N"


def norm_token(value) -> str:
    if pd.isna(value):
        return "BLANK"
    text = str(value).strip().upper()
    if text == "":
        return "BLANK"
    return text


def get_flag_series(df: pd.DataFrame, candidates: list[str], default: str = "N") -> pd.Series:
    for col in candidates:
        if col in df.columns:
            return df[col].fillna(default).apply(norm_flag)
    return pd.Series([default] * len(df), index=df.index).apply(norm_flag)


def calc_txn(row: pd.Series) -> str:
    try:
        current = f"{int(row['GSTR-2B Year'])}{int(row['GSTR-2B Period']):02d}"
        original = f"{int(row['GSTR-2B Original Year'])}{int(row['GSTR-2B Original Period']):02d}"
        return "Y" if current == original else "N"
    except Exception:
        return "N"


def declared_type(value) -> str:
    try:
        return "NONZERO" if float(value) != 0 else "ZERO"
    except Exception:
        return "ZERO"


def note_type_matches(section: str, note_type: str, allowed: set[str]) -> bool:
    if section not in {"CDN", "CDNA"}:
        return True
    return note_type in allowed


def get_4a_bucket(row: pd.Series) -> str:
    section = norm_token(row.get("Section"))
    reverse_charge = norm_token(row.get("Reverse Charge"))
    itc_availability = norm_token(row.get("ITC Availability"))
    note_type = norm_token(row.get("Note Type (Credit/Debit)"))

    itc_allowed = {"Y", "BLANK"}
    reverse_charge_non_rcm = {"N", "BLANK", "-"}

    if section in {"IMPG", "IMPGSEZ", "IMPGA", "IMPGSEZA"} and reverse_charge in reverse_charge_non_rcm and itc_availability in itc_allowed:
        return "4A1"

    if section in {"ISD", "ISDA"} and reverse_charge in reverse_charge_non_rcm and itc_availability in itc_allowed:
        return "4A4"

    if section in {"B2B", "B2BA", "ECOM", "ECOMA"} and reverse_charge == "Y" and itc_availability in itc_allowed:
        return "4A3"

    if section in {"CDN", "CDNA"} and reverse_charge == "Y" and itc_availability in {"Y", "BLANK", "N"} and note_type_matches(section, note_type, {"C", "D"}):
        return "4A3"

    if section in {"B2B", "B2BA", "ECOM", "ECOMA"} and reverse_charge in reverse_charge_non_rcm and itc_availability in itc_allowed:
        return "4A5"

    if section in {"CDN", "CDNA"} and reverse_charge in reverse_charge_non_rcm and itc_availability in {"Y", "BLANK", "N"} and note_type_matches(section, note_type, {"C", "D"}):
        return "4A5"

    return "4A5"


def qualifies_for_4d2(row: pd.Series) -> bool:
    section = norm_token(row.get("Section"))
    reverse_charge = norm_token(row.get("Reverse Charge"))
    itc_availability = norm_token(row.get("ITC Availability"))
    note_type = norm_token(row.get("Note Type (Credit/Debit)"))

    if section in {"IMPG", "IMPGSEZ", "ISD", "ISDA", "B2B", "B2BA", "ECOM", "ECOMA"}:
        return reverse_charge in {"N", "BLANK", "Y", "-"} and itc_availability == "N"

    if section in {"CDN", "CDNA"}:
        return reverse_charge in {"N", "BLANK", "Y", "-"} and itc_availability == "N" and note_type == "D"

    return False


def route_4a_output(row: pd.Series, result: dict) -> dict:
    bucket = get_4a_bucket(row)
    routed = result.copy()

    original_value = routed.get("4A5_Original", "")
    tax_value = routed.get("4A5_Tax", "")
    routed["4A5_Original"] = ""
    routed["4A5_Tax"] = ""
    routed[f"{bucket}_Original"] = original_value
    routed[f"{bucket}_Tax"] = tax_value
    return routed


def enrich_4d2_output(row: pd.Series, result: dict) -> dict:
    enriched = result.copy()
    if qualifies_for_4d2(row):
        enriched["4D2_Original"] = "Full Amount"
        enriched["4D2_Tax"] = "Full Amount"
    return enriched


def apply_rule(row: pd.Series) -> dict:
    result = {col: "" for col in OUT_COLS}
    result["Rule Applied"] = None

    if qualifies_for_4d2(row):
        result["4D2_Original"] = "Full Amount"
        result["4D2_Tax"] = "Full Amount"
        result["Rule Applied"] = "4D2"
        return result

    s = row["Section"]
    itc = row["ITC"]
    decl = row["DECL"]
    inv = row["INV"]
    txn = row["TXN"]
    same = row["SAME"]
    moved = row["MOVED"]

    dv = "Declared Value"
    fv = "Full Value"
    delta = "Delta Value"
    b1 = "Column of 4B1"
    b2 = "Column of 4B2"

    base_sec = ["B2B", "CDN", "ECOM", "IMPG", "IMPGSEZ", "ISD"]
    amend_sec = ["B2BA", "CDNA", "ECOMA", "ISDA"]

    if decl == "NONZERO":
        if itc == "Y":
            if s in base_sec and inv == "D":
                if txn == "N" and same == "Y" and moved == "Y":
                    result.update({"4A5_Original": dv, "4B2_Original": dv, "Rule Applied": 1})
                    return route_4a_output(row, result)
                if txn == "N" and same == "Y" and moved == "N":
                    result.update({"4A5_Original": dv, "4B2_Original": dv, "4D1_Tax": dv, "Rule Applied": 2})
                    return route_4a_output(row, result)
                if txn == "Y":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "Rule Applied": 3})
                    return route_4a_output(row, result)
                if txn == "N" and same == "N":
                    result.update({"4A5_Tax": dv, "4B1_Original": dv, "4B2_Original": dv, "4D1_Tax": dv, "Rule Applied": 4})
                    return route_4a_output(row, result)

            if s in amend_sec:
                if txn == "N":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Tax": b1, "4B2_Original": dv, "4B2_Tax": b2, "4D1_Tax": dv, "Rule Applied": 5})
                    return route_4a_output(row, result)
                if txn == "Y":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Original": b1, "4B1_Tax": b1, "4B2_Original": b2, "4B2_Tax": b2, "Rule Applied": 6})
                    return route_4a_output(row, result)

            if s in base_sec:
                if txn == "N":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Tax": b1, "4B2_Original": dv, "4B2_Tax": b2, "4D1_Tax": dv, "Rule Applied": 7})
                    return route_4a_output(row, result)
                if txn == "Y":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Original": b1, "4B1_Tax": b1, "4B2_Original": b2, "4B2_Tax": b2, "Rule Applied": 8})
                    return route_4a_output(row, result)

        if itc == "N":
            if s in base_sec and inv == "D":
                if txn == "N" and same == "Y" and moved == "Y":
                    result.update({"4A5_Original": dv, "4B2_Original": dv, "Rule Applied": 9})
                    return route_4a_output(row, result)
                if txn == "N" and same == "Y" and moved == "N":
                    result.update({"4A5_Original": dv, "4B2_Original": dv, "4D1_Tax": dv, "Rule Applied": 10})
                    return route_4a_output(row, result)
                if txn == "Y":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "Rule Applied": 11})
                    return route_4a_output(row, result)
                if txn == "N" and same == "N":
                    result.update({"4A5_Tax": dv, "4B1_Original": dv, "4B2_Original": dv, "4D1_Tax": dv, "Rule Applied": 12})
                    return route_4a_output(row, result)

            if s in amend_sec:
                if txn == "N":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Tax": b1, "4B2_Original": dv, "4B2_Tax": b2, "4D1_Tax": dv, "Rule Applied": 13})
                    return route_4a_output(row, result)
                if txn == "Y":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Original": b1, "4B1_Tax": b1, "4B2_Original": b2, "4B2_Tax": b2, "Rule Applied": 14})
                    return route_4a_output(row, result)

            if s in base_sec:
                if txn == "N":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Tax": b1, "4B2_Original": dv, "4B2_Tax": b2, "4D1_Tax": dv, "Rule Applied": 15})
                    return route_4a_output(row, result)
                if txn == "Y":
                    result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Original": b1, "4B1_Tax": b1, "4B2_Original": b2, "4B2_Tax": b2, "Rule Applied": 16})
                    return route_4a_output(row, result)

    itc_yes_blank_block = (itc == "BLANK") or (itc == "Y" and decl == "ZERO")
    if itc_yes_blank_block:
        if s in base_sec and inv == "D":
            if txn == "N" and same == "Y" and moved == "Y":
                result.update({"4A5_Original": fv, "4B2_Original": fv, "Rule Applied": 17})
                return route_4a_output(row, result)
            if txn == "N" and same == "Y" and moved == "N":
                result.update({"4A5_Original": fv, "4B2_Original": fv, "4D1_Tax": fv, "Rule Applied": 18})
                return route_4a_output(row, result)
            if txn == "Y":
                result.update({"4A5_Original": fv, "4A5_Tax": fv, "Rule Applied": 19})
                return route_4a_output(row, result)
            if txn == "N" and same == "N":
                result.update({"4A5_Tax": fv, "4B1_Original": fv, "4B2_Original": fv, "4D1_Tax": fv, "Rule Applied": 20})
                return route_4a_output(row, result)

        if s in amend_sec:
            if txn == "N" and same == "Y":
                result.update({"4A5_Original": delta, "4A5_Tax": fv, "4B1_Tax": b1, "4B2_Original": delta, "4B2_Tax": b2, "4D1_Tax": fv, "Rule Applied": 21})
                return route_4a_output(row, result)
            if txn == "N":
                result.update({"4A5_Original": delta, "4A5_Tax": delta, "4B1_Tax": b1, "4B2_Original": delta, "4B2_Tax": b2, "4D1_Tax": delta, "Rule Applied": 22})
                return route_4a_output(row, result)
            if txn == "Y" and same == "Y":
                result.update({"4A5_Original": fv, "4A5_Tax": fv, "4B1_Original": b1, "4B1_Tax": b1, "4B2_Original": b2, "4B2_Tax": b2, "Rule Applied": 23})
                return route_4a_output(row, result)
            if txn == "Y":
                result.update({"4A5_Original": dv, "4A5_Tax": dv, "4B1_Original": b1, "4B1_Tax": b1, "4B2_Original": b2, "4B2_Tax": b2, "Rule Applied": 24})
                return route_4a_output(row, result)

        if s in base_sec:
            if txn == "N":
                result.update({"4A5_Original": fv, "4A5_Tax": fv, "4B1_Tax": b1, "4B2_Original": fv, "4B2_Tax": b2, "4D1_Tax": fv, "Rule Applied": 25})
                return route_4a_output(row, result)
            if txn == "Y":
                result.update({"4A5_Original": fv, "4A5_Tax": fv, "4B1_Original": b1, "4B1_Tax": b1, "4B2_Original": b2, "4B2_Tax": b2, "Rule Applied": 26})
                return route_4a_output(row, result)

    return route_4a_output(row, result)


def build_phase_two_summary(detail_df: pd.DataFrame) -> pd.DataFrame:
    summary_columns = [
        "Company Description",
        "State Description",
        "GSTIN",
        "3B Table",
        "Value for Table",
        "Sum of IGST",
        "Sum of CGST",
        "Sum of SGST/ UTGST",
        "Sum of Cess Amount",
    ]
    output_to_table = {
        "4A1_Tax": "4A1",
        "4A3_Tax": "4A3",
        "4A4_Tax": "4A4",
        "4A5_Tax": "4A5",
        "4B1_Tax": "4B1",
        "4B2_Tax": "4B2",
        "4D1_Tax": "4D1",
        "4D2_Tax": "4D2",
    }
    value_source_map = {
        "Full Value": ("IGST (Amt)", "CGST (Amt)", "SGST/UTGST (Amt)", "Cess (Amt)"),
        "Full Amount": ("IGST (Amt)", "CGST (Amt)", "SGST/UTGST (Amt)", "Cess (Amt)"),
        "Declared Value": ("Declared IGST", "Declared CGST", "Declared SGST", "Declared Cess"),
        "Delta Value": ("Delta IGST Amount", "Delta CGST Amount", "Delta SGST/UTGST Amount", "Delta CESS Amount"),
        "Column of 4B1": ("4B1 IGST (Amt)", "4B1 CGST (Amt)", "4B1 SGST (Amt)", "4B1 CESS (Amt)"),
        "Column of 4B2": ("4B2 IGST (Amt)", "4B2 CGST (Amt)", "4B2 SGST (Amt)", "4B2 CESS (Amt)"),
    }
    value_label_map = {
        "Full Value": "Full Value",
        "Full Amount": "Full Amount",
        "Declared Value": "Declared Value",
        "Delta Value": "Delta Value",
        "Column of 4B1": "Amount of 4B1",
        "Column of 4B2": "Amount of 4B2",
    }
    records = []
    working_df = detail_df.copy()

    for col in ["Company Description", "State Description", "GSTIN"]:
        if col not in working_df.columns:
            working_df[col] = ""

    for source_cols in value_source_map.values():
        for col in source_cols:
            if col not in working_df.columns:
                working_df[col] = 0

    for output_col, table_name in output_to_table.items():
        labels = working_df[output_col].fillna("").astype(str).str.strip()
        matched_rows = working_df.loc[labels != ""].copy()
        if matched_rows.empty:
            continue

        matched_rows["_value_label_raw"] = labels.loc[matched_rows.index]
        for raw_value, value_group in matched_rows.groupby("_value_label_raw"):
            source_cols = value_source_map.get(raw_value)
            value_label = value_label_map.get(raw_value)
            if not source_cols or not value_label:
                continue

            summary_frame = value_group[["Company Description", "State Description", "GSTIN"]].copy()
            summary_frame["3B Table"] = table_name
            summary_frame["Value for Table"] = value_label
            summary_frame["Sum of IGST"] = pd.to_numeric(working_df.loc[value_group.index, source_cols[0]], errors="coerce").fillna(0)
            summary_frame["Sum of CGST"] = pd.to_numeric(working_df.loc[value_group.index, source_cols[1]], errors="coerce").fillna(0)
            summary_frame["Sum of SGST/ UTGST"] = pd.to_numeric(working_df.loc[value_group.index, source_cols[2]], errors="coerce").fillna(0)
            summary_frame["Sum of Cess Amount"] = pd.to_numeric(working_df.loc[value_group.index, source_cols[3]], errors="coerce").fillna(0)
            records.append(summary_frame)

    if not records:
        return pd.DataFrame(columns=summary_columns)

    summary_df = pd.concat(records, ignore_index=True)
    summary_df = summary_df.groupby(
        ["Company Description", "State Description", "GSTIN", "3B Table", "Value for Table"],
        as_index=False,
    ).sum()
    return summary_df[summary_columns]


def prepare_input_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = canonicalize_columns(df)
    missing = validate_required_columns(df)
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    working_df = df.copy()

    for optional_text_col in ["Reverse Charge", "ITC Availability", "Note Type (Credit/Debit)"]:
        if optional_text_col not in working_df.columns:
            working_df[optional_text_col] = ""

    for col in ["Declared IGST", "Declared CGST", "Declared SGST", "Declared Cess"]:
        working_df[col] = pd.to_numeric(working_df[col], errors="coerce").fillna(0)

    working_df["Declared value (computed)"] = (
        working_df["Declared IGST"]
        + working_df["Declared CGST"]
        + working_df["Declared SGST"]
        + working_df["Declared Cess"]
    )

    working_df["ITC"] = working_df["ITC Reduction Required"].apply(norm_itc)
    working_df["TXN"] = working_df.apply(calc_txn, axis=1)
    working_df["SAME"] = get_flag_series(working_df, ["Original and Amendment in same month"])
    working_df["MOVED"] = get_flag_series(working_df, ["Amendment moved"])
    working_df["DECL"] = working_df["Declared value (computed)"].apply(declared_type)
    working_df["INV"] = working_df["Invoice Status (My Action)"].fillna("").astype(str).str.strip()

    for col in OUT_COLS:
        working_df[col] = ""

    return working_df


def process_dataframe(
    df: pd.DataFrame,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    working_df = prepare_input_dataframe(df)
    results = []
    total_rows = len(working_df)

    for idx, (_, row) in enumerate(working_df.iterrows(), start=1):
        results.append(apply_rule(row))
        if progress_callback is not None:
            progress_callback(idx, total_rows)

    result_df = pd.DataFrame(results, index=working_df.index)
    working_df[OUT_COLS] = result_df[OUT_COLS]
    summary_df = build_phase_two_summary(working_df)
    return working_df, summary_df


def dataframe_to_excel_bytes(df: pd.DataFrame, sheet_name: str) -> bytes:
    buffer = BytesIO()
    df.to_excel(buffer, index=False, sheet_name=sheet_name)
    return buffer.getvalue()


def process_excel_bytes(
    file_bytes: bytes,
    progress_callback: Callable[[int, int], None] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, bytes, bytes]:
    input_df = pd.read_excel(BytesIO(file_bytes))
    detail_df, summary_df = process_dataframe(input_df, progress_callback=progress_callback)
    detail_bytes = dataframe_to_excel_bytes(detail_df, "Detailed Output")
    summary_bytes = dataframe_to_excel_bytes(summary_df, "GSTR_2B_Table_4_Summary")
    return detail_df, summary_df, detail_bytes, summary_bytes
