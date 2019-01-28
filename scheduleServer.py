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
import cherrypy
import time
import random
import string

#Config
TBAkey = "yZEr4WuQd0HVlm077zUI5OWPfYsVfyMkLtldwcMYL6SkkQag29zhsrWsoOZcpbSj"
scoutRecordsDatabase = "testDatabase.db"
outputFile = "schedule.xlsx"
port = 8000
maxYear = 2019

#Initialize TBA connection
tba = tbapy.TBA(TBAkey)

#Database initializing code
def initDatabase():
    conn = sql.connect(scoutRecordsDatabase)
    cur = conn.cursor()
    cur.execute("DROP TABLE IF EXISTS matchRecords")
    cur.execute("""CREATE TABLE matchRecords (
        scout TEXT,
        team TEXT,
        count INTEGAR
        ); """)
    cur.execute("DROP TABLE IF EXISTS preferences")
    cur.execute("""CREATE TABLE preferences (
        team INTEGAR,
        scout TEXT
        ); """)
    cur.execute("DROP TABLE IF EXISTS scouts")
    cur.execute("""CREATE TABLE scouts (
        name TEXT,
        enabled INTEGAR
        ); """)
    cur.execute("DROP TABLE IF EXISTS event")
    cur.execute("""CREATE TABLE event (
        friendlyname TEXT,
        key TEXT,
        timestamp TEXT
        ); """)
    cur.execute("DROP TABLE IF EXISTS schedule")
    cur.execute("""CREATE TABLE schedule (
        match INTEGAR,
        B1 INTEGAR,
        B1_scout TEXT,
        B2 INTEGAR,
        B2_scout TEXT,
        B3 INTEGAR,
        B3_scout TEXT,
        R1 INTEGAR,
        R1_scout TEXT,
        R2 INTEGAR,
        R2_scout TEXT,
        R3 INTEGAR,
        R3_scout TEXT
        ); """)
    cur.execute("DROP TABLE IF EXISTS selection")
    cur.execute("""CREATE TABLE selection (
        year INTEGAR
        ); """)
    cur.execute("INSERT INTO event(friendlyname,key,timestamp) VALUES ('NA','NA','NA')")
    cur.execute("INSERT INTO selection(year) VALUES (2017)")
    conn.commit()
    conn.close()

#Check if database exists & create if doesn't exist
tempPath = Path(scoutRecordsDatabase)
if not tempPath.is_file():
    initDatabase()

def getSchedule(event, eventFriendlyname):
    #Connect to database
    conn = sql.connect(scoutRecordsDatabase)
    cur = conn.cursor()
    
    #Read records
    #Get scouts
    cur.execute("SELECT * FROM scouts")
    dbScouts = cur.fetchall()
    scoutlist = []
    for row in dbScouts:
        if row[1] == 1:
            scoutlist.append(row[0])

    #Get records
    scoutRecords = []
    scoutRecords_clean = []
    def createScoutRecords():
        for i in range(0, len(scoutlist)):
            scoutRecords.append({})
            scoutRecords_clean.append({})
    
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
        return("Error - needs 6 scouts")

    #Create match schedule
    matchlistRaw = tba.event_matches(event)
    if len(matchlistRaw) == 0:
        return("Error - no schedule available")

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
            scoutRecords[scoutlist.index(row[1])][fullTeam] = 99999

    #Create priority lists
    def priorityList(team):
        sortedScouts = sorted(scoutRecords, key=lambda x: (-x[team], x['total']))
        tempOutput = []
        for i in range(0, len(sortedScouts)):
            tempOutput.append(sortedScouts[i]['id'])
        return tempOutput

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
                if len(list) > 0:
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
    for i in range(0, len(scoutlist)):
        cur.execute("DELETE FROM matchRecords WHERE scout=?", (scoutlist[i],))
    for scoutnumber in range(0, len(scoutRecords_clean)):
        for team, count in scoutRecords_clean[scoutnumber].items():
            if count > 0:
                cur.execute("INSERT INTO matchRecords(scout,team,count) VALUES (?,?,?)", (scoutlist[scoutnumber],team,count,))

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
    worksheet.write(0, 3, "Primary %", headingLeft)
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
        
        #Find primary %
        scoutNumber = scoutlist.index(primaryScouts[team])
        scoutedMatches = 0
        totalMatches = 0
        for i in range(0, len(schedule)):
            for scheduleTeam, scheduleScout in schedule[i].items():
                if scheduleTeam == team:
                    totalMatches += 1
                    if scheduleScout == scoutNumber:
                        scoutedMatches += 1
        worksheet.write(row, 3, str(round((scoutedMatches/totalMatches)*100)) + "%")

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
            teamsOutput.append({"match": matchnumber + 1, "team": int(matchlist[matchnumber][i][3:]), "alliance": alliance})
    teamsOutput = sorted(teamsOutput, key=lambda x: (x['team'], x['match']))

    for i in range(0, len(teamsOutput)):
        worksheet.write(i + 1, 0, teamsOutput[i]["team"])
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

    #Update event table
    cur.execute("UPDATE event SET key=?", (event,))
    cur.execute("UPDATE event SET friendlyname=?", (eventFriendlyname,))
    cur.execute("UPDATE event SET timestamp=?", (time.ctime(),))

    #Close sqlite connection
    conn.commit()
    conn.close()
    return("Success")

