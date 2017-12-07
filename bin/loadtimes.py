import time as Time
from swimdb import Swim, TeamMeet, TeamSeason, Swimmer, toTime, Meet, seasonString, TeamStats, Improvement
import re
import os
import urlparse
from peewee import *
from events import badEventMap

urlparse.uses_netloc.append("postgres")
if "DATABASE_URL" in os.environ:  # production
	url = urlparse.urlparse(os.environ["DATABASE_URL"])
	db = PostgresqlDatabase(database=url.path[1:],
    	user=url.username,
    	password=url.password,
    	host=url.hostname,
    	port=url.port)
else:
	db = PostgresqlDatabase('swimdb', user='hallmank')

def getNewConfs():
	confTeams = {}
	with open('data/newconferences.txt', 'r') as file:
		for line in file:
			parts = re.split('\t', line.strip())
			division = parts[0]
			gender = parts[1]
			year = '20' + parts[2]
			conf = parts[3]
			team = parts[4]
			if not division in confTeams:
				confTeams[division] = {}
			if not gender in confTeams[division]:
				confTeams[division][gender] = {}
			if not year in confTeams[division][gender]:
				confTeams[division][gender][year] = {}
			if not conf in confTeams[division][gender][year]:
				confTeams[division][gender][year][team] = conf
	return confTeams

'''
load in new swim times
can load in to all SQL tables if params are true
'''
def load(loadMeets=False, loadTeams=False, loadSwimmers=False, loadSwims=False, loadTeamMeets=False, loadyear=15):
	swims = []
	swimmers = []
	swimmerKeys = set()
	newTeams = []
	teamKeys = set()
	meets = []
	meetKeys = set()
	teamMeets = []
	teamMeetKeys = set()
	swimKeys = set()
	root = 'data/20' + str(loadyear)

	for swimFileName in os.listdir(root):
		match = re.search('(\D+)(\d+)([mf])new', swimFileName)
		if not match:
			continue
		div, year, gender = match.groups()

		if not (int(year) == loadyear):
			continue
		#if not 'new' in swimFileName:
		#	continue

		confTeams = getNewConfs()

		with open(root + '/' + swimFileName) as swimFile:
			if div == 'DI':
				division = 'D1'
			elif div == 'DII':
				division = 'D2'
			elif div == 'DIII':
				division = 'D3'
			print division, swimFileName

			for idx, line in enumerate(swimFile):
				swimArray = re.split('\t', line)
				meet = swimArray[0].strip()
				d = swimArray[1]
				(season, swimDate) = seasonString(d)
				name = swimArray[2]
				year = swimArray[3]
				team = swimArray[4]
				gender = swimArray[5]
				event = swimArray[6]
				time = toTime(swimArray[7])

				if name == '&nbsp;':  # junk data
					continue

				if event in badEventMap:
					event = badEventMap[event]

				if season and swimDate and name and team and gender and event and time:
					pass
				else:  # missing some information
					print season, swimDate, name, year, team, gender, event, time
					continue

				try:
					conference = confTeams[division][gender][str(season)][team]
				except KeyError:
					conference = ''

				if 'Relay' in event: relay = True
				else: relay = False

				if relay:
					name = team + ' Relay'
					year = ''

				if loadTeams:
					key = str(season) + team + gender + division
					if not key in teamKeys:  # try each team once
						teamKeys.add(key)
						try:  # don't double add for teams not loaded yet
							teamID = TeamSeason.get(TeamSeason.season==season, TeamSeason.team==team,
										   TeamSeason.gender==gender, TeamSeason.division==division).id
						except TeamSeason.DoesNotExist:
							newTeam = {'season': season, 'conference': conference, 'team': team, 'gender':
								gender, 'division': division}
							newTeams.append(newTeam)

				if loadMeets:
					key = str(season) + meet + gender
					if not key in meetKeys:
						meetKeys.add(key)  # try each meet once
						try:  # don't double add for meets not loaded yet
							meetID = Meet.get(Meet.meet==meet, Meet.season==season, Meet.gender==gender).id
						except Meet.DoesNotExist:
							newMeet = {'season': season, 'gender': gender, 'meet': meet, 'date': swimDate}
							meets.append(newMeet)

				if loadSwimmers:
					teamID = TeamSeason.get(TeamSeason.season==season, TeamSeason.team==team,
										   TeamSeason.gender==gender, TeamSeason.division==division).id
					key = str(season) + name + str(teamID) + gender
					if not key in swimmerKeys:
						swimmerKeys.add(key)
						try:
							swimmerID = Swimmer.get(Swimmer.season==season, Swimmer.name==name, Swimmer.teamid==teamID,
													Swimmer.gender==gender).id
						except Swimmer.DoesNotExist:
							newSwimmer = {'season': season, 'name': name, 'year': year, 'team': team, 'gender':
								gender, 'teamid': teamID}
							swimmers.append(newSwimmer)

				if loadTeamMeets:
					key = str(season) + meet + gender + team
					if not key in teamMeetKeys:
						teamMeetKeys.add(key)
						meetID = Meet.get(Meet.meet==meet, Meet.season==season, Meet.gender==gender).id
						teamID = TeamSeason.get(TeamSeason.season==season, TeamSeason.team==team,
										   TeamSeason.gender==gender, TeamSeason.division==division).id
						try:
							teamMeetID = TeamMeet.get(TeamMeet.meet==meetID, TeamMeet.team==teamID).id
						except TeamMeet.DoesNotExist:
							newTeamMeet = {'meet': meetID, 'team': teamID}
							teamMeets.append(newTeamMeet)

				if loadSwims:
					key = name + event + str(time) + str(swimDate)
					if not key in swimKeys:
						swimKeys.add(key)
						try:
							Swim.get(Swim.name==name, Swim.time<time+.01, Swim.time > time-.01, Swim.event==event,
								Swim.date==swimDate)  # floats in SQL and python different precision
						except Swim.DoesNotExist:
							teamID = TeamSeason.get(TeamSeason.season==season, TeamSeason.team==team,
										   TeamSeason.gender==gender, TeamSeason.division==division).id
							swimmerID = Swimmer.get(Swimmer.name==name, Swimmer.teamid==teamID).id
							newSwim = {'meet': meet, 'date': swimDate, 'season': season, 'name': name, 'year': year, 'team': team,
					   			'gender': gender, 'event': event, 'time': time, 'conference': conference, 'division':
								division, 'relay': relay, 'swimmer': swimmerID}
							swims.append(newSwim)

						# incremental load
						if len(swims) > 1000:
							print 'Swims: ', len(swims)
							print Swim.insert_many(swims).execute()
							swims = []


	db.connect()

	if loadTeams and len(newTeams) > 0:
		print 'Teams:', len(newTeams)
		TeamSeason.insert_many(newTeams).execute()

	if loadMeets and len(meets) > 0:
		print 'Meets:', len(meets)
		Meet.insert_many(meets).execute()

	if loadSwimmers and len(swimmers) > 0:
		print 'Swimmers:', len(swimmers)
		Swimmer.insert_many(swimmers).execute()

	if loadTeamMeets and len(teamMeets) > 0:
		print 'Team Meets:', len(teamMeets)
		TeamMeet.insert_many(teamMeets).execute()

	#if loadSwims and len(swims) > 0:
	#	print 'Swims: ', len(swims)
	#	Swim.insert_many(swims).execute()

		#for i in range(len(swims) / 100):
		#	print i
		#	with db.transaction():
		#		print swims[i*100:(i+1)*100]
		#		Swim.insert_many(swims[i*100:(i+1)*100]).execute()
		#print 'Done!'

