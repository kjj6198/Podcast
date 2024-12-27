import fs from "fs";
import { parser } from "rss-parser";

const RSS_FEED_URL = process.env.RSS_FEED_URL; // Replace with your RSS feed URL
const OUTPUT_DIR = "./episodes"; // Directory to save the markdown files

async function fetchRSS() {
  const response = await axios.get(RSS_FEED_URL);
  return response.data;
}

async function parseRSS(rss) {
  const feed = await parser.parseString(rss);
  return feed.items;
}

function generateMarkdown(episode) {
  const { title, pubDate, description } = episode;
  const filename = `${title}.md`;
  const content = `---
title: ${title}
date: ${pubDate}
description: ${description}
---

${description}
`;

  fs.writeFileSync(`${OUTPUT_DIR}/${filename}`, content);
}

async function main() {
  const rss = await fetchRSS();
  const episodes = await parseRSS(rss);

  if (!fs.existsSync(OUTPUT_DIR)) {
    fs.mkdirSync(OUTPUT_DIR);
  }

  for (const episode of episodes) {
    generateMarkdown(episode);
  }
}

main().catch(console.error);
