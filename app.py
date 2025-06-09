import string
import streamlit as st
import pandas as pd
import polars as pl
import os
from io import StringIO
from db import Annotation, SessionLocal
from datetime import datetime

# === Define decorators for caching the data files ===
@st.cache_data(show_spinner=False)
def load_coded_df(db_path, last_modified):
    import pandas as pd
    import polars as pl

    # Load DB
    session = SessionLocal()
    df = pd.read_sql("SELECT * FROM annotations", session.bind)
    session.close()
    df = pl.from_pandas(df)

    # Ensure num_experiments column exists
    if "N_experiments" not in df.columns:
        df = df.with_columns(pl.lit(1).alias("N_experiments"))
    else:
        df = df.with_columns([
            pl.col("N_experiments").cast(pl.Int64, strict=False).fill_null(1)
        ])

    # Manually repeat each row
    repeated_rows = []
    for row in df.iter_rows(named=True):
        num_reps = row.get("N_experiments", 1)
        for exp_num in range(1, num_reps + 1):
            new_row = row.copy()
            new_row["experiment_number"] = exp_num
            repeated_rows.append(new_row)

    # Convert back to Polars
    expanded_df = pl.DataFrame(repeated_rows)

    return expanded_df



@st.cache_data(show_spinner=False)
def load_journal_articles(excel_path):
    if os.path.exists(excel_path):
        # Read all sheets with pandas
        sheets_dict = pd.read_excel(excel_path, sheet_name=None)
        # Convert each sheet to polars
        return {sheet_name: pl.from_pandas(df) for sheet_name, df in sheets_dict.items()}
    else:
        return {}

@st.cache_data(show_spinner=False)
def load_codebook(codebook_path, last_modified):
    if os.path.exists(codebook_path):
        return pl.read_csv(codebook_path)
    else:
        return pl.DataFrame()

# === Define funcions ===
def abbreviate_title(title):
    if pd.isna(title):
        return "no_title"
    words = [w.translate(str.maketrans('', '', string.punctuation)) for w in str(title).split()]
    return "_".join(words[:3]).lower()

def abbreviate_authors(authors):
    if pd.isna(authors):
        return "no_authors"
    surnames = [n.split(" ")[-1] for n in str(authors).split("; ")]
    surnames = [n.title() for n in surnames]
    if len(surnames) <= 3:
        return ", ".join(surnames)
    else:
        return ", ".join(surnames[:3]) + " et al."

def render_article_table(filtered_df, journal_name):
    # Header row
    header_cols = st.columns([2.5, 1, 1, 6, 2, 2, 2])
    header_cols[0].markdown("**Author**")
    header_cols[1].markdown("**Year**")
    header_cols[2].markdown("**Exp#**")
    header_cols[3].markdown("**Title**")
    header_cols[4].markdown("**Link**")
    header_cols[5].markdown("**Action**")
    header_cols[6].markdown("**Status**")

    # Data rows

    # Data rows
    for row_idx, row in enumerate(filtered_df.iter_rows(named=True)):
        is_coded = row["Status"] == "✅ Coded"
        button_label = "🔍 Review" if is_coded else "📝 Annotate"
        
        # Generate unique entry ID
        entry_id = f"{row['article_index']}"

        cols = st.columns([2.5, 1, 1, 6, 2, 2, 2])
        cols[0].markdown(f"{row['author']}")
        cols[1].markdown(str(row['date']))
        exp_number = row.get("experiment_number", "1")
        cols[2].markdown(str(exp_number))
        cols[3].markdown(f"{row['title']}")
        cols[4].markdown(f"[Open]({row['url']})", unsafe_allow_html=True)
        cols[6].markdown(str(row['Status']))

        # Make button key unique per experiment
        if cols[5].button(button_label, key=f"annotate_{entry_id}_{row_idx}"):
            # Load annotation
            if is_coded:
                # Pull full annotation for this article+experiment
                session = SessionLocal()
                existing = (
                    session.query(Annotation)
                    .filter(Annotation.article_index == row["article_index"])
                    .filter(Annotation.experiment_number == row["experiment_number"])
                    .first()
                )
                session.close()
                if existing:
                    row_dict = {col.name: getattr(existing, col.name) for col in Annotation.__table__.columns}
                else:
                    st.warning(f"Could not find annotation for {entry_id} in database.")
                    return
            else:
                # Use row directly as a new annotation
                row_dict = dict(row)

            row_dict["journal"] = journal_name
            st.session_state["selected_article"] = row_dict
            st.query_params.update({"mode": "Review Entry" if is_coded else "Add Entry"})
            st.rerun()

