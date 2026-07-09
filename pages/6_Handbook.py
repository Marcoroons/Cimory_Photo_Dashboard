"""Handbook page, rendered from docs/handbook.md so it is easy to edit."""

from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Handbook", page_icon="📖", layout="wide")

from lib.auth import require_auth
from lib.ui import render_sidebar

user = require_auth()
render_sidebar(user)

st.title("Handbook")

handbook = Path(__file__).resolve().parent.parent / "docs" / "handbook.md"
if handbook.exists():
    st.markdown(handbook.read_text(encoding="utf-8"))
else:
    st.info("Handbook file not found at docs/handbook.md.")
