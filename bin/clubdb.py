from peewee import *
import os
import sys
import re
from datetime import date as Date
import time as Time
import urlparse
from playhouse.migrate import *
from swimdb import toTime, swimTime, Swim
from scipy.stats import norm, skewnorm, expon
import numpy as np
#import matplotlib.mlab as mlab
import matplotlib.pyplot as plt
from math import log
from sympy import binomial
import heapq
from events import eventsSCY, allEventsSCY, allevents, eventConvert, SCMfactor, eventtoSCY, eventsLCM

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

'''kills outliers from list greater than rsigma or less than lsigma'''
def rejectOutliers(dataX, dataY=None, l=5, r=6):
	u = np.mean(dataX)
	s = np.std(dataX)

	if dataY:
		data = zip(dataX, dataY)
		newList = [float(i) for i in data if (u - l*s < i[0] < u + r*s)]
		newX, newY = zip(*newList)
		return list(newX), list(newY)
	else:
		newList = [i for i in dataX if (u - l*s < i < u + r*s)]
	#print swimTime(max(newList)), swimTime(min(newList))
	#print "Num rejected: " + str(len(dataX)-len(newList))
	return newList


'''used to find the the full CDF of times in a single event and a divsion, gender'''
def getSkewCDF(gender, age, event, course='LCM', percent=1.0, year=None):
	def makeCDF(a, mu, sigma, percent):  # returns a frozen truncated normal CDF
		def freezeCDF(x):
			rank = skewnorm.cdf(x, a, mu, sigma)
			if rank < percent:
				return (percent - rank) * (1 / percent)
			else:
				return 0
		return freezeCDF

	try:
		if year:
			dist = Clubtimedist.get(gender=gender, age=age, event=event, course=course, year=year)
		else:
			dist = Clubtimedist.select().where(Clubtimedist.gender==gender, Clubtimedist.age==age,
				Clubtimedist.event==event, Clubtimedist.course==course, Clubtimedist.year.is_null()).get()
	except Clubtimedist.DoesNotExist:
		dist = saveSkewDist(gender, age, event, course, year=year)

	frozen = makeCDF(dist.a, dist.mu, dist.sigma, percent)
	return frozen


def getSkewDist(gender, age, event, course='LCM', getData=False, year=None):
	try:
		if year:
			dist = Clubtimedist.get(gender=gender, age=age, event=event, course=course, year=year)
		else:
			dist = Clubtimedist.select().where(Clubtimedist.gender==gender, Clubtimedist.age==age,
				Clubtimedist.event==event, Clubtimedist.course==course, Clubtimedist.year.is_null()).get()
	except Clubtimedist.DoesNotExist:
		dist = saveSkewDist(gender, age, event, course, year=year)
	if dist:
		if getData:  # just return the object
			return dist
		frozen = skewnorm(dist.a, dist.mu, dist.sigma)
		return frozen
	return


def saveSkewDist(gender, age, event, course='LCM', plot=False, year=None, getstats=False):
		age = int(age)
		times = []

		if course =='SCM':
			LCMdist = getSkewDist(gender, age, event, 'LCM', True)
			SCYdist = getSkewDist(gender, age, eventtoSCY[event], 'SCY', True)
			a = (LCMdist.a + SCYdist.a)/2 * SCMfactor[gender][event]
			mu = (LCMdist.mu + SCYdist.mu)/2 * SCMfactor[gender][event]
			sigma = (LCMdist.sigma + SCYdist.sigma)/2 * SCMfactor[gender][event]
			newDist = Clubtimedist(gender=gender, age=age, course=course, event=event, a=a, mu=mu, sigma=sigma,
								   year=year)
			newDist.save()
			return newDist

		# for the full dist (age 23) we will use all times older than 18
		if age < 23:
			if year:
				for swim in Clubswim.select(Clubswim.time).join(Clubswimmer).switch(Clubswim).join(Clubteam).where(
							Clubswimmer.gender==gender, Clubteam.season==year,
							Clubswim.event==event, Clubswimmer.age==age, Clubswim.course==course):
					times.append(swim.time / 100.0)
			else:
				for swim in Clubswim.select(Clubswim.time).join(Clubswimmer).where(Clubswimmer.gender==gender,
							Clubswim.event==event, Clubswimmer.age==age, Clubswim.course==course):
					times.append(swim.time / 100.0)
		else:
			if year:
				for swim in Clubswim.select(Clubswim.time).join(Clubswimmer).switch(Clubswim).join(Clubteam).where(
							Clubswimmer.gender==gender, Clubteam.season==year,
							Clubswim.event==event, Clubswimmer.age > 17, Clubswim.course==course):
					times.append(swim.time / 100.0)
			else:
				for swim in Clubswim.select(Clubswim.time).join(Clubswimmer).where(Clubswimmer.gender==gender,
					Clubswim.event==event, Clubswimmer.age > 17, Clubswim.course==course):
					times.append(swim.time / 100.0)

		print event, age, gender, course, len(times)

		if len(times) == 0:
			return

		if len(times) < 100:  # not enough data, go up and down a year
			for swim in Clubswim.select(Clubswim.time).join(Clubswimmer).where(Clubswimmer.gender==gender,
						Clubswim.event==event, Clubswimmer.age==age + 1, Clubswim.course==course):
					times.append(swim.time / 100.0)
			for swim in Clubswim.select(Clubswim.time).join(Clubswimmer).where(Clubswimmer.gender==gender,
						Clubswim.event==event, Clubswimmer.age==age - 1, Clubswim.course==course):
					times.append(swim.time / 100.0)

		print swimTime(min(times)), len(times)
		if getstats:
			return min(times), len(times)

		times = rejectOutliers(times, l=4, r=4)
		#times = [log(i) for i in times]

		# best fit of data
		(mu, sigma) = norm.fit(times)
		#print mu, sigma
		a = 5
		(a, mu, sigma) = skewnorm.fit(times, a, loc=mu, scale=sigma)
		#print mu, sigma, a
		loc, scale = expon.fit(times)
		print loc, scale

		if plot:  # the histogram of the data
			n, bins, patches = plt.hist(times, 60, normed=1)
			y = skewnorm.pdf(bins, a, mu, sigma)
			plt.plot(bins, y)
			#y = expon.pdf(bins, loc=loc, scale=scale)
			plt.plot(bins, y)
			plt.show()
			return
		newDist = Clubtimedist(gender=gender, age=age, course=course, event=event, a=a, mu=mu, sigma=sigma, year=year)
		newDist.save()
		return newDist


