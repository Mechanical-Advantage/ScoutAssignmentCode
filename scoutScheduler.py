import cv2
import os
import requests
import json
import tbapy
from operator import itemgetter
import sqlite3 as sql
from pathlib import Path
import xlsxwriter
import math
from datetime import datetime

#Config
TBAkey = "yZEr4WuQd0HVlm077zUI5OWPfYsVfyMkLtldwcMYL6SkkQag29zhsrWsoOZcpbSj"
scoutRecordsDatabase = "testDatabase.db"
saveUpdatedRecords = False
outputFile = "schedule.xlsx"


if saveUpdatedRecords:
    print("Will save updated scout records.")
else:
    print("Will NOT save updated scout records.")
print()

#Check if database exists
tempPath = Path(scoutRecordsDatabase)
createNewDatabase = not tempPath.is_file()

#Connect to database
def connectDB():
    global conn
    global cur
    conn = sql.connect(scoutRecordsDatabase)
    cur = conn.cursor()

scoutRecords = []
scoutRecords_clean = []
def createScoutRecords():
    for i in range(0, len(scoutlist)):
        scoutRecords.append({})
        scoutRecords_clean.append({})

if createNewDatabase: #Create new database
    print("No database found at '" + scoutRecordsDatabase + "'")
    rawScouts = input("Enter a comma-separated list of scouts: ")
    scoutlist = [x.strip() for x in rawScouts.split(',')]
    createScoutRecords()
    connectDB()
    
    cur.execute("""CREATE TABLE matchRecords (
        scout TEXT,
        team TEXT,
        count INTEGAR
        ); """)
    cur.execute("""CREATE TABLE preferences (
        team INTEGAR,
        scout TEXT
        ); """)
    cur.execute("""CREATE TABLE scouts (
        name TEXT,
        enabled INTEGAR
        ); """)
    for i in range(0, len(scoutlist)):
        cur.execute("INSERT INTO scouts(name,enabled) VALUES (?,1)", (scoutlist[i],))
    conn.commit()

    print("Created database. Stop program now to add team preferences.")
    print()

else: #Read records from database
    connectDB()
    #Get scouts
    cur.execute("SELECT * FROM scouts")
    dbScouts = cur.fetchall()
    scoutlist = []
    for row in dbScouts:
        if row[1] == 1:
            scoutlist.append(row[0])

    #Get records
    cur.execute("SELECT * FROM matchRecords")
    dbMatchRecords = cur.fetchall()
    createScoutRecords()
    for row in dbMatchRecords:
        if row[0] in scoutlist:
            scoutRecords[scoutlist.index(row[0])][row[1]] = row[2]
            scoutRecords_clean[scoutlist.index(row[0])][row[1]] = row[2]

#Finish creation of scout records array
for i in range(0, len(scoutRecords)):
    scoutRecords[i]['total'] = 0
    scoutRecords[i]['id'] = i

#Check for 6 scouts
if len(scoutlist) < 6:
    print("Found " + str(len(scoutlist)) + " scouts. Must have 6 scouts.")
    quit()

#Initialize TBA link
tba = tbapy.TBA(TBAkey)

#Get event code
year = input("Enter year: ")
teamEventsRaw = tba.team_events('frc6328', year)
teamEventsSorted = sorted(teamEventsRaw, key=itemgetter('start_date'))
print()
print("Events:")
i = 0
for i in range(0, len(teamEventsSorted)):
    print(str(i + 1) + ') ' + teamEventsSorted[i].name)
print()
eventNumberRaw = input("Event #: ")
eventNumber = int(eventNumberRaw)-1
event = teamEventsSorted[eventNumber].key
eventFriendlyname = teamEventsSorted[eventNumber].name

#Create match schedule
print("Fetching schedule...")
matchlistRaw = tba.event_matches(event)
if len(matchlistRaw) == 0:
    print("No schedule available.")
    quit()

