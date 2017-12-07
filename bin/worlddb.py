from peewee import *
import os
import re
import xml.etree.ElementTree as ET
from datetime import date as Date
import time as Time
import urlparse
from playhouse.migrate import *
import copy
from swimdb import swimTime
from scipy.stats import norm, skewnorm
import numpy as np
#import matplotlib.mlab as mlab
#import matplotlib.pyplot as plt

#  setup database
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

def timetohun(timeStr):
	parts = re.split('[:.]', timeStr)
	if len(parts) != 4:
		return None
	else:
		hun = int(parts[3])
		hun += int(parts[2]) * 100
		hun += int(parts[1]) * 100 * 60
		hun += int(parts[0]) * 100 * 60 * 60
	return hun
	#00:08:18.41

def rejectOutliers(dataX, dataY=None, l=5, r=6):
	u = np.mean(dataX)
	s = np.std(dataX)

	if dataY:
		data = zip(dataX, dataY)
		newList = [i for i in data if (u - l*s < i[0] < u + r*s)]
		newX, newY = zip(*newList)
		return list(newX), list(newY)
	else:
		newList = [i for i in dataX if (u - l*s < i < u + r*s)]
	#print swimTime(max(newList)), swimTime(min(newList))
	#print "Num rejected: " + str(len(dataX)-len(newList))
	return newList

'''used to find the the full CDF of times in a single event and a divsion, gender'''
def getSkewCDF(gender, event, course='LCM', percent=1.0):
	def makeCDF(a, mu, sigma, percent):  # returns a frozen truncated normal CDF
		def freezeCDF(x):
			rank = skewnorm.cdf(x, a, mu, sigma)
			if rank < percent:
				return (percent - rank) * (1 / percent)
			else:
				return 0
		return freezeCDF

	try:
		dist = Worldtimedist.get(gender=gender, event=event, course=course)
	except Worldtimedist.DoesNotExist:
		dist = saveSkewDist(gender, event, course)

	frozen = makeCDF(dist.a, dist.mu, dist.sigma, percent)
	return frozen


def getSkewDist(gender, event, course='LCM', getData=False):
	try:
		dist = Worldtimedist.get(gender=gender, event=event, course=course)
	except Worldtimedist.DoesNotExist:
		dist = saveSkewDist(gender, event, course)
	if dist:
		if getData:  # just return the object
			return dist
		frozen = skewnorm(dist.a, dist.mu, dist.sigma/2)
		return frozen
	return


def saveSkewDist(gender, event, course='LCM'):
	distance, stroke = re.split(' ', event)
	times = []
	for swim in Worldswim.select(Worldswim.time).join(Worldswimmer).where(Worldswimmer.gender==gender,
		Worldswim.stroke==stroke, Worldswim.distance==distance, Worldswim.course==course):
		times.append(swim.time / 100.0)

	print event, gender, course, len(times)

	times = rejectOutliers(times, l=4, r=2)
	# best fit of data
	(mu, sigma) = norm.fit(times)
	(a, mu, sigma) = skewnorm.fit(times, max(times) - mu, loc=mu, scale=sigma)
	frozen = skewnorm(a, mu, sigma)

	# the histogram of the data
	n, bins, patches = plt.hist(times, 60, normed=1)
	y = skewnorm.pdf(bins, a, mu, sigma)

	plt.plot(bins, y)
	plt.savefig("test.svg", format="svg")
	#plt.show()

	# save off the new dist
	newDist = Worldtimedist(gender=gender, course=course, event=event, a=a, mu=mu, sigma=sigma)
	newDist.save()

	return newDist


class Worldteam(Model):  # name="Azerbaijan" shortname="National Team" code="AZE" nation="AZE" type="NATIONALTEAM"
	name = CharField()
	shortname = CharField()
	code = CharField()
	nation = CharField()
	type = CharField()

	class Meta:
		database = db


class Worldswimmer(Model):  # <ATHLETE athleteid="108081" lastname="KIRILLOV" firstname="Boris" gender="M" birthdate="1992-08-04">
	team = ForeignKeyField(Worldteam)
	lastname = CharField()
	firstname = CharField()
	gender = CharField()
	birthdate = DateField()

	class Meta:
		database = db


