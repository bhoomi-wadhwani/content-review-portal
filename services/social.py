"""
Social media auto-posting service.

Set the relevant env vars to enable each platform:
  Twitter/X  — TWITTER_API_KEY, TWITTER_API_SECRET,
                TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET
  Instagram  — INSTAGRAM_ACCESS_TOKEN, INSTAGRAM_ACCOUNT_ID
  LinkedIn   — LINKEDIN_ACCESS_TOKEN, LINKEDIN_AUTHOR_URN
"""

import json
import os
from pathlib import Path


def post_on_approval(submission) -> None:
    """Called when a submission is approved. Posts to selected platforms and
    stores the results back on submission.social_posted (JSON string)."""
    targets = [t.strip() for t in (submission.social_targets or "").split(",") if t.strip()]
    if not targets:
        return

    file_path = None
    if submission.watermarked_path:
        from flask import current_app
        file_path = str(Path(current_app.config["UPLOAD_FOLDER"]) / submission.watermarked_path)

    caption = submission.social_caption or submission.filename
    results = {}

    for platform in targets:
        try:
            if platform == "twitter":
                results["twitter"] = _post_twitter(caption, file_path, submission.file_type)
            elif platform == "instagram":
                results["instagram"] = _post_instagram(caption, file_path)
            elif platform == "linkedin":
                results["linkedin"] = _post_linkedin(caption, file_path)
            else:
                results[platform] = {"ok": False, "error": "Unknown platform"}
        except Exception as exc:
            results[platform] = {"ok": False, "error": str(exc)}

    submission.social_posted = json.dumps(results)


# ── Twitter / X ────────────────────────────────────────────────────────────

def _post_twitter(caption: str, file_path: str | None, file_type: str) -> dict:
    import tweepy

    auth = tweepy.OAuth1UserHandler(
        os.environ["TWITTER_API_KEY"],
        os.environ["TWITTER_API_SECRET"],
        os.environ["TWITTER_ACCESS_TOKEN"],
        os.environ["TWITTER_ACCESS_SECRET"],
    )
    api_v1 = tweepy.API(auth)
    client  = tweepy.Client(
        consumer_key=os.environ["TWITTER_API_KEY"],
        consumer_secret=os.environ["TWITTER_API_SECRET"],
        access_token=os.environ["TWITTER_ACCESS_TOKEN"],
        access_token_secret=os.environ["TWITTER_ACCESS_SECRET"],
    )

    media_id = None
    if file_path and Path(file_path).exists():
        try:
            if file_type.startswith("image/"):
                media = api_v1.media_upload(filename=file_path)
                media_id = media.media_id
            elif file_type.startswith("video/"):
                media = api_v1.media_upload(filename=file_path, chunked=True, media_category="tweet_video")
                media_id = media.media_id
        except Exception:
            # Free tier doesn't support media upload — fall back to text-only tweet
            pass

    kwargs = {"text": caption}
    if media_id:
        kwargs["media_ids"] = [media_id]

    resp = client.create_tweet(**kwargs)
    tweet_id = resp.data["id"]
    return {"ok": True, "url": f"https://x.com/i/web/status/{tweet_id}"}


# ── Instagram (Meta Graph API) ──────────────────────────────────────────────

def _post_instagram(caption: str, file_path: str | None) -> dict:
    import requests

    token      = os.environ["INSTAGRAM_ACCESS_TOKEN"]
    account_id = os.environ["INSTAGRAM_ACCOUNT_ID"]

    if not file_path or not Path(file_path).exists():
        raise ValueError("Instagram requires a media file")

    # Step 1: create media container
    container = requests.post(
        f"https://graph.facebook.com/v19.0/{account_id}/media",
        params={
            "image_url": file_path,   # must be a public URL in production
            "caption": caption,
            "access_token": token,
        },
    ).json()
    if "error" in container:
        raise RuntimeError(container["error"]["message"])

    # Step 2: publish
    publish = requests.post(
        f"https://graph.facebook.com/v19.0/{account_id}/media_publish",
        params={"creation_id": container["id"], "access_token": token},
    ).json()
    if "error" in publish:
        raise RuntimeError(publish["error"]["message"])

    return {"ok": True, "id": publish.get("id")}


# ── LinkedIn ────────────────────────────────────────────────────────────────

def _post_linkedin(caption: str, file_path: str | None) -> dict:
    import requests

    token      = os.environ["LINKEDIN_ACCESS_TOKEN"]
    author_urn = os.environ["LINKEDIN_AUTHOR_URN"]   # e.g. "urn:li:person:XXXX"

    payload = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": caption},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    resp = requests.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
    )
    resp.raise_for_status()
    return {"ok": True, "id": resp.headers.get("x-restli-id")}
