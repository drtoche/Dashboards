import dash
from dash import Dash, html, dcc, Input, Output, State, ALL, ctx
import plotly.graph_objects as go
import pandas as pd
import requests
import time
from functools import lru_cache

# -----------------------
# Theme
# -----------------------
THEME = {
    "bg": "#0c0c2c",
    "grid": "#1e1e3f",
    "line": "#0face5",
    "text": "#ffffff"
}

API = "https://api.coingecko.com/api/v3/coins/markets"


# -----------------------
# DATA (safe + cached)
# -----------------------
@lru_cache(maxsize=1)
def load_assets():
    try:
        r = requests.get(API, params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 50,
            "page": 1
        }, timeout=10)

        r.raise_for_status()
        data = r.json()

        if not isinstance(data, list):
            return pd.DataFrame()

        df = pd.DataFrame(data)
        if df.empty:
            return pd.DataFrame()

        # Fix 4: drop_duplicates before set_index so df.loc always returns a scalar
        return df[["id", "name"]].drop_duplicates("name").set_index("name")

    except Exception as e:
        print("DATA LOAD ERROR:", e)
        return pd.DataFrame()


df = load_assets()

DEFAULT = df.index[:15].tolist() if not df.empty else [
    "Bitcoin", "Ethereum", "Solana"
]


# -----------------------
# FIGURE (safe + cached per coin)
# -----------------------
@lru_cache(maxsize=32)
def fetch_prices(coin_id):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        r = requests.get(url, params={
            "vs_currency": "usd",
            "days": 1,
            "interval": "hourly"
        }, timeout=10)

        time.sleep(0.5)

        if r.status_code != 200:
            return []

        data = r.json()
        prices = data.get("prices", [])

        if not isinstance(prices, list):
            return []

        return prices

    except Exception:
        return []


def make_fig(name):
    fig = go.Figure()

    if df.empty or name not in df.index:
        fig.add_annotation(text=f"No data: {name}", showarrow=False, font=dict(color="red"))
        fig.update_layout(paper_bgcolor=THEME["bg"], plot_bgcolor=THEME["bg"])
        return fig

    coin_id = df.loc[name, "id"]
    prices = fetch_prices(coin_id)

    if not prices:
        fig.add_annotation(text="No API data", showarrow=False, font=dict(color="red"))
        fig.update_layout(paper_bgcolor=THEME["bg"], plot_bgcolor=THEME["bg"])
        return fig

    # Fix 1: convert ms timestamps to datetime for correct x-axis display
    x = [pd.to_datetime(p[0], unit="ms") for p in prices]
    y = [p[1] for p in prices]

    fig.add_trace(go.Scatter(
        x=x,
        y=y,
        mode="lines",
        line=dict(color=THEME["line"], width=2),
        fill="tozeroy",
        fillcolor="rgba(15,172,229,0.1)"
    ))

    fig.update_layout(
        title=dict(text=name, font=dict(color=THEME["text"], size=13)),
        paper_bgcolor=THEME["bg"],
        plot_bgcolor=THEME["bg"],
        font=dict(color=THEME["text"]),
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(showticklabels=False, gridcolor=THEME["grid"]),
        yaxis=dict(gridcolor=THEME["grid"]),
        height=250
    )

    return fig


# -----------------------
# APP
# -----------------------
app = Dash(__name__)
server = app.server


# -----------------------
# LAYOUT
# -----------------------
app.layout = html.Div(
    style={
        "display": "flex",
        "minHeight": "100vh",
        "backgroundColor": THEME["bg"],
        "color": THEME["text"],
        "fontFamily": "sans-serif"
    },
    children=[

        # Sidebar
        html.Div(
            style={
                "width": "160px",
                "padding": "20px",
                "borderRight": f"1px solid {THEME['grid']}"
            },
            children=[
                html.H3("Crypto"),

                dcc.Dropdown(
                    id="layout",
                    options=[{"label": f"{i} charts", "value": i} for i in range(1, 16)],
                    value=3,
                    clearable=False
                ),

                html.Br(),

                dcc.Dropdown(
                    id="picker",
                    options=[{"label": c, "value": c} for c in DEFAULT],
                    placeholder="Select coin..."
                ),

                dcc.Store(id="store"),
                dcc.Store(id="active", data=0)
            ]
        ),

        # Main
        html.Div(
            style={"flex": 1, "padding": "20px"},
            children=[html.Div(id="grid")]
        )
    ]
)


# -----------------------
# INIT
# Fix 3: extend store with defaults when growing, slice when shrinking
# -----------------------
@app.callback(
    Output("store", "data"),
    Input("layout", "value"),
    State("store", "data")
)
def init(n, current):
    current = current or []
    if len(current) == n:
        return current
    if len(current) < n:
        extras = [c for c in DEFAULT if c not in current]
        return (current + extras)[:n]
    return current[:n]


# -----------------------
# MOVE TO FRONT
# -----------------------
@app.callback(
    Output("store", "data", allow_duplicate=True),
    Output("picker", "value"),
    Input("picker", "value"),
    State("store", "data"),
    prevent_initial_call=True
)
def update(coin, store):
    if not coin or not store:
        return dash.no_update

    store = store.copy()

    if coin in store:
        store.remove(coin)

    store.insert(0, coin)

    return store[:len(store)], None


# -----------------------
# RENDER
# Fix 2: hardcode 3 columns as requested
# -----------------------
@app.callback(
    Output("grid", "children"),
    Input("store", "data")
)
def render(store):
    if not store:
        return []

    children = []

    for i, coin in enumerate(store):
        children.append(
            html.Div(
                children=[
                    dcc.Graph(
                        figure=make_fig(coin),
                        config={"displayModeBar": False}
                    )
                ],
                style={
                    "border": f"1px solid {THEME['grid']}",
                    "borderRadius": "8px"
                }
            )
        )

    return html.Div(
        children,
        style={
            "display": "grid",
            "gridTemplateColumns": "repeat(3, 1fr)",
            "gap": "15px"
        }
    )


# -----------------------
# RUN
# -----------------------
if __name__ == "__main__":
    app.run(debug=True)
