"""IMF bilateral real exchange rate dashboard (Python 3.12)."""
from __future__ import annotations

import io
import os
from datetime import date

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pycountry
import requests
import streamlit as st

BASE = 'https://api.imf.org/external/sdmx/3.0'
START = pd.Timestamp('1976-01-01')
COUNTRIES = {c.alpha_3: c.name for c in pycountry.countries}
COUNTRIES.update({'G163': 'Euro Area', 'USA': 'United States', 'GBR': 'United Kingdom', 'KOR': 'South Korea', 'RUS': 'Russia', 'TUR': 'Türkiye', 'CZE': 'Czechia', 'VNM': 'Vietnam'})
LABELS = {code: f'{name} ({code})' for code, name in COUNTRIES.items()}
CODES = sorted(COUNTRIES, key=lambda c: (c != 'G163', COUNTRIES[c].lower()))

st.set_page_config(page_title='IMF Real Exchange Rate Explorer', page_icon='🌍', layout='wide')
st.title('🌍 IMF Real Exchange Rate Explorer')
st.caption('Monthly IMF CPI and exchange rates · January 1976 onward, where available')


def period_to_date(value: object) -> pd.Timestamp:
    raw = str(value).strip()
    # IMF commonly reports 2024-M01; other CSV representations use 2024-01.
    return pd.to_datetime(raw.replace('-M', '-'), errors='coerce')


@st.cache_data(ttl=86400, show_spinner=False)
def fetch_series(country: str, dataset: str) -> pd.Series:
    """Download one IMF SDMX 3.0 CSV series; preserve actual observation months."""
    if dataset == 'CPI':
        agency, flow, key = 'IMF.STA', 'CPI', f'{country}.CPI._T.IX.M'
    else:
        agency, flow, key = 'IMF.STA', 'ER', f'{country}.XDC_USD.PA_RT.M'
    url = f'{BASE}/data/dataflow/{agency}/{flow}/~/{key}'
    headers = {'Accept': 'text/csv', 'User-Agent': 'IMF-RER-Explorer/1.0'}
    token = os.getenv('IMF_API_KEY', '').strip()
    if token:
        headers['Ocp-Apim-Subscription-Key'] = token
    try:
        response = requests.get(url, params={'c[TIME_PERIOD]': 'ge:1976-M01'}, headers=headers, timeout=45)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f'IMF {dataset} request failed for {country}: {exc}') from exc
    if not response.content or not response.text.strip():
        return pd.Series(dtype='float64', name=f'{dataset}_{country}')
    try:
        df = pd.read_csv(io.StringIO(response.text), low_memory=False)
    except Exception as exc:
        raise RuntimeError(f'IMF returned unreadable {dataset} data for {country}: {exc}') from exc
    df.columns = df.columns.str.strip().str.upper()
    if not {'TIME_PERIOD', 'OBS_VALUE'}.issubset(df.columns):
        raise RuntimeError(f'Unexpected IMF {dataset} response for {country}. Columns: {list(df.columns)}. Verify IMF dataflow and key.')
    if 'COUNTRY' in df.columns:
        df = df[df['COUNTRY'].astype(str).str.upper() == country]
    if 'FREQUENCY' in df.columns:
        df = df[df['FREQUENCY'].astype(str).str.upper() == 'M']
    df['month'] = df['TIME_PERIOD'].map(period_to_date)
    df['value'] = pd.to_numeric(df['OBS_VALUE'], errors='coerce')
    df = df.dropna(subset=['month', 'value'])
    df = df[(df['month'] >= START) & (df['value'] > 0)]
    if df['month'].duplicated().any():
        raise RuntimeError(f'Multiple {dataset} observations found for {country} in one month; verify the IMF series dimensions.')
    return pd.Series(df['value'].to_numpy(), index=pd.DatetimeIndex(df['month']), name=f'{dataset}_{country}').sort_index()


def calculate(country1: str, country2: str, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, float, int]:
    series = [fetch_series(country1, 'CPI'), fetch_series(country2, 'CPI'), fetch_series(country1, 'FX'), fetch_series(country2, 'FX')]
    months = pd.date_range(start, end, freq='MS')
    data = pd.DataFrame(index=months)
    for name, s in zip(['P1_CPI', 'P2_CPI', 'E1_per_USD', 'E2_per_USD'], series):
        data[name] = s.reindex(months)
    data['S_C2_per_C1'] = data['E2_per_USD'] / data['E1_per_USD']
    data['RER'] = data['S_C2_per_C1'] * data['P1_CPI'] / data['P2_CPI']
    valid = data['RER'].notna() & (data['RER'] > 0)
    count = int(valid.sum())
    mean = float(data.loc[valid, 'RER'].mean()) if count else float('nan')
    data['Real_Index'] = 100 * data['RER'] / mean if count else float('nan')
    data.index.name = 'Month'
    return data, mean, count


def line_chart(data: pd.DataFrame, column: str, title: str, ytitle: str, refline: bool = False) -> go.Figure:
    fig = go.Figure()
    # Skip invalid observations rather than using observations from mismatched months.
    valid = data[[column]].dropna()
    fig.add_trace(go.Scatter(x=valid.index, y=valid[column], mode='lines', name=ytitle, line=dict(width=2.5), hovertemplate='%{x|%b %Y}<br>%{y:,.4f}<extra></extra>'))
    if refline:
        fig.add_hline(y=100, line_dash='dash', line_color='gray', annotation_text='Sample mean = 100')
    fig.update_layout(title=title, xaxis_title='Month', yaxis_title=ytitle, hovermode='x unified', height=430, margin=dict(l=35, r=25, t=65, b=45))
    fig.update_xaxes(rangeslider_visible=True)
    return fig


