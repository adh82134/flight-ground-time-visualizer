import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta
import matplotlib.dates as mdates
import matplotlib.cm as cm
import matplotlib.colors as mcolors

st.set_page_config(layout="wide")
st.title("Flight Ground Time Visualizer (RON-Aware + Week Dropdown Edition)")

# --- Load from Downloads ---
downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
excel_files = sorted(
    [f for f in os.listdir(downloads_folder) if f.endswith(".xlsx") and not f.startswith("~$")],
    key=lambda x: os.path.getmtime(os.path.join(downloads_folder, x)),
    reverse=True
)

if not excel_files:
    st.error("No Excel (.xlsx) files found in your Downloads folder.")
    st.stop()

selected_file = st.selectbox("Select a flight schedule Excel file from Downloads:", excel_files)
file_path = os.path.join(downloads_folder, selected_file)

# --- Load data safely ---
df = pd.read_excel(file_path)
df.columns = df.columns.str.strip()

required_cols = ['ARRIVE_DATE_TIME_LOCAL', 'DEPART_DATE_TIME_LOCAL']
for col in required_cols:
    if col not in df.columns:
        st.error(f"Missing required column: {col}")
        st.write("Columns found:", df.columns.tolist())
        st.stop()

df['ARRIVE_DATE_TIME_LOCAL'] = pd.to_datetime(df['ARRIVE_DATE_TIME_LOCAL'], errors='coerce')
df['DEPART_DATE_TIME_LOCAL'] = pd.to_datetime(df['DEPART_DATE_TIME_LOCAL'], errors='coerce')

arrivals = df[df['SKD_TYPE'].str.upper() == 'ARRIVAL']
departures = df[df['SKD_TYPE'].str.upper() == 'DEPARTURE']

# --- Match Arrivals to Departures ---
matched = []
used_departures = set()
for _, arr in arrivals.iterrows():
    same_ac = departures[
        (departures['INFORM_AC'] == arr['INFORM_AC']) &
        (departures['STATION'] == arr['STATION']) &
        (departures['DEPART_DATE_TIME_LOCAL'] > arr['ARRIVE_DATE_TIME_LOCAL'])
    ].sort_values('DEPART_DATE_TIME_LOCAL')

    for _, dep in same_ac.iterrows():
        if dep.name not in used_departures:
            matched.append({
                'STATION': arr['STATION'],
                'INFORM_AC': arr['INFORM_AC'],
                'AIRLINEDESIGNATOR': arr['AIRLINEDESIGNATOR'],
                'ARRIVE': arr['ARRIVE_DATE_TIME_LOCAL'],
                'DEPART': dep['DEPART_DATE_TIME_LOCAL']
            })
            used_departures.add(dep.name)
            break

matched_df = pd.DataFrame(matched)
if matched_df.empty:
    st.warning("No matched flights found.")
    st.stop()

# --- Add week label ---
matched_df['WEEK'] = matched_df['ARRIVE'].dt.strftime("%G_%V")

# --- Week Dropdown ---
unique_weeks = sorted(matched_df['WEEK'].unique())
selected_week = st.selectbox("Select a calendar week (Monday–Sunday):", unique_weeks)

# --- Filter by selected week ---
selected_year, selected_week_number = map(int, selected_week.split("_"))
start_of_week = datetime.strptime(f'{selected_year}-W{selected_week_number}-1', "%G-W%V-%u")
end_of_week = start_of_week + timedelta(days=6)

filtered_df = matched_df[
    ((matched_df['ARRIVE'] >= start_of_week) & (matched_df['ARRIVE'] <= end_of_week))
    | ((matched_df['DEPART'] >= start_of_week) & (matched_df['DEPART'] <= end_of_week))
].copy()

# --- Add helper columns ---
filtered_df['ARRIVE_DATE'] = filtered_df['ARRIVE'].dt.date
filtered_df['DEPART_DATE'] = filtered_df['DEPART'].dt.date

# --- Decide coloring scheme ---
if filtered_df['AIRLINEDESIGNATOR'].nunique() == 1:
    color_by = 'INFORM_AC'