matchlistUnsorted = {}
matchlistDaysUnsorted = {}
for i in range(0, len(matchlistRaw)):
    if matchlistRaw[i].comp_level == 'qm':
        matchlistUnsorted[matchlistRaw[i].match_number] = [matchlistRaw[i].alliances["blue"]["team_keys"][0], matchlistRaw[i].alliances["blue"]["team_keys"][1], matchlistRaw[i].alliances["blue"]["team_keys"][2], matchlistRaw[i].alliances["red"]["team_keys"][0], matchlistRaw[i].alliances["red"]["team_keys"][1], matchlistRaw[i].alliances["red"]["team_keys"][2]]
        matchlistDaysUnsorted[matchlistRaw[i].match_number] = matchlistRaw[i].time

matchlist = []
for i in sorted(matchlistUnsorted.keys()):
    matchlist.append(matchlistUnsorted[i])

matchlistDays = []
day = 0
lastDate = -1
for i in sorted(matchlistDaysUnsorted.keys()):
    matchDay = int(datetime.utcfromtimestamp(matchlistDaysUnsorted[i]).strftime('%d'))
    if matchDay > lastDate:
        day += 1
        lastDate = matchDay
    matchlistDays.append(day)

print("Assigning scouts...")

#Get team list
teamlist = []
for matchnumber in range(0, len(matchlist)):
    for teamnumber in range(0, 6):
        if matchlist[matchnumber][teamnumber] not in teamlist:
            teamlist.append(matchlist[matchnumber][teamnumber])

#Update scout records array (to add teams)
for i in range(0, len(scoutlist)):
    for teamnumber in range(0, len(teamlist)):
        if teamlist[teamnumber] not in scoutRecords[i].keys():
            scoutRecords[i][teamlist[teamnumber]] = 0
            scoutRecords_clean[i][teamlist[teamnumber]] = 0

#Get preferences
cur.execute("SELECT * FROM preferences")
dbPreferences = cur.fetchall()
for row in dbPreferences:
    if row[1] in scoutlist:
        fullTeam = "frc" + str(row[0])
        scoutRecords[scoutlist.index(row[1])][fullTeam] = 9999
    else:
        print("WARNING: not obeying preference for Team " + str(row[0]) + " - scout '" + row[1] + "' not found or disabled")

#Create priority lists
def priorityList(team):
    sortedScouts = sorted(scoutRecords, key=lambda x: (-x[team], x['total']))
    tempOutput = []
    for i in range(0, len(sortedScouts)):
        tempOutput.append(sortedScouts[i]['id'])
    return(tempOutput)

#Create match schedule
def createSchedule(match):
    scheduled = {}
    
    #Generate priority lists
    priorityLists = {}
    for teamnumber in range(0, 6):
        priorityLists[match[teamnumber]] = priorityList(team=match[teamnumber])
    
    #Function for removing a scout from priority lists (once assigned)
    def removeFromPriority(scout):
        for team, list in priorityLists.items():
            while scout in priorityLists[team]:
                priorityLists[team].remove(scout)

    #Function for one cycle of assignments
    def assignScouts():
        #Generate lists of scout requests
        scoutRequests = []
        for i in range(0, len(scoutlist)):
            scoutRequests.append([])
        for team, list in priorityLists.items():
            if len(priorityLists[team]) > 0:
                scoutRequests[priorityLists[team][0]].append(team)
        
        #Iterate through scout requests (resolving conflicts when neccessary)
        for scoutRequestNumber in range(0, len(scoutRequests)):
            if len(scoutRequests[scoutRequestNumber]) == 1:
                #No conflict (scout requested by one team)
                scheduled[scoutRequests[scoutRequestNumber][0]] = scoutRequestNumber #Add to schedule
                priorityLists[scoutRequests[scoutRequestNumber][0]] = [] #Clear priority list for team
                removeFromPriority(scout=scoutRequestNumber) #Remove scout from priority lists (so cannot be selected for another team)
            elif len(scoutRequests[scoutRequestNumber]) > 1:
                #Conflict found (scout requested by multiple teams)
                #Resolved by comparing potential 'loss of experience' if each team used secondary scout
                comparisonData = []
                for i in range(0, len(scoutRequests[scoutRequestNumber])):
                    comparisonData.append(scoutRecords[priorityLists[scoutRequests[scoutRequestNumber][i]][0]][scoutRequests[scoutRequestNumber][i]] - scoutRecords[priorityLists[scoutRequests[scoutRequestNumber][i]][1]][scoutRequests[scoutRequestNumber][i]]) #Find difference between experience of primary and secondary scout
                maxid = 0
                for i in range(0, len(comparisonData)):
                    if comparisonData[i] > comparisonData[maxid]:
                        maxid = i
                scheduled[scoutRequests[scoutRequestNumber][maxid]] = scoutRequestNumber #Add to schedule
                priorityLists[scoutRequests[scoutRequestNumber][maxid]] = [] #Clear priority list for team
                removeFromPriority(scout=scoutRequestNumber) #Remove scout from priority lists (so cannot be selected for another team)
    
    #Run cycles of assignment until schedule created
    while len(scheduled) < 6:
        assignScouts()
    
    #Update scout records
    for team, scout in scheduled.items():
        scoutRecords[scout][team] += 1
        scoutRecords_clean[scout][team] += 1
        scoutRecords[scout]['total'] += 1

    return scheduled

