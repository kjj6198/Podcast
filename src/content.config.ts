import { defineCollection, z } from "astro:content";

import { glob } from "astro/loaders";

const episodes = defineCollection({
  loader: glob({
    pattern: "./src/data/episodes/*.md",
  }),
  schema: z.object({
    title: z.string(),
    date: z.string(),
    link: z.string(),
    mp3: z.string(),
    episode: z.number(),
    duration: z.number(),
    image: z.string(),
  }),
});

export const collections = { episodes };
