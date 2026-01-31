import dash
from dash import dcc, html, Input, Output, dash_table, ctx
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

# Register the page
dash.register_page(__name__, path="/cumulative-stats", name="Cumulative Stats")

league = fantasyLeague()

team_options = [{"label": team, "value": team} for team in allMembers]
week_options = [{"label": week, "value": week} for week in range(1, max(totalMatchupCount.values()) + 1)]
year_options = [{"label": year, "value": year} for year in si]

layout = dbc.Container([
    dbc.Row([dbc.Col(html.H1("Cumulative Stats"), className="mb-4")]),

    dbc.Row([
        dbc.Col([
            html.Div([
                dash_table.DataTable(
                    id='rank-column',
                    columns=[{"name": "Rank", "id": "Rank"}],
                    data=[],
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'center', 'padding': f"{padding}px", 'width': '50px',
                                'font_size': f"{font_size}px"},
                    style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold',
                                  'font_size': f"{header_font_size}px"}
                )
            ], style={'marginRight': '10px'})
        ], width='auto'),

        dbc.Col([
            dash_table.DataTable(
                id='agg-stats-table',
                columns=[{"name": col, "id": col} for col in ['Team'] + mainCats],
                data=[],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'padding': f"{padding}px", 'width': '50px',
                            'font_size': f"{font_size}px"},
                style_header={'backgroundColor': 'rgb(230, 230, 230)', 'fontWeight': 'bold',
                              'font_size': f"{header_font_size}px"}
            ),
            html.Div([
                html.Label("Stat Mode:"),
                dbc.Checklist(
                    options=[{"label": " Averages", "value": "avg"}],
                    value=["avg"],
                    id="toggle-agg",
                    switch=True
                )
            ], className="mt-2")
        ], width=6),

        dbc.Col([
            html.Div([
                html.H5("Year", style={'textAlign': 'center'}),
                html.Div([
                    html.Button("Select All", id="select-year", className="mb-2 me-2"),
                    html.Button("Deselect All", id="deselect-year", className="mb-2")
                ], style={"textAlign": "center"}),
                html.Div([
                    dbc.Button("Select Years", id="year-dropdown-toggle", color="secondary", className="mb-2",
                               n_clicks=0),
                    dbc.Collapse(
                        dcc.Checklist(
                            id="year-checklist",
                            options=year_options,
                            value=[year["value"] for year in year_options],
                            inputStyle={"marginRight": "10px"},
                            labelStyle={"display": "block", "marginBottom": "5px"}
                        ),
                        id="year-dropdown-collapse",
                        is_open=False
                    )
                ]),

            ], style={"border": "1px solid #ccc", "borderRadius": "5px", "padding": "10px", "marginBottom": "10px"}),

            html.Div([
                html.H5("Team", style={'textAlign': 'center'}),
                html.Div([
                    html.Button("Select All", id="select-team", className="mb-2 me-2"),
                    html.Button("Deselect All", id="deselect-team", className="mb-2")
                ], style={"textAlign": "center"}),
                html.Div([
                    dbc.Button("Select Teams", id="team-dropdown-toggle", color="secondary", className="mb-2",
                               n_clicks=0),
                    dbc.Collapse(
                        dcc.Checklist(
                            id="team-checklist",
                            options=team_options,
                            value=[team["value"] for team in team_options],
                            inputStyle={"marginRight": "10px"},
                            labelStyle={"display": "block", "marginBottom": "5px"}
                        ),
                        id="team-dropdown-collapse",
                        is_open=False
                    )
                ]),

            ], style={"border": "1px solid #ccc", "borderRadius": "5px", "padding": "10px"})
        ], width=2),

        dbc.Col([
            html.Div([
                html.H5("Week", style={'textAlign': 'center'}),
                html.Div([
                    html.Button("Select All", id="select-week", className="mb-2 me-2"),
                    html.Button("Deselect All", id="deselect-week", className="mb-2")
                ], style={"textAlign": "center"}),
                html.Div([
                    dbc.Button("Select Weeks", id="week-dropdown-toggle", color="secondary", className="mb-2",
                               n_clicks=0),
                    dbc.Collapse(
                        dcc.Checklist(
                            id="week-checklist",
                            options=week_options,
                            value=[week["value"] for week in week_options],
                            inputStyle={"marginRight": "10px"},
                            labelStyle={"display": "block", "marginBottom": "5px"}
                        ),
                        id="week-dropdown-collapse",
                        is_open=False
                    )
                ]),

            ], style={"border": "1px solid #ccc", "borderRadius": "10px", "padding": "10px",
                      "maxHeight": "1000px", "overflowY": "auto", "marginBottom": "10px"}),

            html.Div([
                html.H5("Season:", style={'textAlign': 'center'}),
                dcc.Checklist(
                    id="season-checklist",
                    options=[{"label": "Reg. Season", "value": "RS"}, {"label": "Playoffs", "value": "PO"}],
                    value=["RS", "PO"],
                    inputStyle={"marginRight": "10px"},
                    labelStyle={"display": "block", "marginBottom": "5px"}
                ),

            ], style={"border": "1px solid #ccc", "borderRadius": "10px", "padding": "10px",
                      "maxHeight": "500px", "overflowY": "auto"})
        ], width=2, style={"alignSelf": "start"})
    ], className="mb-4")
])


