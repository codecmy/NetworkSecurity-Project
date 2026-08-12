"""
Collect real-world labeled URLs with extracted features for retraining.

* Phishing URLs: OpenPhish public feed (https://openphish.com/feed.txt).
* Benign URLs: curated list of well-known legitimate sites.

Writes rows incrementally to real_data/features.csv so training can start
before collection finishes.

Usage:
    python collect_real_data.py [--phishing N] [--benign N]
"""

import argparse
import csv
import os
import sys
import urllib.request

from networksecurity.exception.exception import NetworkSecurityException
from networksecurity.utils.feature_extraction.extractor import (
    FEATURE_NAMES,
    PhishingFeatureExtractor,
)

PHISHING_FEED = "https://openphish.com/feed.txt"
OUTPUT = os.path.join("real_data", "features.csv")

BENIGN_URLS = [
    # technology
    "https://www.google.com", "https://www.youtube.com", "https://github.com",
    "https://stackoverflow.com", "https://www.wikipedia.org", "https://twitter.com",
    "https://www.linkedin.com", "https://www.facebook.com", "https://www.instagram.com",
    "https://www.reddit.com", "https://www.amazon.com", "https://www.netflix.com",
    "https://www.microsoft.com", "https://www.apple.com", "https://www.cisco.com",
    "https://www.ibm.com", "https://www.oracle.com", "https://www.salesforce.com",
    "https://www.adobe.com", "https://www.samsung.com", "https://www.huawei.com",
    "https://www.tesla.com", "https://www.spacex.com", "https://www.openai.com",
    "https://developers.google.com", "https://docs.python.org", "https://nodejs.org",
    "https://www.docker.com", "https://kubernetes.io", "https://reactjs.org",
    "https://angular.io", "https://www.postgresql.org", "https://www.mysql.com",
    "https://redis.io", "https://www.mongodb.com", "https://git-scm.com",
    "https://www.cloudflare.com", "https://www.dropbox.com", "https://www.box.com",
    "https://slack.com", "https://zoom.us", "https://trello.com", "https://asana.com",
    "https://www.notion.so", "https://medium.com", "https://dev.to",
    # news & media
    "https://www.bbc.com", "https://www.cnn.com", "https://www.nytimes.com",
    "https://www.theguardian.com", "https://www.reuters.com", "https://www.npr.org",
    "https://www.forbes.com", "https://www.bloomberg.com", "https://www.wsj.com",
    "https://www.economist.com", "https://news.google.com", "https://www.nationalgeographic.com",
    # education & government
    "https://www.harvard.edu", "https://web.mit.edu", "https://www.stanford.edu",
    "https://www.ox.ac.uk", "https://www.cam.ac.uk", "https://www.caltech.edu",
    "https://www.mit.edu", "https://www.berkeley.edu", "https://www.princeton.edu",
    "https://www.yale.edu", "https://www.whitehouse.gov", "https://www.usa.gov",
    "https://www.nasa.gov", "https://www.state.gov", "https://www.irs.gov",
    "https://www.cdc.gov", "https://www.fda.gov", "https://www.epa.gov",
    "https://www.defense.gov", "https://www.fbi.gov", "https://www.senate.gov",
    "https://www.house.gov", "https://www.supremecourt.gov", "https://www.lochness.com",
    # e-commerce & services
    "https://www.ebay.com", "https://www.walmart.com", "https://www.target.com",
    "https://www.bestbuy.com", "https://www.homedepot.com", "https://www.costco.com",
    "https://www.etsy.com", "https://www.shopify.com", "https://www.airbnb.com",
    "https://www.booking.com", "https://www.expedia.com", "https://www.uber.com",
    "https://www.lyft.com", "https://www.doordash.com", "https://www.paypal.com",
    "https://www.stripe.com", "https://www.square.com", "https://www.chase.com",
    "https://www.bankofamerica.com", "https://www.wellsfargo.com", "https://www.citi.com",
    "https://www.americanexpress.com", "https://www.discover.com", "https://www.fidelity.com",
    "https://www.schwab.com", "https://www.usbank.com", "https://www.capitalone.com",
    "https://www.intuit.com", "https://www.hrblock.com",
    # social & comms
    "https://www.whatsapp.com", "https://t.me", "https://discord.com",
    "https://www.snapchat.com", "https://www.tiktok.com", "https://www.pinterest.com",
    "https://www.quora.com", "https://www.blogger.com", "https://www.wordpress.com",
    "https://www.weebly.com", "https://www.wix.com", "https://www.godaddy.com",
    "https://www.namecheap.com", "https://www.gmail.com", "https://outlook.com",
    "https://www.yahoo.com", "https://proton.me", "https://www.duckduckgo.com",
    "https://www.bing.com", "https://search.brave.com",
    # developers & resources
    "https://www.w3.org", "https://www.ietf.org", "https://www.rfc-editor.org",
    "https://www.apache.org", "https://www.linux.org", "https://www.gnu.org",
    "https://www.mozilla.org", "https://www.google.com/earth", "https://earth.google.com",
    "https://www.openstreetmap.org", "https://www.mapbox.com", "https://www.arcgis.com",
    "https://www.figma.com", "https://www.canva.com", "https://www.sketch.com",
    "https://www.overleaf.com", "https://www.khanacademy.org", "https://www.coursera.org",
    "https://www.edx.org", "https://www.udemy.com", "https://www.codecademy.com",
    "https://leetcode.com", "https://www.hackerrank.com", "https://www.hackerearth.com",
    "https://www.topcoder.com", "https://www.atlassian.com", "https://www.jira.com",
    "https://www.confluence.com", "https://bitbucket.org", "https://gitlab.com",
    # local hosts / standard
    "http://www.example.com", "https://example.org", "https://example.net",
    "https://www.iana.org", "https://tools.ietf.org", "https://www.icann.org",
    "https://www.whois.com", "https://www.verisign.com",
    # more comms
    "https://mail.google.com", "https://drive.google.com", "https://docs.google.com",
    "https://photos.google.com", "https://meet.google.com", "https://calendar.google.com",
    "https://maps.google.com", "https://translate.google.com",
    "https://www.office.com", "https://www.onecare.com", "https://www.onedrive.com",
    "https://www.outlook.com", "https://www.skype.com", "https://teams.microsoft.com",
    "https://www.vimeo.com", "https://www.twitch.tv", "https://www.soundcloud.com",
    "https://open.spotify.com", "https://music.apple.com", "https://www.pandora.com",
    "https://www.hulu.com", "https://www.disneyplus.com", "https://www.peacocktv.com",
    "https://www.paramountplus.com", "https://www.hbo.com", "https://www.showtime.com",
    "https://www.crunchyroll.com", "https://www.barnesandnoble.com", "https://www.barnesandnoble.com",
    "https://www.kobo.com", "https://www.goodreads.com", "https://www.imdb.com",
    "https://www.rottentomatoes.com", "https://www.metacritic.com", "https://www.gamespot.com",
    "https://www.ign.com", "https://www.polygon.com", "https://www.theverge.com",
    "https://arstechnica.com", "https://www.wired.com", "https://www.techcrunch.com",
    "https://www.engadget.com", "https://www.gizmodo.com", "https://www.cnet.com",
    "https://www.tomshardware.com", "https://www.anandtech.com", "https://www.dpreview.com",
    "https://www.photographyblog.com", "https://www.airline.com", "https://www.aa.com",
    "https://www.delta.com", "https://www.united.com", "https://www.southwest.com",
    "https://www.emirates.com", "https://www.britishairways.com", "https://www.lufthansa.com",
    "https://www.klm.com", "https://www.qantas.com", "https://www.airfrance.com",
    "https://www.singaporeair.com", "https://www.cathaypacific.com", "https://www.jal.com",
    "https://www.ana.co.jp", "https://www.turkishairlines.com", "https://www.qatarairways.com",
]


