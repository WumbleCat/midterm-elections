"""Transformation tests (pure functions on small frames)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from electiondata.transform import candidates as cand_t
from electiondata.transform import demographics as demo_t
from electiondata.transform import economics as econ_t
from electiondata.transform import elections as elec_t
from electiondata.transform import polls as polls_t
from electiondata.transform import turnout as turnout_t


def _results() -> pd.DataFrame:
    rows = [
        # year, state, office, candidate, party, votes, total, special
        (2016, "PA", "president", "CLINTON", "DEM", 2926441, 6165478, False),
        (2016, "PA", "president", "TRUMP", "REP", 2970733, 6165478, False),
        (2016, "PA", "president", "JOHNSON", "LIB", 146715, 6165478, False),
        (2016, "PA", "president", "BLANK VOTES", "OTHER", 50000, 6165478, False),
        (2016, "OH", "president", "CLINTON", "DEM", 2394164, 5496487, False),
        (2016, "OH", "president", "TRUMP", "REP", 2841005, 5496487, False),
        (2020, "PA", "president", "BIDEN", "DEM", 3458229, 6915283, False),
        (2020, "PA", "president", "TRUMP", "REP", 3377674, 6915283, False),
        (2020, "OH", "president", "BIDEN", "DEM", 2679165, 5922202, False),
        (2020, "OH", "president", "TRUMP", "REP", 3154834, 5922202, False),
        (2018, "PA", "senate", "CASEY", "DEM", 2792437, 5011555, False),
        (2018, "PA", "senate", "BARLETTA", "REP", 2134848, 5011555, False),
        (2022, "PA", "senate", "FETTERMAN", "DEM", 2751012, 5375621, False),
        (2022, "PA", "senate", "OZ", "REP", 2487260, 5375621, False),
        (2024, "PA", "senate", "CASEY", "DEM", 3384180, 6963137, False),
        (2024, "PA", "senate", "MCCORMICK", "REP", 3399295, 6963137, False),
        (2020, "GA", "senate", "OSSOFF", "DEM", 1000, 2100, False),
        (2020, "GA", "senate", "PERDUE", "REP", 1100, 2100, False),
        (2020, "GA", "senate", "WARNOCK", "DEM", 900, 2000, True),
        (2020, "GA", "senate", "LOEFFLER", "REP", 800, 2000, True),
        (2020, "GA", "senate", "COLLINS", "REP", 300, 2000, True),
    ]
    df = pd.DataFrame(
        rows,
        columns=[
            "year",
            "state",
            "office",
            "candidate",
            "party",
            "votes",
            "total_votes",
            "special",
        ],
    )
    df["state_fips"] = df["state"].map({"PA": "42", "OH": "39", "GA": "13"})
    df["district"] = "statewide"
    df["election_type"] = "general"
    df["election_date"] = pd.to_datetime(df["year"].astype(str) + "-11-03")
    df["publication_date"] = df["election_date"]
    df["publication_date_estimated"] = True
    df["retrieval_date"] = pd.Timestamp("2026-09-20")
    df["revision_vintage"] = "v"
    df["source"] = "MEDSL"
    df["source_url"] = "u"
    df["dataset_id"] = "medsl"
    df["ingestion_run_id"] = "r"
    return df


def test_race_summary_and_derived_metrics():
    s = elec_t.race_summary(_results())
    pa16 = s[(s.state == "PA") & (s.year == 2016) & (s.office == "president")].iloc[0]
    assert pa16["dem_votes"] == 2926441 and pa16["rep_votes"] == 2970733
    assert pa16["other_votes"] == 146715  # blank votes excluded
    assert pa16["total_candidate_votes"] == 2926441 + 2970733 + 146715
    assert pa16["dem_two_party_share"] == pytest.approx(2926441 / (2926441 + 2970733))
    assert pa16["dem_rep_margin"] == pytest.approx(
        pa16["dem_two_party_share"] - pa16["rep_two_party_share"]
    )
    assert pa16["winner_party"] == "REP" and pa16["dem_candidate"] == "CLINTON"
    assert pa16["winning_margin"] == pytest.approx(
        (2970733 - 2926441) / pa16["total_candidate_votes"]
    )
    ga = s[(s.state == "GA") & (s.year == 2020) & (s.office == "senate")]
    assert len(ga) == 2  # regular and special kept separate
    special = ga[ga.special].iloc[0]
    assert special["rep_votes"] == 1100  # jungle: both Republicans summed
    assert special["winner_party"] == "DEM"  # top candidate wins
    assert not pa16["uncontested"]


def test_partisan_lean_and_national_share():
    s = elec_t.race_summary(_results())
    nat = elec_t.national_two_party_share(s)
    dem16 = 2926441 + 2394164
    rep16 = 2970733 + 2841005
    assert nat.set_index("year").loc[2016, "national_dem_two_party_share"] == pytest.approx(
        dem16 / (dem16 + rep16)
    )
    lean = elec_t.presidential_lean(s)
    pa16 = lean[(lean.state == "PA") & (lean.year == 2016)].iloc[0]
    assert pa16["state_partisan_lean"] == pytest.approx(
        2926441 / (2926441 + 2970733) - dem16 / (dem16 + rep16)
    )
    pa20 = lean[(lean.state == "PA") & (lean.year == 2020)].iloc[0]
    # weighted lean: 0.6 * latest + 0.3 * previous (re-weighted since only two terms exist)
    expected = (0.6 * pa20["state_partisan_lean"] + 0.3 * pa16["state_partisan_lean"]) / 0.9
    assert pa20["weighted_state_lean"] == pytest.approx(expected)


def test_political_history_uses_previous_elections_only():
    s = elec_t.race_summary(_results())
    hist = elec_t.political_history(s, "senate")
    pa24 = hist[(hist.state == "PA") & (hist.year == 2024)].iloc[0]
    assert pa24["prev_election_year"] == 2018  # same seat, six years earlier
    assert pa24["prev_dem_share"] == pytest.approx(2792437 / (2792437 + 2134848))
    assert pa24["lean_year"] == 2020  # most recent presidential election before 2024
    assert pa24["average_dem_share_last_2"] == pytest.approx(
        np.mean([2792437 / (2792437 + 2134848), 2751012 / (2751012 + 2487260)])
    )
    pa18 = hist[(hist.state == "PA") & (hist.year == 2018)].iloc[0]
    assert pd.isna(pa18["prev_election_year"]) and pa18["lean_year"] == 2016


def test_turnout_metrics_and_previous():
    t = pd.DataFrame(
        {
            "state": ["PA", "PA", "PA"],
            "year": [2018, 2020, 2022],
            "registered_voters": [8.0, 9.0, 8.8],
            "ballots_cast": [5.0, 7.0, 5.4],
            "mail_votes": [0.2, 2.6, 1.2],
            "early_votes": [0.0, 0.0, 0.0],
        }
    )
    pop = pd.DataFrame(
        {
            "state": ["PA"] * 3,
            "year": [2018, 2020, 2022],
            "population": [12.8, 13.0, 13.0],
            "revision_vintage": ["2019", "2024", "2024"],
        }
    )
    m = turnout_t.turnout_metrics(t, pop)
    r20 = m[m.year == 2020].iloc[0]
    assert r20["turnout_registered"] == pytest.approx(7 / 9) and r20[
        "turnout_population"
    ] == pytest.approx(7 / 13)
    assert r20["mail_vote_share"] == pytest.approx(2.6 / 7)
    prev = turnout_t.previous_turnout(m, "senate")
    assert prev[prev.year == 2022].iloc[0]["previous_turnout_registered"] == pytest.approx(
        5 / 8
    )  # previous midterm, not 2020
    assert pd.isna(prev[prev.year == 2020].iloc[0]["previous_turnout_registered"])


def _labor() -> pd.DataFrame:
    dates = pd.date_range("2023-01-01", "2024-09-01", freq="MS")
    rows = []
    for i, d in enumerate(dates):
        rows.append(
            {
                "state": "PA",
                "date": d,
                "seasonally_adjusted": True,
                "unemployment_rate": 3.0 + 0.1 * i,
                "employment": 6_000_000 + 1000 * i,
                "labor_force": 6_200_000 + 500 * i,
                "publication_date": d + pd.offsets.MonthEnd(0) + pd.Timedelta(days=21),
            }
        )
    return pd.DataFrame(rows)


def test_unemployment_features_respect_as_of():
    lab = _labor()
    f = econ_t.unemployment_features(lab, "2024-10-15").iloc[0]
    assert f["labor_month"] == pd.Timestamp("2024-08-01")  # September not yet published on Oct 15
    assert f["unemployment_rate"] == pytest.approx(3.0 + 0.1 * 19)
    assert f["unemployment_change_12m"] == pytest.approx(1.2)
    assert f["unemployment_change_3m"] == pytest.approx(0.3)
    assert f["employment_growth_12m"] == pytest.approx((6_000_000 + 19000) / (6_000_000 + 7000) - 1)
    assert f["unemployment_rate_3m_avg"] == pytest.approx(
        np.mean([3.0 + 0.1 * i for i in (17, 18, 19)])
    )


def test_national_features():
    dates = pd.date_range("2022-01-01", "2024-09-01", freq="MS")
    rows = []
    for i, d in enumerate(dates):
        pub = d + pd.offsets.MonthEnd(0) + pd.Timedelta(days=10)
        rows += [
            {
                "date": d,
                "measure": "cpi_all_items",
                "seasonally_adjusted": False,
                "value": 100 * (1.003**i),
                "publication_date": pub,
            },
            {
                "date": d,
                "measure": "cpi_all_items",
                "seasonally_adjusted": True,
                "value": 100 * (1.003**i),
                "publication_date": pub,
            },
            {
                "date": d,
                "measure": "nonfarm_payrolls",
                "seasonally_adjusted": True,
                "value": 150000 + 100 * i,
                "publication_date": pub,
            },
            {
                "date": d,
                "measure": "unemployment_rate",
                "seasonally_adjusted": True,
                "value": 4.0,
                "publication_date": pub,
            },
        ]
    nat = econ_t.national_features(pd.DataFrame(rows), "2024-10-15")
    assert nat["national_data_month"] == "2024-09-01"
    assert nat["cpi_yoy"] == pytest.approx(1.003**12 - 1)
    assert nat["cpi_3m_annualized"] == pytest.approx(1.003**12 - 1, rel=1e-6)
    assert nat["payroll_growth_12m"] == pytest.approx((150000 + 100 * 32) / (150000 + 100 * 20) - 1)


def test_industry_shares():
    ind = pd.DataFrame(
        [
            ("PA", 2023, "10", "0", 100.0),
            ("PA", 2023, "10", "1", 5.0),
            ("PA", 2023, "10", "3", 5.0),
            ("PA", 2023, "1013", "5", 10.0),
            ("PA", 2023, "62", "5", 20.0),
        ],
        columns=["state", "year", "industry_code", "own_code", "annual_avg_employment"],
    )
    ind["annual_avg_weekly_wage"] = 1000.0
    ind["avg_annual_pay"] = 52000.0
    ind["publication_date"] = pd.Timestamp("2024-06-30")
    out = econ_t.industry_shares(ind, "2024-10-15").iloc[0]
    assert (
        out["pct_manufacturing"] == pytest.approx(0.10)
        and out["pct_healthcare"] == pytest.approx(0.20)
        and out["pct_government"] == pytest.approx(0.10)
    )
    assert econ_t.industry_shares(ind, "2024-01-01").empty


def test_state_economy_growth():
    rows = []
    for y, v in [(2021, 100.0), (2022, 104.0), (2023, 106.08)]:
        rows.append(
            {
                "state": "PA",
                "year": y,
                "measure": "real_gdp",
                "value": v,
                "publication_date": pd.Timestamp(y + 1, 9, 30),
            }
        )
    out = econ_t.state_economy_features(pd.DataFrame(rows), "2024-10-15").iloc[0]
    assert out["state_economy_year"] == 2023 and out["real_gdp_growth"] == pytest.approx(0.02)


def test_population_and_density_features():
    pop = pd.DataFrame(
        [
            ("PA", 2019, 12.8, "2019", "2019-12-31"),
            ("PA", 2020, 13.0, "2023", "2023-12-31"),
            ("PA", 2021, 13.0, "2023", "2023-12-31"),
            ("PA", 2022, 12.97, "2023", "2023-12-31"),
            ("PA", 2023, 12.96, "2023", "2023-12-31"),
            ("PA", 2023, 12.99, "2024", "2024-12-31"),
            ("PA", 2024, 13.1, "2024", "2024-12-31"),
        ],
        columns=["state", "year", "population", "revision_vintage", "publication_date"],
    )
    for c in (
        "domestic_migration",
        "international_migration",
        "net_migration",
        "domestic_migration_rate",
        "net_migration_rate",
    ):
        pop[c] = 1.0
    out = demo_t.population_as_of(pop, "2024-10-15").iloc[0]
    assert (
        out["population_year"] == 2023
        and out["population"] == 12.96
        and out["population_vintage"] == "2023"
    )
    assert out["population_growth_4y"] == pytest.approx(12.96 / 12.8 - 1)
    geo = pd.DataFrame(
        {
            "state": ["PA"],
            "year": [2020],
            "land_area_sq_miles": [44742.0],
            "observation_date": ["2020-01-01"],
            "publication_date": ["2020-12-31"],
        }
    )
    dens = demo_t.density_features(
        demo_t.population_as_of(pop, "2024-10-15"), geo, "2024-10-15"
    ).iloc[0]
    assert dens["population_density"] == pytest.approx(12.96 / 44742.0)
    assert dens["log_population_density"] == pytest.approx(np.log1p(12.96 / 44742.0))


def test_incumbency_and_finance_snapshot_rule():
    cands = pd.DataFrame(
        [
            (
                "S1",
                2024,
                2024,
                "DEM",
                "senate",
                "PA",
                "statewide",
                "I",
                "C",
                "2024-06-30",
                "2026-09-20",
            ),
            (
                "S2",
                2024,
                2024,
                "REP",
                "senate",
                "PA",
                "statewide",
                "C",
                "C",
                "2024-06-30",
                "2026-09-20",
            ),
            (
                "S3",
                2024,
                2024,
                "REP",
                "senate",
                "OH",
                "statewide",
                "O",
                "C",
                "2024-06-30",
                "2026-09-20",
            ),
            (
                "S4",
                2024,
                2024,
                "DEM",
                "senate",
                "OH",
                "statewide",
                "O",
                "C",
                "2024-06-30",
                "2026-09-20",
            ),
            (
                "S5",
                2024,
                2030,
                "DEM",
                "senate",
                "OH",
                "statewide",
                "I",
                "N",
                "2024-06-30",
                "2026-09-20",
            ),
        ],
        columns=[
            "candidate_id",
            "cycle",
            "election_year",
            "party",
            "office",
            "state",
            "district",
            "incumbent_challenger_status",
            "candidate_status",
            "publication_date",
            "retrieval_date",
        ],
    )
    inc = cand_t.incumbency_features(cands, 2024, "senate", "2024-10-15").set_index("state")
    assert inc.loc["PA", "dem_incumbent"] and not inc.loc["PA", "open_seat"]
    assert inc.loc["OH", "open_seat"] and pd.isna(inc.loc["OH", "incumbent_party"])
    fin = pd.DataFrame(
        [
            (
                "S1",
                2024,
                "DEM",
                "senate",
                "PA",
                "statewide",
                "2024-09-30",
                50.0,
                40.0,
                10.0,
                45.0,
                "2024-10-10",
                "2024-10-12",
                "2024-10-12",
            ),
            (
                "S2",
                2024,
                "REP",
                "senate",
                "PA",
                "statewide",
                "2024-09-30",
                30.0,
                20.0,
                10.0,
                25.0,
                "2024-10-10",
                "2024-10-12",
                "2024-10-12",
            ),
        ],
        columns=[
            "candidate_id",
            "cycle",
            "party",
            "office",
            "state",
            "district",
            "coverage_end_date",
            "total_receipts",
            "total_disbursements",
            "cash_on_hand_end",
            "individual_contributions",
            "publication_date",
            "retrieval_date",
            "revision_vintage",
        ],
    )
    f = cand_t.finance_features(fin, 2024, "senate", "2024-10-15").iloc[0]
    assert f["dem_receipts"] == 50 and f["dem_fundraising_share"] == pytest.approx(50 / 80)
    assert f["log_dem_receipts"] == pytest.approx(np.log1p(50))
    # snapshot retrieved after as_of must not be used at all
    assert cand_t.finance_features(fin, 2024, "senate", "2024-10-11").empty


def test_poll_aggregates_respect_publication_date():
    polls = pd.DataFrame(
        {
            "poll_id": ["a", "b", "c"],
            "state": ["PA", "PA", "PA"],
            "district": ["statewide"] * 3,
            "office": ["senate"] * 3,
            "year": [2024] * 3,
            "end_date": ["2024-10-01", "2024-10-08", "2024-10-14"],
            "publication_date": ["2024-10-02", "2024-10-09", "2024-10-20"],
            "sample_size": [800, 1000, 900],
            "poll_margin": [0.02, 0.04, -0.10],
            "dem_pct": [0.47, 0.48, 0.44],
            "rep_pct": [0.45, 0.44, 0.54],
        }
    )
    out = polls_t.race_poll_features(polls, 2024, "senate", "2024-10-15", "2024-11-05").iloc[0]
    assert out["number_recent_polls"] == 2  # poll c released after as_of is excluded
    assert out["state_poll_margin"] == pytest.approx(np.average([0.02, 0.04], weights=[800, 1000]))
    assert out["days_to_election"] == 21 and out["poll_recency_days"] == 7
    approval = pd.DataFrame(
        {
            "poll_id": ["x"],
            "end_date": ["2024-10-10"],
            "publication_date": ["2024-10-11"],
            "sample_size": [1000],
            "approve": [0.42],
            "net_approval": [-0.12],
        }
    )
    a = polls_t.approval_features(approval, "2024-10-15")
    assert a["approval_average_30d"] == pytest.approx(0.42) and a["n_approval_polls_30d"] == 1
    assert polls_t.approval_features(approval, "2024-10-10")["approval_average_30d"] is None
    assert (
        polls_t.special_election_swing(pd.DataFrame(), "2024-10-15")["special_election_swing_90d"]
        is None
    )
