#!/usr/bin/swift

import Foundation
let key = "yZEr4WuQd0HVlm077zUI5OWPfYsVfyMkLtldwcMYL6SkkQag29zhsrWsoOZcpbSj"
let preferred6328scout: Int? = 0
let outputFile = "/Users/jonah/Desktop/schedule.csv"

func writeString(_ toWrite: String, to destination: String) {
    let url = URL(fileURLWithPath: destination)
    try! toWrite.data(using: .utf8)!.write(to: url, options: .atomic)
}

extension String {
    func toLengthOf(length:Int) -> String {
        if length <= 0 {
            return self
        } else if let to = self.index(self.startIndex, offsetBy: length, limitedBy: self.endIndex) {
            return self.substring(from: to)
            
        } else {
            return ""
        }
    }
}

func runShell(_ args: [String]) -> Data? {
    // Create a Task instance
    let task = Process()
    
    // Set the task parameters
    task.launchPath = "/usr/bin/env"
    task.arguments = args
    
    // Create a Pipe and make the task
    // put all the output there
    let pipe = Pipe()
    task.standardOutput = pipe
    
    // Launch the task
    task.launch()
    
    // Get the data
    let data = pipe.fileHandleForReading.readDataToEndOfFile()
    
    return(data)
}

func TBArequest(_ url: String) -> Data {
    return runShell(["curl", "-s", "-X", "GET", "https://www.thebluealliance.com/api/v3/" + url, "-H", "accept: application/json", "-H", "X-TBA-Auth-Key: " + key])!
}

//Determine event code
print("Enter year:")
let eventlistData = TBArequest("team/frc6328/events/" + readLine()! + "/simple")
let eventlistDataString = String(data: eventlistData, encoding: String.Encoding.utf8) as String!
if eventlistDataString!.range(of: "Invalid year") != nil {
    print()
    print("Invalid year")
    exit(0)
}
let eventlistRaw = try JSONSerialization.jsonObject(with: eventlistData) as! [[String: Any]]
let eventlistSorted = eventlistRaw.sorted(by: { $1["start_date"]! as! String > $0["start_date"]! as! String })

print()
if eventlistSorted.count == 0 {
    print("No events found.")
    exit(0)
}

var id = 0
print("Events:")
for event in eventlistSorted {
    id += 1
    print(String(id) + ") " + String(describing: event["name"]!))
}
print()
print("Which event?")
let eventId = Int(readLine()!)! - 1
let event = String(describing: eventlistSorted[eventId]["key"]!)
let eventName = String(describing: eventlistSorted[eventId]["name"]!)

//Get settings
print()
print("How many scouts?")
let scoutCount = Int(readLine()!)!
if scoutCount < 6 {
    print()
    print("Must have at least 6 scouts.")
    exit(0)
}

//Get match data
print("Creating schedule for " + String(scoutCount) + " scouts at event '" + eventName + "'")
print("Fetching match schedule...")
let data = TBArequest("event/" + event + "/matches/simple")

//Decode JSON
let matchlistRaw = try JSONSerialization.jsonObject(with: data) as! [[String: Any]]
if matchlistRaw.count == 0 {
    print()
    print("No schedule available.")
    exit(0)
}

//Create simple match list
var matchlistQuals: [[String: Any]] = []
for i in matchlistRaw {
    if i["comp_level"]! as! String == "qm" {
        matchlistQuals.append(i)
    }
}
matchlistQuals = matchlistQuals.sorted(by: { $1["match_number"]! as! Int > $0["match_number"]! as! Int })
var matchlist: [[String]] = []
for sourceMatch in matchlistQuals {
    var tempTeams: [String] = []
    let alliances = sourceMatch["alliances"]! as! [String: Any]
    let blueAlliance = alliances["blue"]! as! [String: Any]
    let blueAllianceTeams = blueAlliance["team_keys"]! as! [String]
    for team in blueAllianceTeams {
        tempTeams.append(team)
    }
    let redAlliance = alliances["red"]! as! [String: Any]
    let redAllianceTeams = redAlliance["team_keys"]! as! [String]
    for team in redAllianceTeams {
        tempTeams.append(team)
    }
    matchlist.append(tempTeams)
}

print("Assigning scouts...")

//Create team list
var teamlist: [String] = []
for match in matchlist {
    for team in match {
        if teamlist.contains(team) == false {
            teamlist.append(team)
        }
    }
}

