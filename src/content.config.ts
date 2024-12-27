import { defineCollection, z } from "astro:content";

import { glob } from "astro/loaders";

const episodes = defineCollection({
  loader: glob({
    pattern: "**/*.md",
    base: "src/data/episodes",
  }),
  schema: z.object({
    title: z.string(),
    date: z.string(),
    description: z.string(),
    link: z.string(),
    mp3: z.string(),
    summary: z.string(),
    episode: z.string(),
    duration: z.string(),
    image: z.string(),
  }),
});

export const collections = { episodes };