def deleteDups():
	# cleanup for duplicate swims
	print Swim.raw('DELETE FROM Swim WHERE id IN (SELECT id FROM (SELECT id, '
        'ROW_NUMBER() OVER (partition BY name, event, time, date ORDER BY id) AS rnum '
        'FROM Swim) t '
        'WHERE t.rnum > 1)').execute()

	'''
	print TeamStats.raw('DELETE FROM TeamStats WHERE id IN (SELECT id FROM (SELECT id, '
        'ROW_NUMBER() OVER (partition BY week, teamseasonid_id ORDER BY id) AS rnum '
        'FROM TeamStats) t '
        'WHERE t.rnum > 1)').execute()
    '''

'''
loads into tables in order
'''
def safeLoad(year=18):
	print 'loading teams...'
	load(loadTeams=True, loadyear=year)
	print 'loading meets and swimmers...'
	load(loadMeets=True, loadSwimmers=True, loadyear=year)
	print 'loading teamMeets and swims...'
	load(loadTeamMeets=True, loadSwims=True, loadyear=year)


'''
The following functions are all meant for data correction

merge: helper functions to merge two teams or swimmers into the same
fix: these go through existing data and clean up the various parts
'''
def mergeTeams(sourceTeamId, targetTeamId):
	sourceTeam = TeamSeason.get(id=sourceTeamId)
	targetTeam = TeamSeason.get(id=targetTeamId)

	# clear teamstats
	TeamStats.delete().where(TeamStats.teamseasonid==sourceTeam.id).execute()

	# find swimmers and update their info
	for swimmer in Swimmer.select().where(Swimmer.teamid==sourceTeam.id):
		swimmer.teamid = targetTeam.id
		swimmer.team = targetTeam.team
		swimmer.save()
		# update their swims
		for swim in Swim.select().where(Swim.swimmer==swimmer.id):
			swim.division = targetTeam.division
			swim.conference = targetTeam.conference
			swim.team = targetTeam.team
			swim.season = targetTeam.season
			if swim.relay: # change relay names
				swim.name = targetTeam.team + ' Relay'
			swim.save()

	# now switch the meet linking table
	for teammeet in TeamMeet.select().where(TeamMeet.team==sourceTeam.id):
		teammeet.team = targetTeam.id
		teammeet.save()

	TeamSeason.delete().where(TeamSeason.id==sourceTeamId).execute()

