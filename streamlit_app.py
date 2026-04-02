import streamlit as st
import pandas as pd
from io import BytesIO

from gst_engine import process_dataframe

# -----------------------------
# PAGE CONFIG
# -----------------------------
st.set_page_config(page_title="GST Rule Engine", layout="wide")
st.title("📊 GST Rule Engine - Table 4 Automation")

# -----------------------------
# SESSION STATE INIT
# -----------------------------
if "output_ready" not in st.session_state:
    st.session_state.output_ready = False
    st.session_state.output_bytes = None
    st.session_state.summary_ready = False
    st.session_state.summary_bytes = None

# -----------------------------
# FILE UPLOAD
# -----------------------------
uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx"])

if uploaded_file:
    try:
        df = pd.read_excel(uploaded_file)
        st.success("✅ File uploaded successfully")

    except Exception as e:
        st.error(f"❌ Error reading file: {e}")
        st.stop()

    # -----------------------------
    # GENERATE BUTTON
    # -----------------------------
    generate = st.button("🚀 Generate Calculation", type="primary")

    # -----------------------------
    # PLACEHOLDERS
    # -----------------------------
    download_placeholder = st.empty()
    summary_placeholder = st.empty()

    # -----------------------------
    # PROCESSING
    # -----------------------------
    if generate:
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

            # -----------------------------
            # EXPORT OUTPUT
            # -----------------------------
            output_buffer = BytesIO()
            detail_df.to_excel(output_buffer, index=False, sheet_name="Detailed Output")

            summary_buffer = BytesIO()
            summary_df.to_excel(summary_buffer, index=False, sheet_name="Summary Output")

            st.session_state.output_bytes = output_buffer.getvalue()
            st.session_state.summary_bytes = summary_buffer.getvalue()
            st.session_state.output_ready = True
            st.session_state.summary_ready = True

            progress_bar.progress(100, text="✅ Completed")

            st.success("🎉 Calculation completed successfully")

            # Preview
            st.subheader("🔍 Preview (Top 50 Rows)")
            st.dataframe(detail_df.head(50), use_container_width=True)

        except Exception as e:
            st.error(f"❌ Processing failed: {e}")
            st.session_state.output_ready = False
            st.session_state.summary_ready = False

    # -----------------------------
    # DOWNLOAD BUTTONS
    # -----------------------------
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