def event(cur): #Get event data from database
    cur.execute("SELECT * FROM event")
    dbEvent = cur.fetchall()
    return {"friendlyname": dbEvent[0][0], "key": dbEvent[0][1], "timestamp": dbEvent[0][2]}

def selection(cur): #Get event data from database
    cur.execute("SELECT * FROM selection")
    DBevent = cur.fetchall()
    return {"year": DBevent[0][0]}

def scouts(cur): #Get scoutlist
    cur.execute("SELECT * FROM scouts")
    dbScouts = cur.fetchall()
    scoutlist = {}
    for row in dbScouts:
        scoutlist[row[0]] = row[1] == 1
    return(scoutlist)

def prefs(cur): #Get preferences
    cur.execute("SELECT * FROM preferences")
    dbPrefs = cur.fetchall()
    output = {}
    for row in dbPrefs:
        output[row[0]] = row[1]
    return output

#Server object
eventLookup = {}
resetKey = {}
class mainServer(object):
    @cherrypy.expose
    def index(self):
        conn = sql.connect(scoutRecordsDatabase)
        cur = conn.cursor()
        
        output = """
            <html><head><title>6328 Scout Schedule</title></head><body>
            <h1>6328 Scout Schedule ($event_friendlyname)</h1>
            <a href="/editScouts">Edit scouts</a><br><br>
            <a href="/editPrefs">Edit scout preferences</a><br><br>
            <a href="/create">Create schedule</a>
            
            </body></html>
            """
        output = output.replace("$event_friendlyname", event(cur)["friendlyname"])
        conn.close()
        return(output)

    @cherrypy.expose
    def editScouts(self):
        conn = sql.connect(scoutRecordsDatabase)
        cur = conn.cursor()
    
        output = """
            <html><head><title>Edit Scouts - 6328 Scout Schedule</title></head><body>
            <h1>6328 Scout Schedule ($event_friendlyname)</h1>
            <a href="/">< Return To Home</a><br><br>
            
            <b>Active Scouts:</b><br>
            $activeList_html
            
            <br><b>Disabled Scouts:</b><br>
            $disabledList_html
            
            <br><br><form method="post" action="/editScout_addScout">
            <input type="text", name="scout"><button type="submit">Add Scout</button>
            </form>
            
            <form method="post" action="/editScout_toggleScout">
            <input type="text", name="scout"><button type="submit">Toggle State</button>
            </form>
            
            <form method="post" action="/reset">
            <input type="text", name="key"><button type="submit">Reset Database</button>
            <br>
            Copy "$resetKey" to reset database<br><br>DO NOT reset database between events.
            </form>
            
            </body></html>
            """
    
        scoutlist = scouts(cur)
        activeList_html = ""
        disabledList_html = ""
        for scout, enabled in scoutlist.items():
            if enabled:
                activeList_html = activeList_html + scout + "<br>"
            else:
                disabledList_html = disabledList_html + scout + "<br>"
        
        output = output.replace("$activeList_html", activeList_html)
        output = output.replace("$disabledList_html", disabledList_html)
        output = output.replace("$event_friendlyname", event(cur)["friendlyname"])
        resetKey["key"] = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        output = output.replace("$resetKey", resetKey["key"])
        conn.close()
        return(output)

    @cherrypy.expose
    def editScout_toggleScout(self, scout=""):
        conn = sql.connect(scoutRecordsDatabase)
        cur = conn.cursor()
        scoutlist = scouts(cur)
        if scout in scoutlist:
            if scoutlist[scout]:
                newValue = 0
            else:
                newValue = 1
            cur.execute("UPDATE scouts SET enabled=? WHERE name=?", (newValue,scout))
            conn.commit()
        conn.close()
        return("""<meta http-equiv="refresh" content="0; url=/editScouts" />""")

    @cherrypy.expose
    def editScout_addScout(self, scout=""):
        conn = sql.connect(scoutRecordsDatabase)
        cur = conn.cursor()
        cur.execute("INSERT INTO scouts(name,enabled) VALUES (?,1)", (scout,))
        conn.commit()
        conn.close()
        return("""<meta http-equiv="refresh" content="0; url=/editScouts" />""")

    @cherrypy.expose
    def editPrefs(self):
        conn = sql.connect(scoutRecordsDatabase)
        cur = conn.cursor()
        
        output = """
            <html><head><title>Edit Scout Preferences - 6328 Scout Schedule</title></head><body>
            <h1>6328 Scout Schedule ($event_friendlyname)</h1>
            <a href="/">< Return To Home</a><br><br>
            
            <b>Preferences:</b><br>
            $prefsList_html
            
            <br><br><form method="post" action="/editPrefs_addPref">
            Team:<input type="text", name="team"> Scout:<input type="text", name="scout"><button type="submit">Add Preference</button>
            </form>
            
            <form method="post" action="/editPrefs_removePref">
            Team:<input type="text", name="team"><button type="submit">Remove Preference</button>
            </form>
            
            </body></html>
            """
        
        prefsList = prefs(cur)
        prefsList_html = ""
        for team, scout in prefsList.items():
            prefsList_html = prefsList_html + "Team " + str(team) + " -> " + scout + "<br>"
        
        output = output.replace("$prefsList_html", prefsList_html)
        output = output.replace("$event_friendlyname", event(cur)["friendlyname"])
        conn.close()
        return(output)

    @cherrypy.expose
    def editPrefs_addPref(self, team="0000", scout="testscout"):
        conn = sql.connect(scoutRecordsDatabase)
        cur = conn.cursor()
        cur.execute("INSERT INTO preferences(team,scout) VALUES (?,?)", (int(team), scout))
        conn.commit()
        conn.close()
        return("""<meta http-equiv="refresh" content="0; url=/editPrefs" />""")
    
    @cherrypy.expose
    def editPrefs_removePref(self, team="0000"):
        conn = sql.connect(scoutRecordsDatabase)
        cur = conn.cursor()
        cur.execute("DELETE FROM preferences WHERE team=?", (int(team),))
        conn.commit()
        conn.close()
        return("""<meta http-equiv="refresh" content="0; url=/editPrefs" />""")

    @cherrypy.expose
    def create(self):
        conn = sql.connect(scoutRecordsDatabase)
        cur = conn.cursor()
        
        output = """
            <html><head><title>Create Schedule - 6328 Scout Schedule</title></head><body>
            <h1>6328 Scout Schedule ($event_friendlyname)</h1>
            <a href="/">< Return To Home</a><br><br>
            
            <form method="post" action="/create_changeYear">
            <b>Year: </b><input type="text", name="year", value="$selection_year"><button type="submit">Get Events</button>
            </form>
            
            <form method="post" action="/create_generateSchedule">
            <b>Event: </b><select name="eventkey">$select_html</select><button type="submit">Create Schedule</button>
            </form>
            
            </body></html>
            """
        
        year = selection(cur)["year"]
        teamEventsRaw = tba.team_events('frc6328', year)
        teamEventsSorted = sorted(teamEventsRaw, key=itemgetter('start_date'))
        selectionHtml = ""
        for i in range(0, len(teamEventsSorted)):
            selectionHtml = selectionHtml + "<option value=\"" + teamEventsSorted[i].key + "\">" + teamEventsSorted[i].name + "</option>"
            eventLookup[teamEventsSorted[i].key] = teamEventsSorted[i].name
        
        output = output.replace("$select_html", selectionHtml)
        output = output.replace("$event_friendlyname", event(cur)["friendlyname"])
        output = output.replace("$selection_year", str(year))
        conn.close()
        return(output)

    @cherrypy.expose
    def create_changeYear(self, year=2017):
        if 2017 <= int(year) <= maxYear:
            conn = sql.connect(scoutRecordsDatabase)
            cur = conn.cursor()
            cur.execute("UPDATE selection SET year=?", (int(year),))
            conn.commit()
            conn.close()
        return("""<meta http-equiv="refresh" content="0; url=/create" />""")

    @cherrypy.expose
    def create_generateSchedule(self, eventkey="2017nhgrs"):
        result = getSchedule(event=eventkey, eventFriendlyname=eventLookup[eventkey])
        if result[:5] == "Error":
            output = """
                <html><head><title>Error - 6328 Scout Schedule</title></head><body>
                <a href="/create">< Return</a><br><br>$error
                </body></html>
                """
            output = output.replace("$error", result)
            return(output)
        return("""<meta http-equiv="refresh" content="0; url=/create" />""")

    @cherrypy.expose
    def reset(self, key="notthekey"):
        if key == resetKey["key"]:
            initDatabase()
        return("""<meta http-equiv="refresh" content="0; url=/editScouts" />""")

cherrypy.config.update({'server.socket_port': port})
cherrypy.quickstart(mainServer(), "/", {"/": {"log.access_file": "", "log.error_file": ""}})
