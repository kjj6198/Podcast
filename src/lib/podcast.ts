import Parser from "rss-parser";

export interface Episode {
  number: number;
  title: string;
  publishedAt: Date;
  durationSeconds: number;
  mp3: string;
  link: string;
  summary: string;
  notesHtml: string;
}

export interface Show {
  title: string;
  image: string;
  link: string;
  feedUrl: string;
  episodes: Episode[];
}

const SOUNDON_FOOTER = /(<br\s*\/?>\s*)*--\s*(<br\s*\/?>\s*)*Hosting provided by[\s\S]*?(?=<\/p>|$)/i;

function cleanNotes(html: string) {
  return html
    .replace(SOUNDON_FOOTER, "")
    .replace(/^<p>(\s*<br\s*\/?>)+/i, "<p>")
    .replace(/(<\/ul>)(\s*<br\s*\/?>)+/gi, "$1");
}

function cleanSummary(text: string) {
  return text.split(/\n\s*--\s*\n/)[0].trim();
}

async function loadShow(): Promise<Show> {
  const feedUrl = import.meta.env.RSS_FEED_URL;
  const feed = await new Parser().parseURL(feedUrl);

  const episodes = feed.items
    .map((item) => ({
      number: Number(item.itunes?.episode ?? 0),
      title: (item.title ?? "").replace(/^EP\d+\s*[|｜]\s*/, ""),
      publishedAt: new Date(item.pubDate!),
      durationSeconds: Number(item.itunes?.duration ?? 0),
      mp3: item.enclosure!.url,
      link: item.link!,
      summary: cleanSummary(item.contentSnippet ?? ""),
      notesHtml: cleanNotes(item["content:encoded"] ?? item.content ?? ""),
    }))
    .sort((a, b) => b.number - a.number);

  return {
    title: feed.title!,
    image: feed.image?.url ?? feed.itunes?.image ?? "",
    link: episodes[0].link.split("/episodes/")[0],
    feedUrl,
    episodes,
  };
}

let show: Promise<Show> | undefined;

export function getShow() {
  show ??= loadShow();
  return show;
}

const dateFormat = new Intl.DateTimeFormat("zh-TW", {
  year: "numeric",
  month: "long",
  day: "numeric",
  timeZone: "Asia/Tokyo",
});

export const formatDate = (date: Date) => dateFormat.format(date);

export const formatDuration = (seconds: number) => `${Math.round(seconds / 60)} 分鐘`;
