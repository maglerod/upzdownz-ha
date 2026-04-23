# UpzDownz — Home Assistant Integration

Automatically collect data from Home Assistant and push it to your [UpzDownz Metric Dashboard](https://upzdownz.com). Configure everything through the Home Assistant UI — no YAML required.

## What it does

- Collects sensor snapshots, battery levels, unavailable devices, calendar events and weather forecasts
- Pushes data to UpzDownz on a configurable schedule (1 min – 1 hour)
- Fully configured through the Home Assistant UI — no YAML needed
- Shows live sync status as diagnostic sensor entities

## Requirements

- Home Assistant 2023.9 or later
- An active UpzDownz account — [upzdownz.com](https://upzdownz.com)
- Your UpzDownz API key (found in Dashboard → Settings → API)

## Getting started

After installation, go to **Settings → Devices & Services → Add Integration** and search for **UpzDownz**.