'''time conversion utility'''
def convert(gender, age, event, time, toage=None, fromCourse='LCM', toCourse='SCY'):
	if fromCourse==toCourse and age==toage:
		return time
	if not toage:
		toage = age

	# align events
	if fromCourse=='SCY' and (toCourse=='SCM' or toCourse=='LCM'):
		if event=='500 Free':
			toevent = '400 Free'
		elif event=='1650 Free':
			toevent = '1500 Free'
		else:
			toevent = event
	elif (fromCourse=='SCM' or fromCourse=='LCM') and toCourse=='SCY':
		if event == '400 Free':
			toevent = '500 Free'
		elif event == '1500 Free':
			toevent = '1650 Free'
		else:
			toevent = event
	else:
		toevent = event

	fromdist = getSkewDist(gender, age, event, fromCourse)
	todist = getSkewDist(gender, toage, toevent, toCourse)

	# find percentile rank of course time was done in
	percent = fromdist.sf(time)

	# convert using inverse survival function
	newtime = todist.isf(percent)

	# print time, round(newtime, 2)
	return newtime


class Clubteam(Model):  # one per season
	season = IntegerField()
	team = CharField()
	gender = CharField()
	#state = CharField()
	winnats = FloatField(null=True)
	strengthdual = FloatField(null=True)
	strengthinvite = FloatField(null=True)
	topSwimmers = {}

	class Meta:
		indexes = ((('season', 'team', 'gender'), True),)
		database = db

	def topTimes(self, dateStr=None, events=allEventsSCY):
		if not dateStr:
			meetDate = Date.today()
			dateStr = str(meetDate.year) + '-' + str(meetDate.month) + '-' + str(meetDate.day)

		newMeet = Clubmeet()
		for swim in Swim.raw("SELECT event, time, rank, name, meet, team, year FROM "
				"(SELECT swim.name, time, event, meet, ts.team, rank() "
				"OVER (PARTITION BY swim.name, event ORDER BY time) "
				"FROM (clubswim "
				"INNER JOIN clubteam ts "
				"ON team_id=ts.id and ts.id=%s) "
				"WHERE swim.date < %s) AS a "
				"WHERE a.rank=1", self.id, dateStr):
			swim.gender = self.gender
			swim.season = self.season
			if events:
				if swim.event in events:
					newMeet.addSwim(swim)
			else:
				newMeet.addSwim(swim)

		return newMeet

	def topTeamScore(self):
		events = eventsSCY
		topMeet = self.topTimes(events=events)

		topMeet.topEvents(teamMax=17, indMax=3)
		scores = topMeet.expectedScores(swimmers=16, division=self.division)

		if self.team in scores:
			return scores[self.team]
		return 0


