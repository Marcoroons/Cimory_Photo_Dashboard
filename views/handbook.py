"""Handbook page, rendered from docs/handbook.md so it is easy to edit."""

from pathlib import Path

import streamlit as st

from lib.ui import page_context

page_context()

st.title("Handbook")

handbook = Path(__file__).resolve().parent.parent / "docs" / "handbook.md"
if handbook.exists():
    st.markdown(handbook.read_text(encoding="utf-8"))
else:
    st.info("Handbook file not found at docs/handbook.md.")
