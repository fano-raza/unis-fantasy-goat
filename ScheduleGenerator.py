import os
import sys

REPO_ROOT = os.path.abspath(os.path.dirname(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from espn_fr.basketball import league
from yfpy_fr.query import YahooFantasySportsQuery
from constants import *
import csv
from shared.runtime_config import calendar_csv_path

## ESPN league/login info
leagueID = 82864377
espn_s2 = 'AEB10E76tw6SHjpKpDqw7nBJndJfFekcJaC%2FiUC0JrJ2wj1Nb5YcBVZ04ary1%2F%2FEiiqzXaA1UPb0CcRBu%2FMpigZ%2BX6Hr%2FqD0nan6hZfQok4YHbHuVkIAVHzfUnJ%2FLDPNMqtIcS8ZmhAFVwW62RM6HlhFSk1DZz6z29J0TZjioAkFhYwVDaf6ILm%2FrtaSTeBSPwdSOqxxyd%2F%2FzlZwt1avKDdP0fLxEytLrCGjtUpd8LANz6kvqXLgUBjRCz0YBrKbYlfzkc6zhmt2Fx%2Fncfcoi5eEOZbTPlFJRG%2B2k6Qw079Z7g%3D%3D'
swid = '{F1B30D95-9F03-4CA9-BE62-D89858BE885E}'

## YAHOO
year = currentYear
yQuery = YahooFantasySportsQuery('',str(yLeagueIDs[year]),'nba',yGameIDs[year],False,False,yKey,ySec)

gameInfo = yQuery.get_current_game_info()

csvList = []
for week in gameInfo.game_weeks:
    startDate = [int(i) for i in week.start.split("-")]
    endDate = [int(i) for i in week.end.split("-")]
    line = [week.week]+startDate+endDate
    csvList.append(line)

pathname = calendar_csv_path(year)
with open(pathname, 'w') as csvfile:
    header = ["week","start year","start mon", "start day", "end year", "end mon", "end day"]
    writer = csv.writer(csvfile)
    writer.writerow(header)
    writer.writerows(csvList)