class Clubswimmer(Model):
	name = CharField()
	gender = CharField()
	relay = BooleanField()
	age = IntegerField()
	team = CharField()
	ppts = IntegerField(null=True)
	eventppts = CharField(null=True)
	taperSwims = {}

	class Meta:
		indexes = ((('name', 'team', 'gender', 'age'), True),)
		database = db

	def similarSwimmers(self, limit=3, search=100, verbose=False, usePrevious=False):
		# make sure earlier and future ages exist
		previous = self.ageup(-1)
		if not previous:
			if verbose: print 'missing pre'
			return

		futureSelf = self.ageup()
		numSwims = len(self.getSwims())
		if not futureSelf or numSwims < 3:
			if verbose: print 'missing future'
			return

		if verbose:
			if usePrevious: print 'previous swims', previous.eventPoints()
			print 'current swims', self.eventPoints()

		totalDeltas = {}
		if verbose: print 'searching...'
		count = 0
		for s2 in Clubswimmer.select().where(Clubswimmer.gender==self.gender, Clubswimmer.age==self.age).order_by(
				fn.Random()).limit(search*3):  # same age and gender
			if count == search:
				break
			if s2.id==self.id:  # don't use own times, that's cheating
				continue

			future2 = s2.ageup()
			if not future2: continue
			count += 1
			totalDeltas[s2] = self.compare(s2)

			if usePrevious:
				previous2 = s2.ageup(-1)
				if not previous2: continue
				discountFactor = 2.0
				totalDeltas[s2] += previous.compare(previous2) / discountFactor

		# find who was the most similar, probably can keep running total
		totalSwimmers = 0
		totalEvents = 0
		events = {}
		for swimmer, value in sorted(totalDeltas.iteritems(), key=lambda (k, v): (v, k)):
			totalSwimmers += 1
			if totalSwimmers > limit:
				break
			tapers = swimmer.ageup().getTaperSwims()
			if verbose: print 'Comp' + str(totalSwimmers)
			for event in tapers:
				eventCourse = event + '-' + tapers[event].course
				if eventCourse not in events:
					events[eventCourse] = []
				events[eventCourse].append(tapers[event].time)
				totalEvents += 1

		# average out the times for the most similar swimmers
		predictedTapers = {}
		for eventCourse in events:
			time = np.mean(events[eventCourse])
			event, course = eventCourse.split('-')
			ppt = getPoints(event=event, age=self.age, gender=self.gender, time=time, course=course)
			std = np.std(events[eventCourse])
			percent = float(len(events[eventCourse]))/ float(totalEvents)
			predictedTapers[event] = {'time': time, 'std': std, 'ppts': ppt, 'percent': percent}

		futureTapers = futureSelf.getTaperSwims()
		tapers = self.getTaperSwims()

		if verbose:
			print 'swimmer1'
			for event in tapers:
				print event, tapers[event].time / 100.0, tapers[event].getPPTs()
			print 'next season'
			for event in futureTapers:
				print event, futureTapers[event].time / 100.0, futureTapers[event].getPPTs()
			print 'predictions'
			for event in predictedTapers:
				if event in futureTapers:
					print event, predictedTapers[event]['time'] / 100.0, predictedTapers[event]['ppts']

		return previous.getTaperSwims(), tapers, futureTapers, predictedTapers

	def stats(self, distNum=20, topNum=3):  # used to find if two swimmers are similar
		topSwims = self.topSwims(distNum)

		eventDist = {}
		for swim in topSwims:
			eventDist[swim.event] = eventDist.get(swim.event, 0) + 1

		avgPpt = 0
		for swim in topSwims[:topNum]:
			avgPpt += swim.getPPTs()
		avgPpt /= topNum

		return eventDist, avgPpt

	def topSwims(self, n=20, event=None, distinctEvents=True):
		times = []
		for swim in Clubswim.select().where(Clubswim.swimmer==self):
			swim.getPPTs(zscore=False)
			if swim.event=='1000 Yard Freestyle' or (swim.event =='200 Breast' and self.age < 11):
				continue
			times.append(swim)

		times.sort(key=lambda x: x.powerpoints, reverse=True)

		if distinctEvents:  # find the top n events
			topTimes = []
			events = set()
			for swim in times:
				if swim.event in events:
					continue
				events.add(swim.event)
				topTimes.append(swim)
				if len(topTimes) == n: break

		topTimes = times[:n]
		if event:
			topTimes = [time for time in topTimes if time.event==event]

		return topTimes

	# gives top event powerpoints and caches them, courses are lumped together
	def eventPoints(self):
		if self.eventppts:
			swims = {}
			parts = re.split(',', self.eventppts)
			for part in parts:
				event, points = re.split(':', part)
				swims[event] = int(points)
			return swims

		swims = {}
		for swim in self.topSwims():
			if swim.event not in swims:
				swims[swim.event] = 0
			swims[swim.event] += int(swim.powerpoints)

		pptstr = ''
		for event in swims:
			pptstr += event + ':' + str(swims[event]) + ','
		self.eventppts = pptstr[:-1]  # save as hashed string and remove trailing comma
		if len(self.eventppts) < 255:
			self.save()
		return swims

	def getTaperSwims(self, num=3):
		taperSwims = {}
		times = []

		for swim in Clubswim.raw("WITH topTimes as "
			"(SELECT name, gender, meet, event, time, age, course, swimmer_id, row_number() OVER "
			"(PARTITION BY event, name ORDER BY time) as rnum "
			"FROM Clubswim, Clubswimmer WHERE swimmer_id=%s and Clubswimmer.id=%s) "
			"SELECT name, gender, meet, event, time, age, course, swimmer_id FROM topTimes WHERE rnum=1",
			self.id, self.id):
			if swim.event == '1000 Yard Freestyle' or 'Relay' in swim.event or \
				((swim.event == '200 Breast' or swim.event == '200 Fly' or swim.event == '200 Back') and
						 self.age < 11):
				continue
			points = swim.getPPTs(save=False)
			heapq.heappush(times, (points, swim))

		for (points, swim) in heapq.nlargest(num, times):  # take three best times
			taperSwims[swim.event] = swim

		return taperSwims

	def getPPTs(self):
		if self.ppts:
			return self.ppts

		totalPPts = 0
		taperSwims = self.getTaperSwims()
		for event in taperSwims:
			totalPPts += taperSwims[event].getPPTs()

		self.ppts = totalPPts
		self.save()

		return totalPPts

	def ageup(self, years=1):
		try:
			return Clubswimmer.get(team=self.team, gender=self.gender, name=self.name, age=self.age + years)
		except Clubswimmer.DoesNotExist:
			return

	def compare(self, swimmer2, countNulls=True):
		swims1 = self.eventPoints()
		swims2 = swimmer2.eventPoints()

		delta = 0
		events = set(swims1.keys()) | set(swims2.keys())
		for event in events:
			if event in swims1 and event in swims2:
				delta += (swims1[event] - swims2[event]) ** 2
			elif event in swims1:
				delta += swims1[event] ** 2
			elif event in swims2:
				delta += swims2[event] ** 2

		if countNulls:  # assume a standard distance of 250 ppts for events not in common
			for event in set(swims1.keys()) - set(swims2.keys()):
				delta += 100 ** 2
		return delta ** .5

	def getSwims(self):
		swims = []
		for swim in Clubswim.select().where(Clubswim.swimmer==self.id):
			swims.append(swim)
		return swims



class Clubswim(Model):
	swimmer = ForeignKeyField(Clubswimmer)
	team = ForeignKeyField(Clubteam)
	course = CharField()
	event = CharField()
	date = DateField()
	time = IntegerField()  # we will make this the time in ms to make comparisons easy
	meet = CharField()
	powerpoints = IntegerField(null=True)
	place = None
	score = None
	scoreTeam = None
	scoreTime = None
	split = False
	pastTimes = []
	taperTime = None

	class Meta:
		indexes = ((('time', 'event', 'date', 'swimmer', 'team'), True),)
		database = db

	def getPPTs(self, zscore=True, save=False):
		if self.powerpoints:
			return self.powerpoints

		if not self.swimmer.gender or not self.event or not self.time:
			return None

		cdf = getSkewCDF(self.swimmer.gender, self.swimmer.age, self.event, self.course)
		percent = 1 - cdf(self.time/100)
		if percent==0 or not percent:
			print self.time, self.event, self.id
			self.powerpoints = 0
			if save:
				self.save()
			return self.powerpoints
		percentileScore = (1 - percent) * 500
		powerScore = 1 / percent
		if zscore:
			zscore = log(powerScore) * 50  # approximately the number of stds away from the means
		else:
			zscore = 0

		self.powerpoints = percentileScore + zscore
		if save:
			self.save()
		return round(self.powerpoints, 3)

	def expectedPoints(self, numSwimmers=6, losses=0, percent=None):
		scoresR = None
		if numSwimmers == 24:
			scores = [32, 28, 27, 26, 25, 24, 23, 22, 20, 17, 16, 15, 14, 13, 12, 11, 9, 7, 6, 5, 4, 3, 2, 1]
		elif numSwimmers == 16:
			scores = [20, 17, 16, 15, 14, 13, 12, 11, 9, 7, 6, 5, 4, 3, 2, 1]
		elif numSwimmers == 12:
			scores = [15, 13, 12, 11, 10, 9, 7, 5, 4, 3, 2, 1]
		else:
			# enforce max scores per team in dual format
			if not 'Relay' in self.event:
				if losses > 2:
					return 0
			else:
				if losses < 1:
					return 0
			scores = [9, 4, 3, 2, 1]
			scoresR = [11, 4, 2]

		if 'Relay' in self.event:
			if scoresR:
				scores = scoresR
			else:
				scores = [x*2 for x in scores]

		scores = scores[losses:]  # people who you know you will lose to
		totalScore = 0

		if not percent:  # now we will do a combined national, conference, and full level scoring
			percents = [.01, .2, 1.0]
		else:
			percents = [percent]

		for percent in percents:
			cdf = getSkewCDF(self.gender, self.age, self.course, self.event, percent=percent)
			win = cdf(self.getScoreTime())
			lose = 1 - win
			num = numSwimmers - losses - 1  # other swimmers

			for place, score in enumerate(scores[losses:]):
				comb = binomial(num, place)
				totalScore += score * comb * (lose**place * win**(num -place))

		return totalScore / len(percents)


