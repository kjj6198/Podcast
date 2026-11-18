import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

const episodes = defineCollection({
  loader: glob({ pattern: "./src/data/episodes/*.md" }),
  schema: z.object({ episode: z.number() }),
});

const seconds = z.number().nonnegative();

const transcripts = defineCollection({
  loader: glob({ pattern: "./src/data/transcripts/*.json" }),
  schema: z
    .object({
      episode: z.number(),
      speakers: z.array(z.string()).min(1),
      summary: z.object({
        overview: z.string(),
        points: z.array(z.string()),
        chapters: z.array(z.object({ start: seconds, title: z.string() })),
      }),
      lines: z.array(z.object({ start: seconds, end: seconds, speaker: z.string(), text: z.string() })).min(1),
    })
    .refine((t) => t.lines.every((line) => t.speakers.includes(line.speaker)), "every line needs a listed speaker"),
});

export const collections = { episodes, transcripts };
