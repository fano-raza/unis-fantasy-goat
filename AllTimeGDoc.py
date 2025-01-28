from League import fantasyLeague
from constants import *
import datetime
import time
from gdoc_writer import write_gDoc

gDocName = "All-Time Leaders"
firstRow = 10

def updateCarTotals(league: fantasyLeague):
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
    statList = []
    sheetname = "PO AVGs"
    for team in league.historicalMembers:
        statDict = team.get_career_PO_averages()
        row = [team.name]+[statDict[cat] for cat in gDocStatCats]
        statList.append(row)

    worksheet = gc.open(gDocName).worksheet(sheetname)
    
    worksheet.update(statList, f"A{firstRow}:J{firstRow + len(statList) - 1}")
    updateTime(sheetname,"L2")
    write_sheet(sheetname, f"All Time {sheetname}", "A2", bold=True)

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

    i = 0
    while i < len(sheets):
        if sheets[i] == baseSheet:
            pass
        else:
            worksheet_to_copy.duplicate(insert_sheet_index=i+2, new_sheet_name=sheets[i])
        i += 1

def updateTime(sheet, cell):
    now = datetime.datetime.now()
    displayTime = f"{now.month}/{now.day}/{now.year - 2000} {now.hour}:{now.minute:02}"

    write_sheet(sheet, f"UPDATED {displayTime}", cell, bold=True)

if __name__ == '__main__':
    createSheets("Career Totals")
    x = fantasyLeague()
    updateCarTotals(x)
    updateRSTotals(x)
    updatePOTotals(x)
    updateCarAVGs(x)
    updateRSAVGs(x)
    updatePOAVGs(x)