class Clubmeet:
	def __init__(self, topSwim=True):
		self.teams = set()  # teams added as swims are
		self.topSwim = topSwim
		self.scores = None
		self.swims = {}
		self.season = None
		self.winMatrix = None
		self.ageGroups = {'8-': [7, 8], '9-10': [9, 10], '11-12': [11, 12], '13-14': [13, 14], '15-16': [15, 16],
						  '17-18': [17, 18], '19+': [19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30]}
		self.ageGroupMap = {}
		for age in range(6, 30):
			if age < 9:
				self.ageGroupMap[age] = '8-'
			elif age < 11:
				self.ageGroupMap[age] = '9-10'
			elif age < 13:
				self.ageGroupMap[age] = '11-12'
			elif age < 15:
				self.ageGroupMap[age] = '13-14'
			elif age < 17:
				self.ageGroupMap[age] = '15-16'
			elif age < 19:
				self.ageGroupMap[age] = '17-18'
			else:
				self.ageGroupMap[age] = '19+'

	def reset(self, teams=False, times=False):
		for swim in self.getSwims():
			if teams:
				swim.scoreTeam = None
			if times:
				swim.scoreTime = None

	def getSwims(self, team='all', relays=True, ind=True):
		for age in self.swims:
			for event in self.swims[age]:
				for swim in self.swims[age][event]:
					if ind and (swim.team == str(team) or team=='all') and (relays or not swim.relay):
						yield swim

	def addSwim(self, swim):
		if not swim.getScoreTeam() in self.teams:
			self.teams.add(swim.getScoreTeam())

		if swim.swimmer.age not in self.swims:
			self.swims[swim.swimmer.age] = {}
		if swim.event not in self.swims[swim.swimmer.age]:
			self.swims[swim.swimmer.age][swim.event] = []
		self.swims[swim.swimmer.age][swim.event].append(swim)

	def addSwims(self, swims):
		for swim in swims:
			self.addSwim(swim)

	'''
	decides top events for each swimmer
	top swimmers are decided by highest scoring event right now
	'''
	def topEvents(self, teamMax=17, indMax=3, adjEvents=False, debug=False):
		self.place()
		conference = Clubmeet()
		indSwims = {}
		teamSwimmers = {}
		teamDivers = {}
		drops = []
		relayEvents = set()
		events = self.eventSwims.keys()
		for team in self.teams:
			teamSwimmers[team] = 0
			teamDivers[team] = 0

		for event in self.eventSwims:  # we will keep relays as is, but count them towards total swims
			if re.search('Relay', event):
				relayEvents.add(event)
				while not self.eventSwims[event] == []:  # move relays over to new meet
					relay = self.eventSwims[event].pop()
					conference.addSwim(relay)

		for event in relayEvents:
			events.remove(event)

		# pare down
		self.place()
		for event in self.eventSwims:
			if len(self.eventSwims[event]) > 100:
				self.eventSwims[event] = self.eventSwims[event][:99]  # start with top 100 times

		# now make sure that each person swims their top events
		preEvent = None
		nextEvent = None
		if debug: print self
		while not self.isEmpty():
			for event in events:
				if 'Relay' in event:  # shouldn't
					continue
				drop = True  # just allow us to enter the loop
				while drop and not self.eventSwims[event] == []:  # we need to loop on an event until we find
					drop = False
					# print self.eventSwims[event]

					if self.events and type(self.events) == type([]) and event in self.events:
						if not self.events.index(event) == 0:
							preEvent = self.events[self.events.index(event)-1]
						if not self.events.index(event)==len(self.events)-1:
							nextEvent = self.events[self.events.index(event)+1]

					newSwim = self.eventSwims[event].pop(0)

					if preEvent in conference.eventSwims and not adjEvents:  # check to make sure no adjacent events
						for swim in conference.eventSwims[preEvent]:
							if newSwim.name == swim.name and newSwim.getScoreTeam() == swim.getScoreTeam():
								drops.append(newSwim)
								drop = True
								if debug: print 'pre', swim.name, swim.event
								if debug: print 'pre', newSwim.name, newSwim.event
								break
					if nextEvent in conference.eventSwims and not adjEvents:
						for swim in conference.eventSwims[nextEvent]:
							if newSwim.name == swim.name and newSwim.getScoreTeam() == swim.getScoreTeam():
								drop = True
								drops.append(newSwim)
								if debug: print 'post', swim.name, swim.event
								if debug: print 'post', newSwim.name, newSwim.event
								break
					if drop:  # already swimming previous or next event
						continue

					if not newSwim.name+newSwim.getScoreTeam() in indSwims:   # team max events
						if teamSwimmers[newSwim.getScoreTeam()] < teamMax:
							indSwims[newSwim.name + newSwim.getScoreTeam()] = 0  # count same person on two teams
							# differently
							teamSwimmers[newSwim.getScoreTeam()] += 1
						else:
							if debug: print 'team', swim.name, swim.event
							if debug: print 'team', newSwim.name, newSwim.event
							drops.append(newSwim)
							continue # fixed to still add swim when all 18

					if indSwims[newSwim.name + newSwim.getScoreTeam()] < indMax:  # individual max events
						conference.addSwim(newSwim)
						indSwims[newSwim.name + newSwim.getScoreTeam()] += 1
					else:
						if debug: print 'ind', swim.name, swim.event
						if debug: print 'ind', newSwim.name, newSwim.event
						drops.append(newSwim)
						drop = True  # can't swim any more events

		self.score()


		if debug:
			print teamSwimmers, indSwims, teamMax, indMax
			for swim in drops:
				print swim.name, swim.event, swim.getScoreTeam(), swim.time
		self.eventSwims = conference.eventSwims
		return drops

	def expectedScores(self, division='D3', swimmers=6, debug=False):
		self.place()
		scores = {}
		teamSwims = {}

		for event in self.eventSwims:
			teamSwims[event] = {}
			for swim in self.eventSwims[event]:
				if not swim.team in scores:
					scores[swim.team] = 0
				if not swim.team in teamSwims[event]:
					teamSwims[event][swim.team] = 0
				else:
					teamSwims[event][swim.team] += 1

				losses = teamSwims[event][swim.team]
				swim.division = division
				points = swim.expectedPoints(numSwimmers=swimmers, losses=losses)
				swim.score = points
				if points:
					scores[swim.team] += points
				if debug: print swim.event, swim.time, points, int(round(scores[swim.team])), losses

		for team in scores:
			scores[team] = int(round(scores[team]))

		return scores

	def place(self, events='', storePlace=False):
		events = self.getEvents(events)
		for event in events:
			if not event in self.eventSwims or len(self.eventSwims[event]) == 0:
				continue
			self.eventSwims[event] = sorted(self.eventSwims[event], key=lambda s:s.getScoreTime(), reverse=False)
			if storePlace:
				for idx, swim in enumerate(self.eventSwims[event]):
					swim.place = idx + 1

	def score(self, dual=None, events='', heatSize=8):
		events = self.getEvents(events)
		self.place(events)
		self.assignPoints(heats=self.heats, heatSize=heatSize, dual=dual, events=events)

		return self.teamScores(events)

	'''
	assigns points to the swims
	'''
	def assignPoints(self, heats=2, heatSize=8, dual=None, events=None):
		if dual is None:
			if len(self.teams)==2:
				dual=True
			else:
				dual=False

		max = 16
		if heats == 3:
			pointsI = [32, 28, 27, 26, 25, 24, 23, 22, 20, 17, 16, 15, 14, 13, 12, 11, 9, 7, 6, 5, 4, 3, 2, 1]
		elif heats == 2:
			pointsI = [20, 17, 16, 15, 14, 13, 12, 11, 9, 7, 6, 5, 4, 3, 2, 1]
		if heatSize == 6:
			pointsI = [15, 13, 12, 11, 10, 9, 7, 5, 4, 3, 2, 1]

		pointsR = [x*2 for x in pointsI]
		if dual:
			max = 3
			pointsI = [9, 4, 3, 2, 1]
			pointsR = [11, 4, 2]

		for event in self.eventSwims:  # Assign scores to the swims
			if not event in events and self.eventSwims[event]:  # set score of those not being swum to zero
				for swim in self.eventSwims[event]:
					swim.score = 0
			else:
				place = 1
				teamSwims = {}
				for swim in self.eventSwims[event]:
					swim.score = None  # reset score
					if not 'Relay' in swim.event:  # should use real relay var
						team = swim.getScoreTeam()
						if place > len(pointsI) or (team in teamSwims) and teamSwims[team] >= max:
							swim.score = 0
						else:
							swim.score = pointsI[place-1]
							if not team in teamSwims:
								teamSwims[team] = 0
							teamSwims[team] += 1
							place += 1
					else:
						team = swim.getScoreTeam()
						if place > len(pointsR) or (team in teamSwims) and teamSwims[team] >= max:
							swim.score = 0
						else:
							swim.score = pointsR[place-1]
							if not team in teamSwims:
								teamSwims[team] = 0
							teamSwims[team] += 1
							place += 1

	def scoreMonteCarlo(self, dual=None, events='', heatSize=8, heats=2, sigma=.02, runs=500, teamSigma=.02,
						weeksOut=4, taper=False):
		# need to include taper by teams
		weeksIn = 16 - weeksOut
		if taper:
			self.taper(weeksIn)
		# default the sigma if we just know the date
		if weeksOut == -1:
			sigma = 0.045
			teamSigma = .02
		elif weeksOut <= 4:
			teamSigma = .01
			sigma = 0.025
		elif weeksOut <= 8:
			teamSigma = .015
			sigma = 0.035
		elif weeksOut <= 12:
			teamSigma = 0.015
			sigma = 0.0425
		elif weeksOut <= 16:
			teamSigma = 0.025
			sigma = 0.045
		elif weeksOut > 16:
			teamSigma = .0325
			sigma = 0.0375

		events = self.getEvents(events)
		# print teamSigma, sigma, weeksOut

		for event in self.eventSwims:  # assign scores to the swims
			if not event in events and self.eventSwims[event]:  # set score of those not being swum to zero
				for swim in self.eventSwims[event]:
					swim.score = 0

		teamScoresDist = []
		for iternation in range(runs):  # run runs # of times

			teamTapers = {}  # team noise
			for team in self.teams:
				teamTapers[team] = np.random.normal(0, teamSigma)
			for event in self.eventSwims:  # individual swim noise
				for swim in self.eventSwims[event]:
					if swim.time:
						noise = np.random.normal(0, sigma) * swim.getTaperTime()
						teamNoise = teamTapers[swim.team] * swim.getTaperTime()
						swim.scoreTime = swim.getTaperTime() + noise + teamNoise

			# place again
			self.place(events)

			# now score
			self.assignPoints(dual=dual, heats=heats, heatSize=heatSize, events=events)

			teamScoresDist.append(self.teamScores(events))
		self.reset(times=True)  # reset the times to normal

		places = {}  # stores the number of times each team was 1st, 2nd, ect.
		for score in teamScoresDist:
			for idx, (team, score) in enumerate(score):
				if not team in places:
					places[team] = []
				places[team].append(idx)
		# print places

		probMatrix = {}
		for team in places:
			probMatrix[team] = [0 for _ in range(len(places))]
			for place in places[team]:
				probMatrix[team][place] += 1.0/len(places[team])  # add in each individual result

		winMatrix = {}
		for team in probMatrix:
			winMatrix[team] = probMatrix[team][0]

		self.winMatrix = winMatrix
		return probMatrix

	def getTeamWinProb(self, team):
		if not self.winMatrix:
			self.scoreMonteCarlo(dual=False)
		if not team in self.winMatrix:
			return None
		return self.winMatrix[team]

	def getWinProb(self):
		if not self.winMatrix:
			self.scoreMonteCarlo(dual=False)
		return self.winMatrix

	def teamScores(self, events=None, sorted=True):
		if not events:
			events = allEventsSCY
		teams = {}

		for team in self.teams:  # make sure all the teams get some score
			teams[team] = 0

		for event in events:
			if not event in self.eventSwims: continue
			for swim in self.eventSwims[event]:
				team = swim.getScoreTeam()
				if not team in teams:
					teams[team] = 0
				teams[team] += swim.getScore()
		self.scores = teams

		if not sorted:
			return teams

		#now sort
		scores = []
		for team in teams:
			scores.append([team, teams[team]])
		scores.sort(key=lambda t: t[1], reverse=True)

		return scores

	def getTeamScore(self, team):
		if not self.scores:
			self.teamScores()
		if not team in self.scores:
			return None
		return self.scores[team]

	def getScores(self):
		if not self.scores:
			return self.teamScores()
		return self.scores

	def winningTeam(self):
		if not self.scores: self.teamScores()
		if len(self.scores)<1 or len(self.scores[0])<1: return None
		return self.scores[0][0]

	'''
	lists swimmers by team and by points scored
	'''
	def scoreReport(self, repressSwim=False, repressTeam=False):
		self.score()
		scores = {}
		for team in self.teams:
			scores[team] = {'total': 0, 'year': {}, 'swimmer': {}, 'event': {}}
		for event in self.eventSwims:
			for swim in self.eventSwims[event]:
				if not swim.score:
					swim.score = 0
				if swim.relay:
					name = 'Relays'
				else:
					name = swim.name
				if repressSwim and (swim.score == 0 or not swim.score):
					continue   # repress zero scores

				team = swim.getScoreTeam()
				if not name in scores[team]['swimmer']:
					scores[team]['swimmer'][name] = 0
				if not event in scores[team]['event']:
					scores[team]['event'][event] = 0
				scores[team]['swimmer'][name] += swim.score
				scores[team]['total'] += swim.score
				scores[team]['event'][event] += swim.score
				if swim.year:
					if not swim.year in scores[team]['year']:
						scores[team]['year'][swim.year] = 0
					scores[team]['year'][swim.year] += swim.score

		if repressTeam:
			zeroTeams = set()
			for team in scores:
				if scores[team]['total'] == 0:
					zeroTeams.add(team)
			for team in zeroTeams:
				del(scores[team])

		return scores

