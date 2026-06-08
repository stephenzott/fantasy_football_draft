"""
Fetches player flags from a Google Sheet (public CSV export).

The sheet must be shared as "Anyone with the link can view."
Columns: Date | First Name | Last Name | Team | Incident | Resolution
"""

import pandas as pd

SHEET_ID = "1PdD1hmkFPRgOJ_lDb4bhieYV4B4hy0zcBsIkDxJAkEs"
GID = "0"


def fetch_flags() -> dict[str, list[str]]:
    """Return a dict mapping lowercase player name to a list of flag strings.

    Example:
        {"josh jacobs": ["DUI — Paid $500 fine, community service.",
                         "Domestic violence — Resolution undetermined."]}
    """
    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/export?format=csv&gid={GID}"
    )

    try:
        df = pd.read_csv(
            url,
            header=0,
            names=["month", "first_name", "last_name", "team", "incident", "resolution"],
        )
    except Exception as e:
        raise RuntimeError(
            f"Could not fetch flags sheet. Make sure the Google Sheet is set to "
            f"'Anyone with the link can view'.\nError: {e}"
        )

    df = df.dropna(subset=["first_name", "last_name"])

    flags: dict[str, list[str]] = {}
    for _, row in df.iterrows():
        first = str(row["first_name"]).strip()
        last = str(row["last_name"]).strip()
        incident = str(row["incident"]).strip()
        resolution = str(row.get("resolution", "")).strip()

        if first == "nan" or last == "nan" or incident == "nan":
            continue

        key = f"{first} {last}".lower()
        flag = f"{incident} — {resolution}" if resolution and resolution != "nan" else incident
        flags.setdefault(key, []).append(flag)

    return flags


if __name__ == "__main__":
    flags = fetch_flags()
    for name, entries in sorted(flags.items()):
        print(f"\n{name.title()}")
        for f in entries:
            print(f"  • {f}")
