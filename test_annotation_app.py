import streamlit as st
import pandas as pd
import datetime

st.set_page_config(page_title="Acceptability Judgment Coding Form", layout="centered")
st.title("Acceptability Judgment Experiment Coding Form")

# --- Input fields ---
st.header("Study Metadata")
study_id = st.text_input("Study ID / Citation")
year = st.number_input("Year of Publication", min_value=1900, max_value=datetime.datetime.now().year, step=1)
journal = st.text_input("Journal Name")
theory = st.selectbox("Theoretical Framework", ["Minimalism", "HPSG", "LFG", "Construction Grammar", "Other"])

st.header("Participants")
n_participants = st.number_input("Number of Participants", min_value=1, step=1)
l1 = st.text_input("Participant L1 / Language Background")
recruitment = st.text_input("Recruitment Method")

st.header("Judgment Task")
task_type = st.selectbox("Task Type", ["Likert Scale", "Magnitude Estimation", "Binary", "Forced Choice", "Other"])
scale = st.text_input("Scale Used (e.g., 1–5, 0–100)")
instructions = st.text_input("Instructions to Participants")

st.header("Stimuli")
linguistic_phenomenon = st.text_input("Linguistic Phenomenon Investigated")
modality = st.selectbox("Presentation Modality", ["Written", "Audio", "Both"])
sentence_length = st.text_input("Average Sentence Length")
test_items = st.number_input("Number of Test Items", min_value=0, step=1)
fillers = st.number_input("Number of Fillers", min_value=0, step=1)
randomization = st.selectbox("Counterbalancing / Randomization", ["Yes", "No", "Not Reported"])

st.header("Analysis")
stat_method = st.text_input("Statistical Analysis Method(s) Used")
random_effects = st.multiselect("Random Effects Included", ["Participant", "Item", "None", "Not Reported"])
effect_sizes = st.selectbox("Effect Sizes Reported", ["Yes", "No", "Not Reported"])
data_shared = st.selectbox("Data / Code Shared", ["Yes", "No", "On Request", "Not Mentioned"])

st.header("Interpretation")
results_summary = st.text_area("Summary of Results")
theoretical_notes = st.text_area("Theoretical / Interpretive Notes")
coding_confidence = st.selectbox("Confidence in Coding", ["High", "Medium", "Low"])

# --- Submission and saving ---
if st.button("Submit Entry"):
    new_entry = pd.DataFrame.from_records([{
        "StudyID": study_id,
        "Year": year,
        "Journal": journal,
        "Framework": theory,
        "Participants": n_participants,
        "L1": l1,
        "Recruitment": recruitment,
        "TaskType": task_type,
        "Scale": scale,
        "Instructions": instructions,
        "Phenomenon": linguistic_phenomenon,
        "Modality": modality,
        "SentenceLength": sentence_length,
        "TestItems": test_items,
        "Fillers": fillers,
        "Randomization": randomization,
        "StatMethod": stat_method,
        "RandomEffects": ", ".join(random_effects),
        "EffectSizes": effect_sizes,
        "DataShared": data_shared,
        "Results": results_summary,
        "Notes": theoretical_notes,
        "Confidence": coding_confidence
    }])

    # Append to CSV
    try:
        existing = pd.read_csv("coded_studies.csv")
        df = pd.concat([existing, new_entry], ignore_index=True)
    except FileNotFoundError:
        df = new_entry

    df.to_csv("coded_studies.csv", index=False)
    st.success("Entry saved to coded_studies.csv!")
