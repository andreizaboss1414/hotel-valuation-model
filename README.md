# Hotel Valuation Model

A command line tool that takes a hotel's operating inputs and produces a five year
property cash flow, a valuation, and a sensitivity table.

I built this while preparing for asset management interviews, because the one thing I
could not find was a working hotel model I could read, run and argue with. There are
plenty of equity templates. There was nothing for hotels, which is odd, because hotels
are the asset class where the operating account *is* the valuation.

## Why a hotel is not an office

An office building is a lease with a tenant behind it. Value is largely an income
capitalisation of contractually stable rent. A hotel trades daily. Revenue depends on
occupancy, rate, seasonality and brand; cost depends on how well the thing is run. Two
identical buildings in the same street can be worth very different amounts because of
the operating business inside them. This tool models that operating layer explicitly:
departmental profit, undistributed costs, GOP, management fees, the FF&E reserve, and
only then NOI.

## What it does

Inputs (JSON): room count, occupancy, ADR, outlet revenue, departmental margins, fixed
charges, management fee terms, an exit cap rate, a discount rate, and a five year
forecast.

Outputs:

- A five year property level cash flow in the USALI structure
- Occupancy, ADR, RevPAR, TRevPAR, GOP, GOP margin, GOPPAR
- NOI, and NOI per room
- Value by direct capitalisation (NOI divided by cap rate)
- Value by discounted cash flow, with an exit value on the exit cap rate
- The implied going-in cap rate from the DCF value
- Sensitivity tables: value against exit cap rate and ADR movement

## Running it

No dependencies. Python 3.9 or newer, standard library only.

```bash
python3 hotel_valuation.py example.json
```

The example is a fictional 120 room upscale city hotel. It writes a CSV of the full
cash flow alongside the printed summary.

## Metrics used, in one line each

- **Occupancy** rooms sold divided by rooms available
- **ADR** room revenue divided by rooms sold
- **RevPAR** room revenue divided by rooms available, which is ADR times occupancy
- **TRevPAR** total revenue divided by rooms available, including food, beverage and other
- **GOP** gross operating profit, after departmental and undistributed operating costs
- **GOPPAR** GOP divided by rooms available, the like for like operating comparison
- **NOI** net operating income, after management fees, fixed charges and the FF&E reserve
- **Cap rate** stabilised NOI divided by value
- **FF&E reserve** the recurring furniture, fixture and equipment provision, taken here as
  a percentage of gross revenue
- **DSCR** debt service coverage, tested separately when debt is modelled

## Assumptions, stated plainly

- The forecast is straight line. You set the annual changes. There is no seasonality curve.
- The FF&E reserve is a percentage of gross revenue. Real practice varies by brand, age
  and condition, commonly 3 to 5 percent.
- Management fees are a base percentage of revenue plus an incentive percentage of GOP.
- The exit value is a cap rate on the final year NOI. It does not model a sale process,
  transaction costs or capital expenditure beyond the reserve.
- Tax, debt and the owner's cost of capital sit outside the model, on purpose. This is a
  property level tool, not an investment return model.

## What it is not

**Not an appraisal.** It is a practice and demonstration tool. It does not know your
market, your brand, your lease structure or your capex backlog, and it does not claim to.
Put real numbers in and it will do the arithmetic correctly and show you what moves value.
That is all it does.

## Licence

MIT.
