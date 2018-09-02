#!/usr/bin/env python

import re
import requests
import sqlite3
from bs4 import BeautifulSoup
import multiprocessing

def getRacesURLs(homeURL):
    baseURL = 'https://www.onextwo.com/'
    r = requests.get(homeURL)
    # Check if there were US races for that day
    usaPattern = re.compile('>U.S.A.<')
    matches = usaPattern.findall(r.text)
    if len(matches) < 1:
        return []
    # Only get US links
    afterUS = r.text.split('U.S.A.')[-1]
    soup = BeautifulSoup(afterUS, 'html.parser')
    raceItems = soup.findAll("div", {"class": "btn_evaluated"})
    raceURLs = []
    for item in raceItems:
        if item.get_text() != '...':
            raceURLs.append(baseURL + item['onclick'].split('\'')[1])
        else:
            ''' If there are more than 9 races get the races with double digits '''
            dotsR = requests.get(baseURL + item['onclick'].split('\'')[1])
            soup = BeautifulSoup(dotsR.text, 'html.parser')
            raceNos = soup.findAll('td', {'class': 'nr_evaluated'})
            for race in raceNos:
                if len(race.get_text()) > 1:
                    raceURLs.append(baseURL + race.parent.parent.parent.parent['onclick'].split('\'')[1])
    return raceURLs
    
'''
    Will return False if there is an error extracting values (i.e. a dead heat)
'''
def extractDatabaseValues(raceURL, databaseDict):
    r = requests.get(raceURL)
    soup = BeautifulSoup(r.text, 'html.parser')
    # Grab track and date
    trackAndDateItem = soup.find('td', {'class': 'catitem_left'})
    trackAndDateText = trackAndDateItem.get_text().replace('\xa0','').split('-')
    # Grab race event number
    raceEventPattern = re.compile('race_evt=(.*)&')
    raceEvent = raceEventPattern.findall(raceURL)
    # Grab info about horses' odds
    boldItems = soup.findAll('b')
    numbersAndOdds = []
    for item in boldItems:
        try:
            if item.parent["class"][0] == 'item':
                numbersAndOdds += item.parent.parent
        except:
            pass
    numberIndex = 1
    oddsIndex = 22
    oddsList = []
    for i in range(20):
        numberStr = numbersAndOdds[numberIndex].get_text()
        oddsStr = numbersAndOdds[oddsIndex].get_text()
        try:
            number = int(numberStr)
            if oddsStr == '**':
                oddsList.append(-1)
            else:
                odds = round((float(oddsStr)/10)-1, 2)
                oddsList.append(odds)
        except ValueError:
            ''' If 1A has odds but 1 does not '''
            if oddsStr != '**' and len(oddsStr.strip()) > 0:
                odds = round((float(oddsStr)/10)-1, 2)
                oddsList[len(oddsList)-1] = odds
        numberIndex += 1
        oddsIndex += 1
    # Grab info about race results
    topFourResultsText = soup.find('td', {'class': 'subheader'}).get_text()
    topFourResultsNumbersList = []
    resultsOrderList = topFourResultsText.split(':')[1].split('-')
    ''' If there is a dead heat len(resultsOrderList) will be < 4
        or if only the first 3 horses are given                   '''
    if len(resultsOrderList) < 4:
        return False
    for horseNo in resultsOrderList:
        try:
            topFourResultsNumbersList.append(int(horseNo))
        except:
            topFourResultsNumbersList.append(int(horseNo.replace('A','').replace('B','').replace('C','').replace('X','').strip().split('/')[0]))
    # Determine relative odds of top 4 finishers
    topFourResultsOddsRankList = []
    oddsSortedList = sorted(list(filter(lambda x: x != -1, oddsList)))
    for horseNo in topFourResultsNumbersList:
        horseOdds = oddsList[horseNo-1]
        topFourResultsOddsRankList.append(oddsSortedList.index(horseOdds)+1)
    # Add information to the database dictionary
    databaseDict['TRACK'] = trackAndDateText[0]
    databaseDict['DATE'] = trackAndDateText[1]
    databaseDict['RACE_NO'] = int(raceURL.split('=')[-1])
    databaseDict['RACE_EVENT'] = raceEvent[0]
    databaseDict['ID'] = raceEvent[0] + raceURL.split('=')[-1]
    databaseDict['NO_HORSES'] = len(list(filter(lambda x: x != -1, oddsList)))
    for i in range(20):
        if i < len(oddsList) and oddsList[i] > 0:
            databaseDict['ODDS_' + str(i+1)] = oddsList[i]
    databaseDict['NO_1ST'] = topFourResultsNumbersList[0]
    databaseDict['NO_2ND'] = topFourResultsNumbersList[1]
    databaseDict['NO_3RD'] = topFourResultsNumbersList[2]
    databaseDict['NO_4TH'] = topFourResultsNumbersList[3]
    databaseDict['RANK_1ST'] = topFourResultsOddsRankList[0]
    databaseDict['RANK_2ND'] = topFourResultsOddsRankList[1]
    databaseDict['RANK_3RD'] = topFourResultsOddsRankList[2]
    databaseDict['RANK_4TH'] = topFourResultsOddsRankList[3]
    # Grab info about payouts (based on a $2 bet)
    payoutsText = soup.find('td', {'class': 'quote'}).get_text()
    payoutsList = payoutsText.split(' ')
    gatherPayoutInformation(payoutsList, databaseDict)
    print(trackAndDateText[0] + ' (' + trackAndDateText[1] + '): ' + raceURL.split('=')[-1] + '  --- ' + raceEvent[0] + raceURL.split('=')[-1])
    return True