def combined_chart(data: pd.DataFrame, country1: str, country2: str) -> go.Figure:
    fig = make_subplots(specs=[[{'secondary_y': True}]])
    real = data[['Real_Index']].dropna()
    nominal = data[['S_C2_per_C1']].dropna()
    fig.add_trace(go.Scatter(x=real.index, y=real['Real_Index'], name='Real index', mode='lines', line=dict(color='#2563eb', width=2.5)), secondary_y=False)
    fig.add_trace(go.Scatter(x=nominal.index, y=nominal['S_C2_per_C1'], name='Nominal S(t)', mode='lines', line=dict(color='#ea580c', width=2.5)), secondary_y=True)
    fig.add_hline(y=100, line_dash='dash', line_color='gray', opacity=0.5, secondary_y=False)
    fig.update_yaxes(title_text='Real exchange rate index (sample mean = 100)', secondary_y=False)
    fig.update_yaxes(title_text=f'Nominal: {country2} units per {country1} unit', secondary_y=True)
    fig.update_layout(title='Real and nominal exchange rates · dual axis', hovermode='x unified', height=480, legend=dict(orientation='h', y=1.13), margin=dict(l=35, r=35, t=80, b=40))
    fig.update_xaxes(title_text='Month', rangeslider_visible=True)
    return fig


with st.sidebar:
    st.header('Select countries')
    c1 = st.selectbox('Country 1 (base currency)', CODES, index=CODES.index('USA'), format_func=lambda c: LABELS[c])
    c2 = st.selectbox('Country 2 (quote currency)', CODES, index=CODES.index('G163'), format_func=lambda c: LABELS[c])
    st.header('Sample period')
    current_month = pd.Timestamp.today().to_period('M').to_timestamp()
    start_month = st.date_input('Start month', value=START.date(), min_value=START.date(), max_value=current_month.date(), format='YYYY-MM-DD')
    end_month = st.date_input('End month', value=current_month.date(), min_value=START.date(), max_value=current_month.date(), format='YYYY-MM-DD')
    st.header('Chart selection')
    selection = st.radio('Display', ['Real', 'Nominal', 'Both'], index=2)
    st.caption('Dates are interpreted by month; the day of month is ignored.')
    if st.button('Refresh IMF cache'):
        fetch_series.clear()
        st.rerun()

start = pd.Timestamp(start_month).to_period('M').to_timestamp()
end = pd.Timestamp(end_month).to_period('M').to_timestamp()
if c1 == c2:
    st.warning('Select two different countries.')
    st.stop()
if start > end:
    st.error('Start month must not be later than end month.')
    st.stop()

st.markdown(f'**Country 1:** {COUNTRIES[c1]} ({c1}) &nbsp; | &nbsp; **Country 2:** {COUNTRIES[c2]} ({c2})')
st.latex(r'S(t)=\frac{E_2(t)}{E_1(t)}\qquad RER(t)=S(t)\frac{P_1(t)}{P_2(t)}\qquad RealIndex(t)=100\frac{RER(t)}{RER^*}')
with st.spinner('Retrieving monthly IMF data…'):
    try:
        data, rer_mean, n = calculate(c1, c2, start, end)
    except RuntimeError as exc:
        st.error(str(exc))
        st.info('Check the IMF API, dataflow availability, series codes, and whether an IMF API subscription key is required. Set IMF_API_KEY in the environment if applicable.')
        st.stop()

m1, m2, m3 = st.columns(3)
m1.metric('Valid RER months', f'{n:,} / {len(data):,}')
m2.metric('Sample mean RER*', f'{rer_mean:,.6g}' if n else 'Unavailable')
m3.metric('Sample period', f'{start:%b %Y} – {end:%b %Y}')
if n == 0:
    st.warning('No valid overlapping CPI and FX observations for this country pair and sample. Try another pair or period.')
else:
    st.caption('Valid RER months require CPI and local-currency-per-USD FX observations for both countries in the SAME month. Missing months are skipped, never filled.')
    if selection in ('Real', 'Both'):
        st.plotly_chart(line_chart(data, 'Real_Index', 'Real exchange rate index', 'Real index (sample mean = 100)', True), use_container_width=True)
    if selection in ('Nominal', 'Both'):
        st.plotly_chart(line_chart(data, 'S_C2_per_C1', 'Nominal exchange rate', f'{c2} currency units per {c1} currency unit'), use_container_width=True)
    if selection == 'Both':
        st.plotly_chart(combined_chart(data, c1, c2), use_container_width=True)

st.subheader('Download sample data')
output = data.reset_index().copy()
output['Month'] = output['Month'].dt.strftime('%Y-%m')
output['RER_sample_mean'] = rer_mean if n else float('nan')
st.download_button('⬇️ Download CSV (all sample months)', output.to_csv(index=False).encode('utf-8'), file_name=f'IMF_RER_{c1}_{c2}_{start:%Y%m}_{end:%Y%m}.csv', mime='text/csv')
with st.expander('View monthly observations and calculations'):
    st.dataframe(output, use_container_width=True, hide_index=True)
with st.expander('Methodology and limitations'):
    st.markdown('''**Nominal rate:** E2/E1, where each E is local currency units per USD. **Real rate:** S × P1/P2. **Sample mean:** arithmetic mean of valid monthly RER observations in the selected period. **Real index:** 100 × RER / sample mean. CPI reference bases can differ, but constant base differences cancel in the normalized real index. Missing observations are not interpolated. The nominal series can have observations in months where CPI is missing. CPI and FX coverage varies by country and may begin after 1976. Euro Area uses IMF code G163. Source: IMF SDMX 3.0 API; series keys COUNTRY.CPI._T.IX.M and COUNTRY.XDC_USD.PA_RT.M.''')
