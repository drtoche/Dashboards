import dash
from dash import Dash, html, dcc, Input, Output, callback_context
import plotly.express as px
import pandas as pd
import requests
import wbgapi as wb


# Initialize the App
app = Dash(__name__)


# All countries use the same WDI indicator (db=2); IMF WEO is used as a
# supplemental source for OECD countries via direct REST API call
WDI_INDICATOR = 'GC.DOD.TOTL.GD.ZS'

# IMF WEO indicator for general government gross debt (% of GDP)
IMF_INDICATOR = 'GGXWDG_NGDP'

# Countries that benefit from IMF WEO supplemental data (better OECD coverage)
IMF_COUNTRIES = {'JPN', 'DEU', 'FRA', 'ITA', 'CAN', 'ESP', 'KOR', 'AUS', 'MEX', 'BRA'}
 
# Map country name to country ISO code
COUNTRY_CODES = {
    'USA': 'USA',
    'IND': 'IND',
    'GBR': 'GBR',
    'JPN': 'JPN',
    'DEU': 'DEU',
    'FRA': 'FRA',
    'ITA': 'ITA',
    'CHN': 'CHN',
    'RUS': 'RUS',
    'CAN': 'CAN',
    'BRA': 'BRA',
    'ESP': 'ESP',
    'MEX': 'MEX',
    'KOR': 'KOR',
    'AUS': 'AUS'
}
 
# IMF WEO uses its own 3-letter codes which differ from ISO in some cases
IMF_COUNTRY_CODES = {
    'JPN': 'JPN',
    'DEU': 'DEU',
    'FRA': 'FRA',
    'ITA': 'ITA',
    'CAN': 'CAN',
    'BRA': 'BRA',
    'ESP': 'ESP',
    'MEX': 'MEX',
    'KOR': 'KOR',
    'AUS': 'AUS'
}


# Function to fetch World Bank WDI data
def get_wdi_data(country_code, indicator):
    try:
        df = wb.data.DataFrame(indicator, country_code, db=2, labels=True)

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()

        # Identify year columns
        year_cols = [c for c in df.columns if any(char.isdigit() for char in str(c))]
        id_cols = [c for c in df.columns if c not in year_cols]

        df = df.melt(id_vars=id_cols, var_name='date', value_name='value')

        # Cleanup
        df['date'] = df['date'].astype(str).str.extract(r'(\d{4})')[0]
        df = df.dropna(subset=['value', 'date'])

        df['date'] = df['date'].astype(int)
        df['value'] = pd.to_numeric(df['value'], errors='coerce')

        return df.groupby('date')['value'].mean().reset_index().sort_values('date')

    except Exception as e:
        print(f"WDI Fetch Error: {e}")
        return pd.DataFrame()