'''
store time distribution data
'''
class Clubtimedist(Model):
	event = CharField()
	gender = CharField()
	age = IntegerField()
	year = IntegerField(null=True)
	course = CharField()
	mu = FloatField()
	sigma = FloatField()
	a = FloatField(null=True)

	class Meta:
		database = db

def importSwims(loadSwims=False, loadSwimmers=False, loadTeams=False, loadage=18, year=2016, load_course=None):
	# 9/1 starting date
	root = 'data/club/' + str(year) + '/' + str(loadage)

	for fileName in os.listdir(root):
		if 'Club' not in fileName:
			continue
		print fileName

		parts = re.split('_', fileName)
		_, season, course, gender, event, zone, loadage = parts[0], parts[1], parts[2], parts[3], parts[4], parts[5], \
													   parts[6]

		if load_course and load_course != course:
			#print load_course, course
			continue

		print season, course, gender, event, loadage
		with open(root + '/' + fileName) as file:
			swims = []
			swimmers = []
			teams = []
			swimKeys = set()
			swimmerKeys = set()
			teamKeys = set()

			for line in file:
				swimParts = re.split('\t', line)
				if len(swimParts) < 9:
					continue
				try:
					event_course, team, timeStr, date, meet, name, gender, age, standard = \
						swimParts[0], swimParts[1], \
					swimParts[2], swimParts[3], swimParts[4], swimParts[5], swimParts[6], swimParts[7], swimParts[8]
					age = int(age)
					course = event_course[-3:]
					if timeStr[-1]=='r':
						timeStr = timeStr[:-1]
					time = int(toTime(timeStr) * 100)  # time in ms
				except:
					print sys.exc_info()
					print 'parseFail'
					print line
					continue

				if not time or not gender in ['Men', 'Women']  \
						or not event in allevents or not re.match("\d\d\d\d-\d\d-\d\d", date):
					print 'checkFail'
					print (not time), (not gender in ['Men', 'Women']), not event in allevents, \
						not re.match("\d\d/\d\d/\d\d$", date), not (int(age)==int(loadage))
					print age, loadage
					print time, gender, age, event, date
					print line
					continue

				if loadTeams:
					key = team + gender + season
					if not key in teamKeys:
						teamKeys.add(key)
						try:
							Clubteam.get(team=team, gender=gender, season=season)
						except Clubteam.DoesNotExist:
							newTeam = {'team': team, 'gender': gender, 'season': season}
							#print newTeam
							teams.append(newTeam)

				if loadSwimmers:  # will have two per team from aging up
					key = name + team + gender + str(age)
					if not key in swimmerKeys:
						swimmerKeys.add(key)
						try:
							Clubswimmer.get(gender=gender, name=name, team=team, age=age)
						except Clubswimmer.DoesNotExist:
							newSwimmer = {'name': name, 'gender': gender, 'relay': False, 'age': age, 'team': team}
							#print newSwimmer
							swimmers.append(newSwimmer)

				if loadSwims:
					teamID = Clubteam.get(team=team, gender=gender, season=season).id
					swimmerID = Clubswimmer.get(gender=gender, name=name, team=team, age=age).id
					key = time, event, date, swimmerID, teamID
					if not key in swimKeys:
						swimKeys.add(key)
						try:
							Clubswim.get(time=time, event=event, date=date, swimmer=swimmerID, team=teamID)
						except Clubswim.DoesNotExist:
							newSwim = {'meet': meet, 'date': date,
								   'event': event, 'time': time, 'course': course, 'swimmer': swimmerID, 'team': teamID}
							swims.append(newSwim)
							#print newSwim


		#print swims, swimmers

		db.connect()
		if loadTeams and len(teams) > 0:
			print 'Teams:', len(teams)
			print Clubteam.insert_many(teams).execute()

		if loadSwimmers and len(swimmers) > 0:
			print 'Swimmers:', len(swimmers)
			print Clubswimmer.insert_many(swimmers).execute()

		if loadSwims and len(swims) > 0:
			print 'Swims:', len(swims)
			print Clubswim.insert_many(swims).execute()

