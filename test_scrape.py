#!/usr/bin/env python3
import urllib.request, http.cookiejar, urllib.parse, sys, re

cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

# GET /login
r1 = opener.open("http://localhost:5000/login")
print("GET /login:", r1.status)

# POST /login
data = urllib.parse.urlencode({"username": "admin", "password": "magochic2026"}).encode()
r2 = opener.open("http://localhost:5000/login", data=data)
print("POST /login:", r2.status, r2.reason)
print("Final URL:", r2.url)

body = r2.read().decode()
text = re.sub(r'<[^>]+>', ' ', body)
text = re.sub(r'\s+', ' ', text)

if "invalid" in text.lower() or "contrase" in text.lower() or "incorrecto" in text.lower():
    print("LOGIN FAILED:", text[:300])
else:
    print("LOGIN OK - proceeding to scrape")

# GET /scrape
r3 = opener.open("http://localhost:5000/scrape")
print("Scrape status:", r3.status, r3.reason)
body3 = r3.read().decode()
text3 = re.sub(r'<[^>]+>', ' ', body3)
text3 = re.sub(r'\s+', ' ', text3)
print("Scrape response:", text3[:500])
