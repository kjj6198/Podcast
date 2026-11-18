# 八百屋 Boys

Website for [八百屋 Boys](https://yaoyaboys.com), a Mandarin podcast by Kalan and Mooly, two software engineers working in Tokyo and Fukuoka. We talk about life, careers, and tech in Japan.

Built with Astro and Tailwind CSS. Every page reads the podcast RSS feed at build time, so a new episode shows up on the next deploy. To replace the feed's show notes for an episode, add `src/data/episodes/<number>.md` with `episode: <number>` in the frontmatter.

## Development

Set `RSS_FEED_URL` to the podcast feed, then:

```sh
bun install
bun run dev
```

## TODO

- Fine-tune show notes
- Add subtitles and AI summaries
