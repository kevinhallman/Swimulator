from math import log
from itertools import permutations, product, combinations
#import statsmodels.api as sm

from scipy.stats import norm, truncnorm, skewnorm
from scipy.interpolate import UnivariateSpline
#from scipy.interpolate import interp1d
#from numpy.linalg import lstsq
#from scipy import polyfit, polyval
from scipy.stats import linregress
#import matplotlib.mlab as mlab
from math import erf, sqrt


	'''
	statistical methods
	'''
	def eventProjection(self, event, time, gender, year, threshold=.002, division=None):
		if year not in {'Freshman', 'Sophomore', 'Junior'}: return

		# first find similar times done same year
		uBound = time + time * threshold
		lBound = time - time * threshold
		print time, division  #uBound, lBound

		similarSwims = []
		for swim in Swim.select().where(Swim.event==event, Swim.gender==gender, Swim.year==year, Swim.time>lBound,
										Swim.time<uBound, Swim.division==division):
			# check to see if thats a top time for that swimmer
			topSwims = self.topSwims(swim.swimmer, n=10)
			if swim in topSwims:
				similarSwims.append(swim)
				#print swim.event, swim.name, swim.time
				if len(similarSwims) > 200: break

		# now see how those swimmers did next season
		def project(year):
			times = []
			for swim in similarSwims:
				try:
					nextSwimmer = Swimmer.get(Swimmer.name==swim.name, Swimmer.team==swim.team, Swimmer.year==year)
					swims = self.topSwims(nextSwimmer.id, event=event, n=5)  # get best event time in top swims
					for swim in swims:
						times.append(swim.time)
				except Swimmer.DoesNotExist:
					pass
			return times


		times1 = project(nextYear(year))
		times2 = project(nextYear(nextYear(year)))
		times3 = project(nextYear(nextYear(nextYear(year))))
		print len(times1), len(times2), len(times3)
		print np.mean(times1), np.std(times1)
		print np.mean(times2), np.std(times2)
		print np.mean(times3), np.std(times3)

	def eventProjection2(self, event, time, gender, year='Freshman', threshold=.005, division='D1'):
		uLimit = time + time*threshold
		lLimit = time - time*threshold
		times = []
		#print time, event, gender
		for imp in Improvement.select().where(Improvement.event==event,
				Improvement.gender==gender, Improvement.fromtime<uLimit, Improvement.fromtime>lLimit,
							Improvement.division==division, Improvement.fromyear==year):
			times.append(imp.totime-imp.fromtime)

		#print times
		if len(times) > 5:
			return np.mean(times), np.std(times), len(times)
			#n, bins, patches = plt.hist(times, 60, normed=1, alpha=0.75)
			#plt.show()

	# returns an improvement function
	def getExtrapEvent(self, event, gender, year='Freshman', division='D1'):
		sentinelString = event+gender+year+division
		if sentinelString in self.eventImpCache:
			return self.eventImpCache[sentinelString]

		# get fastest, slowest times
		timeStart, timeEnd = None, None
		for swim in Swim.select(fn.Min(Swim.time), fn.Max(Swim.time)).where(Swim.event==event, Swim.gender==gender,
								Swim.division==division, Swim.year==year):
			timeStart, timeEnd = swim.min, swim.max
		if not timeStart or not timeEnd:
			return

		if '1650' in event or '1000' in event:
			interval = 2
		elif '100' in event or '50' in event:
			interval =.25
		elif '200' in event:
			interval =.5
		elif '400' in event or '500' in event:
			interval = 1
		else:
			interval = 1

		timeCurve, x, y, w = [], [], [], []
		for time in np.arange(timeStart, timeEnd, interval):
			data = self.eventProjection2(event, time, gender)
			if data:
				mu, sigma, n = data
				timeCurve.append((time, round(mu, 2), round(sigma,2)))
				x.append(time)
				y.append(mu)
				w.append(1/sigma)

		f = UnivariateSpline(x, y, w)

		self.eventImpCache[sentinelString] = f
		return f

	def fitEvent(self, event, gender, division=None, plot=True):
		timesX = []
		timesY = []
		dif = []
		timesXW, timesYW, difW = [], [], []
		if division:
			improvementsMen = Improvement.select().where(Improvement.event==event, Improvement.gender=='Men',
													  Improvement.division==division)
			improvementsWomen = Improvement.select().where(Improvement.event==event, Improvement.gender=='Women',
													  Improvement.division==division)
		else:
			improvementsMen = Improvement.select().where(Improvement.event==event, Improvement.gender=='Men')
			improvementsWomen = Improvement.select().where(Improvement.event==event, Improvement.gender=='Women')

		for time in improvementsMen:
			timesX.append(time.fromtime)
			timesY.append(time.totime)
			dif.append((time.fromtime - time.totime) / ((time.fromtime + time.totime) / 2) * 100)
		for time in improvementsWomen:
			timesXW.append(time.fromtime)
			timesYW.append(time.totime)
			difW.append((time.fromtime - time.totime) / ((time.fromtime + time.totime) / 2) * 100)

		if len(timesX)<10: return
		print event
		slope, intercept, r_value, p_value, std_err = linregress(timesX, timesY)
		print slope, intercept, r_value, p_value, std_err, event
		timesX, dif = rejectOutliers(timesX, dif, l=10, r=3)
		timesXW, difW = rejectOutliers(timesXW, difW, l=10, r=3)

		timeStart = min(timesX)
		timeEnd = max(timesX)
		timeStartW = min(timesXW)
		timeEndW = max(timesXW)
		print timeStart, timeEnd
		newX = np.arange(timeStart, timeEnd, .25)

		# 2nd degree fix on the time, absolute time dropped
		fit, res, _, _, _= np.polyfit(timesX, dif, 1, full=True)
		fitW, resW, _, _, _= np.polyfit(timesXW, difW, 1, full=True)
		#print res, np.mean(dif), np.std(dif)

		fit_fn = np.poly1d(fit)
		fit_fnW = np.poly1d(fitW)

		if plot:
			figure = {
  				"data": [
					go.Scatter(
						x=timesX,
						y=dif,
						mode='markers',
						name='Men'
					),
					go.Scatter(
						x=timesXW,
						y=difW,
						mode='markers',
						name='Women'
					),
					go.Scatter(
						x=[timeStart, timeEnd],
						y=[fit_fn(timeStart), fit_fn(timeEnd)],
						mode='line',
						name='Men Fit'
					),
					go.Scatter(
						x=[timeStartW, timeEndW],
						y=[fit_fnW(timeStartW), fit_fnW(timeEndW)],
						mode='line',
						name='Women Fit'
					)
				],
    			"layout": go.Layout(title=event)
			}
			py.iplot(figure, filename=event)

	def eventCombos(self, topNum=20000):  # find most commonly swum event combinations, returns correlation matrix
		# find rates of each combo, powerpoints for each combo and the correlation matrix
		combos = {}
		pptCombos = {}
		corrMatrix = {}
		n = 0
		for swimmer in Swimmer.select(Swimmer.id).where(Swimmer.season==2016):
			swims = self.topSwims(swimmer.id, season=2016, n=3, distinctEvents=True)  # get their top three swims in
			# different events
			if len(swims) < 3: continue
			n+=1
			if n >topNum:
				break
			events = []
			for swim in swims:
				events.append(swim.event)
			#print events
			events.sort()
			eventStr = ''
			for event in events:
				eventStr+=' - ' + event
			combos[eventStr] = combos.get(eventStr, 0) + 1

			cdf = self.getTimeCDF(swim.gender, swim.division, swim.event, 100)
			points = 1 - cdf(swim.time)
			pptCombos[eventStr] = pptCombos.get(eventStr, 0) + points

			for perm in permutations(events, 2):
				if perm[0] not in corrMatrix:
					corrMatrix[perm[0]] = {}
				corrMatrix[perm[0]][perm[1]] = corrMatrix[perm[0]].get(perm[1], 0) + 1

		comboMatrix = [['Event Combination', '% of All Combinations', 'Power Ranking']]
		totalNum = sum(combos.values())
		for combo, value in sorted(combos.items(), key=itemgetter(1)):
			comboMatrix.append([combo[3:], round(value / float(totalNum), 2), round(pptCombos[combo] / float(value),2)])
			print combo[3:], round(value / float(totalNum), 2), round(pptCombos[combo] / float(value), 2)

		'''
		eventHeader = ''
		for event in corrMatrix:
			eventHeader += event + '\t'
		print eventHeader

		for event in corrMatrix:
			eventLine = event
			for event2 in corrMatrix:  # some of these events might not be in inner matrix
				if event2 in corrMatrix[event]:
					eventLine += '\t' + str(corrMatrix[event][event2])
				else:
					eventLine += '\t' + '0'
			print eventLine
		'''
		dataMatrix = []
		for idx1, event1 in enumerate(corrMatrix):
			dataMatrix.append([])
			for idx2, event2 in enumerate(corrMatrix):
				try:
					total = sum(corrMatrix[event1].values())
					# normalize
					dataMatrix[idx1].append(float(corrMatrix[event1][event2])/total)
				except KeyError:
					dataMatrix[idx1].append(0)

		figure = {
  			"data": [
				go.Heatmap(
					z=dataMatrix,
        			x=corrMatrix.keys(),
        			y=corrMatrix.keys()
				)
			],
    		"layout": go.Layout(title="Event Correlations", margin={'l': 175, 'b': 150})
		}
		py.plot(figure, filename="teamDropFitWomen.html")

		return corrMatrix

	def bestMeet(self, corrMatrix, topNum=10):

		# first get all possible 3-day meet formats
		events = list(eventsChampInd) #['100 Yard Freestyle', '200 Yard Freestyle', '100 Yard Butterfly']#
		possMeets = []
		# all possible ways to split events into three groups
		flaglist = product([1, 2, 3], repeat=len(events))
		for n, flags in enumerate(flaglist):  # now apply partitions to events
			l1 = [events[i] for i, flag in enumerate(flags) if flag==1]
			l2 = [events[i] for i, flag in enumerate(flags) if flag==2]
			l3 = [events[i] for i, flag in enumerate(flags) if flag==3]
			possMeets.append((l1, l2, l3))

		# add correlations for events that are on the same day
		meetScores = {}
		lineupCombos = set()
		for meet in possMeets:
			doubled = 0
			meetStrings = []
			for day in meet:
				str = ''
				for event in sorted(day):
					str += event
				if not str == '':
					meetStrings.append(str)
				for combo in combinations(day, 2):
					if combo[0] in corrMatrix and combo[1] in corrMatrix[combo[0]]:
						doubled += corrMatrix[combo[0]][combo[1]]

			meetString = ''
			for day in sorted(meetStrings):
				meetString += day + ' -  '
			if meetString not in lineupCombos:
				meetScores[meetString] = doubled
				lineupCombos.add(meetString)


		#return the top n
		n=0
		for lineup in sorted(meetScores.items(), key=operator.itemgetter(1)):
			n+=1
			if n >topNum: break
			print lineup

	def impStats(self, division='D1', gender='Women', season=2016):
		teamStr = []
		teamNames = []
		teamImp = {}
		teamImpOrdered = []

		# top 25 teams
		for stats in Team.select().where(Team.gender==gender, Team.division==division).order_by(
				Team.strengthinvite.desc()).limit(25):
			strength = self.topTeamScore(stats.name, dual=False, division=division, gender=gender, season=season)
			teamNames.append(stats.name)
			teamStr.append(strength)
			teamImpOrdered.append(stats.improvement)

		# get all the improvement data for each team
		boxes = []
		teamImpMeans = []
		for team in teamNames:
			teamImp[team] = []
			for stats in Improvement.select().where(Improvement.team==team, Improvement.gender==gender):
				teamImp[team].append(stats.percentImp())
			boxes.append(go.Box(y=teamImp[team], name=team))
			teamImpMeans.append(np.mean(teamImp[team]))

		print np.mean(stats.improvement), division, gender

		slope, intercept, r_value, p_value, std_err = linregress(teamStr, teamImpMeans)
		print slope, intercept, r_value, p_value, std_err

		fit, res, _, _, _= np.polyfit(teamStr, teamImpMeans, 1, full=True)
		print res


		fit_fn = np.poly1d(fit)

		start = min(teamStr)
		end = max(teamStr)

		boxes.append(go.Scatter(
					x=[start, end],
					y=[fit_fn(start), fit_fn(end)],
					name="Best Fit",
				))

		#offline.plot({'data': boxes}, filename='teamDropsMen.html')
		print teamStr, teamImpOrdered
		figure = {
  			"data": [
				go.Scatter(
					x=teamStr,
					y=teamImpOrdered,
					mode='markers+text',
					name="Women's Teams",
					text=teamNames,
					textposition='top'
				)#,
				#go.Scatter(
				#	x=[start, end],
				#	y=[fit_fn(start), fit_fn(end)],
				#	name="Best Fit",
				#)
			],
    		"layout": go.Layout()
		}
		py.plot(figure, filename="teamDropFitWomen.html")

		def getTimeMode(self, gender, division, event):
		import matplotlib.pyplot as plt
		#from scipy.stats import skewnorm
		times = []
		for swim in Swim.select(Swim.time).where(Swim.division==division, Swim.gender==gender, Swim.event==event,
												 Swim.season==2016):
			if swim.time > 15:
				times.append(swim.time)
		if len(times) == 0:
			return
		times = rejectOutliers(times, l=4, r=4)
		(mu, sigma) = norm.fit(times)

		topNums = (0, 0)
		topCount = 0
		#print mu, sigma
		for i in range(50):
			hi = mu - mu*(24.5-i)/250
			lo = mu - mu*(25.5-i)/250
			count = Swim.select(fn.COUNT(Swim.id)).where(Swim.division==division, Swim.gender==gender,
							Swim.event==event, Swim.time<hi, Swim.time>lo, Swim.season==2016).scalar()
			#print hi, lo, count
			if count > topCount:
				topCount = count
				topNums = (lo, hi)
		mode = (topNums[0] + topNums[1])/2
		print event, mu, sigma, max(times)
		fit = skewnorm.fit(times, max(times)-mu, loc=mu, scale=sigma)
		print fit
		# fit2 = (-mu, fit[1], fit[2], sigma
		# mun, sigman = mode, sigma
		# fit2 = (-mu, (max(times)-mun)/(sigman), mun, sigman)
		# print fit2
		r = skewnorm(*fit)
		plt.hist(r.rvs(100000), bins=50, normed=True)
		plt.hist(times, bins=50, normed=True, alpha=0.5)
		plt.show()

	def improvement(self, gender='Men', teams=MIAC, events=allEvents, season1=thisSeason()-1, season2=thisSeason()-2,
					season3=None, season4=None):
		# get top times for the seasons
		top1 = self.taperSwims(teams=teams, gender=gender, season=season1)
		top2 = self.taperSwims(teams=teams, gender=gender, season=season2)
		if season3:
			top3 = self.topTimes(gender=gender, events=events, teams=teams, season=season3, meetForm=False)
		if season4:
			top4 = self.topTimes(gender=gender, events=events, teams=teams, season=season4, meetForm=False)

		# finds improvement between two seasons
		def calcImprovement(top1, top2):
			allImprovement = {}
			teamImprovement = {}
			for team in top1:
				if not team in top2:
					continue
				if not team in allImprovement:
					allImprovement[team] = {}
					teamImprovement[team] = []
				for swimmer in top1[team]:
					if not swimmer in top2[team]:
						continue
					if not swimmer in allImprovement:
						allImprovement[team][swimmer] = {}
					for event in top1[team][swimmer]:
						if not event in top2[team][swimmer]:
							continue
						time1 = top1[team][swimmer][event].time
						time2 = top2[team][swimmer][event].time
						drop = (time2-time1) / ((time1+time2) / 2) * 100
						print swimmer, event, time1, time2
						if abs(drop) > 10:  # toss outliers
							continue
						allImprovement[team][swimmer][event] = drop
						teamImprovement[team].append(drop)
			return allImprovement, teamImprovement

		allImprovement, teamImprovement = calcImprovement(top1, top2)

		if season3:  # combine in optional season 3
			allImprovement2, teamImprovement2 = calcImprovement(top2, top3)
			combined = teamImprovement.copy()
			for team in teamImprovement2:
				if team in combined:
					combined[team].extend(teamImprovement2[team])
				else:
					combined[team] = teamImprovement2[team]
			teamImprovement = combined

		if season4 and season3: # combine in optional season 4
			allImprovement2, teamImprovement2 = calcImprovement(top3, top4)
			combined = teamImprovement.copy()
			for team in teamImprovement2:
				if team in combined:
					combined[team].extend(teamImprovement2[team])
				else:
					combined[team] = teamImprovement2[team]
			teamImprovement = combined

		return teamImprovement, allImprovement

	def improvement2(self, gender='Men', teams=MIAC, season1=thisSeason()-1, season2=thisSeason()-2):
		posSeasons = [2016, 2015, 2014, 2013, 2012, 2011]
		#print season1, season2
		if season1 > season2 and season1 in posSeasons and season2 in posSeasons:
			seasons = range(season2, season1)
			#print seasons
		teamImprovement = {}
		for swim in Improvement.select().where(Improvement.fromseason << seasons, Improvement.gender==gender,
									   Improvement.team << list(teams)):
			if swim.team not in teamImprovement:
				teamImprovement[swim.team] = []
			teamImprovement[swim.team].append(swim.improvement)

		if len(teams)==1 and teams[0] in teamImprovement:
			return teamImprovement[teams[0]]
		return teamImprovement