# Function to fetch IMF WEO data via direct REST API
def get_imf_data(country_code):
    try:
        imf_code = IMF_COUNTRY_CODES.get(country_code)
        if not imf_code:
            return pd.DataFrame()

        url = (
            f"https://www.imf.org/external/datamapper/api/v1/{IMF_INDICATOR}"
            f"/{imf_code}"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        values = data.get('values', {}).get(IMF_INDICATOR, {}).get(imf_code, {})

        if not values:
            return pd.DataFrame()

        df = pd.DataFrame(list(values.items()), columns=['date', 'value'])
        df['date'] = pd.to_numeric(df['date'], errors='coerce')
        df['value'] = pd.to_numeric(df['value'], errors='coerce')
        df = df.dropna()

        return df.sort_values('date').reset_index(drop=True)

    except Exception as e:
        print(f"IMF Fetch Error: {e}")
        return pd.DataFrame()


# Merge WDI and IMF data, preferring IMF where available (better OECD coverage)
def get_debt_data(country_code, manual_indicator=None):
    indicator = manual_indicator or WDI_INDICATOR

    wdi_df = get_wdi_data(country_code, indicator)

    # Only supplement with IMF data when using the default indicator
    if manual_indicator is None and country_code in IMF_COUNTRIES:
        imf_df = get_imf_data(country_code)
        if not imf_df.empty:
            if not wdi_df.empty:
                # Merge: use IMF values where available, fill gaps with WDI
                merged = pd.merge(imf_df, wdi_df, on='date', how='outer',
                                  suffixes=('_imf', '_wdi'))
                merged['value'] = merged['value_imf'].combine_first(merged['value_wdi'])
                return merged[['date', 'value']].dropna().sort_values('date')
            return imf_df

    return wdi_df


# App Layout (UI)
app.layout = html.Div([
    html.H1("Public Debt (% of GDP)", style={'textAlign': 'center'}),
    
    html.Div([
        html.Label("Select Country:", style={'fontWeight': 'bold'}),
        dcc.Dropdown(
            id='country-dropdown',
            options=[{'label': k, 'value': v} for v, k in [
                ('USA', 'United States'), ('JPN', 'Japan'), ('DEU', 'Germany'),
                ('FRA', 'France'), ('ITA', 'Italy'), ('GBR', 'United Kingdom'),
                ('IND', 'India'), ('CHN', 'China'), ('RUS', 'Russia'),
                ('CAN', 'Canada'), ('BRA', 'Brazil'), ('ESP', 'Spain'),
                ('MEX', 'Mexico'), ('KOR', 'South Korea'), ('AUS', 'Australia')
            ]],
            value='USA',
            clearable=False
        ),
        
        # Hidden/Advanced Section
        html.Details([
            html.Summary("Advanced: Manual Indicator Override"),
            html.Div([
                html.Label("Enter World Bank Indicator Code:"),
                dcc.Input(
                    id='manual-indicator',
                    type='text',
                    value=WDI_INDICATOR,
                    style={'width': '100%'}
                ),
            ], style={'padding': '10px', 'backgroundColor': '#f9f9f9'})
        ], style={'marginTop': '20px'})
        
    ], style={'width': '40%', 'margin': 'auto'}),

    dcc.Graph(id='debt-line-chart')
])


# Interactive Callbacks
@app.callback(
    [Output('debt-line-chart', 'figure'),
     Output('manual-indicator', 'value')],
    [Input('country-dropdown', 'value'),
     Input('manual-indicator', 'value')]
)
def update_graph(selected_country, manual_code):
    ctx = callback_context
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Logic: Only update the text box if the country was changed
    if trigger_id == 'country-dropdown' or not trigger_id:
        display_indicator = WDI_INDICATOR
        manual_override = None
    else:
        display_indicator = manual_code
        manual_override = manual_code

    # Map dropdown selection to ISO code
    iso_code = COUNTRY_CODES.get(selected_country, selected_country)
    
    # Primary fetch (WDI + IMF supplement for OECD countries)
    df = get_debt_data(iso_code, manual_override)

    if df.empty:
        fig = px.scatter(title=f"No data found for {selected_country}")
        return fig, display_indicator

    fig = px.line(df, x='date', y='value', 
                  labels={'value': 'Debt (% of GDP)', 'date': 'Year'},
                  template='plotly_white')

    # Extend Y-axis below to 0 and above to about 20% of max value
    y_max = df['value'].max() * 1.2
    fig.update_layout(
        hovermode="x unified",
        title={
            'text': f"Debt for {selected_country}<br><sup>Indicator: {display_indicator}</sup>",
            'x': 0.5,
            'xanchor': 'center'
        },
        yaxis=dict(range=[0, y_max])
    )
    
    fig.update_traces(hovertemplate=f"<b>Indicator:</b> {display_indicator}<br><b>Year:</b> %{{x}}<br><b>Debt:</b> %{{y}}% of GDP<extra></extra>")

    return fig, display_indicator


# Run the server
if __name__ == '__main__':
    app.run(debug=True)