//Create scout record array
var scoutRecords: [[String: Int]] = [[String: Int]](repeating: [:], count: scoutCount)
var currentId = 0
for scout in 0...scoutRecords.count - 1 {
    for team in teamlist {
        scoutRecords[scout][team] = 0
    }
    if preferred6328scout != nil {
        if preferred6328scout == currentId {
            scoutRecords[scout]["frc6328"] = 999
        }
    }
    scoutRecords[scout]["total"] = 0
    scoutRecords[scout]["id"] = currentId
    currentId += 1
}

//Create priority lists
func priorityList(for team: String) -> [Int] {
    let sortedScouts = scoutRecords.sorted(by:{
        if $0[team]! != $1[team]! {
            return $0[team]! > $1[team]!
        } else {
            return $0["total"]! < $1["total"]!
        }
    })
    var tempOutput: [Int] = []
    for i in sortedScouts {
        tempOutput.append(i["id"]!)
    }
    return tempOutput
}

//Create match schedule
func createSchedule(for match: [String]) -> [String: Int] {
    var priorityLists: [String: [Int]] = [:]
    for team in match {
        priorityLists[team] = priorityList(for: team)
    }
    var scheduled: [String: Int?] = [:]
    for team in match {
        scheduled[team] = nil
    }
    func assignScouts() {
        //Generate scout requests
        var scoutRequests: [[String]] = [[String]](repeating: [], count: scoutCount)
        for (team, _) in priorityLists {
            if priorityLists[team]!.count != 0 {
                scoutRequests[priorityLists[team]![0]].append(team)
            }
        }
        
        func removeFromPriority(_ scout: Int) {
            for (team, _) in priorityLists {
                if priorityLists[team]!.count > 0 {
                    let originalCount = priorityLists[team]!.count
                    for f in 1...originalCount {
                        if priorityLists[team]![originalCount - f] == scout {
                            priorityLists[team]!.remove(at: originalCount - f)
                        }
                    }
                }
            }
        }
        for i in 0...scoutRequests.count - 1 {
            if scoutRequests[i].count == 1 {
                scheduled[scoutRequests[i][0]] = i
                priorityLists[scoutRequests[i][0]] = []
                removeFromPriority(i)
            } else if scoutRequests[i].count > 1 {
                var comparisonData: [Int] = []
                for f in scoutRequests[i] {
                    comparisonData.append(scoutRecords[priorityLists[f]![0]][f]! - scoutRecords[priorityLists[f]![1]][f]!)
                }
                var maxid = 0
                for f in 0...comparisonData.count - 1 {
                    if comparisonData[f] > comparisonData[maxid] {
                        maxid = f
                    }
                }
                scheduled[scoutRequests[i][maxid]] = i
                priorityLists[scoutRequests[i][maxid]] = []
                removeFromPriority(i)
            }
        }
    }
    while scheduled.count < 6 {
        assignScouts()
    }
    for (team, scout) in scheduled {
        scoutRecords[scout!][team] = scoutRecords[scout!][team]! + 1
        scoutRecords[scout!]["total"] = scoutRecords[scout!]["total"]! + 1
    }
    var finalSchedule: [String: Int] = [:]
    for (team, scout) in scheduled {
        finalSchedule[team] = scout!
    }
    return finalSchedule
}

var schedule: [[String: Int]] = []
for match in matchlist {
    schedule.append(createSchedule(for: match))
}

//Write to output file
print("Saving to file '\(outputFile)'")
var tempOutput = "Match,Team1,Team2,Team3,Team4,Team5,Team6,Team1scout,Team2scout,Team3scout,Team4scout,Team5scout,Team6scout"
var matchNumber = 0
for match in schedule {
    matchNumber += 1
    var teams: [String] = []
    var scouts: [String] = []
    for (team, scout) in match {
        teams.append(team.toLengthOf(length: 3))
        scouts.append(String(scout + 1))
    }
    var fullList = teams + scouts
    var tempLine = "\n\(matchNumber),"
    for i in 0...fullList.count - 1 {
        tempLine = tempLine + fullList[i]
        if i != fullList.count - 1 {
            tempLine = tempLine + ","
        }
    }
    tempOutput = tempOutput + tempLine
}
writeString(tempOutput, to: outputFile)
print("Saved schedule.")

var matchnumber = 0
for match in schedule {
    matchnumber += 1
    for (team, scout) in match {
        if scout == 0 {
            print("M\(matchnumber): \(team)")
        }
    }
}