class Worldswim(Model):  # <RESULT eventid="1" place="59" lane="10" heat="2" swimtime="00:01:06.79" points="588" reactiontime="+77">
	swimmer = ForeignKeyField(Worldswimmer)
	round = CharField()  # PRE, SOP, SEM, FIN, SOS
	course = CharField()
	distance = CharField()
	stroke = CharField()
	time = IntegerField()  # we will make this the time in ms to make comparisons easy
	meet = CharField()
	date = DateField()
	heat = IntegerField(null=True)
	lane = IntegerField(null=True)
	points = IntegerField(null=True)
	relay = BooleanField()
	reactiontime = IntegerField(null=True)
	place = IntegerField(null=True)

	class Meta:
		database = db

'''
store time distribution data
'''
class Worldtimedist(Model):
	event = CharField()
	gender = CharField()
	course = CharField()
	mu = FloatField()
	sigma = FloatField()
	a = FloatField(null=True)

	class Meta:
		database = db

def importSwims(loadSwims=False, loadSwimmers=False, loadTeams=False):
	# 9/1 starting date
	root = 'data/world'

	for fileName in os.listdir(root):
		if not 'xml' in fileName:
			continue

		tree = ET.parse(root + '/' + fileName)
		xmlroot = tree.getroot()
		meet = xmlroot.find('MEETS').find('MEET')
		meetName = meet.get('name')
		course = meet.get('course')
		print meetName

		# first parse out the event ids
		# <EVENT eventid="9" number="9" preveventid="-1" gender="F" round="PRE" daytime="0930" order="1">
        #                    <SWIMSTYLE distance="100" relaycount="1" stroke="BACK"/>
		dates = []
		events = {}
		for session in meet.find('SESSIONS').findall('SESSION'):
			date = session.get('date')
			dates.append(date)
			for event in session.find('EVENTS').findall('EVENT'):
				id = event.get('eventid')
				round = event.get('round')
				distance = event.find('SWIMSTYLE').get('distance')
				stroke = event.find('SWIMSTYLE').get('stroke')
				if event.find('SWIMSTYLE').get('relaycount') == '1':
					relay = False
				else:
					relay = True
				events[id] = {'round': round,
							  'distance': distance,
							  'stroke': stroke,
							  'relay': relay,
							  'date': date}

		for club in meet.find('CLUBS').findall('CLUB'):
			# <CLUB name="Albania" shortname="National Team" code="ALB" nation="ALB" type="NATIONALTEAM">
			name = club.get('name')
			nation = club.get('nation')
			type = club.get('type')
			code = club.get('code')
			shortname = club.get('shortname')

			print 'TEAM:', name, nation, type, code, shortname
			teamID = Worldteam.get_or_create(name=name, type=type, nation=nation, code=code,
											 shortname=shortname).id

			if club.find('ATHLETES') is None:  # I guess they didn't swim
				continue
			# <ATHLETE athleteid="101520" lastname="ALEKSI" firstname="Franci" gender="M" birthdate="1998-11-09">
			for athlete in club.find('ATHLETES').findall('ATHLETE'):
				lastname = athlete.get('lastname')
				firstname = athlete.get('firstname')
				birthdate = athlete.get('birthdate')
				gender = athlete.get('gender')

				print 'SWIMMER:', lastname, firstname, birthdate, gender
				swimmerID = Worldswimmer.get_or_create(lastname=lastname, firstname=firstname, birthdate=birthdate,
											  gender=gender, team=teamID).id

				# <RESULT eventid="13" place="67" lane="6" heat="2" swimtime="00:02:06.82" points="520" reactiontime="+63">
				if athlete.find('RESULTS') is None:  # I guess they didn't swim
					continue
				for swim in athlete.find('RESULTS').findall('RESULT'):
					eventid = swim.get('eventid')
					distance, stroke, relay, date, round = events[eventid]['distance'], events[eventid]['stroke'], \
										events[eventid]['relay'], events[eventid]['date'], events[eventid]['round']

					place = swim.get('place')
					lane = swim.get('lane')
					heat = swim.get('heat')
					try:
						time = timetohun(swim.get('swimtime'))  # time in ms
					except:
						continue
					if not time:
						continue
					points = swim.get('points')
					if swim.get('reactiontime'):
						reactiontime = int(swim.get('reactiontime'))
					else:
						reactiontime = None

					print 'SWIM:', distance, stroke, relay, date, round, place, lane, heat, time, points, reactiontime
					Worldswim.get_or_create(distance=distance, stroke=stroke, relay=relay, date=date, round=round,
											place=place, lane=lane, heat=heat, time=time, points=points,
											reactiontime=reactiontime, swimmer=swimmerID, course=course, meet=meetName)
			#relays
			#for athlete in club.find('ATHLETES').findall('ATHLETE'):



		#print swims, swimmers
		'''
		db.connect()
		if loadTeams and len(teams) > 0:
			print 'Teams:', len(teams)
			print Worldteam.insert_many(teams).execute()

		if loadSwimmers and len(swimmers) > 0:
			print 'Swimmers:', len(swimmers)
			print Worldswimmer.insert_many(swimmers).execute()

		if loadSwims and len(swims) > 0:
			print 'Swims:', len(swims)
			print Worldswim.insert_many(swims).execute()
		'''

