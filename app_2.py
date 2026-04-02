import streamlit as st
import hashlib
import pandas as pd
from io import BytesIO

from gst_engine_ruletable import process_dataframe

# -----------------------------
# PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="GST Rule Engine", layout="wide")
st.title("📊 GST Rule Engine - Table 4 Automation")

# -----------------------------
# SESSION STATE INIT
# -----------------------------
for key, value in {
    "output_ready": False,
    "output_bytes": None,
    "summary_ready": False,
    "summary_bytes": None,
    "detail_preview": None,
    "last_processed_file_hash": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

# -----------------------------
# FILE UPLOAD
# -----------------------------
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    download_placeholder = st.empty()
    summary_placeholder = st.empty()

    file_bytes = uploaded_file.getvalue()
    current_file_hash = hashlib.sha256(file_bytes).hexdigest()

    needs_processing = (
        st.session_state.last_processed_file_hash != current_file_hash
        or not st.session_state.output_ready
    )

    preview_to_show = None

    if needs_processing:
        try:
            df = pd.read_excel(BytesIO(file_bytes))
            st.success("✅ File uploaded successfully")

        except Exception as e:
            st.error(f"❌ Error reading file: {e}")
            st.stop()

        st.session_state.output_ready = False
        st.session_state.summary_ready = False
        st.session_state.output_bytes = None
        st.session_state.summary_bytes = None
        st.session_state.detail_preview = None

        progress_bar = st.progress(0, text="Starting...")

        def update_progress(current, total):
            percent = int(current * 100 / total) if total else 100
            progress_bar.progress(
                percent,
                text=f"Processing: {percent}% ({current}/{total})"
            )

        try:
            with st.spinner("Processing data..."):
                detail_df, summary_df = process_dataframe(
                    df,
                    progress_callback=update_progress
                )

            output_buffer = BytesIO()
            detail_df.to_excel(output_buffer, index=False, sheet_name="Detailed Output")

            summary_buffer = BytesIO()
            summary_df.to_excel(summary_buffer, index=False, sheet_name="Summary Output")

            st.session_state.output_bytes = output_buffer.getvalue()
            st.session_state.summary_bytes = summary_buffer.getvalue()
            st.session_state.output_ready = True
            st.session_state.summary_ready = True
            st.session_state.detail_preview = detail_df.head(50)
            st.session_state.last_processed_file_hash = current_file_hash

            progress_bar.progress(100, text="✅ Completed")

            st.success("🎉 Calculation completed successfully")
            preview_to_show = st.session_state.detail_preview

        except Exception as e:
            st.error(f"❌ Processing failed: {e}")
            st.session_state.output_ready = False
            st.session_state.summary_ready = False
            preview_to_show = None
    else:
        if st.session_state.detail_preview is not None:
            st.success("🎉 Calculation completed successfully")
            preview_to_show = st.session_state.detail_preview

    if preview_to_show is not None:
        st.subheader("🔍 Preview (Top 50 Rows)")
        st.dataframe(preview_to_show, use_container_width=True)

    if st.session_state.output_ready:
        download_placeholder.download_button(
            "⬇ Download Detailed Output",
            data=st.session_state.output_bytes,
            file_name="gst_detailed_output.xlsx"
        )
    else:
        download_placeholder.info("Run calculation to enable download")

    if st.session_state.summary_ready:
        summary_placeholder.download_button(
            "⬇ Download Summary Output",
            data=st.session_state.summary_bytes,
            file_name="gst_summary_output.xlsx"
        )
    else:
        summary_placeholder.info("Run calculation to enable summary download")

else:
    st.info("📁 Please upload an Excel file to begin")
