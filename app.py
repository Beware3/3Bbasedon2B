import streamlit as st
import pandas as pd
from io import BytesIO
import re

from gst_engine import process_dataframe


st.set_page_config(page_title="GST Rule Engine", layout="wide")
st.title("📊 GST Rule Engine - 4A5 / 4B / 4D")
@@ -10,418 +12,34 @@

if uploaded_file:
file_token = f"{uploaded_file.name}:{uploaded_file.size}"
    if st.session_state.get('uploaded_file_token') != file_token:
        st.session_state['uploaded_file_token'] = file_token
        st.session_state['output_ready'] = False
        st.session_state['output_bytes'] = None
        st.session_state['summary_ready'] = False
        st.session_state['summary_bytes'] = None
    if st.session_state.get("uploaded_file_token") != file_token:
        st.session_state["uploaded_file_token"] = file_token
        st.session_state["output_ready"] = False
        st.session_state["output_bytes"] = None
        st.session_state["summary_ready"] = False
        st.session_state["summary_bytes"] = None

df = pd.read_excel(uploaded_file)
    df.columns = df.columns.map(lambda col: str(col).strip())

st.success("✅ File uploaded successfully")

    def normalize_header(name):
        cleaned = re.sub(r'[?]+', '', str(name).strip().lower())
        cleaned = re.sub(r'\s*\(\s*', '(', cleaned)
        cleaned = re.sub(r'\s*\)\s*', ')', cleaned)
        return ' '.join(cleaned.split())

    expected_headers = [
        'Section',
        'ITC Reduction Required',
        'Invoice Status (My Action)',
        'GSTR-2B Year',
        'GSTR-2B Period',
        'GSTR-2B Original Year',
        'GSTR-2B Original Period',
        'Declared IGST',
        'Declared CGST',
        'Declared SGST',
        'Declared Cess',
        'Original and Amendment in same month',
        'Amendment moved',
        'Company Description',
        'State Description',
        'GSTIN',
        'IGST (Amt)',
        'CGST (Amt)',
        'SGST/UTGST (Amt)',
        'Cess (Amt)',
        '4B1 IGST (Amt)',
        '4B1 CGST (Amt)',
        '4B1 SGST (Amt)',
        '4B1 CESS (Amt)',
        '4B2 IGST (Amt)',
        '4B2 CGST (Amt)',
        '4B2 SGST (Amt)',
        '4B2 CESS (Amt)',
        'Delta IGST Amount',
        'Delta CGST Amount',
        'Delta SGST/UTGST Amount',
        'Delta CESS Amount'
    ]
    canonical_headers = {normalize_header(col): col for col in expected_headers}
    rename_map = {}

    for col in df.columns:
        normalized = normalize_header(col)
        if normalized in canonical_headers:
            rename_map[col] = canonical_headers[normalized]

    df = df.rename(columns=rename_map)

    # -----------------------------
    # REQUIRED COLUMNS
    # -----------------------------
    required_cols = [
        'Section',
        'ITC Reduction Required',
        'Invoice Status (My Action)',
        'GSTR-2B Year',
        'GSTR-2B Period',
        'GSTR-2B Original Year',
        'GSTR-2B Original Period',
        'Declared IGST',
        'Declared CGST',
        'Declared SGST',
        'Declared Cess'
    ]

    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        st.error(f"❌ Missing columns: {missing}")
        st.stop()

    # -----------------------------
    # NORMALIZATION
    # -----------------------------
    def norm_itc(x):
        if str(x).strip().upper() in ['Y', 'YES']:
            return 'Y'
        if str(x).strip() == '' or pd.isna(x):
            return 'BLANK'
        return 'N'

    def norm_flag(x):
        return 'Y' if str(x).strip().upper() == 'Y' else 'N'

    def get_flag_series(df, candidates, default='N'):
        for col in candidates:
            if col in df.columns:
                return df[col].fillna(default).apply(norm_flag)
        return pd.Series([default] * len(df), index=df.index).apply(norm_flag)

    def calc_txn(row):
        try:
            current = f"{int(row['GSTR-2B Year'])}{int(row['GSTR-2B Period']):02d}"
            original = f"{int(row['GSTR-2B Original Year'])}{int(row['GSTR-2B Original Period']):02d}"
            return 'Y' if current == original else 'N'
        except:
            return 'N'

    def declared_type(x):
        try:
            return "NONZERO" if float(x) != 0 else "ZERO"
        except:
            return "ZERO"

    # -----------------------------
    # DECLARED VALUE CALCULATION
    # -----------------------------
    for col in ['Declared IGST','Declared CGST','Declared SGST','Declared Cess']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['Declared value (computed)'] = (
        df['Declared IGST'] +
        df['Declared CGST'] +
        df['Declared SGST'] +
        df['Declared Cess']
    )

    # -----------------------------
    # APPLY NORMALIZATION
    # -----------------------------
    df['ITC'] = df['ITC Reduction Required'].apply(norm_itc)
    df['TXN'] = df.apply(calc_txn, axis=1)

    df['SAME'] = get_flag_series(df, ['Original and Amendment in same month'])
    df['MOVED'] = get_flag_series(df, ['Amendment moved'])

    df['DECL'] = df['Declared value (computed)'].apply(declared_type)
    df['INV'] = df['Invoice Status (My Action)'].fillna('').astype(str).str.strip()

    # -----------------------------
    # OUTPUT INIT
    # -----------------------------
    out_cols = [
        '4A5_Original',
        '4B1_Original',
        '4B2_Original',
        '4D1_Original',
        '4A5_Tax',
        '4B1_Tax',
        '4B2_Tax',
        '4D1_Tax',
        'Rule Applied'
    ]

    for c in out_cols:
        df[c] = ""

    # -----------------------------
    # RULE ENGINE
    # -----------------------------
    def apply_rule(r):

        res = {c:"" for c in out_cols}
        res['Rule Applied'] = None

        s = r['Section']
        itc = r['ITC']
        decl = r['DECL']
        inv = r['INV']
        txn = r['TXN']
        same = r['SAME']
        moved = r['MOVED']

        DV = "Declared Value"
        FV = "Full Value"
        DELTA = "Delta Value"
        B1 = "Column of 4B1"
        B2 = "Column of 4B2"

        base_sec = ['B2B','CDN','ECOM','IMPG','IMPGSEZ','ISD']
        amend_sec = ['B2BA','CDNA','ECOMA','ISDA']

        # -------- NONZERO --------
        if decl == 'NONZERO':

            if itc == 'Y':

                if s in base_sec and inv == 'D':

                    if txn=='N' and same=='Y' and moved=='Y':
                        res.update({'4A5_Original':DV,'4B2_Original':DV,'Rule Applied':1})
                        return res

                    if txn=='N' and same=='Y' and moved=='N':
                        res.update({'4A5_Original':DV,'4B2_Original':DV,'4D1_Tax':DV,'Rule Applied':2})
                        return res

                    if txn=='Y':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'Rule Applied':3})
                        return res

                    if txn=='N' and same=='N':
                        res.update({'4A5_Tax':DV,'4B1_Original':DV,'4B2_Original':DV,'4D1_Tax':DV,'Rule Applied':4})
                        return res

                if s in amend_sec:

                    if txn=='N':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Tax':B1,'4B2_Original':DV,'4B2_Tax':B2,'4D1_Tax':DV,'Rule Applied':5})
                        return res

                    if txn=='Y':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Original':B1,'4B1_Tax':B1,'4B2_Original':B2,'4B2_Tax':B2,'Rule Applied':6})
                        return res

                if s in base_sec:

                    if txn=='N':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Tax':B1,'4B2_Original':DV,'4B2_Tax':B2,'4D1_Tax':DV,'Rule Applied':7})
                        return res

                    if txn=='Y':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Original':B1,'4B1_Tax':B1,'4B2_Original':B2,'4B2_Tax':B2,'Rule Applied':8})
                        return res

            if itc == 'N':

                if s in base_sec and inv=='D':

                    if txn=='N' and same=='Y' and moved=='Y':
                        res.update({'4A5_Original':DV,'4B2_Original':DV,'Rule Applied':9})
                        return res

                    if txn=='N' and same=='Y' and moved=='N':
                        res.update({'4A5_Original':DV,'4B2_Original':DV,'4D1_Tax':DV,'Rule Applied':10})
                        return res

                    if txn=='Y':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'Rule Applied':11})
                        return res

                    if txn=='N' and same=='N':
                        res.update({'4A5_Tax':DV,'4B1_Original':DV,'4B2_Original':DV,'4D1_Tax':DV,'Rule Applied':12})
                        return res

                if s in amend_sec:

                    if txn=='N':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Tax':B1,'4B2_Original':DV,'4B2_Tax':B2,'4D1_Tax':DV,'Rule Applied':13})
                        return res

                    if txn=='Y':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Original':B1,'4B1_Tax':B1,'4B2_Original':B2,'4B2_Tax':B2,'Rule Applied':14})
                        return res

                if s in base_sec:

                    if txn=='N':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Tax':B1,'4B2_Original':DV,'4B2_Tax':B2,'4D1_Tax':DV,'Rule Applied':15})
                        return res

                    if txn=='Y':
                        res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Original':B1,'4B1_Tax':B1,'4B2_Original':B2,'4B2_Tax':B2,'Rule Applied':16})
                        return res

        # -------- ZERO --------
        if decl == 'ZERO':

            if s in base_sec and inv=='D':

                if txn=='N' and same=='Y' and moved=='Y':
                    res.update({'4A5_Original':FV,'4B2_Original':FV,'Rule Applied':17})
                    return res

                if txn=='N' and same=='Y' and moved=='N':
                    res.update({'4A5_Original':FV,'4B2_Original':FV,'4D1_Tax':FV,'Rule Applied':18})
                    return res

                if txn=='Y':
                    res.update({'4A5_Original':FV,'4A5_Tax':FV,'Rule Applied':19})
                    return res

                if txn=='N' and same=='N':
                    res.update({'4A5_Tax':FV,'4B1_Original':FV,'4B2_Original':FV,'4D1_Tax':FV,'Rule Applied':20})
                    return res

            if s in amend_sec:

                if txn=='N' and same=='Y':
                    res.update({'4A5_Original':DELTA,'4A5_Tax':FV,'4B1_Tax':B1,'4B2_Original':DELTA,'4B2_Tax':B2,'4D1_Tax':FV,'Rule Applied':21})
                    return res

                if txn=='N':
                    res.update({'4A5_Original':DELTA,'4A5_Tax':DELTA,'4B1_Tax':B1,'4B2_Original':DELTA,'4B2_Tax':B2,'4D1_Tax':DELTA,'Rule Applied':22})
                    return res

                if txn=='Y' and same=='Y':
                    res.update({'4A5_Original':FV,'4A5_Tax':FV,'4B1_Original':B1,'4B1_Tax':B1,'4B2_Original':B2,'4B2_Tax':B2,'Rule Applied':23})
                    return res

                if txn=='Y':
                    res.update({'4A5_Original':DV,'4A5_Tax':DV,'4B1_Original':B1,'4B1_Tax':B1,'4B2_Original':B2,'4B2_Tax':B2,'Rule Applied':24})
                    return res

            if s in base_sec:

                if txn=='N':
                    res.update({'4A5_Original':FV,'4A5_Tax':FV,'4B1_Tax':B1,'4B2_Original':FV,'4B2_Tax':B2,'4D1_Tax':FV,'Rule Applied':25})
                    return res

                if txn=='Y':
                    res.update({'4A5_Original':FV,'4A5_Tax':FV,'4B1_Original':B1,'4B1_Tax':B1,'4B2_Original':B2,'4B2_Tax':B2,'Rule Applied':26})
                    return res

        return res

    def build_phase_two_summary(detail_df):
        summary_columns = [
            'Company Description',
            'State Description',
            'GSTIN',
            '3B Table',
            'Value for Table',
            'Sum of IGST',
            'Sum of CGST',
            'Sum of SGST/ UTGST',
            'Sum of Cess Amount',
        ]
        output_to_table = {
            '4A5_Tax': '4A5',
            '4B1_Tax': '4B1',
            '4B2_Tax': '4B2',
            '4D1_Tax': '4D1',
        }
        value_source_map = {
            'Full Value': ('IGST (Amt)', 'CGST (Amt)', 'SGST/UTGST (Amt)', 'Cess (Amt)'),
            'Declared Value': ('Declared IGST', 'Declared CGST', 'Declared SGST', 'Declared Cess'),
            'Delta Value': ('Delta IGST Amount', 'Delta CGST Amount', 'Delta SGST/UTGST Amount', 'Delta CESS Amount'),
            'Column of 4B1': ('4B1 IGST (Amt)', '4B1 CGST (Amt)', '4B1 SGST (Amt)', '4B1 CESS (Amt)'),
            'Column of 4B2': ('4B2 IGST (Amt)', '4B2 CGST (Amt)', '4B2 SGST (Amt)', '4B2 CESS (Amt)'),
        }
        value_label_map = {
            'Full Value': 'Full Value',
            'Declared Value': 'Declared Value',
            'Delta Value': 'Delta Value',
            'Column of 4B1': 'Amount of 4B1',
            'Column of 4B2': 'Amount of 4B2',
        }
        records = []
        working_df = detail_df.copy()

        for col in ['Company Description', 'State Description', 'GSTIN']:
            if col not in working_df.columns:
                working_df[col] = ''

        for source_cols in value_source_map.values():
            for col in source_cols:
                if col not in working_df.columns:
                    working_df[col] = 0

        for output_col, table_name in output_to_table.items():
            labels = working_df[output_col].fillna('').astype(str).str.strip()
            matched_rows = working_df.loc[labels != ''].copy()
            if matched_rows.empty:
                continue

            matched_rows['_value_label_raw'] = labels.loc[matched_rows.index]
            for raw_value, value_group in matched_rows.groupby('_value_label_raw'):
                source_cols = value_source_map.get(raw_value)
                value_label = value_label_map.get(raw_value)
                if not source_cols or not value_label:
                    continue

                summary_frame = value_group[['Company Description', 'State Description', 'GSTIN']].copy()
                summary_frame['3B Table'] = table_name
                summary_frame['Value for Table'] = value_label
                summary_frame['Sum of IGST'] = pd.to_numeric(working_df.loc[value_group.index, source_cols[0]], errors='coerce').fillna(0)
                summary_frame['Sum of CGST'] = pd.to_numeric(working_df.loc[value_group.index, source_cols[1]], errors='coerce').fillna(0)
                summary_frame['Sum of SGST/ UTGST'] = pd.to_numeric(working_df.loc[value_group.index, source_cols[2]], errors='coerce').fillna(0)
                summary_frame['Sum of Cess Amount'] = pd.to_numeric(working_df.loc[value_group.index, source_cols[3]], errors='coerce').fillna(0)
                records.append(summary_frame)

        if not records:
            return pd.DataFrame(columns=summary_columns)

        summary_df = pd.concat(records, ignore_index=True)
        summary_df = summary_df.groupby(
            ['Company Description', 'State Description', 'GSTIN', '3B Table', 'Value for Table'],
            as_index=False
        ).sum()
        return summary_df[summary_columns]

