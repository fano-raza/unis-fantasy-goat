import dash
from dash import dcc, html, Input, Output, dash_table
import dash_bootstrap_components as dbc
import pandas as pd
import os
import sys

# Add parent dir to sys.path for module access
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from StatGenerator import *
from constants import *
from constants import seasonInfoDict as si
from Models.League import *
from DashApp.style_sheet import *


# Determine the parent directory and add it to sys.path
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from StatGenerator import *
from constants import *
from Models.League import *
import DashApp.style_sheet

# Register the page with Dash
dash.register_page(__name__, path="/weekly-stats", name="Weekly Stats")

# Instantiate the fantasyLeague object
league = fantasyLeague()

# Define column headers
weekStatColDisplay = ['Team'] + mainCats + ['Score', 'Rating', 'Rank']

# Layout for the Weekly Stats page
layout = dbc.Container([
    dbc.Row([
        dbc.Col(html.H1("UNIS 2014 Fantasy"), className="mb-4")
    ]),

    dbc.Row([
        dbc.Col(html.Label("Select Year:", style={'margin-right': '10px'}), width="auto"),
        dbc.Col([
            dcc.Dropdown(
                id='year-dropdown',
                options=[{'label': str(year), 'value': year} for year in si],
                value=currentYear,
                clearable=False
            )
        ], width=2, align='middle'),

        dbc.Col([
            html.Label("Select Week:"),
            dcc.Input(id='week-input', type='number',
                      value=league.seasons[currentYear].currentWeek,
                      min=1,
                      max=20)
        ], width=4),

        dbc.Col([
            html.Button('Update', id='update-button', n_clicks=0, className="mt-4")
        ], width=4)
    ], className="mb-4"),

    dbc.Row([
        dbc.Col([
            html.Label("Select Team:"),
            dcc.Dropdown(id='focus-team-dropdown', clearable=False, style={'width': '100px'})
        ], style={'marginRight': '50px'}, width=str(width)),

        dbc.Col([
            dash_table.DataTable(
                id='focus-team-stats',
                columns=[{"name": col, "id": col} for col in mainCats],
                data=[],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'padding': f"{padding}px", 'width': '50px',
                            'font_size': f"{font_size}px"},
                style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold',
                              'font_size': f"{header_font_size}px"}
            )
        ], style={'marginRight': '50px'}, width=str(width)),

        dbc.Col([
            dash_table.DataTable(
                id='focus-team-rating',
                columns=[{"name": col, "id": col} for col in ['Rating', 'Rank']],
                data=[],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'padding': f"{padding}px", 'width': '100px',
                            'font_size': f"{font_size}px"},
                style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold',
                              'font_size': f"{header_font_size}px"}
            )
        ], width=str(width))
    ],
        justify='start',
        className='mb-4 g-0',
        style={'marginRight': f"{pageMargin}px", 'marginLeft': f"{pageMargin}px"}
    ),

    dbc.Row([
        dbc.Col([
            dash_table.DataTable(
                id='opp-stats-table',
                columns=[{"name": col, "id": col} for col in weekStatColDisplay],
                data=[],
                style_table={'overflowX': 'auto'},
                style_data_conditional=[
                    {'if': {'column_id': 'Team'}, 'width': '150px'},
                    {'if': {'column_id': 'Rating'}, 'width': '100px'},
                    {'if': {'column_id': 'Rank'}, 'width': '100px'},
                ],
                style_cell={'textAlign': 'center', 'padding': f"{padding}px", 'width': '50px',
                            'font_size': f"{font_size}px"},
                style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold',
                              'font_size': f"{header_font_size}px"}
            )
        ], width=str(width))
    ],
        justify='start',
        className='g-0',
        style={'marginRight': f"{pageMargin}px", 'marginLeft': f"{pageMargin}px"}
    )
])