#Create schedule for each match
schedule = []
for matchnumber in range(0, len(matchlist)):
    tempScheduleRaw = createSchedule(matchlist[matchnumber])
    tempSchedule = {}
    for team, scout in tempScheduleRaw.items():
        tempSchedule[int(team[3:])] = scout
    schedule.append(tempSchedule)

#Write scout records to database
if saveUpdatedRecords:
    for i in range(0, len(scoutlist)):
        cur.execute("DELETE FROM matchRecords WHERE scout=?", (scoutlist[i],))
    for scoutnumber in range(0, len(scoutRecords_clean)):
        for team, count in scoutRecords_clean[scoutnumber].items():
            if count > 0:
                cur.execute("INSERT INTO matchRecords(scout,team,count) VALUES (?,?,?)", (scoutlist[scoutnumber],team,count,))
    conn.commit()
    print("Wrote records to database.")

#Write output (create workbook)
workbook = xlsxwriter.Workbook(outputFile)
eventTitle = workbook.add_format({'bold': True, 'font_size': 18})
scoutTitle = workbook.add_format({'underline': True, 'font_size': 14})
headingLeft = workbook.add_format({'bold': True, 'align': 'left'})
headingRight = workbook.add_format({'bold': True, 'align': 'right'})
highlighted = workbook.add_format({'bg_color': 'yellow'})
underlined = workbook.add_format({'underline': True})
dayTitle = workbook.add_format({'underline': True, 'align': 'right'})

#Write output (primary scouts)
worksheet = workbook.add_worksheet("Primary Scouts")
worksheet.write(0, 0, "Team", headingRight)
worksheet.write(0, 1, "Primary", headingLeft)
worksheet.write(0, 2, "Secondary", headingLeft)
primaryScouts = {}
secondaryScouts = {}
for teamnumber in range(0, len(teamlist)):
    sortedScouts = sorted(scoutRecords, key=itemgetter(teamlist[teamnumber]), reverse=True)
    primaryScouts[int(teamlist[teamnumber][3:])] = scoutlist[sortedScouts[0]['id']]
    if sortedScouts[1][teamlist[teamnumber]] == 0:
        secondaryScouts[int(teamlist[teamnumber][3:])] = ""
    else:
        secondaryScouts[int(teamlist[teamnumber][3:])] = scoutlist[sortedScouts[1]['id']]
row = 0
for team in sorted(primaryScouts.keys()):
    row += 1
    worksheet.write(row, 0, team)
    worksheet.write(row, 1, primaryScouts[team])
    worksheet.write(row, 2, secondaryScouts[team])

#Write output (match schedule)
worksheet = workbook.add_worksheet("Matches")
worksheet.write(0, 0, "Match", headingRight)
column = -1
for alliance in ["B", "R"]:
    for i in range(1, 4):
        column += 2
        worksheet.write(0, column, alliance + str(i), headingRight)
        worksheet.write(0, column + 1, "Scout", headingLeft)