def safeImport(age=17, year=2016, load_course='SCY'):
	importSwims(loadTeams=True, loadage=age, year=year, load_course=load_course)
	importSwims(loadSwimmers=True, loadage=age, year=year, load_course=load_course)
	importSwims(loadSwims=True, loadage=age, year=year, load_course=load_course)

def mergeTeams():
	for team in Clubteam.select():
		newTeam = Clubteam.get(team=team.team, gender=team.gender, season=team.season)
		if newTeam.id == team.id:
			continue
		try:
			with db.atomic():
				print Clubswim.update(team=newTeam.id).where(Clubswim.team==team.id).execute()
		except IntegrityError:
			Clubswim.delete().where(Clubswim.team==team.id).execute()
		print Clubteam.delete().where(Clubteam.id==team.id).execute()

def showAgeCurves(age=None):
	men = []
	women = []
	w5, w32, w40, w50, w60, w68, w95 = [], [], [], [], [], [], []
	m5, m32, m40, m50, m60, m68, m95 = [], [], [], [], [], [], []
	for gender in ['Men', 'Women']:
		#for age in range(8, 19):
		for year in range(2007, 2017):
			#year = 1999 + age  # start at 2007
			age = age
			cdf = getSkewDist(gender=gender, age=age, course='SCY', event='100 Free', year=year)
			if gender=='Men':
				m50.append(cdf.median())
				(lo, hi) = cdf.interval(.2)
				m40.append(lo)
				m60.append(hi)
				(lo, hi) = cdf.interval(.68)
				m32.append(lo)
				m68.append(hi)
				(lo, hi) = cdf.interval(.95)
				m5.append(lo)
				m95.append(hi)
			else:
				w50.append(cdf.median())
				(lo, hi) = cdf.interval(.2)
				w40.append(lo)
				w60.append(hi)
				(lo, hi) = cdf.interval(.68)
				w32.append(lo)
				w68.append(hi)
				(lo, hi) = cdf.interval(.95)
				w5.append(lo)
				w95.append(hi)
	#yvalues = range(8, 19)
	yvalues = range(2007, 2017)
	plt.plot(yvalues, w50, 'r-', linewidth=3)
	plt.plot(yvalues, w40, 'r-', linewidth=2)
	plt.plot(yvalues, w60, 'r-', linewidth=2)
	plt.plot(yvalues, w32, 'r-', linewidth=1)
	plt.plot(yvalues, w68, 'r-', linewidth=1)
	plt.plot(yvalues, w95, 'r-')
	plt.plot(yvalues, w5, 'r-')
	plt.plot(yvalues, m50, 'b-', linewidth=3)
	plt.plot(yvalues, m40, 'b-', linewidth=2)
	plt.plot(yvalues, m60, 'b-', linewidth=2)
	plt.plot(yvalues, m32, 'b-', linewidth=1)
	plt.plot(yvalues, m68, 'b-', linewidth=1)
	plt.plot(yvalues, m95, 'b-')
	plt.plot(yvalues, m5, 'b-')
	plt.show()
	print w5, w32, w40, w50, w60, w68, w95, m5, m32, m40, m50, m60, m68, m95

