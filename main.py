
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, time, timedelta
import altair as alt
import uuid

st.set_page_config(page_title="Weekly Staffing Heatmap", layout="wide")

st.title("Weekly Staffing Planner — Heatmap & Intervals")

# --- Helpers ---
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_TO_IDX = {d:i for i, d in enumerate(DAYS)}

def time_range(start: time, end: time, step_minutes: int):
    """Yield times from [start, end) within a single day at given minute steps.
    If end <= start, treat as wrapping at midnight (overnight)."""
    t0 = datetime.combine(datetime.today().date(), start)
    t1 = datetime.combine(datetime.today().date(), end)
    step = timedelta(minutes=step_minutes)

    if t1 <= t0:
        # Wrap at midnight: [t0, midnight) U [midnight, t1)
        t_mid = datetime.combine(datetime.today().date(), time(23, 59, 59))
        t = t0
        while t <= t_mid:
            yield t.time()
            t += step
        # Start from 00:00 of next day
        t = datetime.combine(datetime.today().date(), time(0, 0))
        while t < t1:
            yield t.time()
            t += step
    else:
        t = t0
        while t < t1:
            yield t.time()
            t += step

def build_empty_grid(step_minutes: int) -> pd.DataFrame:
    # Build index of times from 00:00 to 24:00 (exclusive of 24:00 in increments)
    times = []
    t = datetime.combine(datetime.today().date(), time(0,0))
    end = t + timedelta(days=1)
    step = timedelta(minutes=step_minutes)
    while t < end:
        times.append(t.time())
        t += step
    # Create frame with rows=time, columns=days, zero counts
    df = pd.DataFrame(0, index=pd.Index(times, name="Time"), columns=DAYS, dtype=int)
    return df

def apply_person_to_grid(df: pd.DataFrame, person: dict, step_minutes: int):
    mode = person["mode"]  # "Working days" or "Days off"
    selected_days = person["days"]  # list of ints 0..6
    start_t = person["start"]
    end_t = person["end"]

    if mode == "Working days":
        day_indices = selected_days
    else:
        # Days off → working days are complement
        day_indices = [i for i in range(7) if i not in selected_days]

    # For each day, add 1 for all intervals the person works
    # Handle overnight by splitting across day boundaries
    for d_idx in day_indices:
        # normal case: start < end on same day
        if (datetime.combine(datetime.today().date(), end_t) >
            datetime.combine(datetime.today().date(), start_t)):
            for tt in time_range(start_t, end_t, step_minutes):
                if tt in df.index:
                    df.iloc[df.index.get_loc(tt), d_idx] += 1
        else:
            # overnight: day d gets [start, 24:00), day (d+1)%7 gets [00:00, end)
            for tt in time_range(start_t, time(23,59,59), step_minutes):
                # inclusive last tick near midnight
                if tt in df.index:
                    df.iloc[df.index.get_loc(tt), d_idx] += 1
            next_day = (d_idx + 1) % 7
            for tt in time_range(time(0,0), end_t, step_minutes):
                if tt in df.index:
                    df.iloc[df.index.get_loc(tt), next_day] += 1

def pretty_time(t: time) -> str:
    return datetime.strptime(t.strftime("%H:%M"), "%H:%M").strftime("%I:%M %p")

# --- Session State ---
if "people" not in st.session_state:
    st.session_state.people = []  # list of dicts with keys: id,name,mode,days,start,end
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None

st.sidebar.header("Add / Edit Person")

colA, colB = st.sidebar.columns([1,1])
with colA:
    mode = st.selectbox("Interpret days as:", ["Working days", "Days off"])
with colB:
    interval = st.selectbox("Interval (minutes)", [15, 30, 60], index=1)

name = st.sidebar.text_input("Name")
days_pick = st.sidebar.multiselect("Days", DAYS, default=["Monday","Tuesday","Wednesday","Thursday","Friday"])
col1, col2 = st.sidebar.columns(2)
with col1:
    start_t = st.sidebar.time_input("Shift start", value=time(9,0), step=300)
with col2:
    end_t = st.sidebar.time_input("Shift end", value=time(17,0), step=300)

btn_cols = st.sidebar.columns([1,1,1])
with btn_cols[0]:
    add_update = st.button("Add / Update", use_container_width=True)
with btn_cols[1]:
    clear_form = st.button("Clear", use_container_width=True)
with btn_cols[2]:
    reset_all = st.button("Reset All", type="secondary", use_container_width=True)

if clear_form:
    st.session_state.edit_id = None
    st.experimental_rerun()

if reset_all:
    st.session_state.people = []
    st.session_state.edit_id = None
    st.experimental_rerun()