# === Define the output file ===
output_file = "new_annotations.csv"

# === Load article list from Excel file with multiple sheets (each sheet = one journal) ===
# Pandas is still needed for reading multi-sheet Excel files
excel_path = "test_articles_dataset.xlsx"

journal_articles = load_journal_articles(excel_path)

# === Get the codes for annotation ===
# Read in the codebook
codebook_path = "codebook_for_app.csv"

# `getmtime`` returns the last modified time as a float (seconds since epoch)
last_modified = os.path.getmtime(codebook_path) if os.path.exists(codebook_path) else 0
df = load_codebook(codebook_path, last_modified)

# Create dictionary to store sections preserving code
ordered_fields = df.select(["section", "code"]).iter_rows(named=True)
field_sections = {}
for row in ordered_fields:
    sec = row["section"]
    code = row["code"]
    if sec not in field_sections:
        field_sections[sec] = []
    field_sections[sec].append(code)

# Create dictionary to store description for each code
field_descriptions = {
    row["code"]: row["description"]
    for row in df.select(["code", "description"]).iter_rows(named=True)
}

# Get list of codes for checkboxes (check all that apply):
checkall_codes = df.filter(pl.col("checkall") == "yes").select("code").to_series().to_list()

# Create dictionary to store default values for relevant codes
default_values_df = df.filter(pl.col("default").is_not_null()).select(["code", "default"])
default_values = {
    row["code"]: row["default"] for row in default_values_df.iter_rows(named=True)
}

# Create dictionary to store list of values for codes
codebook_values_df = df.filter(pl.col("values").is_not_null()).select(["code", "values"])
codebook_values = {
    row["code"]: [v.strip() for v in row["values"].split("; ")]
    for row in codebook_values_df.iter_rows(named=True)
}

# Create dictionary for the help descriptions
help_descriptions = {
    row["code"]: row["help"]
    for row in df.select(["code", "help"]).iter_rows(named=True)
}

# Create list of specific code that might be tricky. We'll add a comment box
# for each of these...
# commentable_fields_expandable = ["statistical_test", "stat_scale", "instructions"]
commentable_fields_expandable = []

# === Setup the app page ===
st.set_page_config(page_title="Acceptability Judgment Coding Form", layout="wide")
st.title("Coding Acceptability Judgment Experiments")

# Add code to increase font size
st.markdown("""
    <style>
    div[class*="stTextInput"] label,
    div[class*="stTextArea"] label,
    div[class*="stSelectbox"] label,
    div[class*="stRadio"] label,
    div[class*="stCheckbox"] label {
        font-size: 2rem !important;
        font-weight: 600;
    }
    </style>
    """, unsafe_allow_html=True)


# Sidebar for mode selection
# mode = st.sidebar.radio("Select mode:", ["Article Dashboard", "Add Entry", "Review Entries"])

# Sidebar Home button
st.sidebar.markdown(
    """
    <style>
    .home-button {
        background-color: #0E1117;
        color: white !important;
        font-size: 1.4rem;
        font-weight: bold;
        padding: 0.6em 1em;
        border-radius: 10px;
        border-width: 1px;
        text-align: center;
        display: block;
        text-decoration: none !important;
        margin-top: 1em;
    }
    .home-button:hover {
        background-color: #005bb5;
        text-decoration: none !important;
    }
    </style>
    <form action="/?mode=Article+Dashboard" method="get">
        <button type="submit" class="home-button">Dashboard Home</button>
    </form>
    """,
    unsafe_allow_html=True
)

# Get mode from URL query param, default to dashboard
mode = st.query_params.get("mode", "Article Dashboard")

# Override with query param if present
query_mode = st.query_params.get("mode")
if query_mode:
    mode = query_mode

