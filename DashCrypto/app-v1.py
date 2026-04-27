import dash
from dash import Dash, html, dcc, Input, Output, State, ALL, ctx
import plotly.graph_objects as go
import pandas as pd
import requests
from functools import lru_cache

# -----------------------
# Config / Theme
# -----------------------
BCHAIN_THEME = {
    'bg_color': '#0c0c2c',
    'accent_blue': '#0055ff',
    'line_color': '#0face5',
    'grid_color': '#1e1e3f',
    'text_color': '#ffffff'
}

API_URL = "https://api.coingecko.com/api/v3/coins/markets"


# -----------------------
# Data Layer (cached + safe)
# -----------------------
@lru_cache(maxsize=1)
def get_crypto_data():
    try:
        params = {
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 50,
            "page": 1,
            "sparkline": True
        }
        r = requests.get(API_URL, params=params, timeout=10)
        r.raise_for_status()
        df = pd.DataFrame(r.json())
        # keep BOTH name and id
        df = df[['id', 'name']]
        return df.set_index('name')
    except Exception:
        return pd.DataFrame()

df_all = get_crypto_data()
TOP_15 = df_all.index[:15].tolist() if not df_all.empty else ["Bitcoin"] * 15


# -----------------------
# Figure Factory
# -----------------------
def create_fig(coin_name):
    if coin_name in df_all.index:
        row = df_all.loc[coin_name]

        prices = row.get('sparkline_in_7d', {}).get('price', [])
    else:
        prices = []

    if not prices:
        prices = [0]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        y=prices,
        mode='lines',
        line=dict(color=BCHAIN_THEME['line_color'], width=3),
        fill='tozeroy',
        fillcolor='rgba(15, 172, 229, 0.1)'
    ))

    fig.update_layout(
        title=f"<b>{coin_name.upper()}</b>",
        paper_bgcolor=BCHAIN_THEME['bg_color'],
        plot_bgcolor=BCHAIN_THEME['bg_color'],
        font=dict(color=BCHAIN_THEME['text_color']),
        margin=dict(l=30, r=10, t=35, b=20),
        xaxis=dict(gridcolor=BCHAIN_THEME['grid_color'], showticklabels=False),
        yaxis=dict(gridcolor=BCHAIN_THEME['grid_color']),
        height=250
    )

    return fig


# -----------------------
# App Init
# -----------------------
app = Dash(__name__)
server = app.server


# -----------------------
# Layout
# -----------------------
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>Dash</title>
        {%favicon%}
        {%css%}
        <style>
            .dropdown-dark .Select-control {
                background-color: #ffffff !important;
                color: #000000 !important;
            }
            .dropdown-dark .Select-value-label {
                color: #000000 !important;
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

app.layout = html.Div(
    style={
        'display': 'flex',
        'minHeight': '100vh',
        'backgroundColor': BCHAIN_THEME['bg_color'],
        'color': BCHAIN_THEME['text_color'],
        'fontFamily': 'sans-serif'
    },
    children=[

        # Sidebar
        html.Div(
            style={
                'width': '130px',
                'padding': '20px',
                'borderRight': f'1px solid {BCHAIN_THEME["grid_color"]}'
            },
            children=[
                html.H2("Crypto Monitor"),

                html.Label("Layout"),
                dcc.Dropdown(
                    id='layout-selector',
                    options=[{'label': f'{i} charts', 'value': i} for i in range(1, 16)],
                    value=3,
                    clearable=False,
                    style={'color': '#000'},
                    className='dropdown-dark'
                ),

                html.Br(),

                html.Label("Select Chart"),
                dcc.Dropdown(
                    id='crypto-search',
                    options=[{'label': c, 'value': c} for c in df_all.index],
                    placeholder="Select coin...",
                    style={'color': '#000'},
                    className='dropdown-dark'
                ),

                # Centralized state
                dcc.Store(id='charts-store'),
                dcc.Store(id='active-index', data=0)
            ]
        ),

        # Main
        html.Div(
            style={
                'flex': 1, 
                'padding': '20px',
                'backgroundColor': BCHAIN_THEME['bg_color'],
                'minHeight': '100vh'
                },
            children=[
                html.Div(id='charts-container')
            ]
        )
    ]
)


# -----------------------
# Initialize Store
# -----------------------
@app.callback(
    Output('charts-store', 'data'),
    Input('layout-selector', 'value'),
    State('charts-store', 'data')
)
def init_store(n, current):
    if current and len(current) == n:
        return current

    return TOP_15[:n]


# -----------------------
# Handle Chart Replacement
# -----------------------
@app.callback(
    Output('charts-store', 'data', allow_duplicate=True),
    Output('crypto-search', 'value'),
    Input('crypto-search', 'value'),
    State('charts-store', 'data'),
    State('active-index', 'data'),
    prevent_initial_call=True
)
def replace_chart(coin, charts, active_idx):
    if not coin or not charts:
        return dash.no_update

    charts = charts.copy()

    # Remove the selected coin if it already exists
    if coin in charts:
        charts.remove(coin)

    # Insert selected coin at the front
    charts.insert(0, coin)

    # Ensure length stays the same (drop last)
    charts = charts[:len(charts)]

    return charts, None


# -----------------------
# Track Active Chart
# -----------------------
@app.callback(
    Output('active-index', 'data'),
    Input({'type': 'chart', 'index': ALL}, 'n_clicks'),
    prevent_initial_call=True
)
def set_active(n_clicks):
    if not ctx.triggered_id:
        return 0
    return ctx.triggered_id['index']


# -----------------------
# Render Charts
# -----------------------
@app.callback(
    Output('charts-container', 'children'),
    Input('charts-store', 'data'),
    Input('active-index', 'data')
)
def render(charts, active_idx):
    if not charts:
        return []

    cols = min(len(charts), 3)

    grid_style = {
        'display': 'grid',
        'gridTemplateColumns': f'repeat({cols}, 1fr)',
        'gap': '15px'
    }

    children = []

    for i, coin in enumerate(charts):
        is_active = i == active_idx

        children.append(
            html.Div(
                id={'type': 'chart', 'index': i},
                children=[
                    dcc.Graph(
                        figure=create_fig(coin),
                        config={'displayModeBar': False}
                    )
                ],
                style={
                    'border': f'1px solid {BCHAIN_THEME["grid_color"]}',
                    'borderRadius': '8px',
                    'boxShadow': '0 0 12px #0face5' if is_active else 'none',
                    'cursor': 'pointer'
                }
            )
        )

    return html.Div(children, style=grid_style)


# -----------------------
# Run
# -----------------------
if __name__ == '__main__':
    app.run(debug=True)