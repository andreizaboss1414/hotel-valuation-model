#!/usr/bin/env python3
"""Hotel valuation practice model.

A practice and demonstration tool, not an appraisal. It builds a five year
property level cash flow for a single hotel from a handful of operating
assumptions, then values the hotel by direct capitalisation and by discounted
cash flow, and prints a sensitivity table on cap rate and ADR.

Standard library only, Python 3.9 or later.

Usage:
    python3 hotel_valuation.py example.json
    python3 hotel_valuation.py example.csv --csv out.csv
    python3 hotel_valuation.py                   (runs on built-in defaults)
    python3 hotel_valuation.py --print-defaults  (dumps the default input as JSON)
"""

import argparse
import copy
import csv
import json
import os
import sys

YEARS = 5  # explicit forecast horizon; year 6 is only used for the exit value

DEFAULTS = {
    "name": "Default hotel (illustrative)",
    "currency": "CHF",
    "rooms": 100,
    "days_per_year": 365,
    # Year 1 operating assumptions
    "occupancy": 0.70,
    "adr": 250.0,
    "rooms_margin": 0.70,
    "rooms_variable_cost_pct": 0.10,
    "outlets": [
        {"name": "Food and beverage", "revenue": 3000000, "margin": 0.18},
        {"name": "Other operated departments", "revenue": 400000, "margin": 0.35},
    ],
    "scale_outlets_with_occupancy": True,
    "undistributed_costs": {
        "Administration and general": 900000,
        "Information and telecom systems": 150000,
        "Sales and marketing": 600000,
        "Property operation and maintenance": 450000,
        "Utilities": 320000,
    },
    "management_fee_base_pct": 0.03,
    "management_fee_incentive_pct": 0.0,
    "fixed_charges": {
        "Property and capital taxes": 180000,
        "Insurance": 90000,
    },
    "ffe_reserve_pct": 0.04,
    "capex": [0, 0, 0, 0, 0],
    # Valuation
    "going_in_cap_rate": None,  # None means: use the exit cap rate
    "exit_cap_rate": 0.050,
    "discount_rate": 0.070,
    "selling_costs_pct": 0.02,
    # Years 2 to 5. Each item is a single number (same every year) or a list of 4.
    "forecast": {
        "occupancy": None,  # None means: hold year 1 occupancy flat
        "adr_growth": 0.02,
        "outlet_revenue_growth": 0.02,
        "cost_growth": 0.015,
    },
    "sensitivity": {
        "cap_rate_steps": [-0.005, -0.0025, 0.0, 0.0025, 0.005],
        "adr_steps": [-0.10, -0.05, 0.0, 0.05, 0.10],
    },
}


# --------------------------------------------------------------------------
# Input handling
# --------------------------------------------------------------------------