generate = st.button("Generate Calculation", type="primary")

download_button_placeholder = st.empty()
summary_button_placeholder = st.empty()
    if st.session_state.get('output_ready', False) and st.session_state.get('output_bytes'):

    if st.session_state.get("output_ready", False) and st.session_state.get("output_bytes"):
download_button_placeholder.download_button(
"⬇ Download Output",
            data=st.session_state['output_bytes'],
            data=st.session_state["output_bytes"],
file_name="output.xlsx",
)
else:
download_button_placeholder.info("Generate the calculation to enable output download.")

    if st.session_state.get('summary_ready', False) and st.session_state.get('summary_bytes'):
    if st.session_state.get("summary_ready", False) and st.session_state.get("summary_bytes"):
summary_button_placeholder.download_button(
"⬇ Download Summary Output",
            data=st.session_state['summary_bytes'],
            data=st.session_state["summary_bytes"],
file_name="summary_output.xlsx",
)
else:
@@ -431,57 +49,48 @@ def build_phase_two_summary(detail_df):
progress_banner = st.info("Calculation is in progress. Expected time: a few seconds.")
progress_bar = st.progress(0, text="Calculation progress: 0%")

        # -----------------------------
        # APPLY RULES
        # -----------------------------
try:
            with st.spinner("Generating calculation file..."):
                results = []
                total_rows = len(df)

                for idx, (_, row) in enumerate(df.iterrows(), start=1):
                    results.append(apply_rule(row))
                    progress_pct = int(idx * 100 / total_rows) if total_rows else 100
                    progress_bar.progress(
                        progress_pct,
                        text=f"Calculation progress: {progress_pct}% ({idx}/{total_rows} rows)",
                    )
            def update_progress(current: int, total: int) -> None:
                progress_pct = int(current * 100 / total) if total else 100
                progress_bar.progress(
                    progress_pct,
                    text=f"Calculation progress: {progress_pct}% ({current}/{total} rows)",
                )

                result = pd.DataFrame(results, index=df.index)
                df[out_cols] = result[out_cols]
            with st.spinner("Generating calculation file..."):
                detail_df, summary_df = process_dataframe(df, progress_callback=update_progress)

