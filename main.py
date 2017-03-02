#!/usr/bin/python

from time import time
from requests import get
import tweepy
import dateutil.parser
import os
from bs4 import BeautifulSoup

CTFTIME_API_URL = "https://ctftime.org/api/v1/events/"

#interval at which this script is called
UPDATE_TIME = 5 * 60 #5 minutes
DAY_TIMESTAMP = 60 * 60 * 24 #24 hours


NEW_CTF = """New CTF!
{}, starts at {}
{}
"""

NEW_CTF_TWITTER = """New CTF!
{} organized by {}, starts at {}
{}
"""

REMIND_CTF = """{} starts in under 24 hours!
{}
"""

REMIND_CTF_TWITTER = """{} organized by {} starts in under 24 hours!
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
    config = open(os.path.dirname(os.path.realpath(__file__))+"/config", "r").read().split("\n")

    consumer_key = config[0]
    consumer_secret = config[1]
    access_token = config[2]
    access_token_secret = config[3]

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)

    return tweepy.API(auth)

def readFrom(file):
    f = open(os.path.dirname(os.path.realpath(__file__))+"/"+file, "rb")
    r = f.read()
    f.close()
    return eval(r)

def writeTo(q, file):
    f = open(os.path.dirname(os.path.realpath(__file__))+"/"+file, "wb")
    f.write(str(q))
    f.close()

def appendTo(q, file):
    tab = readFrom(file)
    tab.append(q)
    writeTo(tab, file)


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

        try:
            api.update_with_media(filename, status=data)
        except tweepy.TweepError:
            tweet(data)

        os.remove(filename)

    #coulnd't get the image, tough luck
    else:
        tweet(data)


def getOrganizerTwitterHandle(organizer):
    data = get("https://ctftime.org/team/" + str(organizer)).text

    soup = BeautifulSoup(data, "lxml")

    ret = ""

    for i in soup.find_all("div", {"class":"span10"}):

        for c in i.children:
            for q in str(c).split("\n"):
                if "Twitter:" in q:
                    if "http" in q:
                        s = BeautifulSoup(q, "lxml")
                        url = s.find_all("a")[0].get("href")
                        ret = "@" + url.split("/")[-1]
                    elif "@" in q:
                        ret = q[12:-4]
                    else:
                        ret = "@" + q[12:-4]

    return ret


def tweetNew(event):
    print("Tweet new")

    start = event["start"].replace("T", " ")[:-6]+" UTC"

    orgTwitter = getOrganizerTwitterHandle(event["organizers"][0]["id"])

    if orgTwitter != "":
        payload = NEW_CTF_TWITTER.format(event["title"], orgTwitter, start, event["ctftime_url"])
    else:
        payload = NEW_CTF.format(event["title"], start, event["ctftime_url"])

    if len(payload) > 140:
        payload = NEW_CTF.format(event["ctftime_url"], start, "")

    if(event["logo"] != ""):
        tweetWithImage(payload, event["logo"])
    else:
        tweet(payload)


def tweetRemind(event):
    print("Tweet remind")

    orgTwitter = getOrganizerTwitterHandle(event["organizers"][0]["id"])

    if(orgTwitter != ""):
        payload = REMIND_CTF_TWITTER.format(event["title"], orgTwitter, event["ctftime_url"])
    else:
        payload = REMIND_CTF.format(event["title"], event["ctftime_url"])

    if len(payload) > 140:
        payload = REMIND_CTF.format(event["ctftime_url"], ":)")

    if(event["logo"] != ""):
        tweetWithImage(payload, event["logo"])
    else:
        tweet(payload)

def ctfInList(ctf, list):
    for i in list:
        if i["ctf_id"] == ctf["ctf_id"]:
            return True
    return False

#get current time in unix epoch
currentTime = int(time())

#tweeted once
first = readFrom("first")
#tweeted twice
second = readFrom("second")

justFetched = fetchAll()

updates = 0

for f in justFetched[::-1]:

    startTime = dateutil.parser.parse(f["start"])

    startTimeEpoch = int(startTime.strftime("%s"))
    #no need to think about ctfs for time travelers...
    if startTimeEpoch > currentTime:
        #we don't really care for onsite events
        if not f["onsite"] and f["restrictions"] == "Open":
            #brand new tweet
            if not ctfInList(f, second) and not ctfInList(f, first):
                tweetNew(f)
                appendTo(f, "first")

            if ctfInList(f, first) and not ctfInList(f, second) and (startTimeEpoch-currentTime)<DAY_TIMESTAMP:
                tweetRemind(f)
                appendTo(f, "second")