def deep_merge(base, override):
    """Return base updated with override. Dicts merge, everything else replaces."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def parse_number(text):
    """Parse '0.74', '74%', "1'200'000" or '1_200_000' into a float."""
    s = str(text).strip().replace("'", "").replace("_", "").replace(" ", "")
    if s.endswith("%"):
        return float(s[:-1]) / 100.0
    return float(s)


def parse_value(text):
    """A cell is a number, a semicolon separated list of numbers, or text."""
    s = str(text).strip()
    if s.lower() in ("", "none", "null"):
        return None
    if s.lower() in ("true", "yes"):
        return True
    if s.lower() in ("false", "no"):
        return False
    if ";" in s:
        return [parse_number(p) for p in s.split(";") if p.strip() != ""]
    try:
        return parse_number(s)
    except ValueError:
        return s


def load_csv(path):
    """Read a two column key,value CSV into the same shape as the JSON input.

    Keys:
      rooms, occupancy, adr, ...            top level values
      outlet.<Name>.revenue / .margin       one outlet per name
      undistributed.<Name>                  one undistributed cost line
      fixed_charge.<Name>                   one fixed charge line
      forecast.<field>                      e.g. forecast.adr_growth = 0.03;0.025;0.02;0.02
      sensitivity.<field>                   e.g. sensitivity.adr_steps = -0.1;0;0.1
    Lines starting with # and a 'key,value' header are ignored.
    """
    data = {}
    outlets = {}
    outlet_order = []
    undistributed = {}
    fixed = {}
    with open(path, newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if not row or not row[0].strip() or row[0].strip().startswith("#"):
                continue
            key = row[0].strip()
            if key.lower() == "key":
                continue
            raw = row[1] if len(row) > 1 else ""
            if key.startswith("outlet."):
                name, _, field = key[len("outlet."):].rpartition(".")
                if not name or field not in ("revenue", "margin"):
                    raise ValueError("CSV key %r: use outlet.<Name>.revenue or outlet.<Name>.margin" % key)
                if name not in outlets:
                    outlets[name] = {"name": name}
                    outlet_order.append(name)
                outlets[name][field] = parse_number(raw)
            elif key.startswith("undistributed."):
                undistributed[key[len("undistributed."):]] = parse_number(raw)
            elif key.startswith("fixed_charge."):
                fixed[key[len("fixed_charge."):]] = parse_number(raw)
            elif "." in key:
                section, _, field = key.partition(".")
                data.setdefault(section, {})[field] = parse_value(raw)
            else:
                data[key] = parse_value(raw)
    if outlets:
        data["outlets"] = [outlets[n] for n in outlet_order]
    if undistributed:
        data["undistributed_costs"] = undistributed
    if fixed:
        data["fixed_charges"] = fixed
    return data


def load_input(path):
    if path is None:
        return copy.deepcopy(DEFAULTS)
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        with open(path, encoding="utf-8") as handle:
            user = json.load(handle)
    elif ext == ".csv":
        user = load_csv(path)
    else:
        raise ValueError("Input file must end in .json or .csv, got %r" % path)
    # Lists of outlets and cost dicts given by the user replace the defaults
    # entirely, so a hotel without a spa does not inherit the default spa.
    cfg = deep_merge(DEFAULTS, user)
    for key in ("undistributed_costs", "fixed_charges"):
        if key in user:
            cfg[key] = copy.deepcopy(user[key])
    return cfg


def path_of(value, name, length):
    """Expand a scalar or a list into a list of `length` values."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return [float(value)] * length
    if isinstance(value, list) and len(value) == length:
        return [float(v) for v in value]
    raise ValueError("%s must be a single number or a list of %d numbers, got %r" % (name, length, value))


def validate(cfg):
    errors = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    check(cfg["rooms"] > 0, "rooms must be positive")
    check(cfg["days_per_year"] > 0, "days_per_year must be positive")
    check(0 < cfg["occupancy"] <= 1, "occupancy must be a fraction between 0 and 1, e.g. 0.74")
    check(cfg["adr"] > 0, "adr must be positive")
    check(-1 <= cfg["rooms_margin"] < 1, "rooms_margin must be a fraction, e.g. 0.72")
    check(0 <= cfg["rooms_variable_cost_pct"] <= 1 - cfg["rooms_margin"],
          "rooms_variable_cost_pct must be between 0 and (1 - rooms_margin)")
    for o in cfg["outlets"]:
        check("name" in o and "revenue" in o and "margin" in o,
              "each outlet needs name, revenue and margin: %r" % o)
        if "margin" in o:
            check(-1 <= o["margin"] < 1, "outlet margin must be a fraction: %r" % o)
    check(cfg["exit_cap_rate"] > 0, "exit_cap_rate must be positive, e.g. 0.05")
    gi = cfg.get("going_in_cap_rate")
    check(gi is None or gi > 0, "going_in_cap_rate must be positive or null")
    check(cfg["discount_rate"] > -1, "discount_rate must be greater than -1")
    check(0 <= cfg["selling_costs_pct"] < 1, "selling_costs_pct must be a fraction")
    check(isinstance(cfg["capex"], list) and len(cfg["capex"]) == YEARS,
          "capex must be a list of %d numbers" % YEARS)
    for pct in ("management_fee_base_pct", "management_fee_incentive_pct", "ffe_reserve_pct"):
        check(0 <= cfg[pct] < 1, "%s must be a fraction" % pct)
    fc = cfg["forecast"]
    for key in ("adr_growth", "outlet_revenue_growth", "cost_growth"):
        try:
            path_of(fc[key], "forecast." + key, YEARS - 1)
        except ValueError as exc:
            errors.append(str(exc))
    if fc.get("occupancy") is not None:
        try:
            occ = path_of(fc["occupancy"], "forecast.occupancy", YEARS - 1)
            check(all(0 < x <= 1 for x in occ), "forecast.occupancy values must be between 0 and 1")
        except ValueError as exc:
            errors.append(str(exc))
    if errors:
        raise ValueError("Input problems:\n  - " + "\n  - ".join(errors))


# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------

def project(cfg, adr_shift=0.0):
    """Project YEARS + 1 years. Year 6 exists only to set the exit value.

    adr_shift moves ADR by a percentage in every year (used for sensitivity).
    Rooms costs are anchored to the unshifted base case, so a rate change
    flows through to profit net only of commissions, as it does in practice.
    """
    n = YEARS + 1
    fc = cfg["forecast"]
    # Paths for years 2..5, then year 6 repeats year 5.
    adr_g = path_of(fc["adr_growth"], "adr_growth", YEARS - 1)
    out_g = path_of(fc["outlet_revenue_growth"], "outlet_revenue_growth", YEARS - 1)
    cost_g = path_of(fc["cost_growth"], "cost_growth", YEARS - 1)
    adr_g, out_g, cost_g = adr_g + adr_g[-1:], out_g + out_g[-1:], cost_g + cost_g[-1:]
    if fc.get("occupancy") is None:
        occ_path = [cfg["occupancy"]] * n
    else:
        later = path_of(fc["occupancy"], "occupancy", YEARS - 1)
        occ_path = [cfg["occupancy"]] + later + later[-1:]

    rooms = cfg["rooms"]
    available = rooms * cfg["days_per_year"]

    # Calibrate rooms department costs on year 1 of the base case:
    # cost = variable % of rooms revenue + fixed amount per occupied room.
    base_sold = available * cfg["occupancy"]
    base_rooms_rev = base_sold * cfg["adr"]
    base_rooms_cost = base_rooms_rev * (1 - cfg["rooms_margin"])
    var_pct = cfg["rooms_variable_cost_pct"]
    cpor_year1 = (base_rooms_cost - base_rooms_rev * var_pct) / base_sold

    years = []
    adr = cfg["adr"] * (1 + adr_shift)
    out_index = 1.0
    cost_index = 1.0
    for t in range(n):
        if t > 0:
            adr *= 1 + adr_g[t - 1]
            out_index *= 1 + out_g[t - 1]
            cost_index *= 1 + cost_g[t - 1]
        occ = occ_path[t]
        sold = available * occ
        rooms_rev = sold * adr
        rooms_cost = rooms_rev * var_pct + sold * cpor_year1 * cost_index
        rooms_profit = rooms_rev - rooms_cost

        occ_factor = occ / cfg["occupancy"] if cfg.get("scale_outlets_with_occupancy", True) else 1.0
        outlet_lines = []
        for o in cfg["outlets"]:
            rev = o["revenue"] * out_index * occ_factor
            outlet_lines.append((o["name"], rev, rev * o["margin"]))

        total_rev = rooms_rev + sum(r for _, r, _ in outlet_lines)
        dept_profit = rooms_profit + sum(p for _, _, p in outlet_lines)
        undistributed = [(k, v * cost_index) for k, v in cfg["undistributed_costs"].items()]
        total_undistributed = sum(v for _, v in undistributed)
        gop = dept_profit - total_undistributed

        base_fee = total_rev * cfg["management_fee_base_pct"]
        incentive_fee = max(0.0, gop) * cfg["management_fee_incentive_pct"]
        fixed = [(k, v * cost_index) for k, v in cfg["fixed_charges"].items()]
        total_fixed = sum(v for _, v in fixed)
        ebitda = gop - base_fee - incentive_fee - total_fixed
        ffe = total_rev * cfg["ffe_reserve_pct"]
        noi = ebitda - ffe
        capex = float(cfg["capex"][t]) if t < YEARS else 0.0

        years.append({
            "year": t + 1,
            "occupancy": occ,
            "adr": adr,
            "available_room_nights": available,
            "occupied_room_nights": sold,
            "revpar": rooms_rev / available,
            "rooms_revenue": rooms_rev,
            "outlets": outlet_lines,
            "total_revenue": total_rev,
            "trevpar": total_rev / available,
            "rooms_cost": rooms_cost,
            "rooms_cost_per_occupied_room": rooms_cost / sold,
            "rooms_profit": rooms_profit,
            "departmental_profit": dept_profit,
            "undistributed": undistributed,
            "total_undistributed": total_undistributed,
            "gop": gop,
            "gop_margin": gop / total_rev,
            "goppar": gop / available,
            "base_fee": base_fee,
            "incentive_fee": incentive_fee,
            "fixed_charges": fixed,
            "total_fixed_charges": total_fixed,
            "ebitda": ebitda,
            "ffe_reserve": ffe,
            "noi": noi,
            "noi_margin": noi / total_rev,
            "noi_per_room": noi / rooms,
            "capex": capex,
            "cash_flow": noi - capex,
        })
    return years


