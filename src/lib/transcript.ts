import type { CollectionEntry } from "astro:content";

export type Transcript = CollectionEntry<"transcripts">["data"];
export type TranscriptLine = Transcript["lines"][number];

export interface Turn {
  speaker: string;
  start: number;
  lines: TranscriptLine[];
}

export function toTurns(lines: TranscriptLine[]): Turn[] {
  const turns: Turn[] = [];
  for (const line of lines) {
    const last = turns.at(-1);
    if (last?.speaker === line.speaker) last.lines.push(line);
    else turns.push({ speaker: line.speaker, start: line.start, lines: [line] });
  }
  return turns;
}

const speakerTones = ["text-primary", "text-teal"];

export const speakerTone = (transcript: Transcript, speaker: string) =>
  speakerTones[transcript.speakers.indexOf(speaker) % speakerTones.length];