def topstrokes():
	teams = {}
	total = 0
	for swim in Worldswim.select().where(Worldswim.round=='FIN').join(Worldswimmer).join(\
			Worldteam):
		#if int(swim.distance) > 200:
		#	distance = 'distance'
		#else:
		#	distance = swim.distance
		#if swim.swimmer.lastname=='MOROZOV':
		#	print swim.stroke, swim.time, swim.distance
		#else:
		#	continue
		country = swim.swimmer.team.nation
		if country not in ['DEN', 'SWE', 'NED', 'BRA', 'RSA']:
			continue

		if country not in teams:
			teams[country] = {'total': 0}
		name = swim.swimmer.firstname.lower() + ' ' + swim.swimmer.lastname.lower()
		if name not in teams[country]:
			teams[country][name] = 0
		teams[country][name] += 9 - swim.place
		teams[country]['total'] += 9 - swim.place
		#total += 9 - swim.place

	print teams

	for team in teams:
		if teams[team]['total'] > 1:
			outarr = ['0', '0', '0', '0']
			outarr[0] = team
			for place in teams[team]:
				pass
				'''
				if place==1:
					outarr[1] = str(int(teams[team][place]))
				elif place==2:
					outarr[2] = str(int(teams[team][place]))
				elif place==3:
					outarr[3] = str(int(teams[team][place]))
				'''
				'''
				if gender=='M':
					outarr[1] = str(int(teams[team][gender]))
				elif gender=='F':
					outarr[2] = str(int(teams[team][gender]))
				'''
				'''
				if distance=='50':
					outarr[1] = str(int(teams[team][distance]))
				elif distance=='100':
					outarr[2] = str(int(teams[team][distance]))
				elif distance=='200':
					outarr[3] = str(int(teams[team][distance]))
				elif distance=='distance':
					outarr[4] = str(int(teams[team][distance]))
				'''
				'''
				if stroke=='FLY':
					outarr[1] = str(int(teams[team][stroke]))
				if stroke=='BACK':
					outarr[2] = str(int(teams[team][stroke]))
				if stroke=='BREAST':
					outarr[3] = str(int(teams[team][stroke]))
				elif stroke=='MEDLEY':
					outarr[4] = str(int(teams[team][stroke]))
				elif stroke=='FREE':
					outarr[5] = str(int(teams[team][stroke]))
				'''
			outstr = ''
			for part in outarr:
				outstr += part + ','
			print outstr

	print total

