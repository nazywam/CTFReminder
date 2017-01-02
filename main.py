#!/usr/bin/python

from time import time
from requests import get
import tweepy
from dateutil.parser import parse
import os

CTFTIME_API_URL = "https://ctftime.org/api/v1/events/"

#interval at which this script is called
UPDATE_TIME = 5 * 60 #5 minutes
DAY_TIMESTAMP = 1 * 60 * 24 #24 hours

NEW_CTF = """New CTF announced!
{}, starts at {}
{}
"""

REMIND_CTF = """{} starts in under 24 hours!
{}
"""

def fetchCtfs(timeStart, timeEnd):
    dataParameters = {
        "limit":"1000",
        "start":str(timeStart),
        "finish":str(timeEnd),
    }

    r = get(url=CTFTIME_API_URL, params=dataParameters)

    #u wot m8
    payload = r.text.replace("false", "False").replace("true", "True")

    return eval(payload)


def fetchAll():
    currentTime = int(time())  #strip the milliseconds
    return (fetchCtfs(currentTime, currentTime + 1000000000))

def initAPI():
    config = open("config", "r").read().split("\n")

    consumer_key = config[0]
    consumer_secret = config[1]
    access_token = config[2]
    access_token_secret = config[3]

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)

    return tweepy.API(auth)

def readFrom(file):
    f = open(file, "rb")
    r = f.read()
    f.close()
    return eval(r)

def writeTo(q, file):
    f = open(file, "wb")
    f.write(str(q))
    f.close()


def tweet(data):
     api = initAPI()
     api.update_status(status=data)

def tweetWithImage(data, imageUrl):
    filename = 'temp.png'

    request = get(imageUrl, stream=True)
    if request.status_code == 200:
        with open(filename, 'wb') as image:
            for chunk in request:
                image.write(chunk)

        api = initAPI()
        api.update_with_media(filename, status=data)
        os.remove(filename)

    #coulnd't get the image, tough luck
    else:
        tweet(data)


def tweetNew(event):

    start = event["start"].replace("T", " ")[:-6]+" UTC"

    payload = NEW_CTF.format(event["title"], start, event["ctftime_url"])

    if(event["logo"] != ""):
        tweetWithImage(payload, event["logo"])
    else:
        tweet(payload)


def tweetRemind(event):

    payload = REMIND_CTF.format(event["title"], event["ctftime_url"])

    if(event["logo"] != ""):
        tweetWithImage(payload, event["logo"])
    else:
        tweet(payload)

#get current time in unix epoch
currentTime = int(time())

#tweeted once
first = readFrom("first")
#tweeted twice
second = readFrom("second")

justFetched = fetchAll()

updates = 0

for f in justFetched[::-1]:

    startTime = parse(f["start"])

    startTimeEpoch = int(startTime.strftime("%s"))
    #no need to think about ctfs for time travelers...
    if startTimeEpoch > currentTime:
        #we don't really care for onsite events
        if not f["onsite"]:
            #brand new tweet
            if f not in second and f not in first:
                tweetNew(f)
                first.append(f)
                updates += 1

            if f in first and (startTimeEpoch-currentTime)<DAY_TIMESTAMP:
                tweetRemind(f)
                second.append(f)
                updates += 1

writeTo(first, "first")
writeTo(second, "second")

l = open("log", "a")
l.write(str(currentTime)+" "+str(updates))
l.close()