def irr(cash_flows):
    """Internal rate of return by bisection. Returns None if no sign change."""
    def npv(rate):
        return sum(cf / (1 + rate) ** i for i, cf in enumerate(cash_flows))
    lo, hi = -0.99, 1.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def value(cfg, adr_shift=0.0, exit_cap=None, going_in_cap=None):
    years = project(cfg, adr_shift)
    r = cfg["discount_rate"]
    exit_cap = cfg["exit_cap_rate"] if exit_cap is None else exit_cap
    if going_in_cap is None:
        going_in_cap = cfg.get("going_in_cap_rate") or cfg["exit_cap_rate"]

    explicit = years[:YEARS]
    discount_factors = [1 / (1 + r) ** y["year"] for y in explicit]
    pv_cash_flows = sum(y["cash_flow"] * d for y, d in zip(explicit, discount_factors))
    exit_noi = years[YEARS]["noi"]
    gross_exit = exit_noi / exit_cap
    net_exit = gross_exit * (1 - cfg["selling_costs_pct"])
    pv_exit = net_exit * discount_factors[-1]
    dcf_value = pv_cash_flows + pv_exit
    direct_cap_value = explicit[0]["noi"] / going_in_cap

    flows = [-direct_cap_value] + [y["cash_flow"] for y in explicit]
    flows[-1] += net_exit
    return {
        "years": years,
        "discount_factors": discount_factors,
        "pv_cash_flows": pv_cash_flows,
        "exit_noi": exit_noi,
        "gross_exit_value": gross_exit,
        "net_exit_value": net_exit,
        "pv_exit_value": pv_exit,
        "dcf_value": dcf_value,
        "direct_cap_value": direct_cap_value,
        "going_in_cap_rate": going_in_cap,
        "exit_cap_rate": exit_cap,
        "implied_cap_rate_from_dcf": explicit[0]["noi"] / dcf_value,
        "exit_share_of_dcf": pv_exit / dcf_value,
        "irr_at_direct_cap_price": irr(flows),
    }


def sensitivity(cfg, method):
    """Rows: cap rate shifts. Columns: ADR shifts. Cells: value."""
    sens = cfg["sensitivity"]
    base_exit = cfg["exit_cap_rate"]
    base_going_in = cfg.get("going_in_cap_rate") or base_exit
    rows = []
    for cs in sens["cap_rate_steps"]:
        row = []
        for a in sens["adr_steps"]:
            if method == "dcf":
                res = value(cfg, adr_shift=a, exit_cap=base_exit + cs)
                row.append(res["dcf_value"] if base_exit + cs > 0 else None)
            else:
                cap = base_going_in + cs
                res = value(cfg, adr_shift=a, going_in_cap=cap if cap > 0 else 1)
                row.append(res["direct_cap_value"] if cap > 0 else None)
        rows.append(row)
    return rows


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

def money(x, unit=1.0, decimals=0):
    if x is None:
        return "n/a"
    v = x / unit
    if round(v, decimals) == 0:
        v = 0.0  # avoid printing "-0"
    return "{:,.{d}f}".format(v, d=decimals)


def pct(x, decimals=1):
    return "n/a" if x is None else "{:.{d}f}%".format(x * 100, d=decimals)