output_buffer = BytesIO()
                df.to_excel(output_buffer, index=False)
                st.session_state['output_bytes'] = output_buffer.getvalue()
                st.session_state['output_ready'] = True
                detail_df.to_excel(output_buffer, index=False)
                st.session_state["output_bytes"] = output_buffer.getvalue()
                st.session_state["output_ready"] = True

                summary_df = build_phase_two_summary(df)
summary_buffer = BytesIO()
                summary_df.to_excel(summary_buffer, index=False, sheet_name='GSTR_2B_Table_4_Summary')
                st.session_state['summary_bytes'] = summary_buffer.getvalue()
                st.session_state['summary_ready'] = True
                summary_df.to_excel(summary_buffer, index=False, sheet_name="GSTR_2B_Table_4_Summary")
                st.session_state["summary_bytes"] = summary_buffer.getvalue()
                st.session_state["summary_ready"] = True

download_button_placeholder.download_button(
"⬇ Download Output",
                    data=st.session_state['output_bytes'],
                    data=st.session_state["output_bytes"],
file_name="output.xlsx",
)
summary_button_placeholder.download_button(
"⬇ Download Summary Output",
                    data=st.session_state['summary_bytes'],
                    data=st.session_state["summary_bytes"],
file_name="summary_output.xlsx",
)

progress_banner.success("Calculation completed. File is ready to download.")
            progress_bar.progress(100, text=f"Calculation progress: 100% ({len(df)}/{len(df)} rows)")
            progress_bar.progress(100, text=f"Calculation progress: 100% ({len(detail_df)}/{len(detail_df)} rows)")
st.success("✅ Rules applied successfully")
            st.dataframe(df.head(50), use_container_width=True)
            st.dataframe(detail_df.head(50), use_container_width=True)

except Exception as e:
            st.session_state['output_ready'] = False
            st.session_state['output_bytes'] = None
            st.session_state['summary_ready'] = False
            st.session_state['summary_bytes'] = None
            st.session_state["output_ready"] = False
            st.session_state["output_bytes"] = None
            st.session_state["summary_ready"] = False
            st.session_state["summary_bytes"] = None
download_button_placeholder.info("Generate the calculation to enable output download.")
summary_button_placeholder.info("Generate the calculation to enable summary download.")
progress_banner.error("Calculation failed.")