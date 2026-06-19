# Podcast Reader

A Python script to download podcast episodes from RSS feeds, organize them by album, and update MP3 metadata.

## Features

- ✅ Parses RSS/Atom podcast feeds
- ✅ Downloads MP3 episodes with progress tracking
- ✅ **Automatically creates album-specific directories**
- ✅ **Saves the original `feed.xml` locally**
- ✅ Renames files using `S{season}E{episode}_{title}.mp3` convention
- ✅ Updates ID3 tags (Title, Artist, Album, Date, Track, Genre, Description)
- ✅ Debug mode to preview episodes without downloading
- ✅ Skips already downloaded episodes
- ✅ Date filtering to only download episodes newer than a specific date
- ✅ Configurable episode limit

## Installation

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python podcast_reader.py --feed https://feeds.acast.com/public/shows/63a2074753e78800112ac3db
```

### Options

| Option | Short | Description | Default |
|--------|-------|-------------|---------|
| `--feed` | `-f` | RSS feed URL (required) | - |
| `--output` | `-o` | Base directory for podcasts | `./podcasts` |
| `--max-episodes` | `-m` | Max episodes to download (0=all) | `0` |
| `--artist` | `-a` | Artist name for ID3 tags | `Unknown Artist` |
| `--since` | `-s` | Only download episodes newer than this date (YYYY-MM-DD) | None |
| `--debug` | `-d` | Preview without downloading | `False` |

### Examples

**Download all episodes:**
```bash
python podcast_reader.py -f https://feeds.acast.com/public/shows/63a2074753e78800112ac3db
```

**Download only 10 episodes:**
```bash
python podcast_reader.py -f URL -m 10
```

**Custom base folder:**
```bash
python podcast_reader.py -f URL -o ./my_collection
```

**Download only episodes from the last month:**
```bash
python podcast_reader.py -f URL --since 2023-10-01
```

**Debug run (preview only):**
```bash
python podcast_reader.py -f URL -d
```

## Directory Structure

The script automatically organizes downloads by podcast name:

```
./podcasts/
└── Backstage_at_the_Vinyl_Cafe/
    ├── feed.xml
    ├── S07E23_Summer_Adventures_MacCaulays_Mountain.mp3
    ├── S07E22_Autumn_Stories.mp3
    ├── S07E21_Winter_Wonderland.mp3
    └── ...
```

## File Naming Convention

Files are named using this pattern:
```
S{season}E{episode}_{title}.mp3
```

Example: `S07E23_Summer_Adventures_MacCaulays_Mountain.mp3`

If season/episode info is unavailable, falls back to:
```
YYYY-MM-DD_{title}.mp3
```

## Metadata Fields Updated

| Field | Source |
|-------|--------|
| **Title** | Episode title |
| **Artist** | Configured artist (default: *Unknown Artist*) |
| **Album** | Podcast title |
| **Date** | Episode publish date |
| **Track** | Episode number |
| **Genre** | "Podcast" |
| **Description** | Episode summary (HTML stripped) |

## Dependencies

- **feedparser** - RSS/Atom feed parsing
- **mutagen** - Audio metadata manipulation
- **requests** - HTTP downloads with progress

## Notes

- The script will skip episodes that already exist in the output directory
- Partial downloads are automatically cleaned up on failure
- HTML tags are stripped from descriptions before saving to metadata
- Progress is shown during downloads
- The original RSS feed is saved as `feed.xml` inside the album folder for reference

## License

This project is licensed under the [MIT License](LICENSE).
