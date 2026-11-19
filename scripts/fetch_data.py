#!/usr/bin/env python3
"""
Fetch live numbers for the cards into data/profile.json:
  - the last year of daily contributions (GraphQL contributionCalendar; with a token
    that has read:user this includes private contributions, same as the profile page)
  - stars / forks for every repo referenced in data/content.json

Token: $GH_TOKEN or $GITHUB_TOKEN (falls back to `gh auth token` locally).

    python scripts/fetch_data.py
"""
import datetime
import json
import os
import subprocess
import sys

import requests

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CONTENT = os.path.join(ROOT, "data", "content.json")
OUT = os.path.join(ROOT, "data", "profile.json")
USER = os.environ.get("PROFILE_USER", "Andrei9383")


def token():
    t = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    try:
        return subprocess.check_output(["gh", "auth", "token"], text=True).strip()
    except Exception:
        sys.exit("no token: set GH_TOKEN")


def gql(query, **variables):
    r = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers={"Authorization": f"bearer {token()}"},
        timeout=30,
    )
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        sys.exit(f"graphql error: {body['errors']}")
    return body["data"]


def main():
    content = json.load(open(CONTENT))
    data = gql(
        """query($login:String!){ user(login:$login){
             contributionsCollection{ contributionCalendar{ totalContributions
               weeks{ contributionDays{ date contributionCount weekday } } } } } }""",
        login=USER,
    )
    cal = data["user"]["contributionsCollection"]["contributionCalendar"]
    days = [
        {"date": d["date"], "count": d["contributionCount"], "weekday": d["weekday"]}
        for w in cal["weeks"]
        for d in w["contributionDays"]
    ]

    repos = {}
    for slug in sorted({p["repo"] for p in content["projects"]} | {content["tiles"][0]["repo"]}):
        owner, name = slug.split("/")
        try:
            r = gql(
                "query($o:String!,$n:String!){ repository(owner:$o,name:$n){ stargazerCount forkCount isPrivate } }",
                o=owner, n=name,
            )["repository"]
        except SystemExit:
            r = None
        repos[slug] = r or {"stargazerCount": 0, "forkCount": 0, "isPrivate": True}

    out = {
        "user": USER,
        "fetched": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "total": cal["totalContributions"],
        "days": days,
        "repos": repos,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=1)
    print(f"wrote data/profile.json: {out['total']} contributions, {len(days)} days, {len(repos)} repos")


if __name__ == "__main__":
    main()
