from Models.League import fantasyLeague
from Models.team_profile import build_team_summary_df
from constants import *
import datetime
import pandas as pd
import inspect
import re
from StatGenerator import updateStatCSV

gDocName = "All-Time Leaders"
firstRow = 10

def _colnum_to_letter(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s

def _parse_a1_cell(a1: str) -> tuple[str, int]:
    """
    "B7" -> ("B", 7)
    """
    m = re.match(r"^([A-Za-z]+)(\d+)$", a1.strip())
    if not m:
        raise ValueError(f"Invalid A1 cell: {a1}")
    return m.group(1).upper(), int(m.group(2))

def updateCarTotals(league: fantasyLeague):
    print(inspect.currentframe().f_code.co_name)
    statList = []
    sheetname = "Career Totals"
    for team in league.historicalMembers:
        statDict = team.get_career_totals()
        row = [team.name]+[statDict[cat] for cat in gDocStatCats]
        statList.append(row)

    worksheet = gc.open(gDocName).worksheet(sheetname)
    
    worksheet.update(statList, f"A{firstRow}:J{firstRow + len(statList) - 1}")

    updateTime(sheetname,"L2")
    write_sheet(sheetname, f"All Time {sheetname}", "A2", bold=True)

def updateRSTotals(league: fantasyLeague):
    print(inspect.currentframe().f_code.co_name)
    statList = []
    sheetname = "RS Totals"
    for team in league.historicalMembers:
        statDict = team.get_career_RS_totals()
        row = [team.name]+[statDict[cat] for cat in gDocStatCats]
        statList.append(row)

    worksheet = gc.open(gDocName).worksheet(sheetname)
    
    worksheet.update(statList, f"A{firstRow}:J{firstRow + len(statList) - 1}")
    updateTime(sheetname,"L2")
    write_sheet(sheetname, f"All Time {sheetname}", "A2", bold=True)
def updatePOTotals(league: fantasyLeague):
    print(inspect.currentframe().f_code.co_name)
    statList = []
    sheetname = "PO Totals"
    for team in league.historicalMembers:
        statDict = team.get_career_PO_totals()
        row = [team.name]+[statDict[cat] for cat in gDocStatCats]
        statList.append(row)

    worksheet = gc.open(gDocName).worksheet(sheetname)
    
    worksheet.update(statList, f"A{firstRow}:J{firstRow + len(statList) - 1}")
    updateTime(sheetname,"L2")
    write_sheet(sheetname, f"All Time {sheetname}", "A2", bold=True)

def updateCarAVGs(league: fantasyLeague):
    print(inspect.currentframe().f_code.co_name)
    statList = []
    sheetname = "Career AVGs"
    for team in league.historicalMembers:
        statDict = team.get_career_averages()
        row = [team.name]+[statDict[cat] for cat in gDocStatCats]
        statList.append(row)

    worksheet = gc.open(gDocName).worksheet(sheetname)
    
    worksheet.update(statList, f"A{firstRow}:J{firstRow + len(statList) - 1}")
    updateTime(sheetname,"L2")
    write_sheet(sheetname, f"All Time {sheetname}", "A2", bold=True)

def updateRSAVGs(league: fantasyLeague):
    print(inspect.currentframe().f_code.co_name)
    statList = []
    sheetname = "RS AVGs"
    for team in league.historicalMembers:
        statDict = team.get_career_RS_averages()
        row = [team.name]+[statDict[cat] for cat in gDocStatCats]
        statList.append(row)

    worksheet = gc.open(gDocName).worksheet(sheetname)
    
    worksheet.update(statList, f"A{firstRow}:J{firstRow + len(statList) - 1}")
    updateTime(sheetname,"L2")
    write_sheet(sheetname, f"All Time {sheetname}", "A2", bold=True)

def updatePOAVGs(league: fantasyLeague):
    print(inspect.currentframe().f_code.co_name)
    sheetname = "PO AVGs"
    statList = []

    # for team in league.historicalMembers:
    #     statDict = team.get_career_PO_averages()
    #     row = [team.name]+[statDict[cat] for cat in gDocStatCats]
    #     statList.append(row)

    for team in league.historicalMembers:
        df = team.get_career_PO_averages_df()
        pd.set_option('future.no_silent_downcasting', True)
        df = df.fillna(0)
        statList.append([team.name]+df[gDocStatCats].values.tolist()[0])

    worksheet = gc.open(gDocName).worksheet(sheetname)
    
    worksheet.update(statList, f"A{firstRow}:J{firstRow + len(statList) - 1}")
    updateTime(sheetname,"L2")
    write_sheet(sheetname, f"All Time {sheetname}", "A2", bold=True)

def updateSummarySheet(league: fantasyLeague, clear_sheet: bool = True):
    """
    Populates the 'Summary' worksheet in Google Sheet gDocName with the final summary dataframe.

    Assumes these exist/imported elsewhere:
      - gc (gspread client)
      - build_team_summary_df(allMembers, reuse_managers=...)
      - updateTime(sheetname, cell)  (optional)
      - write_sheet(sheetname, title, cell, bold=True) (optional)
    """
    print(inspect.currentframe().f_code.co_name)
    sheetname = "Summary"
    start_cell = "A4"

    # Build final summary DF
    df = build_team_summary_df(reuse_managers={tm.name:tm for tm in league.historicalMembers})

    # Make it Sheets-friendly
    df_to_upload = df.copy()
    df_to_upload = df_to_upload.where(pd.notnull(df_to_upload), "")  # NaN -> ""
    values = [df_to_upload.columns.tolist()] + df_to_upload.values.tolist()

    # Open worksheet
    ws = gc.open(gDocName).worksheet(sheetname)

    if clear_sheet:
        ws.clear()

    # Compute range (so it works with your worksheet.update(values, range) style)
    start_col_letters, start_row = _parse_a1_cell(start_cell)
    start_col_num = 0
    for ch in start_col_letters:
        start_col_num = start_col_num * 26 + (ord(ch) - 64)

    n_rows = len(values)
    n_cols = len(values[0]) if n_rows else 0

    end_col_num = start_col_num + n_cols - 1
    end_row = start_row + n_rows - 1
    end_col_letters = _colnum_to_letter(end_col_num)

    rng = f"{start_col_letters}{start_row}:{end_col_letters}{end_row}"

    # Write values
    ws.update(values, rng)

    # Optional helpers you already use elsewhere
    try:
        updateTime(sheetname, "L2")
    except Exception:
        pass

    try:
        write_sheet(sheetname, "All Time Summary", "A2", bold=True)
    except Exception:
        pass

    return df


def write_sheet(sheet, text, cell, bold = False, italic = False, underline = False):
    worksheet = gc.open(gDocName).worksheet(sheet)

    worksheet.update([[text],[""]], f"{cell}:{cell[0]}{int(cell[1])+1}")
    worksheet.format(cell, {"textFormat":{
        'bold':bold,
        'italic':italic,
        'underline':underline
    },
    "horizontalAlignment": "CENTER"
    })

def createSheets(baseSheet):
    sheets = [
        "Career Totals", "RS Totals", "PO Totals",
        "Career AVGs", "RS AVGs", "PO AVGs"
              ]

    worksheet_to_copy = gc.open(gDocName).worksheet(baseSheet)

    for i in range(len(sheets)):
        if sheets[i] == baseSheet:
            pass
        else:
            worksheet_to_copy.duplicate(insert_sheet_index=i+2, new_sheet_name=sheets[i])

def updateTime(sheet, cell):
    now = datetime.datetime.now()
    displayTime = f"{now.month}/{now.day}/{now.year - 2000} {now.hour}:{now.minute:02}"

    write_sheet(sheet, f"UPDATED {displayTime}", cell, bold=True)

if __name__ == '__main__':
    # createSheets("Career Totals")
    # updateStatCSV(currentYear)
    x = fantasyLeague()
    # updateCarTotals(x)
    # updateRSTotals(x)
    # updatePOTotals(x)
    # updateCarAVGs(x)
    # updateRSAVGs(x)
    # updatePOAVGs(x)
    updateSummarySheet(x)
