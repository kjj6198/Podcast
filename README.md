# 八百屋 Boys

Website for [八百屋 Boys](https://yaoyaboys.com), a Mandarin podcast by Kalan and Mooly, two software engineers working in Tokyo and Fukuoka. We talk about life, careers, and tech in Japan.

Built with Astro and Tailwind CSS. The home page lists episodes straight from the podcast RSS feed. A weekly GitHub Action runs `scripts/parsePodcast.js`, which writes one markdown file per new episode to `src/data/episodes/` for the episode pages.

## Development

Set `RSS_FEED_URL` to the podcast feed, then:

```sh
bun install
bun run dev
```

## TODO

- Fine-tune show notes
- Add subtitles and AI summaries
