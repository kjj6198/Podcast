# 八百屋 Boys

Website for [八百屋 Boys](https://yaoyaboys.com), a Mandarin podcast by Kalan and Mooly, two software engineers working in Tokyo and Fukuoka. We talk about life, careers, and tech in Japan.

Built with Astro and Tailwind CSS. Every page reads the podcast RSS feed at build time, so a new episode shows up on the next deploy. To replace the feed's show notes for an episode, add `src/data/episodes/<number>.md` with `episode: <number>` in the frontmatter.

## Development

Set `RSS_FEED_URL` to the podcast feed, then:

```sh
bun install
bun run dev
```

## Transcripts

Episode pages show a summary, chapters and a transcript that follows playback. Each episode's data lives in `src/data/transcripts/<number>.json`. `pipeline/transcribe.py` creates these files locally:

1. It downloads the episode MP3 from the feed.
2. [Breeze-ASR-25](https://huggingface.co/MediaTek-Research/Breeze-ASR-25) transcribes it with word timings, through faster-whisper.
3. WeSpeaker voice embeddings over 1.5 second windows are clustered into two voices, and each line gets the voice that speaks most of it.
4. Claude corrects the text in batches of 60 lines without merging or splitting them, then writes the summary and chapters.
5. Voices are matched across episodes, and Claude's reading of who addresses whom decides which voice is Kalan.

The pipeline needs [uv](https://docs.astral.sh/uv/), FFmpeg, a signed in [Claude Code](https://code.claude.com/docs/en/overview) CLI and the Breeze-ASR-25 weights converted to CTranslate2 at `~/.cache/podcast-cut/breeze-asr-25-ct2`. Every stage caches its output in `.context/pipeline/`, so a rerun only does what is missing.

```sh
cd pipeline
uv run python transcribe.py 15              # one episode on an idle GPU
uv run python transcribe.py --device cpu    # every episode without a transcript, on CPU
```

With `--device cuda`, the script waits before each episode until the GPU is idle. Two workers, one per device, can run at once and never take the same episode.

## TODO

- Fine-tune show notes
