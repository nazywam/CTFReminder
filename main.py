#!/usr/bin/python3
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timedelta
from time import time
from typing import Any, Dict, List, Optional, Tuple

import config
import dateutil.parser
import pytz
import tweepy # type: ignore
from requests import get
from templates import *

log = logging.getLogger(__file__)
log.setLevel(logging.DEBUG)

file_handler = logging.FileHandler('ctfreminder.log')
file_handler.setLevel(logging.DEBUG)
log.addHandler(file_handler)

CTFTIME_EVENTS_URL = "https://ctftime.org/api/v1/events/"

HEADERS = {
    "User-Agent": config.USER_AGENT
}
UPDATE_TIME = 5 * 60 #5 minutes
DAY_TIMESTAMP = 60 * 60 * 24 #24 hours
YEAR_SECONDS = 31536000


def fetch_ctfs(time_start: int, time_end: int) -> Optional[List[Dict[str, Any]]]:
    log.debug("Querying for a list of ctfs from %d to %d", time_end, time_end)
    params = {
        "limit": 1000,
        "start": time_start,
        "finish": time_end,
    }

    r = get(url=CTFTIME_EVENTS_URL, params=params, headers=HEADERS)
    if r.status_code != 200:
        log.error("Ctftime responded with %d :(", r.status_code)
        return None

    return r.json()


def fetch_all_ctfs() -> Optional[List[Dict[str, Any]]]:
    now = int(time())
    return fetch_ctfs(now, now + YEAR_SECONDS)


def get_twitter() -> tweepy.API:
    consumer_key = config.TWITTER_CONSUMER_KEY
    consumer_secret = config.TWITTER_CONSUMER_SECRET
    access_token = config.TWITTER_ACCESS_TOKEN
    access_token_secret = config.TWITTER_ACCESS_TOKEN_SECRET

    auth = tweepy.OAuthHandler(consumer_key, consumer_secret)
    auth.set_access_token(access_token, access_token_secret)
    return tweepy.API(auth)


def tweet_text(status: str) -> None:
    if config.PRODUCTION:
        api = get_twitter()
        api.update_status(status=status)
    else:
        print("TWEET:")
        print(status)
        print("")


def fetch_image(url: str, save_path: str) -> bool:
    r = get(url, stream=True)
    if r.status_code != 200:
        log.error("Couldn't get the image from %s, returned %d", url, r.status_code)
        return False
    
    with open(save_path, 'wb') as f:
        for chunk in r:
            f.write(chunk)
    return True


def tweet_text_image(status: str, image_url: str) -> None:
    if config.PRODUCTION:
        twitter = get_twitter()

        with tempfile.NamedTemporaryFile() as image_path:
            if fetch_image(image_url, image_path.name):
                twitter.update_with_media(image_path.name, status=status)
            else:
                twitter.update_status(status=status)
    else:
        print("TWEET WITH IMAGE:")
        print(status)
        print(image_url)
        print("")


# unfortunatelly not exposed via api :< 
def scrape_organiser_twitter(organiser_id: int) -> Optional[str]:
    log.debug("Fetching twitter handle for team %d", organiser_id)
    
    organiser_page = get(url=f"https://ctftime.org/team/{organiser_id}", headers=HEADERS).text

    twitter_core_r = '<p>Twitter: (.*?)</p>'
    twitter_url_r = 'twitter\\.com/(.*?)\\"'

    twitter_row = re.findall(twitter_core_r, organiser_page)
    if not twitter_row:
        log.warning("Failed to get the twitter row")
        return None
    
    row = twitter_row[0]
    log.info("Got the twitter row: %s", repr(row))

    twitter_url = re.findall(twitter_url_r, row)
    if twitter_url:
        return f"@{twitter_url[0]}"
    elif row.startswith('@'):
        return row
    else:
        return f"@{row}"


def tweet_new_ctf(event: Dict[str, Any]) -> None:
    title = event["title"]
    ctftime_url = event["ctftime_url"]
    logo_url = event["logo"]
    log.info("Tweeting about a new ctf: %s", title)

    event_start = dateutil.parser.parse(event["start"])
    start = event_start.strftime("%Y-%m-%d %H:%M:%S UTC")
    org_handle = scrape_organiser_twitter(event["organizers"][0]["id"])

    if org_handle:
        payload = NEW_CTF_TWITTER.format(title, org_handle, start, ctftime_url)
    else:
        payload = NEW_CTF.format(title, start, ctftime_url)

    if len(payload) > 140:
        payload = NEW_CTF.format(ctftime_url, start, "")

    if logo_url:
        tweet_text_image(status=payload, image_url=logo_url)
    else:
        tweet_text(status=payload)


def tweet_ctf_reminder(event: Dict[str, Any]) -> None:
    title = event["title"]
    ctftime_url = event["ctftime_url"]
    logo_url = event["logo"]
    org_handle = scrape_organiser_twitter(event["organizers"][0]["id"])

    log.info("Tweeting a reminder about a ctf: %s", title)

    if org_handle:
        payload = REMIND_CTF_TWITTER.format(title, org_handle, ctftime_url)
    else:
        payload = REMIND_CTF.format(title, ctftime_url)

    if len(payload) > 140:
        payload = REMIND_CTF.format(ctftime_url, ":)")

    if logo_url:
        tweet_text_image(payload, logo_url)
    else:
        tweet_text(payload)


def read_database() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not os.path.exists(config.DB_PATH):
        return ([], [])
    else:
        with open(config.DB_PATH, 'r') as f:
            data = json.loads(f.read())
            return (
                data["mentioned_once"],
                data["mentioned_twice"]
            )

def save_database(once: List[Dict[str, Any]], twice: List[Dict[str, Any]]) -> None:
    with open(config.DB_PATH, 'w') as f:
        f.write(json.dumps({
            "mentioned_once": once,
            "mentioned_twice": twice,
        }))


def pool_ctfs() -> None:
    current_time = pytz.UTC.localize(datetime.now())

    log.info("Reading previously tweeted ctfs from database")
    first, second = read_database()
    log.info("Getting new ctfs")
    ctfs = fetch_all_ctfs()

    if not ctfs:
        log.error("Failed to get any ctfs")
        return

    for f in ctfs[::-1]:
        start_time = dateutil.parser.parse(f["start"])
        # do not report past ftfs
        if start_time > current_time:
            if not f["onsite"] and f["restrictions"] == "Open":
                
                ctf_id = f["ctf_id"]

                if not ctf_id in second and not ctf_id in first:
                    tweet_new_ctf(f)
                    first.append(ctf_id)
                    save_database(first, second)

                if ctf_id in first and not ctf_id in second and current_time + timedelta(hours=24) > start_time:
                    tweet_ctf_reminder(f)
                    second.append(ctf_id)
                    save_database(first, second)


if __name__ == '__main__':
    pool_ctfs()