def topRelay(team):
	topSwims = {'M': {}, 'F': {}}
	for swim in Worldswim.select().join(Worldswimmer).join(Worldteam).where(Worldteam.nation==team.nation,
					Worldswim.distance=='100', Worldswim.meet=='16th FINA WORLD CHAMPIONSHIPS'):
		#print swim.date
		name = swim.swimmer.firstname.lower() + ' ' + swim.swimmer.lastname.lower()
		#name = swim.swimmer.id
		gender = swim.swimmer.gender
		if swim.stroke not in topSwims[gender]:
			topSwims[gender][swim.stroke] = {}
		if name not in topSwims[gender][swim.stroke]:
			topSwims[gender][swim.stroke][name] = swim.time
		else:
			if topSwims[gender][swim.stroke][name] > swim.time:
				topSwims[gender][swim.stroke][name] = swim.time

	#print topSwims

	# ba, br, fl, fr
	# six gender combos
	strokes = ['BACK', 'BREAST', "FLY", 'FREE']
	eventcombos = [['M', 'M', 'F', 'F'],
				   ['M', 'F', 'M', 'F'],
				   ['M', 'F', 'F', 'M'],
				   ['F', 'M', 'M', 'F'],
				   ['F', 'M', 'F', 'M'],
				   ['F', 'F', 'M', 'M']]

	def optimizeRelay(genders, relay):
		if len(relay) == 4:
			return relay
		stroke = strokes[len(relay)]
		gender = genders[len(relay)]
		posrelays = []
		for swimmer in topSwims[gender][stroke]:
			if swimmer not in relay.keys():
				time = topSwims[gender][stroke][swimmer]
				tempRelay = copy.deepcopy(relay)
				tempRelay[swimmer] = time
				posrelays.append(optimizeRelay(genders, tempRelay))
		toptime = 100000
		toprelay = None
		for posrelay in posrelays:
			time = sum(posrelay.values())
			if time < toptime:
				toprelay = posrelay
				toptime = time
		return optimizeRelay(genders, toprelay)

	relays = []
	for combo in eventcombos:
		# first check to see if events were swum
		bad = False
		for idx, stroke in enumerate(strokes):
			gender = combo[idx]
			if gender not in topSwims:
				bad = True
			else:
				if stroke not in topSwims[gender]:
					bad = True
		if not bad:
			relays.append((optimizeRelay(combo, {}), combo))

	# now out of the gender combinations see which was best
	toprelay = None
	bestgenders = None
	for relay in relays:
		if not toprelay or sum(relay[0].values()) < sum(toprelay.values()):
			toprelay, bestgenders = relay

	if toprelay:
		print toprelay, swimTime(sum(toprelay.values())/ 100.0), bestgenders
		return toprelay, bestgenders
	else:
		return None, None


	#print topSwims

def eventDifferences():
	sampleSize = 100000
	strokeDifs = {'BACK': [], 'BREAST': [], 'FLY': [], 'FREE': []}
	for stroke in ['BACK', 'BREAST', 'FLY', 'FREE']:
		event = '100 ' + stroke
		distM = getSkewDist('M', event=event, course='LCM')
		menSwims = distM.rvs(size=sampleSize)
		#print stroke
		#print menSwims
		distW = getSkewDist('F', event=event, course='LCM')
		womenSwims = distW.rvs(size=sampleSize)
		#print womenSwims
		strokeDifs[stroke] = [timeM - womenSwims[idx] for idx, timeM in enumerate(menSwims)]

	menCount = {'BACK': 0, 'BREAST': 0, 'FLY': 0, 'FREE': 0}
	for idx in range(sampleSize):
		backDiff = strokeDifs['BACK'][idx]
		breastDiff = strokeDifs['BREAST'][idx]
		flyDiff = strokeDifs['FLY'][idx]
		freeDiff = strokeDifs['FREE'][idx]

		if backDiff > breastDiff and backDiff > flyDiff or backDiff > breastDiff and backDiff > freeDiff or backDiff \
				> freeDiff and backDiff > flyDiff:
			menCount['BACK'] += 1
		if breastDiff > backDiff and breastDiff > flyDiff or breastDiff > backDiff and breastDiff > freeDiff or breastDiff \
				> freeDiff and breastDiff > flyDiff:
			menCount['BREAST'] += 1
		if flyDiff > breastDiff and flyDiff > backDiff or flyDiff > breastDiff and flyDiff > freeDiff or flyDiff \
				> freeDiff and flyDiff > backDiff:
			menCount['FLY'] += 1
		if freeDiff > breastDiff and freeDiff > flyDiff or freeDiff > breastDiff and freeDiff > backDiff or freeDiff \
				> backDiff and freeDiff > flyDiff:
			menCount['FREE'] += 1

	print menCount







if __name__== '__main__':
	'''
	db.drop_tables([Worldswim])
	db.drop_tables([Worldswimmer])
	db.drop_tables([Worldteam])
	db.create_tables([Worldteam])
	db.create_tables([Worldswimmer])
	db.create_tables([Worldswim])
	'''
	#importSwims()

	#eventDifferences()
	saveSkewDist('F', '100 FREE')

	#topstrokes()
	'''
	allgenders = []
	for nation in ['USA','AUS','CHN','GBR','FRA','HUN','SWE','JPN','ITA','RSA','RUS','GER','NED','BRA','DEN','NZL']:
		team = Worldteam.get(nation=nation)
		print nation
		toprelay, genders = topRelay(team)
		if genders:
			allgenders.append(genders)

	gendercounts = [0 for i in range(len(allgenders[0]))]
	for genders in allgenders:
		for idx, gender in enumerate(genders):
			if gender == 'F':
				gendercounts[idx] += 1
	percentages = [i/float(len(allgenders)) for i in gendercounts]
	print percentages
	'''