# Define callbacks for interactivity
# Example: Callback to update week max and current week
@dash.callback(
    [Output('week-input', 'max'),
     Output('week-input', 'value')],
    [Input('year-dropdown', 'value')]
)
def update_week_max(year):
    max_week = RS_weekCountDict[year] + playoffRounds[year]
    current_week = league.seasons[year].currentWeek
    return max_week, current_week

def get_week_stats(year, week, focus_team):
    opp_df = league.get_filtered_df(years=[year], weeks=[week], real=False, opps=[focus_team])
    if opp_df.empty:
        focus_team = league.get_filtered_df(years=[year], weeks=[week], real=True)['Team'][0]
        opp_df = league.get_filtered_df(years=[year], weeks=[week], real=False, opps=[focus_team])

    opp_df['FG%'] = opp_df['FG%'].apply(lambda x: round(x, 3))
    opp_df['FT%'] = opp_df['FT%'].apply(lambda x: round(x, 3))
    opp_df['Score'] = opp_df.apply(lambda row: f"{row['cat_losses']}-{row['cat_wins']}", axis=1)
    opp_df['Rating'] = opp_df['week_rating'].apply(lambda x: round(x, 1))
    opp_df['Rank'] = opp_df['week_rank']

    focus_df = league.get_filtered_df(years=[year], weeks=[week], real=True, teams=[focus_team])
    focus_df['FG%'] = focus_df['FG%'].apply(lambda x: round(x, 3))
    focus_df['FT%'] = focus_df['FT%'].apply(lambda x: round(x, 3))
    focus_df['Rating'] = focus_df['week_rating'].apply(lambda x: round(x, 1))
    focus_df['Rank'] = focus_df['week_rank']

    opp_df = opp_df.sort_values('week_rank')

    return opp_df, focus_df

@dash.callback(
    [Output('focus-team-dropdown', 'options'),
     Output('focus-team-dropdown', 'value'),
     Output('opp-stats-table', 'data'),
     Output('opp-stats-table', 'style_data_conditional'),
     Output('focus-team-stats', 'data'),
     Output('focus-team-rating', 'data')],
    [Input('update-button', 'n_clicks'),
     Input('year-dropdown', 'value'),
     Input('week-input', 'value'),
     Input('focus-team-dropdown', 'value')]
)
def update_table(n_clicks, year, week, focus_team):
    team_options = [{'label': team, 'value': team} for team in league.get_filtered_df(years=[year], weeks=[week], real=True)['Team']]
    if {'label': focus_team, 'value': focus_team} not in team_options:
        focus_team = team_options[0]['value']

    opp_df, focus_df = get_week_stats(year, week, focus_team)
    opp_table_data = opp_df.to_dict('records')
    focus_team_data = focus_df.to_dict('records')

    style_cond = [{'if': {'column_id': 'Team'}, 'width': '150px'},
                  {'if': {'column_id': 'Rating'}, 'width': '100px'},
                  {'if': {'column_id': 'Rank'}, 'width': '100px'}]
    style_cond += red_green_cond_style(focus_team_data, opp_table_data)

    return team_options, focus_team, opp_table_data, style_cond, focus_team_data, focus_team_data

def red_green_cond_style(main_stats, comp_stats):
    style_cond = []
    for i, row in enumerate(comp_stats):
        for cat in mainCats:
            main_val = main_stats[0][cat]
            comp_val = row[cat]

            if main_val > comp_val:
                color = 'green' if cat in posCats else 'red'
            elif main_val < comp_val:
                color = 'red' if cat in posCats else 'green'
            else:
                color = 'white'

            style_cond.append({
                'if': {'row_index': i, 'column_id': cat},
                'backgroundColor': color,
                'color': 'white' if color in ['red', 'green'] else 'black'
            })
    return style_cond

def update_week_max(year):
    max_week = totalMatchupCount[year]
    current_week = league.seasons[year].currentWeek
    return max_week, current_week

# Additional callbacks should be defined here