for matchnumber in range(0, len(matchlist)):
    worksheet.write(matchnumber + 1, 0, matchnumber + 1)
    for i in range(0, 6):
        worksheet.write(matchnumber + 1, (i * 2) + 1, int(matchlist[matchnumber][i][3:]), underlined)
        worksheet.write(matchnumber + 1, (i * 2) + 2, scoutlist[schedule[matchnumber][int(matchlist[matchnumber][i][3:])]])

#Write output (match schedule (long))
worksheet = workbook.add_worksheet("Matches_long")
worksheet.write(0, 0, "Team", headingRight)
worksheet.write(0, 1, "Match", headingRight)
worksheet.write(0, 2, "Alliance", headingRight)
teamsOutput = []
for matchnumber in range(0, len(matchlist)):
    for i in range(0, len(matchlist[matchnumber])):
        if i < 3:
            alliance = 1
        else:
            alliance = 0
        teamsOutput.append({"match": matchnumber + 1, "team": matchlist[matchnumber][i][3:], "alliance": alliance})
teamsOutput = sorted(teamsOutput, key=lambda x: (x['team'], x['match']))

for i in range(0, len(teamsOutput)):
    worksheet.write(i + 1, 0, int(teamsOutput[i]["team"]))
    worksheet.write(i + 1, 1, teamsOutput[i]["match"])
    worksheet.write(i + 1, 2, teamsOutput[i]["alliance"])

#Write output (scout schedules)
#Create long formatted (sort schedule)
scoutSchedules = {}
for i in range(0, len(scoutlist)):
    scoutSchedules[scoutlist[i]] = []
for matchnumber in range(0, len(schedule)):
    for team, scout in schedule[matchnumber].items():
        scoutSchedules[scoutlist[scout]].append({"match": matchnumber + 1, "team": team})
for scout, matches in scoutSchedules.items():
    scoutSchedules[scout] = sorted(scoutSchedules[scout], key=lambda x: (x['match'], x['team']))

#Generate schedules
for scout, matches in scoutSchedules.items():
    #Set up worksheet
    worksheet = workbook.add_worksheet("Schedule (" + scout + ")")
    worksheet.write(0, 0, "Scouting Schedule (" + eventFriendlyname + ")", eventTitle)
    worksheet.write(1, 0, scout, scoutTitle)
    worksheet.write(3, 0, "Match", headingRight)
    worksheet.write(3, 1, "Team", headingRight)
    
    #Write schedule
    notes = []
    i = -1
    lastDay = 1
    nextWrite = "match"
    matchnumber = 0
    while True:
        i += 1
        column = int(math.floor(i / 43) * 3)
        row = int((i - ((column / 3) * 43)) + 4)
        if matchlistDays[matches[matchnumber]["match"] - 1] > lastDay: #Need to add day title, skip line
            lastDay += 1
            nextWrite = "day"
        
        elif nextWrite == "day": #Add day title
            if row < 42:
                worksheet.write(row, column, "Day " + str(lastDay), dayTitle)
                nextWrite = "match"
        
        else: #Add match
            worksheet.write(row, column, matches[matchnumber]["match"])
            if primaryScouts[matches[matchnumber]["team"]] != scout:
                if not any(d['team'] == matches[matchnumber]["team"] for d in notes): #Add to notes if not already
                    notes.append({"scout": primaryScouts[matches[matchnumber]["team"]], "team": matches[matchnumber]["team"]})
                worksheet.write(row, column+1, matches[matchnumber]["team"], highlighted)
            else:
                worksheet.write(row, column+1, matches[matchnumber]["team"])
            matchnumber += 1
            if matchnumber >= len(matches):
                break

    #Add notes
    if len(notes) > 0:
        if (column / 3) == 2:
            startingColumn = column
            startingRow = row + 2
        else:
            startingColumn = column + 3
            startingRow = 3
        worksheet.write(startingRow, startingColumn, "Team", headingRight)
        worksheet.write(startingRow, startingColumn + 1, "Scout", headingLeft)
        notes = sorted(notes, key=itemgetter("team"))
        for i in range(0, len(notes)):
            worksheet.write(startingRow + i + 1, startingColumn, notes[i]["team"])
            worksheet.write(startingRow + i + 1, startingColumn + 1, notes[i]["scout"])

#Save workbook
workbook.close()
print("Wrote to output file '" + outputFile + "'")
