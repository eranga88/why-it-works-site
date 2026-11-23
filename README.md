# Why It Works – website

The website for the [Why It Works](https://www.youtube.com/@HeresWhyItWorks) YouTube channel.
New uploads show up on the site automatically.

## How it updates itself

1. Every 3 hours, GitHub Actions runs `scripts/update_videos.py` ([workflow](.github/workflows/update-videos.yml)).
2. The script reads the channel's public YouTube feed and **adds** any new videos to `data/videos.json`.
   It never deletes anything, so the list keeps growing.
3. If something changed, the workflow commits the file.
4. `scripts/build_site.py` turns the list into plain HTML pages in `_site/`, and the workflow publishes them to GitHub Pages.

## What's built for search engines (SEO)

- **A page per video** at `/videos/<title>/`, with its own title, meta description, full description text,
  related videos and newer/older links. The address is fixed the first time a video is seen, so links never break.
- **A page per topic** at `/topics/<topic>/` with a written intro, plus `/topics/` listing them all.
- **Structured data:** `VideoObject` on every video page (so it can show in Google's video results),
  `BreadcrumbList`, `CollectionPage` on topic pages, and `Organization` + `WebSite` on the homepage linked to the YouTube channel.
- **`sitemap.xml`** with Google video-sitemap entries for every video, and **`robots.txt`** pointing to it. Both update on every run.
- **Canonical links, Open Graph and Twitter cards** on every page, so shared links show the video thumbnail.
- **Fast pages:** the YouTube player loads only when someone presses play. All content is in the HTML, so it works without JavaScript.

### After the site is live

1. Add the site in [Google Search Console](https://search.google.com/search-console) and submit `https://<your-site>/sitemap.xml`.
   Do the same in [Bing Webmaster Tools](https://www.bing.com/webmasters) (it can import from Search Console).
2. Put the website link in your YouTube channel's links and in your video descriptions.
3. Longer YouTube descriptions = more text on each video page = better ranking. Aim for 2–3 sentences at least.

## One-time setup on GitHub

1. Create a new repository on GitHub, for example `why-it-works-site`, and push this folder to its `main` branch.
2. In the repo go to **Settings → Pages → Build and deployment → Source** and pick **GitHub Actions**.
3. Go to **Actions → Update videos & deploy site → Run workflow** to publish it the first time.
   The site appears at `https://<your-username>.github.io/why-it-works-site/`.

## Optional: import every old video

YouTube's feed only lists the newest 15 uploads. To pull in the whole back catalogue:

1. Create a free **YouTube Data API v3** key in [Google Cloud Console](https://console.cloud.google.com/apis/library/youtube.googleapis.com).
2. In the repo: **Settings → Secrets and variables → Actions → New repository secret**,
   name `YOUTUBE_API_KEY`, paste the key.
3. Run the workflow again. All uploads are added, and view counts stay fresh on every run.

## Changing things

- **Topic of a video:** edit its `"topic"` in `data/videos.json` and add `"topic_locked": true` so the job won't change it back.
  Topics: `phone`, `security`, `ai`, `space`, `budget`, `how`.
- **Topic rules:** the keyword lists are at the top of `scripts/update_videos.py` (`TOPICS`).
- **How often it checks:** change the `cron` line in the workflow.
- **Custom domain:** buy a domain, then in the repo add two Actions **variables** (Settings → Secrets and variables → Actions → Variables):
  `SITE_URL` = `https://yourdomain.com` and `CUSTOM_DOMAIN` = `yourdomain.com`. Then set the same domain in Settings → Pages → Custom domain.
- **Topic page intros:** edit `TOPIC_INTROS` in `scripts/build_site.py`.

## Run locally

```bash
python3 scripts/update_videos.py              # refresh data/videos.json
SITE_URL=http://localhost:8000 python3 scripts/build_site.py   # build pages into _site/
python3 -m http.server 8000 -d _site          # then open http://localhost:8000
```