def fetch_phishing_urls(limit: int) -> list:
    with urllib.request.urlopen(PHISHING_FEED, timeout=30) as resp:
        lines = [ln.strip() for ln in resp.read().decode().splitlines() if ln.strip()]
    return lines[:limit]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--phishing", type=int, default=300)
    parser.add_argument("--benign", type=int, default=300)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    extractor = PhishingFeatureExtractor(request_timeout=6.0, resolve_timeout=4.0, use_whois=False)

    written = 0
    if os.path.exists(OUTPUT):
        with open(OUTPUT, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            written = sum(1 for _ in reader)

    mode = "a" if written else "w"
    with open(OUTPUT, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["url", "label"] + FEATURE_NAMES)
        if not written:
            writer.writeheader()

        def process(urls, label):
            nonlocal written
            done = 0
            for url in urls:
                try:
                    features = extractor.extract(url)
                    row = {"url": url, "label": label, **features}
                    writer.writerow(row)
                    f.flush()
                    done += 1
                    written += 1
                except Exception as exc:
                    print(f"skip {url}: {exc}", file=sys.stderr)
                if done and done % 25 == 0:
                    print(f"[{label}] collected {done}/{len(urls)} (total rows: {written})", flush=True)

        try:
            print("Fetching phishing feed...", flush=True)
            process(fetch_phishing_urls(args.phishing), "phishing")
        except Exception as exc:
            print(f"phishing collection failed: {exc}", file=sys.stderr)

        print("Collecting benign URLs...", flush=True)
        process(BENIGN_URLS[: args.benign], "legitimate")

    print(f"DONE. Total rows: {written}")


if __name__ == "__main__":
    main()
