import dash
from dash import dcc, html, Input, Output, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
from StatGenerator import genWeekStatDict
from constants import *
from constants import seasonInfoDict as si

# Sample function to simulate your data retrieval function
def get_week_stats(year, week):
    df = pd.DataFrame(genWeekStatDict(year, week))
    df = df.iloc[1:-1]
    df.loc['Team'] = df.columns
    print(df)
    return df

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Layout of the app
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H1("NBA Fantasy League Stats"), className="mb-4")
    ]),
    dbc.Row([
        dbc.Col([
            html.Label("Select Year:"),
            dcc.Dropdown(
                id='year-dropdown',
                options=[{'label': str(year), 'value': year} for year in si],
                value=currentYear,  # Default selected year
                clearable=False
            )
        ], width=4),
        dbc.Col([
            html.Label("Select Week:"),
            dcc.Input(id='week-input', type='number', value=1, min=1, max=20),],
            width=4),
        dbc.Col([
            html.Button('Update', id='update-button', n_clicks=0, className="mt-4")
        ], width=4)
    ]),
    dbc.Row([
        dbc.Col([
            dash_table.DataTable(
                id='stats-table',
                columns=[
                    {"name": col, "id": col} for col in ['Team', 'FG%', 'FT%', '3PM', 'PTS', 'AST', 'REB', 'STL', 'BLK', 'TO']
                ],
                data=[],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'left'},
                style_header={
                    'backgroundColor': 'rgb(230, 230, 230)',
                    'fontWeight': 'bold'
                }
            )
        ], width=12)
    ])
])

# Callback to update the table based on the year and week number input
@app.callback(
    Output('stats-table', 'data'),
    Input('update-button', 'n_clicks'),
    Input('year-dropdown', 'value'),
    Input('week-input', 'value')
)
def update_table(n_clicks, year, week):
    if n_clicks > 0:
        df = get_week_stats(year, week)
        return df.to_dict('records')  # Convert DataFrame to a list of dictionaries for Dash
    return []

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)