# Handle add/update
if add_update:
    if not name.strip():
        st.sidebar.error("Please enter a name.")
    elif start_t == end_t:
        st.sidebar.error("Start time and end time cannot be identical (duration would be 0).")
    else:
        payload = {
            "id": st.session_state.edit_id or str(uuid.uuid4()),
            "name": name.strip(),
            "mode": mode,
            "days": [DAY_TO_IDX[d] for d in days_pick],
            "start": start_t,
            "end": end_t
        }
        if st.session_state.edit_id is None:
            st.session_state.people.append(payload)
        else:
            # update existing
            for i, p in enumerate(st.session_state.people):
                if p["id"] == st.session_state.edit_id:
                    st.session_state.people[i] = payload
                    break
            st.session_state.edit_id = None
        st.experimental_rerun()

st.subheader("Current People")
if len(st.session_state.people) == 0:
    st.info("No people added yet. Use the sidebar to add staff.")
else:
    # Build a table with actions
    # Display readable values
    display_rows = []
    for p in st.session_state.people:
        display_rows.append({
            "id": p["id"],
            "Name": p["name"],
            "Interpretation": p["mode"],
            "Days": ", ".join([DAYS[i] for i in sorted(p["days"])] if p["days"] else "(none)"),
            "Start": pretty_time(p["start"]),
            "End": pretty_time(p["end"]),
        })
    df_people = pd.DataFrame(display_rows).set_index("id")
    st.dataframe(df_people, use_container_width=True)

    # Action buttons per person
    c1, c2 = st.columns(2)
    with c1:
        target_edit = st.selectbox("Select a person to edit", options=["(select)"] + [p["id"] for p in st.session_state.people],
                                   format_func=lambda x: "(select)" if x=="(select)" else df_people.loc[x, "Name"])
        if st.button("Load into form"):
            if target_edit != "(select)":
                st.session_state.edit_id = target_edit
                person = next(p for p in st.session_state.people if p["id"] == target_edit)
                # populate form by re-render with defaults
                st.session_state["__form_defaults__"] = {
                    "mode": person["mode"],
                    "interval": interval,
                    "name": person["name"],
                    "days": [DAYS[i] for i in person["days"]],
                    "start": person["start"],
                    "end": person["end"],
                }
                # Note: Streamlit doesn't allow programmatically setting widget values cleanly without state hacks.
                # We'll just instruct the user to manually adjust if needed.
                st.info("Selected. Update the sidebar fields manually, then click Add / Update to save changes.")
    with c2:
        target_del = st.selectbox("Select a person to remove", options=["(select)"] + [p["id"] for p in st.session_state.people],
                                  format_func=lambda x: "(select)" if x=="(select)" else df_people.loc[x, "Name"])
        if st.button("Remove"):
            if target_del != "(select)":
                st.session_state.people = [p for p in st.session_state.people if p["id"] != target_del]
                st.success("Removed.")
                st.experimental_rerun()

st.markdown("---")

# Heatmap & interval table options
st.subheader("Staffing Intervals (Monday 12:00am — Sunday 12:00am)")
colh1, colh2, colh3 = st.columns([1,1,1])
with colh1:
    show_table = st.checkbox("Show interval table", value=True)
with colh2:
    show_heatmap = st.checkbox("Show heatmap", value=True)
with colh3:
    annotate_counts = st.checkbox("Annotate counts on heatmap", value=False)

# Build staffing grid
grid = build_empty_grid(interval)
for person in st.session_state.people:
    apply_person_to_grid(grid, person, interval)

# Make Time index pretty strings for display (12-hour clock)
grid_display = grid.copy()
grid_display.index = [datetime.strptime(t.strftime("%H:%M"), "%H:%M").strftime("%I:%M %p") for t in grid_display.index]

if show_table:
    # Optional conditional formatting as gradient heatmap
    st.markdown("**Interval Table**")
    st.caption("Tip: Use the toggle below to apply heatmap-style conditional formatting to the table.")
    cmode = st.toggle("Apply heatmap conditional formatting to table", value=True)
    if cmode:
        st.dataframe(grid_display.style.background_gradient(axis=None), use_container_width=True)
    else:
        st.dataframe(grid_display, use_container_width=True)

if show_heatmap:
    st.markdown("**Heatmap**")
    # Prepare data for Altair
    df_melt = grid_display.reset_index().melt(id_vars="Time", var_name="Day", value_name="Staff")
    chart = alt.Chart(df_melt).mark_rect().encode(
        x=alt.X("Day:N", sort=DAYS),
        y=alt.Y("Time:N", sort=list(grid_display.index)),
        color=alt.Color("Staff:Q", scale=alt.Scale(scheme="greens")),
        tooltip=["Day:N", "Time:N", "Staff:Q"],
    ).properties(width=700, height=800)

    if annotate_counts:
        text = alt.Chart(df_melt).mark_text(baseline='middle').encode(
            x=alt.X("Day:N", sort=DAYS),
            y=alt.Y("Time:N", sort=list(grid_display.index)),
            text="Staff:Q",
        )
        chart = chart + text

    st.altair_chart(chart, use_container_width=True)

# Footer
st.markdown("---")
st.caption("Overnight shifts are supported. If shift end <= start, hours after midnight are applied to the next day.")
