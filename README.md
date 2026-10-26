# IMF Real Exchange Rate Explorer

A Streamlit dashboard for comparing the monthly bilateral real and nominal exchange rates of two IMF reporting countries or the Euro Area (IMF code `G163`). Python **3.12**.

## Quick start

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

The browser opens the Streamlit dashboard. Choose two countries, sample dates, and Real/Nominal/Both. When **Both** is selected, three charts appear: Real, Nominal, and Combined (dual-axis). Otherwise, one chart appears. Export the full sample-month table as CSV.

## IMF data source

API base: `https://api.imf.org/external/sdmx/3.0`.

The app requests SDMX 3.0 CSV data using the following IMF series keys:

- CPI: `{ISO3}.CPI._T.IX.M` (IMF.STA / CPI dataflow)
- FX: `{ISO3}.XDC_USD.PA_RT.M` (IMF.STA / ER dataflow)

Requests use `/data/dataflow/{agency}/{flow}/~/{key}` with a start-time constraint. **Important:** IMF dataflows, access requirements, and codes can change. The API could not be live-tested in the authoring environment. If the IMF returns no observations or an HTTP error, verify the relevant flow's current agency, dimensions and version using the IMF data portal. The app surfaces these errors rather than silently substituting other data. If your IMF access requires a subscription key, set `IMF_API_KEY` in the environment before launching Streamlit; it is passed as the `Ocp-Apim-Subscription-Key` request header. The IMF may require you to obtain credentials independently.

The country dropdown uses ISO 3166-1 alpha-3 names plus Euro Area `G163`. Inclusion in the dropdown **does not guarantee** that a country has both required IMF series.

## Calculation

Let `E1` and `E2` be the respective local-currency units per US dollar; `P1` and `P2` are the respective CPI indices. For a given month:

```
S(t) = E2(t) / E1(t)                  # Country 2 currency per Country 1 currency
RER(t) = S(t) * P1(t) / P2(t)
RER* = arithmetic mean of RER(t) over valid months in the selected period
Real_Index(t) = 100 * RER(t) / RER*
```

RER* changes whenever the sample dates change. Nominal `S(t)` is **never normalized**. A valid RER month requires all four input observations **from that same calendar month**. Missing observations are skipped, not forward-filled or paired with another month. The real chart joins successive valid points across skipped months. The nominal chart uses all months with both FX observations even if a CPI is missing. CSV includes **every calendar month** in the selected period, with missing values blank, raw inputs, nominal S, RER, Real Index, and sample mean.

The Real Index has an arithmetic sample mean of 100. CPI base-year differences that are constant within a series cancel when constructing this sample-normalized index.

## Deploy online

Push `app.py`, `requirements.txt`, and `README.md` to a Git repository and deploy `app.py` on Streamlit Community Cloud using Python 3.12. If a subscription key is required, configure it as a secret/environment variable and do not commit it to the repository.

## Known limitations

- IMF monthly coverage can be incomplete or start well after January 1976.
- The IMF may change dataset ownership, keys, schema, or API authentication; verify live API responses before relying on results.
- Country dropdown is based on ISO country codes and does not certify IMF reporting availability.
- No interpolation, seasonal adjustment, or alternate CPI harmonization is performed.
- Dates are monthly even though Streamlit's date input displays a day.
