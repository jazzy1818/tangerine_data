"""Summarize observed Tangerine account access and account-level inflows."""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
TIERS = ["Lower", "Middle", "Upper"]
SHARED_ACCESS = "Shared account access"
OWNER_ONLY = "Owner record only"


def build_tables():
    monthly = pd.read_csv(DATA / "monthly_summary.csv", usecols=["account_id", "month", "money_in"])
    account_inflows = monthly.groupby("account_id").agg(
        median_monthly_account_inflow=("money_in", "median"),
        account_last_month=("month", "max"),
    )
    lower, upper = account_inflows["median_monthly_account_inflow"].quantile([1 / 3, 2 / 3])
    account_inflows["inflow_tier"] = pd.cut(
        account_inflows["median_monthly_account_inflow"],
        bins=[float("-inf"), lower, upper, float("inf")],
        labels=TIERS,
    )

    clients = pd.read_csv(DATA / "clients.csv", usecols=["client_id", "birth_date"], parse_dates=["birth_date"])
    dispositions = pd.read_csv(DATA / "dispositions.csv", usecols=["client_id", "account_id", "type"])
    people = dispositions.rename(columns={"type": "account_role"}).merge(clients, on="client_id", validate="many_to_one")
    people = people.merge(account_inflows, on="account_id", how="left", validate="many_to_one")

    as_of = pd.Period(monthly["month"].max(), freq="M").end_time.normalize()
    birthday = people.pop("birth_date")
    birthday_this_year = (birthday.dt.month * 100 + birthday.dt.day) <= (as_of.month * 100 + as_of.day)
    people["age"] = as_of.year - birthday.dt.year - (~birthday_this_year).astype(int)
    people["age_as_of"] = as_of.date().isoformat()

    identity = ["account_id", "client_id", "age"]
    owners = people.loc[people["account_role"].eq("owner"), identity]
    authorized = people.loc[people["account_role"].eq("authorized user"), identity]
    connections = owners.rename(columns={"client_id": "owner_client_id", "age": "owner_age"}).merge(
        authorized.rename(columns={"client_id": "authorized_client_id", "age": "authorized_age"}),
        on="account_id",
        validate="one_to_many",
    )
    connections["connection_type"] = SHARED_ACCESS

    people["relationship_status"] = people["account_id"].isin(connections["account_id"]).map({
        True: SHARED_ACCESS, False: OWNER_ONLY,
    })
    return people, connections, lower, upper


def draw_table(axis, rows, headers, widths, height, ink):
    table = axis.table(
        cellText=rows, colLabels=headers, colWidths=widths,
        cellLoc="left", colLoc="left", bbox=[0, 1 - height, 1, height],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, _), cell in table.get_celld().items():
        cell.set_edgecolor("white")
        cell.set_facecolor(ink if row == 0 else ("#EFF4F6" if row % 2 else "#F8FAFB"))
        cell.set_text_props(color="white" if row == 0 else ink, weight="bold" if row == 0 else "normal")


def make_preview(people, connections, lower, upper, destination):
    counts = (
        people.groupby(["relationship_status", "inflow_tier"], observed=True)
        .size()
        .unstack(fill_value=0)
        .reindex(index=[SHARED_ACCESS, OWNER_ONLY], columns=TIERS, fill_value=0)
    )
    counts["Total"] = counts.sum(axis=1)
    pairs = connections.sort_values("account_id").head(10)
    ink = "#172B36"
    muted = "#4D616B"
    fig, (detail, summary) = plt.subplots(1, 2, figsize=(15, 7.8), gridspec_kw={"width_ratios": [1, 1.23]})
    fig.subplots_adjust(left=0.06, right=0.94, top=0.79, bottom=0.15, wspace=0.18)
    fig.text(0.06, 0.93, "Shared-account connections and client labels", fontsize=23, weight="bold", color=ink)
    as_of = pd.Timestamp(people["age_as_of"].iloc[0])
    fig.text(0.06, 0.879, f"Tangerine datathon data. Ages at {as_of:%B %Y}.", fontsize=11, color=muted)

    detail.set_title("Connections", loc="left", fontsize=15, weight="bold", color=ink, pad=15)
    detail.axis("off")
    if pairs.empty:
        detail.text(0, 0.95, "No shared account access appears in the records.", va="top", color=muted)
    else:
        cells = [
            [str(row.account_id), f"{row.owner_client_id} ({row.owner_age})", f"{row.authorized_client_id} ({row.authorized_age})"]
            for row in pairs.itertuples(index=False)
        ]
        draw_table(detail, cells, ["Account ID", "Owner ID (age)", "Authorized ID (age)"], [0.21, 0.35, 0.44], 0.85, ink)
    detail.text(0, 0.10, f"{len(pairs):,} records shown. The CSV includes all {len(connections):,} shared-account connections.",
                fontsize=9, color=muted, va="top")

    summary.set_title("Labels by account inflow tier", loc="left", fontsize=15, weight="bold", color=ink, pad=15)
    summary.axis("off")
    label_rows = [[label, *(f"{count:,}" for count in row)] for label, row in counts.iterrows()]
    draw_table(summary, label_rows, ["Account access", *counts.columns], [0.52, 0.12, 0.12, 0.12, 0.12], 0.4, ink)
    summary.text(0, 0.53, f"{len(people):,} clients in the labels CSV. Join either client ID from the\nconnections table to the client ID in the labels table.",
                 fontsize=10, color=muted, va="top")

    fig.text(0.06, 0.058, f"Inflow tiers use thirds of median monthly account inflows. Cutoffs are CAD {lower:,.2f} and {upper:,.2f}.",
             fontsize=9, color=muted)
    fig.text(0.06, 0.033, "Access roles come from the account records. Individual income and family relationships are unverified.",
             fontsize=9, color=muted)
    fig.savefig(destination, dpi=160, facecolor="white")
    plt.close(fig)


def main():
    labels, connections, lower, upper = build_tables()
    output = ROOT / "outputs"
    output.mkdir(exist_ok=True)
    label_columns = [
        "client_id", "age", "age_as_of", "account_id", "account_role", "median_monthly_account_inflow",
        "inflow_tier", "account_last_month", "relationship_status",
    ]
    labels.sort_values("client_id")[label_columns].to_csv(output / "client_labels.csv", index=False, float_format="%.3f")
    connections.sort_values(["connection_type", "account_id"]).to_csv(output / "client_connections.csv", index=False)
    make_preview(labels, connections, lower, upper, output / "income_and_relationships.png")
    print(f"Wrote {len(labels):,} client labels and {len(connections):,} connections in {output}")


if __name__ == "__main__":
    main()