# Clear button check logic
if st.session_state.get("confirm_clear", False):
    with st.expander("⚠️ Confirm Clear Fields"):
        st.warning("This will erase all coded values (but keep the metadata). Are you sure?")
        col1, col2 = st.columns(2)
        if col1.button("Yes, clear all fields"):
            # Clear all coding fields (but keep metadata)
            preserved = ["article_index", "title", "author", "journal", "year", "url", "searchterms"]
            for field in list(st.session_state.keys()):
                if field not in preserved and not field.startswith("_"):  # Avoid Streamlit internals
                    st.session_state[field] = ""
            st.session_state["confirm_clear"] = False
            st.success("Annotation fields cleared.")
            st.experimental_rerun()

        if col2.button("Cancel"):
            st.session_state["confirm_clear"] = False

# === Article Dashboard =======================================
if mode == "Article Dashboard":

    st.subheader("Article Dashboard")
    
    # Add download button
    with st.sidebar:
        # 🔹 Top section: filter and sort controls
        st.markdown("### ")
        filter_option = st.radio("Filter by coding status:", ["All", "Coded", "Not coded"])

        sort_column = st.selectbox(
            "Sort by column", 
            options=["date", "author", "title"], 
            index=0,
            key=f"sort_by_main"
        )
        sort_descending = st.checkbox("Sort descending", value=False)

        # 🔹 Spacer to push download to the bottom
        st.markdown("<div style='flex:1'></div>", unsafe_allow_html=True)

        # 🔹 Bottom section: download button
        try:
            session = SessionLocal()
            df = pd.read_sql("SELECT * FROM annotations", session.bind)
            session.close()
        except Exception as e:
            st.error(f"Could not load annotations: {e}")
            df = pd.DataFrame()

        if not df.empty:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
            export_filename = f"annotations_from_articles_{timestamp}.csv"

            # Insert the button *inside* the styled box
            st.download_button(
                label="📥 Download annotations as CSV",
                data=df.to_csv(index=False),
                file_name=export_filename,
                mime="text/csv",
                key="download_csv_button"
            )
        else:
            st.info("No annotations available yet.")


    if not journal_articles:
        st.warning(f"No article file found at '{excel_path}'")
    else:
        # ✅ Load coded entries from SQLite, using timestamp for cache busting
        last_modified = os.path.getmtime("annotations.db")
        coded_df = load_coded_df("annotations.db", last_modified)

        if coded_df.is_empty():
            coded_articles = []
        else:
            coded_articles = coded_df.select("article_index").unique().to_series().to_list()

        tabs = st.tabs(list(journal_articles.keys()))

        for i, (journal_name, df) in enumerate(journal_articles.items()):
            with tabs[i]:
                df = df.clone()  # polars doesn't have .copy(); use .clone() instead
                
                if "Include" in df.columns:
                    df = df.with_columns(
                        pl.col("Include").cast(str).fill_null("").alias("Include")
                    ).filter(pl.col("Include") != "x")
                if df.height > 0:
                    df = df.rename({col: col.strip().lower().replace(" ", "_") for col in df.columns if isinstance(col, str)})

                    if "article_index" not in df.columns:
                        if "title" in df.columns and "date" in df.columns:
                            df = df.with_columns([
                                pl.struct(["author"]).map_elements(lambda x: abbreviate_authors(x["author"]), return_dtype=pl.Utf8).alias("author_abbr"),
                                pl.col("date").cast(pl.Utf8).alias("date_str"),
                                pl.struct(["title"]).map_elements(lambda x: abbreviate_title(x["title"]), return_dtype=pl.Utf8).alias("title_abbr")
                            ])
                            df = df.with_columns(
                                (pl.col("author_abbr") + "_" + pl.col("date_str") + "_" + pl.col("title_abbr")).alias("article_index")
                            )
                        else:
                            st.warning(f"Sheet '{journal_name}' is missing the 'article_index' column and cannot create one.")
                            continue

                    df = df.with_columns([
                        pl.when(pl.col("article_index").is_in(coded_articles))
                        .then(pl.lit("✅ Coded"))
                        .otherwise(pl.lit("❌ Not coded"))
                        .alias("Status"),

                        pl.col("url").fill_null("").map_elements(lambda x: f"[Open]({x})", return_dtype=pl.Utf8).alias("Link")
                    ])

                    if filter_option == "Coded":
                        filtered_df = df.filter(pl.col("Status") == "✅ Coded")
                    elif filter_option == "Not coded":
                        filtered_df = df.filter(pl.col("Status") == "❌ Not coded")
                    else:
                        filtered_df = df

                    num_coded = df.filter(pl.col("Status") == "✅ Coded").height
                    num_total = df.height

                    # Messages above table
                    st.markdown(f"Articles coded in *{journal_name}* so far: {num_coded} / {num_total}. **Note that some articles may involve more than one experiment.**")

                    # st.markdown("### Articles")

                    # Add a search box just above the article list
                    search_query = st.text_input(f"🔍 Search articles in {journal_name}", key=f"search_{journal_name}")

                    if search_query:
                        # Create searchable text field
                        filtered_df = filtered_df.with_columns([
                            (
                                pl.col("title").fill_null("") + " " +
                                pl.col("author").fill_null("") + " " +
                                pl.col("article_index").fill_null("")
                            ).alias("search_text")
                        ])
                        
                        # Filter using case-insensitive match
                        filtered_df = filtered_df.filter(
                            pl.col("search_text").str.to_lowercase().str.contains(search_query.lower())
                        )
                    
                    # sort the dataframe
                    filtered_df = filtered_df.sort(sort_column, descending=sort_descending)

                    # Render the articles for the journal
                    render_article_table(filtered_df, journal_name)
                else:
                    st.info(f"No articles found for {journal_name}.")
                   

