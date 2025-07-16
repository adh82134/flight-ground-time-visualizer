import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
from datetime import datetime, timedelta
import matplotlib.dates as mdates

st.set_page_config(layout="wide")
st.title("Flight Ground Time Visualizer (RON-Aware + Dropdown Edition)")

# --- File Uploader ---
uploaded_file = st.file_uploader("Upload a flight schedule Excel file", type=["xlsx"])

if not uploaded_file:
    st.warning("Please upload an Excel (.xlsx) file to continue.")
    st.stop()

# --- Load data ---
df = pd.read_excel(uploaded_file)

# --- Parse datetime columns ---
df['ARRIVE_DATE_TIME_LOCAL'] = pd.to_datetime(df['ARRIVE_DATE_TIME_LOCAL'], errors='coerce')
df['DEPART_DATE_TIME_LOCAL'] = pd.to_datetime(df['DEPART_DATE_TIME_LOCAL'], errors='coerce')

arrivals = df[df['SKD_TYPE'].str.upper() == 'ARRIVAL']
departures = df[df['SKD_TYPE'].str.upper() == 'DEPARTURE']

# --- Match arrivals to departures ---
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
                'ARRIVE': arr['ARRIVE_DATE_TIME_LOCAL'],
                'DEPART': dep['DEPART_DATE_TIME_LOCAL']
            })
            used_departures.add(dep.name)
            break

matched_df = pd.DataFrame(matched)
if matched_df.empty:
    st.warning("No matched flights found.")
    st.stop()

# --- Date picker ---
min_date = matched_df['ARRIVE'].min().date()
max_date = matched_df['DEPART'].max().date()
date_range = st.date_input("Select date range", (min_date, max_date))

# --- Plot ground time chart for each selected day ---
grouped = matched_df.copy()
grouped['ARRIVE_DATE'] = grouped['ARRIVE'].dt.date
grouped['DEPART_DATE'] = grouped['DEPART'].dt.date

for day in pd.date_range(date_range[0], date_range[1]):
    fig, ax = plt.subplots(figsize=(10, 2.5))
    current_day = day.date()

    flights_today = grouped[
        (grouped['ARRIVE_DATE'] == current_day) |
        (grouped['DEPART_DATE'] == current_day)
    ]

    y_pos = 0
    for _, row in flights_today.iterrows():
        ac = row['INFORM_AC']
        arrive = row['ARRIVE']
        depart = row['DEPART']

        # Ground time on same day
        if row['ARRIVE_DATE'] == current_day and row['DEPART_DATE'] == current_day:
            ax.barh(y_pos, depart - arrive, left=arrive, height=0.3, color='steelblue')

            # Time label on top
            label = f"{arrive.strftime('%H:%M')} → {depart.strftime('%H:%M')}"
            ax.text(arrive + (depart - arrive) / 2, y_pos + 0.35,
                    label, ha='center', va='bottom', color='black', fontsize=8, weight='bold')

            # Aircraft type below bar
            ax.text(arrive + (depart - arrive) / 2, y_pos - 0.4,
                    f"{ac}", ha='center', va='top', color='black', fontsize=8)

        # RON case – arrive previous day, depart today
        elif row['DEPART_DATE'] == current_day:
            midnight = datetime.combine(current_day, datetime.min.time())
            ax.barh(y_pos, depart - midnight, left=midnight, height=0.3, color='red')
            ax.text(midnight + (depart - midnight) / 2, y_pos,
                    f"{ac} 00:00 → {depart.strftime('%H:%M')}",
                    ha='center', va='center', color='black', fontsize=8)

        # RON case – arrive today, depart next day
        elif row['ARRIVE_DATE'] == current_day:
            midnight = datetime.combine(current_day + timedelta(days=1), datetime.min.time())
            ax.barh(y_pos, midnight - arrive, left=arrive, height=0.3, color='orange')
            ax.text(arrive + (midnight - arrive) / 2, y_pos,
                    f"{ac} {arrive.strftime('%H:%M')} → 00:00",
                    ha='center', va='center', color='black', fontsize=8)

        y_pos += 1

    ax.set_xlim([datetime.combine(current_day, datetime.min.time()),
                 datetime.combine(current_day + timedelta(days=1), datetime.min.time())])
    ax.set_xlabel("Time of Day")
    ax.set_yticks([])
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
    ax.set_title(f"Ground Time for {current_day}")
    st.pyplot(fig)