else:
    color_by = 'AIRLINEDESIGNATOR'

categories = filtered_df[color_by].dropna().unique()
cmap = cm.get_cmap('tab20', len(categories))
color_map = {cat: mcolors.to_hex(cmap(i)) for i, cat in enumerate(categories)}

# --- Sticky Legend with fallback ---
legend_html = f"""
<style>
.sticky-legend {{
    position: sticky;
    top: 0;
    background-color: white;
    padding: 10px;
    border-bottom: 2px solid #ccc;
    z-index: 999;
}}
.legend-item {{
    margin-right: 15px;
    display: flex;
    align-items: center;
}}
.legend-color {{
    width: 20px;
    height: 20px;
    margin-right: 5px;
}}
</style>
<div class="sticky-legend">
    <b>Color Coding by {color_by}:</b><br>
    <div style="display:flex; flex-wrap:wrap;">
"""

for cat in categories:
    legend_html += f"""
        <div class="legend-item">
            <div class="legend-color" style="background:{color_map[cat]};"></div>
            <span style="font-size:14px;">{cat}</span>
        </div>
    """
legend_html += "</div></div>"

try:
    # Try rendering sticky HTML legend
    components.html(legend_html, height=100)
except:
    st.warning("HTML legend rendering failed. Showing fallback legend.")

    # Fallback: Matplotlib-style legend
    fig, ax = plt.subplots(figsize=(6, 1))
    handles = [plt.Rectangle((0, 0), 1, 1, color=color_map[cat]) for cat in categories]
    ax.legend(handles, categories, title=f"Color Coding by {color_by}", loc="center", ncol=4)
    ax.axis("off")
    st.pyplot(fig)

# --- Plot per day of the week ---
for day in pd.date_range(start_of_week, end_of_week):
    fig, ax = plt.subplots(figsize=(10, 2.5))
    current_day = day.date()

    flights_today = filtered_df[
        (filtered_df['ARRIVE_DATE'] == current_day) | 
        (filtered_df['DEPART_DATE'] == current_day)
    ]

    y_pos = 0
    for _, row in flights_today.iterrows():
        ac = row['INFORM_AC']
        arrive = row['ARRIVE']
        depart = row['DEPART']
        category = row[color_by]
        color = color_map.get(category, '#808080')  # default gray if missing

        # Regular same-day flight
        if row['ARRIVE_DATE'] == current_day and row['DEPART_DATE'] == current_day:
            ax.barh(y_pos, depart - arrive, left=arrive, height=0.4, color=color)
            label = f"{arrive.strftime('%H:%M')} → {depart.strftime('%H:%M')}"
            ax.text(arrive + (depart - arrive) / 2, y_pos,
                    f"{label}\n{ac}",
                    ha='center', va='center', color='black', fontsize=8, weight='bold')

        # RON arrives today
        elif row['ARRIVE_DATE'] == current_day:
            midnight = datetime.combine(current_day + timedelta(days=1), datetime.min.time())
            ax.barh(y_pos, midnight - arrive, left=arrive, height=0.4, color=color)
            ax.text(arrive + (midnight - arrive) / 2, y_pos,
                    f"{arrive.strftime('%H:%M')} → 00:00\n{ac}",
                    ha='center', va='center', color='black', fontsize=8, weight='bold')

        # RON departs today
        elif row['DEPART_DATE'] == current_day:
            midnight = datetime.combine(current_day, datetime.min.time())
            ax.barh(y_pos, depart - midnight, left=midnight, height=0.4, color=color)
            ax.text(midnight + (depart - midnight) / 2, y_pos,
                    f"00:00 → {depart.strftime('%H:%M')}\n{ac}",
                    ha='center', va='center', color='black', fontsize=8, weight='bold')

        y_pos += 1

    ax.set_ylim(-0.5, y_pos + 0.5)
    ax.set_xlim([
        datetime.combine(current_day, datetime.min.time()),
        datetime.combine(current_day + timedelta(days=1), datetime.min.time())
    ])
    ax.set_xlabel("Time of Day")
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.set_title(f"Ground Time for {current_day}")
    st.pyplot(fig)