def cash_flow_rows(years):
    """Line items for the CSV and the printed table: (label, values, kind)."""
    ys = years[:YEARS]
    rows = [
        ("Occupancy", [y["occupancy"] for y in ys], "pct"),
        ("ADR", [y["adr"] for y in ys], "rate"),
        ("RevPAR", [y["revpar"] for y in ys], "rate"),
        ("Occupied room nights", [y["occupied_room_nights"] for y in ys], "count"),
        ("Rooms revenue", [y["rooms_revenue"] for y in ys], "money"),
    ]
    for i, (name, _, _) in enumerate(ys[0]["outlets"]):
        rows.append((name + " revenue", [y["outlets"][i][1] for y in ys], "money"))
    rows += [
        ("Total revenue", [y["total_revenue"] for y in ys], "money"),
        ("Rooms dept. profit", [y["rooms_profit"] for y in ys], "money"),
    ]
    for i, (name, _, _) in enumerate(ys[0]["outlets"]):
        rows.append((name + " dept. profit", [y["outlets"][i][2] for y in ys], "money"))
    rows.append(("Total dept. profit", [y["departmental_profit"] for y in ys], "money"))
    for i, (name, _) in enumerate(ys[0]["undistributed"]):
        rows.append(("Less " + name, [-y["undistributed"][i][1] for y in ys], "money"))
    rows += [
        ("GOP", [y["gop"] for y in ys], "money"),
        ("GOP margin", [y["gop_margin"] for y in ys], "pct"),
        ("GOPPAR", [y["goppar"] for y in ys], "rate"),
        ("Less base management fee", [-y["base_fee"] for y in ys], "money"),
        ("Less incentive management fee", [-y["incentive_fee"] for y in ys], "money"),
    ]
    for i, (name, _) in enumerate(ys[0]["fixed_charges"]):
        rows.append(("Less " + name, [-y["fixed_charges"][i][1] for y in ys], "money"))
    rows += [
        ("EBITDA before FF&E reserve", [y["ebitda"] for y in ys], "money"),
        ("Less FF&E reserve", [-y["ffe_reserve"] for y in ys], "money"),
        ("NOI", [y["noi"] for y in ys], "money"),
        ("NOI margin", [y["noi_margin"] for y in ys], "pct"),
        ("NOI per room", [y["noi_per_room"] for y in ys], "count"),
        ("Less capital expenditure", [-y["capex"] for y in ys], "money"),
        ("Property level cash flow", [y["cash_flow"] for y in ys], "money"),
    ]
    return rows


def write_csv(path, years, result):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        w = csv.writer(handle)
        w.writerow(["line_item"] + ["year_%d" % (i + 1) for i in range(YEARS)])
        for label, values, kind in cash_flow_rows(years):
            digits = 4 if kind == "pct" else 2
            w.writerow([label] + [round(v, digits) for v in values])
        w.writerow(["Discount factor"] + [round(d, 6) for d in result["discount_factors"]])
        w.writerow(["PV of cash flow"] + [round(y["cash_flow"] * d, 2)
                                          for y, d in zip(years, result["discount_factors"])])


def fmt_cell(value_, kind):
    if kind == "pct":
        return pct(value_)
    if kind == "rate":
        return money(value_, decimals=1)
    if kind == "count":
        return money(value_)
    return money(value_, unit=1000.0)