def mergeSwimmers(sourceSwimmerId, targetSwimmerId):
	sourceSwimmer = Swimmer.get(id=sourceSwimmerId)
	targetSwimmer = Swimmer.get(id=targetSwimmerId)
	targetTeam = TeamSeason.get(id=targetSwimmer.teamid)
	print targetTeam.team
	for swim in Swim.select().where(Swim.swimmer==sourceSwimmer):
		swim.team = targetTeam.team
		swim.division = targetTeam.division
		swim.conference = targetTeam.conference
		swim.season = targetTeam.season
		swim.swimmer = targetSwimmer.id
		swim.name = targetSwimmer.name
		try:
			print swim.name, swim.event, swim.time, swim.date
			Swim.get(name=swim.name, event=swim.event, date=swim.date)
			# should mean the swims already exist
			print 'delete', swim.id
			Swim.delete().where(Swim.id==swim.id).execute()
		except Swim.DoesNotExist:
			print 'move', swim.id
			swim.save()

	Swimmer.delete().where(Swimmer.id==sourceSwimmerId).execute()

def fixRelays():
	'''finds relays that are attached to non-relay swimmers'''
	count = 0
	for swim in Swim.select(Swim.name, Swim.id, Swim.relay, Swimmer.name, Swimmer.teamid, TeamSeason.team,
							TeamSeason.season, TeamSeason.team, TeamSeason.gender).join(
			Swimmer).join(TeamSeason).where(~Swimmer.name.endswith('Relay'), Swim.relay==True):
		print swim.id, swim.swimmer.name, swim.name, swim.swimmer.teamid.team, swim.swimmer.teamid.id
		try:
			relay = Swimmer.get(Swimmer.teamid==swim.swimmer.teamid.id, Swimmer.name.endswith('Relay'))
			if relay.name != swim.name:
				continue
			swim.swimmer = relay.id
			swim.save()
		except Swimmer.DoesNotExist:
			team = swim.swimmer.teamid
			name = team.team + ' Relay'
			relay = Swimmer.create(teamid=team.id, gender=team.gender, season=team.season, team=team.team, name=name)
			if relay.name != swim.name:
				continue
			swim.swimmer = relay.id
			swim.save()

		count +=1
		if count%1000==0: print count
	print count

	'''now fix ones with gender mismatch'''
	count = 0
	for swim in Swim.select().join(Swimmer).where(Swimmer.gender=='Men', Swim.gender=='Women'):
		count += 1
		try:
			newswimmer = Swimmer.get(Swimmer.season==swim.season, Swimmer.name==swim.name, Swimmer.team==swim.team,
							  Swimmer.gender==swim.gender)
			swim.swimmer = newswimmer.id
			swim.save()
		except Swimmer.DoesNotExist:
			try:
				team = TeamSeason.get(TeamSeason.season==swim.season, TeamSeason.gender==swim.gender,
							   TeamSeason.team==swim.team)
				n=Swimmer.create(teamid=team.id, gender=team.gender, season=team.season, team=team.team, name=swim.name)
				swim.swimmer = n.id
				swim.save()
			except TeamSeason.DoesNotExist:
				print swim.event, swim.name, swim.team, swim.season, swim.gender

	print count

def fixConfs():
	newConfs = getNewConfs()
	for team in TeamSeason.select().where(TeamSeason.season>2010):
		try:
			conf = newConfs[team.division][team.gender][str(team.season)][team.team]
			if conf != team.conference:
				print team.id, team.team, team.conference, conf
				team.conference = conf
				team.save()

				# now fix the swims
				for swim in Swim.select().join(Swimmer).join(TeamSeason).where(TeamSeason.id==team.id):
					if swim.conference != conf:
						swim.conference = conf
						swim.save()
						#print 'fixed swim'
		except:
			pass

def fixDupTeams():
	confTeams = getNewConfs()

	for team in TeamSeason.raw('SELECT id, team, conference, gender, division, season FROM '
							'(SELECT id, gender, team, division, conference, season, ROW_NUMBER() '
	 						'OVER (partition BY season, gender, team, division ORDER BY id) '
							'AS rnum FROM teamseason) t WHERE t.rnum > 1'):
		print team.id, team.team, team.conference, team.division
		try:
			conf = confTeams[team.division][team.gender][str(team.season)][team.team]
			print conf
			newTeam = TeamSeason.get(team=team.team, conference=conf, division=team.division,
						   gender=team.gender, season=team.season)
			if newTeam.id!=team.id:
				mergeTeams(team.id, newTeam.id)
		except KeyError:
			pass

