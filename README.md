# Content Review Portal

A web app where you can send clients a private link to review content — they can approve it, request changes, or reject it. Built as a take-home project.

**Live:** https://content-review-portal.onrender.com

---

## What it does

- Upload content (image, video, PDF) for a specific client
- A unique review link gets generated and shared with the client
- Client opens the link, views the watermarked content and makes a decision
- For videos — client can pause at any moment and drop a comment pinned to that exact timestamp
- Once a decision is made, the team gets an email notification
- On approval, it can auto-post the content to Twitter/X, Instagram or LinkedIn

---

## Stack

**Flask** — handles all the routing, form submissions and page rendering. Kept it lightweight since this didn't need a heavy framework.

**SQLAlchemy + SQLite** — SQLAlchemy is the ORM so all database operations are in Python, no raw SQL. SQLite is the database — simple file-based DB, good enough for this scale.

**Pillow** — used for watermarking images. Lets you open an image, draw text or overlay on top of it and save it back.

**ReportLab** — used for watermarking PDFs. Pillow can't touch PDFs so ReportLab handles generating a watermark layer that gets stamped onto the PDF pages.

**Flask-Mail** — sends the email notification to the team when a client makes a decision. Plugs into Flask's app context so it picks up SMTP config from env vars automatically.

**Tweepy** — the Python wrapper for the Twitter/X API. Used to auto-post approved content as a tweet. Media upload needs a paid API tier so text-only tweets work on free.

**Gunicorn** — the production WSGI server. Flask's built-in server isn't meant for production, Gunicorn is what actually serves the app on Render.

**Render** — where the app is hosted. Free tier, so SQLite resets on every redeploy (not ideal for production but fine for a demo).

**UptimeRobot** — pings the app every 5 mins so Render doesn't spin it down due to inactivity on the free tier.

---

## Social media auto-post

The code supports posting to Twitter/X, Instagram and LinkedIn on approval. Each platform's logic is in `services/social.py`. To actually use it the app needs real API credentials set as env vars — the placeholders are in the code, just needs the keys wired in.

---

## Models

- `Client` — stores client name and email
- `Submission` — the uploaded file, its review status, client comment, social targets
- `VideoComment` — timestamped comments left by the client on a video, each storing the second and the comment text