def print_summary(cfg, result, csv_path):
    cur = cfg["currency"]
    years = result["years"]
    out = []
    p = out.append
    p("HOTEL VALUATION PRACTICE MODEL - not an appraisal")
    p("=" * 78)
    p("Property:        %s" % cfg["name"])
    p("Rooms:           %s" % money(cfg["rooms"]))
    p("Discount rate:   %s    Exit cap rate: %s    Going-in cap rate: %s"
      % (pct(cfg["discount_rate"], 2), pct(result["exit_cap_rate"], 2), pct(result["going_in_cap_rate"], 2)))
    p("")
    p("FIVE YEAR PROPERTY LEVEL CASH FLOW (money in %s thousands, rates in %s)" % (cur, cur))
    p("-" * 78)
    header = "%-40s" % "" + "".join("%8s" % ("Y%d" % (i + 1)) for i in range(YEARS))
    p(header)
    for label, values, kind in cash_flow_rows(years):
        if label in ("Total revenue", "GOP", "NOI", "Property level cash flow"):
            p("")
        p("%-40s" % label[:40] + "".join("%8s" % fmt_cell(v, kind) for v in values))
    p("")
    y1 = years[0]
    p("KEY YEAR 1 METRICS")
    p("-" * 78)
    p("RevPAR            %s %s" % (cur, money(y1["revpar"], decimals=2)))
    p("TRevPAR           %s %s" % (cur, money(y1["trevpar"], decimals=2)))
    p("GOP               %s %s   (margin %s)" % (cur, money(y1["gop"]), pct(y1["gop_margin"])))
    p("GOPPAR            %s %s" % (cur, money(y1["goppar"], decimals=2)))
    p("NOI               %s %s   (margin %s, %s %s per room)"
      % (cur, money(y1["noi"]), pct(y1["noi_margin"]), cur, money(y1["noi_per_room"])))
    p("")
    p("VALUATION")
    p("-" * 78)
    p("Direct capitalisation: Y1 NOI %s / going-in cap %s"
      % (money(y1["noi"]), pct(result["going_in_cap_rate"], 2)))
    p("  Value                          %s %s   (%s %s per room)"
      % (cur, money(result["direct_cap_value"]), cur, money(result["direct_cap_value"] / cfg["rooms"])))
    p("Discounted cash flow at %s:" % pct(cfg["discount_rate"], 2))
    p("  PV of Y1-Y5 cash flows         %s %s" % (cur, money(result["pv_cash_flows"])))
    p("  Exit value: Y6 NOI %s / %s = %s, less %s selling costs = %s"
      % (money(result["exit_noi"]), pct(result["exit_cap_rate"], 2), money(result["gross_exit_value"]),
         pct(cfg["selling_costs_pct"], 1), money(result["net_exit_value"])))
    p("  PV of exit value               %s %s   (%s of DCF value)"
      % (cur, money(result["pv_exit_value"]), pct(result["exit_share_of_dcf"])))
    p("  Value                          %s %s   (%s %s per room)"
      % (cur, money(result["dcf_value"]), cur, money(result["dcf_value"] / cfg["rooms"])))
    p("Implied going-in cap rate from DCF value: %s" % pct(result["implied_cap_rate_from_dcf"], 2))
    p("Unlevered IRR if bought at the direct cap value and sold at the exit value: %s"
      % pct(result["irr_at_direct_cap_price"], 2))
    p("")

    sens = cfg["sensitivity"]
    for method, title, base_cap in (
            ("dcf", "DCF VALUE: exit cap rate (rows) vs ADR change in every year (columns)",
             result["exit_cap_rate"]),
            ("direct", "DIRECT CAP VALUE: going-in cap rate (rows) vs ADR change (columns)",
             result["going_in_cap_rate"])):
        p("SENSITIVITY - %s, %s thousands" % (title, cur))
        p("-" * 78)
        p("%-10s" % "Cap rate" + "".join("%12s" % ("ADR %+.0f%%" % (a * 100)) for a in sens["adr_steps"]))
        table = sensitivity(cfg, method)
        for cs, row in zip(sens["cap_rate_steps"], table):
            p("%-10s" % pct(base_cap + cs, 2) + "".join("%12s" % money(v, unit=1000.0) for v in row))
        p("")
    if csv_path:
        p("Cash flow written to %s" % csv_path)
    p("Practice tool. Inputs are assumptions, outputs are arithmetic, not an opinion of value.")
    print("\n".join(out))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Hotel valuation practice model (not an appraisal).")
    parser.add_argument("input", nargs="?", help="input file, .json or .csv (optional)")
    parser.add_argument("--csv", default="cashflow.csv",
                        help="where to write the cash flow CSV (default: cashflow.csv)")
    parser.add_argument("--no-csv", action="store_true", help="do not write a CSV")
    parser.add_argument("--print-defaults", action="store_true",
                        help="print the default input as JSON and exit")
    args = parser.parse_args(argv)

    if args.print_defaults:
        print(json.dumps(DEFAULTS, indent=2))
        return 0
    try:
        cfg = load_input(args.input)
        validate(cfg)
        result = value(cfg)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Error: %s" % exc, file=sys.stderr)
        return 2
    csv_path = None if args.no_csv else args.csv
    if csv_path:
        write_csv(csv_path, result["years"], result)
    print_summary(cfg, result, csv_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
