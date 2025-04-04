import dash
from dash import dcc, html, Input, Output, dash_table
# import dash
import dash_bootstrap_components as dbc
import pandas as pd
from StatGenerator import *
from constants import *
from constants import seasonInfoDict as si
from Models.League import *
from style_sheet import *

#instantiate fantasyLeague object
league = fantasyLeague()

# column definitions
weekStatColDisplay = ['Team']+mainCats+['Score', 'Rating', 'Rank']
focusStatColDisplay = mainCats+['Rating', 'Rank']

# Initialize the Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], use_pages=True, pages_folder="")

# Layout of the app
app.layout = dbc.Container([
    ## HEADER/TITLE
    dbc.Row([
        dbc.Col(html.H1("UNIS 2014 Fantasy"), className="mb-4")
    ]),

    ## YEAR SELECT MENU
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

        ## WEEK SELECT MENU
        dbc.Col([
            html.Label("Select Week:"),
            dcc.Input(id='week-input', type='number',
                      value=league.seasons[currentYear].currentWeek,
                      min=1,
                      max=20),],
            width=4),
        dbc.Col([
            html.Button('Update', id='update-button', n_clicks=0, className="mt-4")
        ], width=4)
    ], className="mb-4"),

    dbc.Row([
        ## FOCUS TEAM SELECT
        dbc.Col([
            html.Label("Select Team:"),
            dcc.Dropdown(
                id='focus-team-dropdown',
                clearable=False,
                style={'width': '100px'}
            )
        ], style={'marginRight': '50px'}, width=str(width)),

        ## FOCUS TEAM MAIN CATS
        dbc.Col([
            dash_table.DataTable(
                id='focus-team-stats',
                columns=[{"name": col, "id": col} for col in mainCats],
                data=[],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'padding': f"{padding}px", 'width': '50px',
                            'font_size':f"{font_size}px"},
                style_header={
                    'backgroundColor': 'rgb(230, 230, 230)',
                    'fontWeight': 'bold', 'font_size':f"{header_font_size}px"
                }
            )
        ], style={'marginRight': '50px'}, width=str(width)),

        ## FOCUS TEAM RATING/RANK
        dbc.Col([
            dash_table.DataTable(
                id='focus-team-rating',
                columns=[{"name": col, "id": col} for col in ['Rating', 'Rank']],
                data=[],
                style_table={'overflowX': 'auto'},
                style_cell={'textAlign': 'center', 'padding': f"{padding}px", 'width': '100px',
                            'font_size':f"{font_size}px"},
                style_header={
                    'backgroundColor': 'rgb(230, 230, 230)',
                    'fontWeight': 'bold', 'font_size':f"{header_font_size}px"
                }
            )
        ], width=str(width))

    ],
        justify='start',
        className='mb-4 g-0',
        style={
            'marginRight': f"{pageMargin}px",
            'marginLeft': f"{pageMargin}px"
        }
    ),

    dbc.Row([
        ## OTHER TEAM STATS
        dbc.Col([
            # html.H4("All Teams"),
            dash_table.DataTable(
                id='opp-stats-table',
                columns=[
                    {"name": col, "id": col} for col in weekStatColDisplay
                ],
                data=[],
                style_table={'overflowX': 'auto'},
                style_data_conditional=[
                    {'if': {'column_id': 'Team'}, 'width': '150px'},
                    {'if': {'column_id': 'Rating'}, 'width': '100px'},
                    {'if': {'column_id': 'Rank'}, 'width': '100px'},
                ],
                style_cell={'textAlign': 'center', 'padding': f"{padding}px", 'width': '50px',
                            'font_size':f"{font_size}px"},
                style_header={
                    'backgroundColor': 'rgb(230, 230, 230)',
                    'fontWeight': 'bold', 'font_size':f"{header_font_size}px"
                },

            )
        ], width=str(width))
    ],
        justify='start',
        className='g-0',
        style={
            'marginRight': f"{pageMargin}px",
            'marginLeft': f"{pageMargin}px"
        }),
    dash.page_container  # This is required for multi-page apps
])

# Callback to update week max and current weeks
@app.callback(
    [Output('week-input', 'max'),
     Output('week-input', 'value')],
    [Input('year-dropdown', 'value')]
)
def update_week_max(year):
    max_week = weekCountDict[year]+playoffRounds[year]
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
    opp_df['Rating'] = opp_df['week_rating'].apply(lambda x: round(x, 3))
    opp_df['Rank'] = opp_df['week_rank'].apply(lambda x: round(x, 2))

    focus_df = league.get_filtered_df(years=[year], weeks=[week], real=True, teams=[focus_team])
    focus_df['FG%'] = focus_df['FG%'].apply(lambda x: round(x, 3))
    focus_df['FT%'] = focus_df['FT%'].apply(lambda x: round(x, 3))
    focus_df['Rating'] = focus_df['week_rating'].apply(lambda x: round(x, 3))
    focus_df['Rank'] = focus_df['week_rank'].apply(lambda x: round(x, 2))

    return opp_df, focus_df

# Callback to update the table based on the year and week number input
@app.callback(
    [Output('focus-team-dropdown', 'options'),
     Output('focus-team-dropdown', 'value'),
     Output('opp-stats-table', 'data'),
     Output('opp-stats-table', 'style_data_conditional'),  # New output for styling
     Output('focus-team-stats', 'data'),
     Output('focus-team-rating', 'data')],

    [Input('update-button', 'n_clicks'),
     Input('year-dropdown', 'value'),
     Input('week-input', 'value'),
     Input('focus-team-dropdown', 'value')]
)
def update_table(n_clicks, year, week, focus_team):
    # Get teams data
    team_options = [{'label': team, 'value': team} for team in
                    league.get_filtered_df(years=[year], weeks=[week], real=True)['Team']]

    if {'label': focus_team, 'value': focus_team} not in team_options:
        focus_team = team_options[0]['value']
        # Default to first team in team_options if current focus_team selection is not valid option

    # Get data
    opp_df, focus_df = get_week_stats(year, week, focus_team)
    opp_table_data = opp_df.to_dict('records')
    focus_team_data = focus_df.to_dict('records')

    # Generate initial conditional formatting for opp_stat_table
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
                color = 'white'  # No styling

            style_cond.append({
                'if': {'row_index': i, 'column_id': cat},
                'backgroundColor': color,
                'color': 'white' if color in ['red', 'green'] else 'black'
                # 'color': 'black'
            })
    return style_cond

# Run the app
if __name__ == '__main__':
    app.run_server(debug=True)