def fixDivision():
	for swim in Swim.select(Swim, Swimmer, TeamSeason).join(Swimmer).join(TeamSeason).where(Swim.division!=
																	TeamSeason.division):
		try:
			newTeam = TeamSeason.get(team=swim.team, division=swim.division, season=swim.season, gender=swim.gender)
			if newTeam.id != swim.swimmer.teamid.id:
				print newTeam.team, newTeam.division, newTeam.season
			newSwimmer = Swimmer(name=swim.name, teamid=newTeam.id)
			print newSwimmer.name
			swim.swimmer = newSwimmer.id
			swim.save()
		except TeamSeason.DoesNotExist:
			pass

# allows for manual checking of swimmer names and guesses if they need to be merged
def fixDupSwimmers():
	for swim in Swim.raw('SELECT id, time, meet, event, season, gender, name, swimmer_id, team, year FROM '
							'(SELECT id, time, meet, event, season, gender, name, swimmer_id, team, year, ROW_NUMBER() '
	 						'OVER (partition BY time, meet, event, season, gender, team, year ORDER BY id) '
							'AS rnum FROM swim) s WHERE s.rnum > 1'):
		for swim2 in Swim.select().where(Swim.time==swim.time, Swim.meet==swim.meet, Swim.event==swim.event,
								Swim.season==swim.season, Swim.gender==swim.gender, Swim.team==swim.team):
			if swim.id==swim2.id:
				continue
			if swim.swimmer==swim2.swimmer:
				continue
			if not ',' in swim.name:
				print swim.name, swim.id
				continue
			if not ',' in swim2.name:
				print swim2.name, swim2.id
				continue
			first, last = re.split(',', swim.name)
			first2, last2 = re.split(',', swim2.name)
			if first==first2 or last==last2:
				print swim.id, swim.event, swim.time, swim.name, swim2.name, swim.swimmer.id, swim2.swimmer.id
				response = raw_input('Merge (y/n)?')
				if response=='y':
					try:
						mergeSwimmers(swim2.swimmer.id, swim.swimmer.id)  # higher id # coming later and is target
					except Swimmer.DoesNotExist: # already merged
						pass

def deleteDupImprovement():
	Improvement.raw('DELETE FROM Improvement WHERE id IN (SELECT id FROM (SELECT id, '
        'ROW_NUMBER() OVER (partition BY name, event, fromseason, team ORDER BY id) AS rnum '
        'FROM Improvement) i '
        'WHERE i.rnum > 1)').execute()

def uniqueSwimmers():
	for swimmer in Swimmer.raw('SELECT id, season, name, teamid_id, gender FROM '
						'(SELECT id, season, name, teamid_id, gender, ROW_NUMBER() '
	 					'OVER (partition BY season, name, teamid_id, gender ORDER BY id) '
						'AS rnum FROM swimmer) s WHERE s.rnum > 1'):
		print swimmer.name, swimmer.id, swimmer.season, swimmer.teamid, swimmer.gender
		for targetSwimmer in Swimmer.select().where(Swimmer.name==swimmer.name, Swimmer.season==swimmer.season,
									   Swimmer.teamid==swimmer.teamid, Swimmer.gender==swimmer.gender):
			if targetSwimmer.id != swimmer.id:
				try:
					mergeSwimmers(swimmer.id, targetSwimmer.id)
				except Swimmer.DoesNotExist:  # already merged
					pass
			#print targetSwimmer.name, targetSwimmer.id, targetSwimmer.season, targetSwimmer.team, targetSwimmer.gender

def fixMeetNames():
	for char in ['+', '@', '&']:
		searchStr = '%' + char + '%'
		for meet in Meet.select().where(Meet.meet % searchStr):
			print meet.meet
			if char == '+':
				newName = meet.meet.replace('+', ' ')
			elif char == '@':
				newName = meet.meet.replace('@', 'at')
			else:
				newName = meet.meet.replace('&', 'and')

			print newName
			Swim.update(meet=newName).where(Swim.meet==meet.meet).execute()

			meet.meet = newName
			meet.save()


if __name__ == '__main__':
	start = Time.time()
	#fixMeetNames()
	#uniqueSwimmers()
	#deleteDups()
	#fixDupSwimmers()
	safeLoad(year=18)
	#safeLoad(year=18)
	#deleteDupImprovement()
	#fixConfs()
	#fixDivision()
	#fixRelays()
	# migrateImprovement()
	# addRelaySwimmers()
	stop = Time.time()
	print stop - start