def showAttrition(gender='Women'):
	raw_data = {}
	percentile_swims = {}
	percentile_drops = {}
	for year in range(2007, 2017):
		age = year - 1999
		percentile_swims[str(age)] = {}
		percentile_drops[str(age)] = {}
		dist1 = getSkewDist(gender=gender, age=age, course='SCY', event='100 Free', year=year)
		dist2 = getSkewDist(gender=gender, age=age+1, course='SCY', event='100 Free', year=year)

		# get swims for that year
		swims = {}
		for swim in Clubswim.select(Clubswim, Clubswimmer, Clubteam).join(Clubswimmer).switch()\
				.join(Clubteam).where(Clubteam.season==year,
			Clubswimmer.gender==gender, Clubswimmer.age==age):
			swims[swim.swimmer.name] = swim
		orig_size = len(swims)

		# see who swam next season

		newSwims = {}
		for swim in Clubswim.select(Clubswim, Clubswimmer, Clubteam).join(Clubswimmer).switch()\
				.join(Clubteam).where(Clubteam.season==year+1,
			Clubswimmer.gender==gender, Clubswimmer.age==age+1):
			newSwims[swim.swimmer.name] = swim

		# go though young folks and see what percentile they were in the next year
		for name in swims:
			percentileold = str(int(dist1.cdf(swims[name].time/100) * 5) * 2)
			if percentileold == 10: percentileold = 8
			if name in newSwims:
				percentilenew = str(int(dist2.cdf(newSwims[name].time / 100) * 5) * 2)
				if percentilenew == 10: percentilenew = 8
				#print newSwims[name].time, percentilenew
			else:
				percentilenew = '9'#'None'
			source_target = str(age) +'-'+ percentileold +'-'+ str(age+1) +'-'+ percentilenew
			if source_target not in raw_data:
				raw_data[source_target] = 0
			raw_data[source_target] += 1

			if not percentileold in percentile_swims[str(age)]:
				percentile_swims[str(age)][str(percentileold)] = 0
				percentile_drops[str(age)][str(percentileold)] = 0
			percentile_swims[str(age)][str(percentileold)] += 1
			if percentilenew=='9':
				percentile_drops[str(age)][str(percentileold)] += 1

		# now get the ones who didn't swim the first year
		for name in newSwims:
			if name not in swims:
				percentileold = '9'#'None'
				percentilenew = str(int(dist2.cdf(newSwims[name].time / 100) * 5) * 2)
				if percentilenew == 10: percentilenew = 8
				source_target = str(age) +'-'+ percentileold +'-'+ str(age+1) +'-'+ percentilenew
				if source_target not in raw_data:
					raw_data[source_target] = 0
				raw_data[source_target] += 1

		for age in percentile_swims:
			for percentile in ['0', '2', '4', '6', '8']:  #percentile_swims[age]:
				print age, percentile, percentile_drops[age][percentile] / float(percentile_swims[age][percentile])


	links = {'source':[], 'target':[], 'value': [], 'label': []}
	nodes = {'label':[]}
	for label in raw_data:
		parts = label.split('-')
		#print parts
		#print "['Age:" + parts[0] + ' %' + parts[1] + "','Age:" \
		#	  + parts[2] + ' %' + parts[3] + "'," + str(raw_data[label]) + "],"
		links['source'].append(int(parts[0] + parts[1]))
		links['target'].append(int(parts[2] + parts[3]))
		links['value'].append(raw_data[label])
		nodes['label'].append(parts[0] + parts[1])

