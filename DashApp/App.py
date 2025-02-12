import dash
from dash import dcc, html, Input, Output, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
from StatGenerator import genWeekStatDict
from constants import *
from constants import seasonInfoDict as si
from Models.League import *

# Sample function to simulate your data retrieval function
def get_week_stats(year, week):
    data = genWeekStatDict(year, week)
    # print(data)

    df = pd.DataFrame.from_dict(data, orient='index')
    # Reset index to make team names a column
    df = df.reset_index().rename(columns={'index': 'Team'})
    df = df.drop(columns=['Opp'])

    return df

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

## test comment to see if push works

# Layout of the app
app.layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H1("NBA Fantasy League Stats"), className="mb-4")
    ]),

    dbc.Row([
        dbc.Col(html.Label("Select Year:", style={'margin-right': '10px'}), width="auto"),
        dbc.Col([
            dcc.Dropdown(
                id='year-dropdown',
                options=[{'label': str(year), 'value': year} for year in si],
                value=currentYear,  # Default selected year
                clearable=False
            )
        ], width=2, align='middle'),
        dbc.Col([
            html.Label("Select Week:"),
            dcc.Input(id='week-input', type='number', value=1, min=1, max=20),],
            width=4),
        dbc.Col([
            html.Button('Update', id='update-button', n_clicks=0, className="mt-4")
        ], width=4)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            # html.H4("Focus Team"),
            html.Label("Select Focus Team:"),
            dcc.Dropdown(
                id='focus-team-dropdown',
                clearable=False,
                style={'width': '100%'}
            )
        ], width=3),  # Adjust width to fit dropdown next to the table

        dbc.Col([
            dash_table.DataTable(
                id='focus-team-table',
                columns=[{"name": col, "id": col} for col in mainCats],
                data=[],
                style_table={'overflowX': 'auto', 'width': '100%'},
                style_cell={'textAlign': 'center'},
                style_header={
                    'backgroundColor': 'rgb(230, 230, 230)',
                    'fontWeight': 'bold'
                }
            )
        ], width=9)  # Set the table to take up more space
    ], align='center', className="mb-4"),
    dbc.Row([
        dbc.Col([
            # html.H4("All Teams"),
            dash_table.DataTable(
                id='stats-table',
                columns=[
                    {"name": col, "id": col} for col in ['Team']+mainCats
                ],
                data=[],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'font': 'Arial'},
                style_header={
                    'backgroundColor': 'rgb(230, 230, 230)',
                    'fontWeight': 'bold'
                },

            )
        ], width=12)
    ])
])

# Callback to update the table based on the year and week number input
@app.callback(
    [Output('focus-team-dropdown', 'options'),
     Output('focus-team-dropdown', 'value'),
     Output('stats-table', 'data'),
     Output('focus-team-table', 'data')],
    [Input('update-button', 'n_clicks'),
     Input('year-dropdown', 'value'),
     Input('week-input', 'value'),
     Input('focus-team-dropdown', 'value')]
)
def update_table(n_clicks, year, week, focus_team):
    df = get_week_stats(year, week)
    main_table_data = df.to_dict('records')

    # Update focus team dropdown options
    team_options = [{'label': team, 'value': team} for team in df['Team']]

    if not focus_team:
        focus_team = df['Team'].iloc[0]  # Default to the first team

    if n_clicks > 0:
        main_table_data = df.to_dict('records')

        # Update the focus team table data
        focus_team_stats = df[df['Team'] == focus_team].drop(columns=['Team']).to_dict('records')
        focus_team_data = focus_team_stats if focus_team_stats else []

        return team_options, focus_team, main_table_data, focus_team_data

    return team_options, focus_team, main_table_data, []

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)