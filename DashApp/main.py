import dash
from dash import html, dcc
import dash_bootstrap_components as dbc

# Initialize the Dash app with Pages support
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], use_pages=True)

# Define the main layout with navigation links
app.layout = dbc.Container([
    dbc.Row([dbc.Col(html.H1("UNIS 2014 Fantasy Dashboard"), className="mb-4")]),

    dbc.Row([
        dbc.Col(dcc.Link("Weekly Stats", href="/weekly-stats"), width=2),
        dbc.Col(dcc.Link("Cumulative Stats", href="/cumulative-stats"), width=2)
    ], className="mb-4"),

    dash.page_container  # Container to render the current page's layout
])

if __name__ == '__main__':
    app.run_server(debug=True)