# === CALLBACKS ===
@dash.callback(
    Output("toggle-agg", "options"),
    Input("toggle-agg", "value")
)
def update_toggle_label(value):
    if "avg" in value:
        return [{"label": "Averages", "value": "avg"}]
    else:
        return [{"label": "Totals", "value": "avg"}]


@dash.callback(
    [Output("agg-stats-table", "data"), Output("rank-column", "data")],
    [Input("year-checklist", "value"),
     Input("week-checklist", "value"),
     Input("team-checklist", "value"),
     Input("season-checklist", "value"),
     Input("toggle-agg", "value")]
)
def update_stats_table(selected_years, selected_weeks, selected_teams, selected_seasons, agg_mode):
    if not selected_years or not selected_weeks or not selected_teams:
        return [], []

    RS = 'RS' in selected_seasons
    PO = 'PO' in selected_seasons

    if "avg" in agg_mode:
        df = league.get_avg_df(years=selected_years, weeks=selected_weeks, teams=selected_teams, RS=RS, PO=PO)
    else:
        df = league.get_totals_df(years=selected_years, weeks=selected_weeks, teams=selected_teams, RS=RS, PO=PO)

    for col in mainCats:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        if col in mainCatsPCT:
            df[col] = df[col].round(3)
        else:
            df[col] = df[col].round(1)

    df = df.sort_values(by='Rank')
    table_data, rank_data = df.to_dict('records'), df[['Rank']].to_dict('records')

    return table_data, rank_data


@dash.callback(
    Output("year-checklist", "value"),
    [Input("year-checklist", "value"), Input("deselect-year", "n_clicks"), Input("select-year", "n_clicks")],
    prevent_initial_call=True
)
def update_year_checklist(selected_values, deselect_clicks, select_clicks):
    triggered_id = ctx.triggered_id
    if triggered_id == "deselect-year":
        return []
    if triggered_id == "select-year":
        return [opt["value"] for opt in year_options]
    return selected_values or []


@dash.callback(
    Output("team-checklist", "value"),
    [Input("team-checklist", "value"), Input("deselect-team", "n_clicks"), Input("select-team", "n_clicks")],
    prevent_initial_call=True
)
def update_team_checklist(selected_values, deselect_clicks, select_clicks):
    triggered_id = ctx.triggered_id
    if triggered_id == "deselect-team":
        return []
    if triggered_id == "select-team":
        return [opt["value"] for opt in team_options]
    # removed ALL logic block
    return selected_values or []


@dash.callback(
    Output("week-checklist", "value"),
    [Input("week-checklist", "value"), Input("deselect-week", "n_clicks"), Input("select-week", "n_clicks")],
    prevent_initial_call=True
)
def update_week_checklist(selected_values, deselect_clicks, select_clicks):
    triggered_id = ctx.triggered_id
    if triggered_id == "deselect-week":
        return []
    if triggered_id == "select-week":
        return [opt["value"] for opt in week_options]

    return selected_values or []