# === Mode: Add Entry ====================================================
elif mode == "Add Entry":
    with st.form("coding_form_add"):
        # Pre-fill metadata if selected from dashboard
        selected_article = st.session_state.get("selected_article", {})

        metadata_fields = ["article_index", "title", "author", "journal", "date", "url", "searchterm"]
        prefill = {field: selected_article.get(field, "") for field in metadata_fields}
        
        header = "Add New Annotation"
        if prefill["author"] and prefill["date"]:
            header += f" — {abbreviate_authors(prefill['author'])} ({prefill['date']})"
        st.subheader(header)

        new_entry = {
            "article_index": prefill['article_index'],
            "authors": prefill['author'],
            "year": prefill['date'],
            "title": prefill["title"],
            "journal": prefill["journal"],
            "url": prefill['url'],
            "searchterms": prefill['searchterm']
        }

        st.markdown("### Metadata")
        article_index = st.text_input("Article ID", value=prefill["article_index"])
        title = st.text_input("Title", value=prefill["title"])
        authors = st.text_input("Authors", value=prefill["author"])
        year = st.text_input("Year", value=prefill["date"])
        journal = st.text_input("Journal", value=prefill["journal"])
        url = st.text_input("URL", value=prefill["url"])
        searchterm = st.text_input("Search terms", value=prefill['searchterm'])

        for section, fields in field_sections.items():
            st.markdown(f"### {section}")
            for field in fields:
                description_text = field_descriptions.get(field, "")
                help_text = help_descriptions.get(field, "")
                default = default_values.get(field, "")
                label = description_text if description_text else field.replace("_", " ").capitalize()
                
                if field in checkall_codes:
                    options = codebook_values[field]
                    selection = st.multiselect(label, options, default=["Not Reported"], help=help_text, key=field)
                    new_entry[field] = "; ".join(selection)
                elif field in codebook_values:
                    options = codebook_values.get(field)
                    if default in options:
                        index = options.index(default) + 1
                    else:
                        index = 0
                    new_entry[field] = st.selectbox(label, [""] + options, index=index, key=field, help=help_text)
                elif field in ["instructions", "coder_comments"]:
                    new_entry[field] = st.text_area(label, key=field)
                else:
                    new_entry[field] = st.text_input(label, value=default, key=field, help=help_text)

                if field in commentable_fields_expandable:
                    with st.expander(f"Add comment on {field.replace('_', ' ').capitalize()} (optional)"):
                        new_entry[f"{field}_comment"] = st.text_area("", key=f"{field}_comment")

        col1, col2, spacer = st.columns([2, 1, 7])
        with col1:
            submitted = st.form_submit_button("New Annotation Added!")
        with col2:
            cancel = st.form_submit_button("❌ Cancel")
            st.markdown(
                """
                <style>
                div[data-testid="stFormSubmitButton"]:nth-of-type(2) button {
                    background-color: #ff4b4b !important;
                    color: white !important;
                }
                </style>
                """,
                unsafe_allow_html=True
            )
    # Clea button
    clear_clicked = st.button("🧹 Clear Annotation Fields")
    
    if clear_clicked:
        st.session_state["confirm_clear"] = True

    if cancel:
        st.query_params.update({"mode": "Article Dashboard"})
        st.rerun()
    elif submitted:
        session = SessionLocal()
        try:
            new_row = Annotation(**new_entry)
            session.add(new_row)  # 🆕 Always inserts
            session.commit()
            st.success("New annotation saved!")
        except Exception as e:
            session.rollback()
            st.error(f"Error: {e}")
        finally:
            session.close()
        load_coded_df.clear()
        st.query_params.update({"mode": "Article Dashboard"})
        st.rerun()

