/**
 * This script is used to parse the RSS feed and generate the markdown files for each episode.
 */
const fs = require("fs");
const Parser = require("rss-parser");

const parser = new Parser();
const RSS_FEED_URL = process.env.RSS_FEED_URL;
const OUTPUT_DIR = "./src/data/episodes"; // Directory to save the markdown files

function generateMarkdown(episode) {
  const { title, date, link, mp3, episode: ep, duration, image } = episode;
  const content = `---
title: ${title}
date: ${date}
link: ${link}
mp3: ${mp3}
episode: ${ep || "0"}
duration: ${duration}
image: ${image}
---

`;

  fs.writeFileSync(`${OUTPUT_DIR}/${ep || "0"}.md`, content);
}

async function main() {
  const feed = await parser.parseURL(RSS_FEED_URL);

  const episodes = feed.items.map((item) => ({
    title: item.title,
    date: new Date(item.pubDate).toLocaleDateString(),
    description: item.contentSnippet,
    link: item.link,
    mp3: item.enclosure.url,
    summary: item.itunes.summary,
    episode: item.itunes.episode,
    duration: item.itunes.duration,
    image: item.itunes.image,
  }));

  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR);
  }

  for (const episode of episodes) {
    if (!fs.existsSync(`${OUTPUT_DIR}/${episode.episode}.md`)) {
      generateMarkdown(episode);
    }
  }
}

main().catch(console.error);
