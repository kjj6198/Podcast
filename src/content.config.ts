import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const episodes = defineCollection({
  loader: glob({ pattern: "./src/data/episodes/*.md" }),
  schema: z.object({ episode: z.number() }),
});

export const collections = { episodes };
