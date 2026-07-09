"""Import wizard: upload or paste, map columns, flag, dedup, append idempotently."""

import streamlit as st

st.set_page_config(page_title="Import", page_icon="📥", layout="wide")

from lib.auth import require_auth
from lib.ui import render_sidebar
from lib import db, imports

user = require_auth()
project, role, teams = render_sidebar(user)
project_id = project["id"]

st.title("Import photos")

if role not in ("owner", "admin", "editor"):
    st.info("Viewers cannot import. Ask an editor or admin to load the file.")
    st.stop()

config = project.get("config") or {}

# ---------------------------------------------------------------------------
# Step 1: source
# ---------------------------------------------------------------------------

st.subheader("1. Choose a source")
src_tab, paste_tab = st.tabs(["Upload file", "Paste table"])

with src_tab:
    uploaded = st.file_uploader("CSV or Excel", type=["csv", "xlsx", "xls"])
    if uploaded is not None:
        try:
            df = imports.read_upload(uploaded)
            st.session_state["import_df"] = df
            st.session_state["import_raw"] = uploaded.getvalue()
            st.session_state["import_name"] = uploaded.name
        except Exception as exc:
            st.error(f"Could not read file: {exc}")

with paste_tab:
    pasted = st.text_area("Paste tab or comma separated rows including a header row", height=160)
    if st.button("Use pasted table") and pasted.strip():
        try:
            df = imports.read_pasted(pasted)
            st.session_state["import_df"] = df
            st.session_state["import_raw"] = pasted.encode("utf-8")
            st.session_state["import_name"] = "pasted.csv"
        except Exception as exc:
            st.error(f"Could not parse pasted text: {exc}")

df = st.session_state.get("import_df")
if df is None:
    st.stop()

# ---------------------------------------------------------------------------
# Step 2: preview
# ---------------------------------------------------------------------------

st.subheader("2. Preview")
st.caption(f"{len(df)} rows, {len(df.columns)} columns from {st.session_state.get('import_name')}")
st.dataframe(df.head(20), use_container_width=True)

source_cols = [str(c) for c in df.columns]

# ---------------------------------------------------------------------------
# Step 3: mapping template
# ---------------------------------------------------------------------------

st.subheader("3. Map columns")

templates = imports.list_templates(project_id)
template_map = {}
if templates:
    tnames = ["(none)"] + [t["name"] for t in templates]
    chosen = st.selectbox("Start from a saved template", options=tnames)
    if chosen != "(none)":
        template_map = next(t["mapping"] for t in templates if t["name"] == chosen)


def _auto(field):
    """Best guess source column for a canonical field."""
    if field in template_map and template_map[field] in source_cols:
        return template_map[field]
    norm = {c.lower().replace(" ", "").replace("_", ""): c for c in source_cols}
    key = field.lower().replace("_", "")
    aliases = {
        "mcm_id": ["mcm", "mcmid", "agent", "agentid"],
        "submission_date": ["date", "submissiondate", "tanggal"],
        "photo_url": ["url", "photourl", "photo", "image", "imageurl", "link"],
        "region": ["region", "area", "wilayah"],
        "center_name": ["center", "centre", "centername", "booth", "namacenter"],
        "captured_at": ["capturedat", "timestamp", "takenat", "waktu"],
        "category": ["category", "kategori", "type"],
        "photo_ref": ["ref", "photoref", "filename", "id"],
        "latitude": ["lat", "latitude"],
        "longitude": ["lon", "lng", "long", "longitude"],
        "gps_distance": ["gpsdistance", "distance", "jarak"],
    }
    if key in norm:
        return norm[key]
    for alias in aliases.get(field, []):
        if alias in norm:
            return norm[alias]
    return None


NOT_PRESENT = "(not present)"
mapping = {}
cols = st.columns(2)
for idx, (field, kind, desc) in enumerate(imports.CANONICAL_FIELDS):
    col = cols[idx % 2]
    options = [NOT_PRESENT] + source_cols
    guess = _auto(field)
    default_idx = options.index(guess) if guess in options else 0
    label = f"{field}  ·  {kind}"
    picked = col.selectbox(label, options=options, index=default_idx,
                          help=desc, key=f"map_{field}")
    if picked != NOT_PRESENT:
        mapping[field] = picked

keep_extras = st.checkbox("Keep unmapped columns in metadata", value=False)

missing = [f for f in imports.REQUIRED_FIELDS if f not in mapping]
if missing:
    st.warning(f"Map the required fields before importing: {', '.join(missing)}")

# ---------------------------------------------------------------------------
# Step 4: save template
# ---------------------------------------------------------------------------

with st.expander("Save this mapping as a template"):
    tpl_name = st.text_input("Template name")
    if st.button("Save template") and tpl_name.strip():
        try:
            imports.save_template(project_id, tpl_name.strip(), mapping, user.id)
            st.success("Template saved. It will appear in the picker next time.")
        except Exception as exc:
            st.error(f"Could not save template: {exc}")

# ---------------------------------------------------------------------------
# Step 5: run import
# ---------------------------------------------------------------------------

st.subheader("4. Import")

raw = st.session_state.get("import_raw")
fhash = imports.file_hash(raw) if raw else None
existing_batch = db.get_batch_by_hash(project_id, fhash) if fhash else None

confirm = True
if existing_batch:
    st.warning(
        "This exact file was imported before. Re-importing is safe and will not "
        "double count, only genuinely new rows are added."
    )
    confirm = st.checkbox("Import anyway", value=False)

can_run = not missing and confirm
if st.button("Run import", disabled=not can_run, type="primary"):
    with st.spinner("Importing..."):
        try:
            result = imports.run_import(
                project_id, mapping, df, raw,
                st.session_state.get("import_name"), config, keep_extras, user.id,
            )
            st.success("Import complete.")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("New rows", result["inserted"])
            c2.metric("Skipped (already present)", result["skipped"])
            c3.metric("Over limit", result["over_limit"])
            c4.metric("Duplicates", result["duplicates"])
            st.caption(
                f"{result['total']} rows processed. "
                f"{result['no_gps']} without GPS, {result['gps_far']} GPS far."
            )
            for key in ("import_df", "import_raw", "import_name"):
                st.session_state.pop(key, None)
        except Exception as exc:
            st.error(f"Import failed: {exc}")