def gatherPayoutInformation(payoutsList, databaseDict):
    index = 0
    while index < len(payoutsList) and len(payoutsList[index]) > 0:
        betType = payoutsList[index].replace(':', '').strip()
        index += 1
        if (betType == 'Win'):
            databaseDict['WIN_1ST'] = convertPayout(payoutsList[index])
        elif (betType == 'Place'):
            placeList = payoutsList[index].split('-')
            databaseDict['PLC_1ST'] = convertPayout(placeList[0])
            databaseDict['PLC_2ND'] = convertPayout(placeList[1])
        elif (betType == 'Show'):
            showList = payoutsList[index].split('-')
            databaseDict['SHW_1ST'] = convertPayout(showList[0])
            databaseDict['SHW_2ND'] = convertPayout(showList[1])
            if len(showList) > 2: 
                databaseDict['SHW_3RD'] = convertPayout(showList[2])
        else:
            databaseDict[betType.upper()] = convertPayout(payoutsList[index].split('-')[0])
        index += 1

def generateInsertString(databaseDict):
    insertStr = ''
    first = True
    for key in databaseDict.items():
        if first:
            if isinstance(key[1], str):
                insertStr += '\'' + key[1] + '\');'
            else:
                insertStr += str(key[1]) + ');'
            first = False
        else:
            if isinstance(key[1], str):
                insertStr = '\'' + key[1] + '\',' + insertStr
            else:
                insertStr = str(key[1]) + ',' + insertStr
    first = True
    for key in databaseDict.items():
        if first:
            insertStr = key[0] + ') VALUES (' + insertStr
            first = False
        else:
            insertStr = key[0] + ',' + insertStr
    insertStr = 'INSERT INTO racesTable (' + insertStr
    return insertStr

def convertPayout(moneyText):
    return round((float(moneyText)/10)*2, 2)

def insertToDatabaseFromHome(homeURL):
    raceURLs = getRacesURLs(homeURL)
    databaseDict = {}
    conn = sqlite3.connect('raceDB.db')
    for url in raceURLs:
        if extractDatabaseValues(url, databaseDict):
            sqlStr = generateInsertString(databaseDict)
            # print(sqlStr)
            try:
                conn.execute(sqlStr)
            except:
                pass
            conn.commit()
        databaseDict.clear()
    conn.close()

def generateHomeURLsForMonth(month, year):
    monthDays = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    homeURLsList = []
    for day in range(monthDays[month-1]):
        homeURL = 'https://www.onextwo.com/info.php?race_type=p&def_lang=en&letter=&time=&do=1&form_d={}&form_m={}&form_y={}&modus=races'.format(day+1, month, year)
        homeURLsList.append(homeURL)
    return homeURLsList

if __name__ == '__main__':
    month = input('Please enter month number: ')
    year = input('Please enter year: ')
    homeURLs = generateHomeURLsForMonth(int(month), int(year))
    p = multiprocessing.Pool(10)
    p.map(insertToDatabaseFromHome, homeURLs)
    # for url in homeURLs:
    #     insertToDatabaseFromHome(url)
    #     print('DAY DONE')

    # r = requests.get('https://www.onextwo.com/race_location.php?race_type=p&def_lang=&race_evt=2147621590')
    # soup = BeautifulSoup(r.text, 'html.parser')
    # raceNos = soup.findAll('td', {'class': 'nr_evaluated'})
    # for race in raceNos:
    #     if len(race.get_text()) > 1:
    #         print(race.parent.parent.parent.parent['onclick'])
    # databaseDict = {}
    # extractDatabaseValues('https://www.onextwo.com/race_detail.php?race_type=p&def_lang=&race_evt=2147622325&race_num=1', databaseDict)
    # print(databaseDict)
    #extractDatabaseValues('https://www.onextwo.com/race_detail.php?race_type=p&def_lang=&race_evt=2147627962&race_num=5', databaseDict)
    #extractDatabaseValues('https://www.onextwo.com/race_detail.php?race_type=p&def_lang=&race_evt=2147627995&race_num=1', databaseDict)