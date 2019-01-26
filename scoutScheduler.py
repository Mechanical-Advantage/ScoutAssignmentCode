import cv2
import os
import requests
import json
import tbapy
from operator import itemgetter
import sqlite3 as sql
from pathlib import Path
import xlsxwriter

#Config
TBAkey = "yZEr4WuQd0HVlm077zUI5OWPfYsVfyMkLtldwcMYL6SkkQag29zhsrWsoOZcpbSj"
scoutRecordsDatabase = "/Users/jonah/Documents/2019 Scout Scheduler/testDatabase.db"
saveUpdatedRecords = False
outputFile = "/Users/jonah/Documents/2019 Scout Scheduler/schedule.xlsx"


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

#Create match schedule
print("Fetching schedule...")
matchlistRaw = tba.event_matches(event)
if len(matchlistRaw) == 0:
    print("No schedule available.")
    quit()

matchlistUnsorted = {}
for i in range(0, len(matchlistRaw)):
    if matchlistRaw[i].comp_level == 'qm':
        matchlistUnsorted[matchlistRaw[i].match_number] = [matchlistRaw[i].alliances["blue"]["team_keys"][0], matchlistRaw[i].alliances["blue"]["team_keys"][1], matchlistRaw[i].alliances["blue"]["team_keys"][2], matchlistRaw[i].alliances["red"]["team_keys"][0], matchlistRaw[i].alliances["red"]["team_keys"][1], matchlistRaw[i].alliances["red"]["team_keys"][2]]

matchlist = []
for i in sorted(matchlistUnsorted.keys()):
    matchlist.append(matchlistUnsorted[i])

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

#Write output (scout schedules)
#Create array of dictionaries for each entry
longFormat = {}
for i in range(0, len(scoutlist)):
    longFormat[scoutlist[i]] = []
for matchnumber in range(0, len(schedule)):
    for team, scout in schedule[matchnumber].items():
        longFormat[scoutlist[scout]].append({"match": matchnumber + 1, "team": team})
for scout, matches in longFormat.items():
    longFormat[scout] = sorted(longFormat[scout], key=lambda x: (x['match'], x['team']))
    
#Save to file
for scout, matches in longFormat.items():
    worksheet = workbook.add_worksheet("Schedule (" + scout + ")")
    bold = workbook.add_format({'bold': True})
    worksheet.write(0, 0, scout, bold)
    worksheet.write(2, 0, "Match")
    worksheet.write(2, 1, "Team")
    for i in range(0, len(matches)):
        worksheet.write(i + 3, 0, matches[i]["match"])
        worksheet.write(i + 3, 1, matches[i]["team"])

#Write output (match schedule)
worksheet = workbook.add_worksheet("Matches")
worksheet.write(0, 0, "Match")
worksheet.write(0, 1, "B1")
worksheet.write(0, 2, "B2")
worksheet.write(0, 3, "B3")
worksheet.write(0, 4, "R1")
worksheet.write(0, 5, "R2")
worksheet.write(0, 6, "R3")
for matchnumber in range(0, len(matchlist)):
    worksheet.write(matchnumber + 1, 0, matchnumber + 1)
    for i in range(0, 6):
        worksheet.write(matchnumber + 1, i + 1, matchlist[matchnumber][i][3:])

#Write output (teams)
worksheet = workbook.add_worksheet("Teams")
worksheet.write(0, 0, "Team")
worksheet.write(0, 1, "Match")
worksheet.write(0, 2, "Alliance Color")
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
    worksheet.write(i + 1, 0, teamsOutput[i]["team"])
    worksheet.write(i + 1, 1, teamsOutput[i]["match"])
    worksheet.write(i + 1, 2, teamsOutput[i]["alliance"])

#Save workbook
workbook.close()
print("Wrote to output file '" + outputFile + "'")
