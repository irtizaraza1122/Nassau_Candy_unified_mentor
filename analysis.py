"""Shared data loading, cleaning and aggregation for the Nassau Candy project."""
import pandas as pd
import numpy as np

FACTORIES = {
    "Lot's O' Nuts": (32.881893, -111.768036),
    "Wicked Choccy's": (32.076176, -81.088371),
    "Sugar Shack": (48.11914, -96.18115),
    "Secret Factory": (41.446333, -90.565487),
    "The Other Factory": (35.1175, -89.971107),
}

PRODUCT_FACTORY = {
    "Wonka Bar - Nutty Crunch Surprise": "Lot's O' Nuts",
    "Wonka Bar - Fudge Mallows": "Lot's O' Nuts",
    "Wonka Bar -Scrumdiddlyumptious": "Lot's O' Nuts",
    "Wonka Bar - Milk Chocolate": "Wicked Choccy's",
    "Wonka Bar - Triple Dazzle Caramel": "Wicked Choccy's",
    "Laffy Taffy": "Sugar Shack",
    "SweeTARTS": "Sugar Shack",
    "Nerds": "Sugar Shack",
    "Fun Dip": "Sugar Shack",
    "Fizzy Lifting Drinks": "Sugar Shack",
    "Everlasting Gobstopper": "Secret Factory",
    "Hair Toffee": "The Other Factory",
    "Lickable Wallpaper": "Secret Factory",
    "Wonka Gum": "Secret Factory",
    "Kazookles": "The Other Factory",
}

STATE_ABBR = {
    'Alabama':'AL','Arizona':'AZ','Arkansas':'AR','California':'CA','Colorado':'CO','Connecticut':'CT',
    'Delaware':'DE','District of Columbia':'DC','Florida':'FL','Georgia':'GA','Idaho':'ID','Illinois':'IL',
    'Indiana':'IN','Iowa':'IA','Kansas':'KS','Kentucky':'KY','Louisiana':'LA','Maine':'ME','Maryland':'MD',
    'Massachusetts':'MA','Michigan':'MI','Minnesota':'MN','Mississippi':'MS','Missouri':'MO','Montana':'MT',
    'Nebraska':'NE','Nevada':'NV','New Hampshire':'NH','New Jersey':'NJ','New Mexico':'NM','New York':'NY',
    'North Carolina':'NC','North Dakota':'ND','Ohio':'OH','Oklahoma':'OK','Oregon':'OR','Pennsylvania':'PA',
    'Rhode Island':'RI','South Carolina':'SC','South Dakota':'SD','Tennessee':'TN','Texas':'TX','Utah':'UT',
    'Vermont':'VT','Virginia':'VA','Washington':'WA','West Virginia':'WV','Wisconsin':'WI','Wyoming':'WY',
}


def load_clean(path="Nassau_Candy_Distributor.csv"):
    """Load, validate and clean the data. Returns (clean_df, cleaning_log dict)."""
    df = pd.read_csv(path)
    log = {"rows_raw": len(df)}

    # standardise text fields
    for c in ["Ship Mode", "City", "State/Province", "Region", "Division", "Product Name", "Country/Region"]:
        df[c] = df[c].astype(str).str.strip()
    df["Postal Code"] = df["Postal Code"].astype(str).str.strip()

    # dates (dd-mm-yyyy)
    df["Order Date"] = pd.to_datetime(df["Order Date"], format="%d-%m-%Y", errors="coerce")
    df["Ship Date"] = pd.to_datetime(df["Ship Date"], format="%d-%m-%Y", errors="coerce")
    log["invalid_dates"] = int(df[["Order Date", "Ship Date"]].isna().any(axis=1).sum())
    df = df.dropna(subset=["Order Date", "Ship Date"]).copy()

    # raw lead time
    df["Raw Lead Time"] = (df["Ship Date"] - df["Order Date"]).dt.days

    # --- date-offset correction -------------------------------------------------
    # Ship dates in the file are shifted by a fixed block per Order-ID year
    # (raw lead times are 904-1,642 days). The Same Day orders in each block
    # sit at the block minimum, so subtracting that minimum restores
    # realistic lead times (Same Day 0-1d ... Standard 4-8d).
    df["ID Year"] = df["Order ID"].str.extract(r"^[A-Za-z]{2}-(\d{4})")[0].astype(int)
    offset = df[df["Ship Mode"] == "Same Day"].groupby("ID Year")["Raw Lead Time"].min()
    df["Date Offset"] = df["ID Year"].map(offset)
    df["Lead Time"] = df["Raw Lead Time"] - df["Date Offset"]
    log["offsets"] = offset.to_dict()

    log["negative_lead_time_removed"] = int((df["Lead Time"] < 0).sum())
    df = df[df["Lead Time"] >= 0].copy()
    log["missing_ship_records"] = 0

    # factory + route
    df["Factory"] = df["Product Name"].map(PRODUCT_FACTORY)
    log["unmapped_products"] = int(df["Factory"].isna().sum())
    df = df.dropna(subset=["Factory"]).copy()
    df["Route (State)"] = df["Factory"] + " → " + df["State/Province"]
    df["Route (Region)"] = df["Factory"] + " → " + df["Region"]
    df["State Code"] = df["State/Province"].map(STATE_ABBR)
    df["Order Year"] = df["Order Date"].dt.year
    log["rows_clean"] = len(df)
    return df.reset_index(drop=True), log


def route_table(df, by="Route (State)", threshold=5, min_orders=1):
    """Aggregate shipments per route with KPIs and an efficiency score."""
    g = df.groupby(by)
    t = g.agg(
        Shipments=("Lead Time", "size"),
        Avg_Lead_Time=("Lead Time", "mean"),
        Median_Lead_Time=("Lead Time", "median"),
        Std_Lead_Time=("Lead Time", "std"),
        Sales=("Sales", "sum"),
        Gross_Profit=("Gross Profit", "sum"),
    ).reset_index()
    t["Std_Lead_Time"] = t["Std_Lead_Time"].fillna(0)
    t["Delay_Frequency_%"] = g["Lead Time"].apply(lambda s: (s > threshold).mean() * 100).values
    # mode-mix adjustment: what lead time would we expect given the route's ship-mode mix?
    mode_avg = df.groupby("Ship Mode")["Lead Time"].mean()
    exp = df.assign(_e=df["Ship Mode"].map(mode_avg)).groupby(by)["_e"].mean().values
    t["Mode_Adjusted_Diff"] = t["Avg_Lead_Time"] - exp
    t = t[t["Shipments"] >= min_orders].copy()
    lo, hi = t["Avg_Lead_Time"].min(), t["Avg_Lead_Time"].max()
    t["Efficiency_Score"] = 100.0 if hi == lo else (hi - t["Avg_Lead_Time"]) / (hi - lo) * 100
    t = t.sort_values("Avg_Lead_Time").reset_index(drop=True)
    t.insert(0, "Rank", np.arange(1, len(t) + 1))
    return t.round(2)