def getPoints(gender, event, time, age, course):
	if (event == '200 Breast' or event == '200 Fly' or event == '200 Back') and age < 11:
			return 0
	cdf = getSkewCDF(gender, age, event, course)
	percent = 1 - cdf(time/100)
	if percent==0 or not percent:
		return 0
	percentileScore = (1 - percent) * 500
	powerScore = 1 / percent
	zscore = log(powerScore) * 50  # approximately the number of stds away from the means

	powerpoints = percentileScore + zscore
	return round(powerpoints, 3)

def testTimePre(limit=100):
	misses = []
	flatMisses = []
	avgFlatMisses = []
	combinedMisses = []
	count = 0
	for s1 in Clubswimmer.select().order_by(fn.Random()):
		if count==limit:
			break

		parts = s1.similarSwimmers(search=1000, limit=10, verbose=True)
		if not parts:
			continue
		count += 1

		pastTimes, times, futureTimes, predictedTimes = parts
		print s1.id
		for event in futureTimes:
			if event in predictedTimes:
				misses.append(abs(futureTimes[event].time - predictedTimes[event]['time']) / futureTimes[event].time)
			if event in times:
				if '400' in event or '1500' in event:
					predictedTime = convert(gender=s1.gender, age=s1.age, toage=s1.age + 1, fromCourse='LCM',
									   toCourse='LCM', event=event, time=times[event].time/100.0)
				else:
					predictedTime = convert(gender=s1.gender, age=s1.age, toage=s1.age + 1, fromCourse='SCY',
									   toCourse='SCY', event=event, time=times[event].time/100.0)
				predictedTimeAvg = None
				if event in pastTimes:
					# from two seasons ago
					if '400' in event or '1500' in event:
						predictedTime2 = convert(gender=s1.gender, age=s1.age-1, toage=s1.age + 1, fromCourse='LCM',
										   toCourse='LCM', event=event, time=pastTimes[event].time/100.0)
					else:
						predictedTime2 = convert(gender=s1.gender, age=s1.age-1, toage=s1.age + 1, fromCourse='SCY',
										   toCourse='SCY', event=event, time=pastTimes[event].time/100.0)
					predictedTimeAvg = (predictedTime*3 + predictedTime2) / 4

				print event
				if event in futureTimes: print 'real', futureTimes[event].time/100.0
				if event in predictedTimes: print 'knn', predictedTimes[event]['time']/100.0
				if predictedTimeAvg:
					print '2convert', predictedTimeAvg
					avgFlatMisses.append(abs(predictedTimeAvg*100 - futureTimes[event].time) / futureTimes[event].time)
				if predictedTime:
					print 'convert', predictedTime
				if event in predictedTimes:
					combine = (predictedTime + predictedTimes[event]['time']/100.0) / 2
					print 'combine', combine
					combinedMisses.append(abs(combine*100 - futureTimes[event].time) / futureTimes[event].time)
				flatMisses.append(abs(predictedTime*100 - futureTimes[event].time) / futureTimes[event].time)


	print 'knn', np.mean(misses), np.std(misses)
	print 'flat', np.mean(flatMisses), np.std(flatMisses)
	print '2flat', np.mean(avgFlatMisses), np.std(avgFlatMisses)
	print 'combine', np.mean(combinedMisses), np.std(combinedMisses)

if __name__== '__main__':
	#for age in range(20, 21):
	#	for year in range(2007, 2015):
	#		safeImport(age=age, year=year, load_course='SCY')
	#		safeImport(age=age, year=year, load_course='LCM')

	#print testTimePre()
	#mark = Clubswimmer.get(id=4487181)
	#mark.similarSwimmers(search=2000, limit=10)

	#showAttrition()
	#showAgeCurves(age=16)

	gender = 'Women'
	records = {}
	for event in eventsLCM:
		for age in ['23']:
			#saveSkewDist(gender=gender, event=event, age=age, course='SCY', plot=False, plot=True)
			minimum, numtimes = saveSkewDist(gender=gender, event=event, age=age, course='LCM', getstats=True)
			records[event] = (minimum, numtimes)


	#for year in range(2010, 2018):

	#'''
	for event in eventsLCM:
		dist = getSkewDist(gender=gender, event=event, age=23, course='LCM')
		num = records[event][1] / 3
		#num = 5000
		#num = Swim.select(Swim.name).where(Swim.event==eventConvert[event], Swim.gender==gender,
		#								   Swim.season==2017).group_by(Swim.name).count()
		record = records[event][0]
		#print event, swimTime(dist.isf(1 - 1.0 / num))
		sample = 1000
		times = []
		top = 0
		for i in range(sample):
			topTime = min(dist.rvs(size=num))
			times.append(topTime)
			if topTime < record:
				top += 1
		mu = np.median(times)
		sigma = np.std(times)
		n, bins, patches = plt.hist(times, 60, normed=1)
		#plt.show()
		print event, swimTime(mu), sigma, norm.cdf(record, loc=mu, scale=sigma), top/float(sample), num
		#'''