# === Mode: Review Entries =========================================
elif mode == "Review Entry":
    with st.form("coding_form_review"):
        selected_article = st.session_state.get("selected_article", {})
        if not selected_article:
            st.warning("No article selected for review.")
            st.stop()

        metadata_fields = ["article_index", "title", "author", "journal", "year", "url", "searchterms"]
        prefill = {field: selected_article.get(field, "") for field in metadata_fields}

        st.subheader(f"Update Annotation — {prefill.get('article_index', '')}")

        new_entry = {
            "article_index": prefill['article_index'],
            "authors": prefill['author'],
            "year": prefill['year'],
            "title": prefill["title"],
            "journal": prefill["journal"],
            "url": prefill['url'],
            "searchterms": prefill['searchterms']
        }

        st.markdown("### Metadata")
        article_index = st.text_input("Article ID", value=prefill["article_index"], disabled=True)
        title = st.text_input("Title", value=prefill["title"])
        authors = st.text_input("Authors", value=prefill["author"])
        year = st.text_input("Year", value=prefill["year"])
        journal = st.text_input("Journal", value=prefill["journal"])
        url = st.text_input("URL", value=prefill["url"])
        searchterm = st.text_input("Search terms", value=prefill["searchterms"])

        for section, fields in field_sections.items():
            st.markdown(f"### {section}")
            for field in fields:
                description_text = field_descriptions.get(field, "")
                help_text = help_descriptions.get(field, "")
                default = default_values.get(field, "")
                label = description_text if description_text else field.replace("_", " ").capitalize()

                if field in checkall_codes:
                    options = codebook_values[field]
                    current = [v.strip() for v in default.split(";")] if default else ["Not Reported"]
                    selection = st.multiselect(label, options, default=current, help=help_text, key=field)
                    new_entry[field] = "; ".join(selection)
                elif field in codebook_values:
                    options = codebook_values.get(field)
                    index = options.index(default) + 1 if default in options else 0
                    new_entry[field] = st.selectbox(label, [""] + options, index=index, key=field, help=help_text)
                elif field in ["instructions", "coder_comments"]:
                    new_entry[field] = st.text_area(label, value=default, key=field)
                else:
                    new_entry[field] = st.text_input(label, value=default, key=field, help=help_text)

                # Handle comments
                comment_default = selected_article.get(f"{field}_comment", "")
                if field in commentable_fields_expandable:
                    with st.expander(f"Add comment on {field.replace('_', ' ').capitalize()} (optional)"):
                        new_entry[f"{field}_comment"] = st.text_area("", value=comment_default, key=f"{field}_comment")

        col1, col2, spacer = st.columns([2, 1, 7])
        with col1:
            submitted = st.form_submit_button("Update Entry")
        with col2:
            cancel = st.form_submit_button("❌ Cancel")
            st.markdown(
                """
                <style>
                div[data-testid="stFormSubmitButton"]:nth-of-type(2) button {
                    background-color: #ff4b4b !important;
                    color: white !important;
                }
                </style>
                """,
                unsafe_allow_html=True
            )
    # Clea button
    clear_clicked = st.button("🧹 Clear Annotation Fields")
    
    if clear_clicked:
        st.session_state["confirm_clear"] = True

    if cancel:
        st.query_params.update({"mode": "Article Dashboard"})
        st.rerun()

    elif submitted:
        session = SessionLocal()
        try:
            existing = session.query(Annotation).filter(
                Annotation.article_index == new_entry["article_index"]
            ).first()

            if existing:
                for key, value in new_entry.items():
                    setattr(existing, key, value)
                session.commit()
                st.success("Annotation updated!")
            else:
                st.error("No existing entry found to update.")
        except Exception as e:
            session.rollback()
            st.error(f"Update failed: {e}")
        finally:
            session.close()

        load_coded_df.clear()
        st.query_params.update({"mode": "Article Dashboard"})
        st.rerun()



