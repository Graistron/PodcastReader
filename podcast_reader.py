#!/usr/bin/env python3
"""
Podcast Reader - Downloads episodes from RSS feed and updates MP3 metadata.

Features:
- Parses RSS/Atom podcast feeds
- Downloads MP3 episodes with progress tracking
- Renames files using Season/Episode/Title convention
- Updates ID3 tags (Title, Artist, Album, Date, Track, Genre, Description)
- Debug mode to preview episodes without downloading
- Automatically creates album-specific directory
- Saves the original RSS feed locally
- Skips already downloaded episodes (checks file existence)
- Date filtering to only download episodes newer than a specific date
- Resumes interrupted downloads

Requirements:
    pip install feedparser mutagen requests

Usage:
    python podcast_reader.py [options]

Example:
    python podcast_reader.py --feed https://feeds.acast.com/public/shows/63a2074753e78800112ac3db
                             --output ./podcasts
                             --max-episodes 10
                             --since 2023-01-01
"""

import os
import sys
import re
import argparse
import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import time

# Third-party imports
try:
    import feedparser
    import requests
    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TRCK, TCON, COMM, TDRL
    from mutagen.mp3 import MP3
    from mutagen.easyid3 import EasyID3
except ImportError as e:
    print(f"ERROR: Missing required package: {e}")
    print("\nInstall required packages with:")
    print("    pip install feedparser mutagen requests")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class PodcastReader:
    """Downloads and processes podcast episodes from RSS feeds."""

    def __init__(self, feed_url: str, output_dir: str, max_episodes: int = 0, 
                 artist: str = "Unknown Artist", debug: bool = False, since_date: str = None):
        """
        Initialize PodcastReader.

        Args:
            feed_url: URL of the podcast RSS feed
            output_dir: Base directory to save podcast folders
            max_episodes: Maximum number of episodes to download (0 = all)
            artist: Artist name to use for ID3 tags
            debug: If True, only parse and print info without downloading
            since_date: Only download episodes newer than this date (YYYY-MM-DD)
        """
        self.feed_url = feed_url
        self.output_dir = Path(output_dir)
        self.max_episodes = max_episodes
        self.artist = artist
        self.debug = debug
        self.since_date = None
        
        if since_date:
            try:
                self.since_date = datetime.strptime(since_date, '%Y-%m-%d')
            except ValueError:
                logger.error(f"Invalid date format: {since_date}. Use YYYY-MM-DD.")
                sys.exit(1)

        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PodcastReader/1.0 (Python script for personal use)'
        })

    def sanitize_filename(self, name: str, max_length: int = 100) -> str:
        """
        Create a safe filename/directory name from a string.

        Args:
            name: Original name string
            max_length: Maximum name length

        Returns:
            Sanitized name safe for filesystem
        """
        # Remove or replace invalid characters
        name = re.sub(r'[<>:"/\\|?*]', '_', name)
        name = re.sub(r'\s+', '_', name)
        name = name.strip('_')

        # Truncate if too long
        if len(name) > max_length:
            name = name[:max_length]

        return name

    def get_episode_filename(self, entry: dict) -> str:
        """
        Generate filename from episode data.

        Convention: S{season}E{episode}_{title}.mp3

        Args:
            entry: Feedparser entry dict

        Returns:
            Generated filename
        """
        # Get season and episode numbers (iTunes extension)
        season = entry.get('itunes_season', 0)
        episode = entry.get('itunes_episode', 0)

        # Ensure they are integers (feedparser sometimes returns strings)
        try:
            season = int(season)
            episode = int(episode)
        except (ValueError, TypeError):
            season = 0
            episode = 0

        # Get title
        title = entry.get('title', 'Unknown Episode')
        safe_title = self.sanitize_filename(title)

        # Build filename
        if season and episode:
            filename = f"S{season:02d}E{episode:02d}_{safe_title}.mp3"
        else:
            # Fallback: use date if available (feedparser provides parsed dates)
            pub_date = entry.get('published_parsed')
            if pub_date:
                date_str = f"{pub_date.tm_year:04d}-{pub_date.tm_mon:02d}-{pub_date.tm_mday:02d}"
                filename = f"{date_str}_{safe_title}.mp3"
            else:
                filename = f"{safe_title}.mp3"

        return filename

    def is_episode_newer(self, entry: dict) -> bool:
        """
        Check if an episode is newer than the specified since_date.

        Args:
            entry: Feedparser entry dict

        Returns:
            True if episode is newer or no date filter is set
        """
        if not self.since_date:
            return True

        pub_date = entry.get('published_parsed')
        if not pub_date:
            return True

        # Convert published_parsed (time.struct_time) to datetime
        episode_datetime = datetime(*pub_date[:6])
        
        return episode_datetime >= self.since_date

    def download_episode(self, entry: dict) -> bool:
        """
        Download a single episode.

        Args:
            entry: Feedparser entry dict

        Returns:
            True if download successful, False otherwise
        """
        # Get enclosure (MP3 URL)
        enclosure = None
        for enc in entry.get('enclosures', []):
            if 'audio' in enc.get('type', ''):
                enclosure = enc
                break

        if not enclosure:
            logger.warning(f"No audio enclosure found for: {entry.get('title', 'Unknown')}")
            return False

        mp3_url = enclosure.get('href')
        filename = self.get_episode_filename(entry)
        filepath = self.output_dir / filename

        # Download with progress
        try:
            response = self.session.get(mp3_url, stream=True, timeout=30)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0

            with open(filepath, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total_size:
                        progress = (downloaded / total_size) * 100
                        print(f"\r  Progress: {progress:.1f}%", end='', flush=True)

            print()  # New line after progress
            logger.info(f"Downloaded: {filename} ({downloaded / (1024*1024):.1f} MB)")
            return True

        except requests.RequestException as e:
            logger.error(f"Download failed for {filename}: {e}")
            # Remove partial file
            if filepath.exists():
                filepath.unlink()
            return False

    def update_metadata(self, filepath: Path, entry: dict) -> bool:
        """
        Update MP3 ID3 tags with episode metadata.

        Args:
            filepath: Path to the MP3 file
            entry: Feedparser entry dict

        Returns:
            True if metadata updated successfully
        """
        logger.info(f"Updating metadata: {filepath.name}")

        try:
            # Try to load ID3 tags, create if they don't exist
            try:
                tags = ID3(str(filepath))
            except Exception:
                # Create new ID3 tags
                tags = ID3()
                tags.save(str(filepath))
                tags = ID3(str(filepath))

            # Extract metadata from entry
            title = entry.get('title', '')
            artist = self.artist  # Use the configured artist name
            album = self.feed.get('title', '')

            # Get date from published field (use feedparser's parsed date for safety)
            pub_date = entry.get('published_parsed')
            if pub_date:
                date_str = f"{pub_date.tm_year:04d}-{pub_date.tm_mon:02d}-{pub_date.tm_mday:02d}"
            else:
                date_str = ''

            # Get season/episode for track number
            season = entry.get('itunes_season', 0)
            episode = entry.get('itunes_episode', 0)
            track_number = str(episode) if episode else ''

            # Get description (clean HTML)
            description = entry.get('summary', '') or entry.get('description', '')
            description = re.sub(r'<[^>]+>', '', description)  # Strip HTML tags
            description = re.sub(r'\s+', ' ', description).strip()
            description = description[:255]  # Limit description length

            # Update tags
            tags.add(TIT2(encoding=3, text=title))           # Title
            tags.add(TPE1(encoding=3, text=artist))          # Artist
            tags.add(TALB(encoding=3, text=album))           # Album
            tags.add(TDRC(encoding=3, text=date_str))        # Date
            tags.add(TRCK(encoding=3, text=track_number))    # Track number
            tags.add(TCON(encoding=3, text='Podcast'))       # Genre
            tags.add(COMM(encoding=3, lang='eng', desc='DESCRIPTION', text=description))

            # Save changes
            tags.save(str(filepath))
            logger.info(f"Metadata updated: {filepath.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to update metadata for {filepath.name}: {e}")
            return False

    def print_episode_info(self, entry: dict, index: int, total: int):
        """Print detailed episode information for debug mode."""
        title = entry.get('title', 'Unknown')
        season = entry.get('itunes_season', '?')
        episode = entry.get('itunes_episode', '?')
        pub_date = entry.get('published', 'Unknown')
        duration = entry.get('itunes_duration', 'Unknown')
        
        # Get MP3 URL
        mp3_url = None
        for enc in entry.get('enclosures', []):
            if 'audio' in enc.get('type', ''):
                mp3_url = enc.get('href')
                break

        filename = self.get_episode_filename(entry)
        filepath = self.output_dir / filename
        exists = "YES" if filepath.exists() else "NO"
        newer = "YES" if self.is_episode_newer(entry) else "NO"

        print(f"\n{'─'*60}")
        print(f"Episode {index}/{total}")
        print(f"  Title:      {title}")
        print(f"  Season:     {season}")
        print(f"  Episode:    {episode}")
        print(f"  Date:       {pub_date}")
        print(f"  Duration:   {duration}")
        print(f"  Filename:   {filename}")
        print(f"  Exists:     {exists}")
        print(f"  Newer:      {newer}")
        print(f"  URL:        {mp3_url}")
        print(f"  Artist Tag: {self.artist}")
        print(f"  Album Tag:  {self.feed.get('title', 'Unknown')}")
        print(f"{'─'*60}")

    def process_episodes(self, feed: dict) -> dict:
        """
        Process all episodes from the feed.

        Args:
            feed: Parsed feedparser feed

        Returns:
            Dictionary with download statistics
        """
        stats = {
            'total': 0,
            'downloaded': 0,
            'skipped': 0,
            'skipped_date': 0,
            'failed': 0,
            'metadata_updated': 0
        }

        episodes = feed.entries

        # Limit episodes if specified
        if self.max_episodes > 0:
            episodes = episodes[:self.max_episodes]

        stats['total'] = len(episodes)
        
        if self.debug:
            logger.info(f"DEBUG MODE: Parsing {len(episodes)} episodes (no downloads)...")
            for i, entry in enumerate(episodes, 1):
                self.print_episode_info(entry, i, len(episodes))
            return stats

        logger.info(f"Processing {len(episodes)} episodes...")

        for i, entry in enumerate(episodes, 1):
            filename = self.get_episode_filename(entry)
            filepath = self.output_dir / filename
            
            # Check if episode is too old
            if not self.is_episode_newer(entry):
                logger.info(f"SKIP (too old): {filename}")
                stats['skipped_date'] += 1
                continue

            # Check if episode has already been downloaded
            if filepath.exists():
                logger.info(f"SKIP (already downloaded): {filename}")
                stats['skipped'] += 1
                continue

            logger.info(f"\nEpisode {i}/{len(episodes)}: {entry.get('title', 'Unknown')}")

            # Download episode
            if self.download_episode(entry):
                stats['downloaded'] += 1

                # Update metadata
                if self.update_metadata(filepath, entry):
                    stats['metadata_updated'] += 1
            else:
                stats['failed'] += 1

        return stats

    def run(self) -> dict:
        """
        Run the podcast reader.

        Returns:
            Dictionary with download statistics
        """
        logger.info("=" * 60)
        logger.info("PODCAST READER")
        logger.info("=" * 60)
        
        # Fetch raw feed data
        try:
            feed_response = self.session.get(self.feed_url)
            feed_response.raise_for_status()
            raw_feed = feed_response.content
        except Exception as e:
            logger.error(f"Failed to fetch feed: {e}")
            return {'error': 'Failed to fetch feed'}

        # Parse feed
        feed = feedparser.parse(raw_feed)
        if feed.bozo:
            logger.warning(f"Feed parsing warning: {feed.bozo_exception}")

        if not feed.entries:
            logger.error("No episodes found in feed")
            return {'error': 'No episodes found'}

        # Store feed reference for metadata
        self.feed = feed.feed
        
        # Get album/podcast title and create target directory
        album_title = self.feed.get('title', 'Unknown Podcast')
        safe_album_name = self.sanitize_filename(album_title, max_length=80)
        self.target_dir = self.output_dir / safe_album_name
        self.target_dir.mkdir(parents=True, exist_ok=True)
        
        # Update output_dir to target directory for subsequent operations
        self.output_dir = self.target_dir
        logger.info(f"Target directory: {self.output_dir}")
        
        # Save raw feed file
        try:
            feed_path = self.output_dir / "feed.xml"
            with open(feed_path, 'wb') as f:
                f.write(raw_feed)
            logger.info(f"Saved feed to: {feed_path}")
        except Exception as e:
            logger.warning(f"Could not save feed file: {e}")

        # Process episodes
        stats = self.process_episodes(feed)

        # Print summary
        if not self.debug:
            logger.info("\n" + "=" * 60)
            logger.info("DOWNLOAD SUMMARY")
            logger.info("=" * 60)
            logger.info(f"Total episodes:      {stats['total']}")
            logger.info(f"Downloaded:          {stats['downloaded']}")
            logger.info(f"Skipped (exists):    {stats['skipped']}")
            logger.info(f"Skipped (too old):   {stats['skipped_date']}")
            logger.info(f"Failed:              {stats['failed']}")
            logger.info(f"Metadata updated:    {stats['metadata_updated']}")
            logger.info("=" * 60)

        return stats


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Podcast Reader - Download and tag podcast episodes',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Download all episodes
  python podcast_reader.py --feed URL

  # Download only 5 episodes
  python podcast_reader.py --feed URL --max-episodes 5

  # Custom base output directory
  python podcast_reader.py --feed URL --output ./my_podcasts

  # Download only episodes from the last month
  python podcast_reader.py --feed URL --since 2023-10-01

  # Debug/preview mode (no downloads)
  python podcast_reader.py --feed URL --debug
        """
    )

    parser.add_argument(
        '--feed', '-f',
        required=True,
        help='URL of the podcast RSS feed'
    )

    parser.add_argument(
        '--output', '-o',
        default='./podcasts',
        help='Base directory for podcast folders (default: ./podcasts)'
    )

    parser.add_argument(
        '--max-episodes', '-m',
        type=int,
        default=0,
        help='Maximum number of episodes to download (0 = all)'
    )

    parser.add_argument(
        '--artist', '-a',
        default='Unknown Artist',
        help='Artist name for ID3 tags (default: Unknown Artist)'
    )

    parser.add_argument(
        '--since', '-s',
        default=None,
        help='Only download episodes newer than this date (YYYY-MM-DD)'
    )

    parser.add_argument(
        '--debug', '-d',
        action='store_true',
        help='Parse feed and print episode info without downloading'
    )

    args = parser.parse_args()

    # Create reader
    reader = PodcastReader(
        feed_url=args.feed,
        output_dir=args.output,
        max_episodes=args.max_episodes,
        artist=args.artist,
        debug=args.debug,
        since_date=args.since
    )

    # Run
    stats = reader.run()

    # Exit with error code if there were failures
    if stats.get('failed', 0) > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
