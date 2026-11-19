import argparse
import ctypes
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from pydantic import BaseModel, Field, ValidationError
from typing import Literal

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".context" / "pipeline"
OUTPUT = ROOT / "src" / "data" / "transcripts"
FEED_URL = "https://feeds.soundon.fm/podcasts/19c85078-347e-4921-9941-2b41d70bad9c.xml"
ASR_MODEL = Path("~/.cache/podcast-cut/breeze-asr-25-ct2").expanduser()
EMBEDDING_MODEL = "pyannote/wespeaker-voxceleb-resnet34-LM"
HOSTS = ("Kalan", "Mooly")
ASR_PROMPT = "八百屋 Boys，Kalan、Mooly，在日本工作的軟體工程師聊日本生活、職涯與科技。"
SAMPLE_RATE = 16_000
WINDOW = 1.5
HOP = 0.75
LLM_MODEL = "sonnet"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; podcast-transcripts)"}


@dataclass
class Episode:
    number: int
    title: str
    mp3: str
    notes: str


class Word(BaseModel):
    start: float
    end: float
    text: str


class Line(BaseModel):
    start: float
    end: float
    speaker: str
    text: str


class Chapter(BaseModel):
    start: float
    title: str


class Summary(BaseModel):
    overview: str
    points: list[str] = Field(min_length=3, max_length=8)
    chapters: list[Chapter] = Field(min_length=2, max_length=12)


class SummaryReply(Summary):
    speakers: dict[Literal["A", "B"], Literal["Kalan", "Mooly", "unknown"]]
    evidence: str = ""


class CorrectedLine(BaseModel):
    id: int
    text: str


class CorrectionReply(BaseModel):
    lines: list[CorrectedLine]


class Transcript(BaseModel):
    episode: int
    speakers: list[str]
    summary: Summary
    lines: list[Line]


def read_feed() -> list[Episode]:
    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd", "content": "http://purl.org/rss/1.0/modules/content/"}
    root = ET.fromstring(urllib.request.urlopen(urllib.request.Request(FEED_URL, headers=HEADERS)).read())
    episodes = []
    for item in root.iter("item"):
        notes = re.sub(r"<[^>]+>", " ", item.findtext("content:encoded", "", ns))
        episodes.append(
            Episode(
                number=int(item.findtext("itunes:episode", "0", ns)),
                title=item.findtext("title", ""),
                mp3=item.find("enclosure").get("url"),
                notes=re.sub(r"\s+", " ", notes).split("Hosting provided by")[0].strip(" -"),
            )
        )
    return episodes


def cached(path: Path, build):
    if path.exists():
        return json.loads(path.read_text())
    path.parent.mkdir(parents=True, exist_ok=True)
    value = build()
    temporary = path.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=1))
    temporary.rename(path)
    return value


def load_audio(episode: Episode) -> np.ndarray:
    mp3 = CACHE / "audio" / f"{episode.number}.mp3"
    if not mp3.exists():
        mp3.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(episode.mp3, headers=HEADERS)) as response:
            mp3.with_suffix(".part").write_bytes(response.read())
        mp3.with_suffix(".part").rename(mp3)
    pcm = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp3), "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "-"],
        check=True,
        capture_output=True,
    ).stdout
    return np.frombuffer(pcm, dtype=np.float32)


def preload_cuda_libraries():
    for package, names in (("nvidia.cublas", ("libcublasLt.so.12", "libcublas.so.12")), ("nvidia.cudnn", ("libcudnn.so.9",))):
        spec = importlib.util.find_spec(package)
        directory = Path(next(iter(spec.submodule_search_locations))) / "lib"
        for name in names:
            ctypes.CDLL(str(directory / name), mode=ctypes.RTLD_GLOBAL)


def transcribe(audio: np.ndarray, device: str) -> list[list[dict]]:
    from faster_whisper import WhisperModel

    if device == "cuda":
        preload_cuda_libraries()
        model = WhisperModel(str(ASR_MODEL), device="cuda", compute_type="float16")
    else:
        model = WhisperModel(str(ASR_MODEL), device="cpu", compute_type="int8", cpu_threads=6)
    segments, _ = model.transcribe(
        audio,
        language="zh",
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
        condition_on_previous_text=False,
        initial_prompt=ASR_PROMPT,
    )
    result = []
    for segment in segments:
        words = [
            Word(start=round(w.start, 2), end=round(w.end, 2), text=w.word).model_dump()
            for w in segment.words or []
            if w.end > w.start
        ]
        if words:
            result.append(words)
        print(f"  asr {segment.end:7.1f}s {segment.text[:40]}", file=sys.stderr)
    return result


def speech_windows(segments: list[list[Word]], duration: float) -> list[float]:
    centers = []
    for words in segments:
        start, end = words[0].start, words[-1].end
        center = start + WINDOW / 2
        while center <= max(end - WINDOW / 2, start + WINDOW / 2):
            centers.append(min(center, duration - WINDOW / 2))
            center += HOP
    return sorted(set(round(c, 2) for c in centers))


def load_embedding_model():
    from pyannote.audio import Model

    return Model.from_pretrained(EMBEDDING_MODEL).eval()


def window_at(audio: np.ndarray, center: float, half: int) -> np.ndarray:
    start = max(0, int(center * SAMPLE_RATE) - half)
    clip = audio[start : start + 2 * half]
    return np.pad(clip, (0, 2 * half - len(clip)))


def embed(model, audio: np.ndarray, centers: list[float]) -> np.ndarray:
    import torch

    half = int(WINDOW * SAMPLE_RATE / 2)
    chunks = np.stack([window_at(audio, c, half) for c in centers])
    embeddings = []
    with torch.inference_mode():
        for batch in np.array_split(chunks, max(1, len(chunks) // 64)):
            tensor = torch.from_numpy(batch).unsqueeze(1)
            embeddings.append(model(tensor).cpu().numpy())
    vectors = np.concatenate(embeddings)
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def cluster(vectors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    from scipy.ndimage import median_filter
    from sklearn.cluster import KMeans

    labels = KMeans(n_clusters=2, n_init=10, random_state=0).fit_predict(vectors)
    for _ in range(5):
        centroids = np.stack([vectors[labels == k].mean(axis=0) for k in (0, 1)])
        centroids /= np.linalg.norm(centroids, axis=1, keepdims=True)
        labels = (vectors @ centroids.T).argmax(axis=1)
    return median_filter(labels, size=3, mode="nearest"), centroids


def assign_speakers(segments: list[list[Word]], centers: list[float], labels: np.ndarray) -> list[dict]:
    centers_arr = np.array(centers)
    lines = []
    for words in segments:
        tags = [int(labels[np.abs(centers_arr - (w.start + w.end) / 2).argmin()]) for w in words]
        runs: list[list[int]] = []
        for index, tag in enumerate(tags):
            if runs and tags[runs[-1][0]] == tag:
                runs[-1].append(index)
            else:
                runs.append([index])
        merged: list[list[int]] = []
        for run in runs:
            length = words[run[-1]].end - words[run[0]].start
            if merged and length < 1.0:
                merged[-1].extend(run)
            else:
                merged.append(run)
        for run in merged:
            speaker = max(set(tags[i] for i in run), key=lambda t: sum(words[i].end - words[i].start for i in run if tags[i] == t))
            lines.append(
                {
                    "start": words[run[0]].start,
                    "end": words[run[-1]].end,
                    "speaker": "AB"[speaker],
                    "text": "".join(words[i].text for i in run).strip(),
                }
            )
    return lines


def refine_speakers(model, audio: np.ndarray, lines: list[dict], centroids: np.ndarray) -> int:
    import torch

    changed = 0
    with torch.inference_mode():
        for line in lines:
            if line["end"] - line["start"] < 0.8:
                continue
            clip = audio[int(line["start"] * SAMPLE_RATE) : int(min(line["end"], line["start"] + 12) * SAMPLE_RATE)]
            vector = model(torch.from_numpy(np.ascontiguousarray(clip))[None, None]).numpy()[0]
            speaker = "AB"[int((centroids @ (vector / np.linalg.norm(vector))).argmax())]
            changed += speaker != line["speaker"]
            line["speaker"] = speaker
    return changed


def diarize(audio: np.ndarray, asr: list[list[dict]]) -> dict:
    model = load_embedding_model()
    segments = [[Word(**w) for w in words] for words in asr]
    centers = speech_windows(segments, len(audio) / SAMPLE_RATE)
    labels, centroids = cluster(embed(model, audio, centers))
    lines = assign_speakers(segments, centers, labels)
    changed = refine_speakers(model, audio, lines, centroids)
    share = sum(line["speaker"] == "A" for line in lines) / len(lines)
    print(f"  speakers: {len(centers)} windows, {changed} lines relabelled, A={share:.0%} of lines", file=sys.stderr)
    return {"lines": lines, "centroids": centroids.tolist()}


def ask_claude(prompt: str) -> dict:
    for attempt in range(3):
        result = subprocess.run(
            ["claude", "-p", "--model", LLM_MODEL, "--output-format", "text"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=900,
            cwd="/tmp",
        )
        match = re.search(r"\{.*\}", result.stdout, re.S)
        if result.returncode == 0 and match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        print(f"  claude attempt {attempt + 1} failed: {result.stderr[-300:]}", file=sys.stderr)
    raise RuntimeError("Claude did not return JSON")


CORRECT_PROMPT = """你是台灣中文 Podcast 逐字稿校對編輯。節目是「八百屋 Boys」，主持人是 Kalan（也叫愷開、愷愷）與 Mooly，兩位在日本東京、福岡工作的台灣軟體工程師。

本集標題：{title}
本集簡介：{notes}

以下是語音辨識的逐字稿片段，每行格式為「id<TAB>文字」。請逐行校對：
- 修正同音錯字、專有名詞、英文技術詞與日文詞（例如 JWT、local storage、おせち）
- 使用台灣繁體中文與全形標點，英文與數字前後保留半形空格
- 每一行都要補上標點：行與行常是同一句話被切開，句子在該行結束就用句號、問號或驚嘆號，句子還沒結束就用逗號，行內也要斷句
- 刪除無意義的重複與口吃，但保留口語語氣，不要改寫內容或總結
- 不要合併或拆分行，每個 id 都要輸出，順序不變

只輸出 JSON，格式：{{"lines": [{{"id": 0, "text": "..."}}]}}

{lines}"""


def correct(episode: Episode, lines: list[dict]) -> list[dict]:
    def fix(offset: int, chunk: list[dict]) -> list[str]:
        body = "\n".join(f"{offset + i}\t{line['text']}" for i, line in enumerate(chunk))
        expected = list(range(offset, offset + len(chunk)))
        for _ in range(3):
            reply = ask_claude(CORRECT_PROMPT.format(title=episode.title, notes=episode.notes[:1200], lines=body))
            try:
                corrected = CorrectionReply.model_validate(reply).lines
            except ValidationError:
                corrected = []
            if [line.id for line in corrected] == expected:
                return [line.text.strip() or original["text"] for line, original in zip(corrected, chunk)]
            print(f"  correction chunk {offset} returned wrong ids, retrying", file=sys.stderr)
        raise RuntimeError(f"correction chunk {offset} failed")

    size = 60
    chunks = [(offset, lines[offset : offset + size]) for offset in range(0, len(lines), size)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        fixed = [text for texts in pool.map(lambda args: fix(*args), chunks) for text in texts]
    return [{**line, "text": text} for line, text in zip(lines, fixed)]


SUMMARY_PROMPT = """以下是 Podcast「八百屋 Boys」的逐字稿。主持人是 Kalan（也叫愷開、愷愷）與 Mooly。逐字稿中的說話者只標成 A 與 B，每行格式為「[秒數] 說話者: 文字」。

本集標題：{title}
本集簡介：{notes}

請用台灣繁體中文輸出 JSON：
- "overview": 2 到 3 句話的本集摘要，以 Kalan 與 Mooly 的名字描述，不要用 A、B
- "points": 4 到 6 個重點，每個一句話
- "chapters": 4 到 8 個章節，"start" 是該段開始的秒數（取自逐字稿），"title" 是 15 字內的標題，第一章從 0 開始
- "speakers": 根據對話內容（自我介紹、互相稱呼）判斷 A 與 B 各是誰，例如 {{"A": "Kalan", "B": "Mooly"}}；無法判斷就填 "unknown"
- "evidence": 一句話說明判斷說話者的依據

只輸出 JSON。

{lines}"""


def summarize(episode: Episode, lines: list[dict]) -> dict:
    body = "\n".join(f"[{line['start']:.0f}] {line['speaker']}: {line['text']}" for line in lines)
    for _ in range(3):
        reply = ask_claude(SUMMARY_PROMPT.format(title=episode.title, notes=episode.notes[:1200], lines=body))
        try:
            return SummaryReply.model_validate(reply).model_dump()
        except ValidationError as error:
            print(f"  summary invalid, retrying: {error.errors()[:2]}", file=sys.stderr)
    raise RuntimeError("summary failed validation")


def name_speakers(numbers: list[int]) -> dict[int, dict[str, str]]:
    centroids = {n: np.array(json.loads((CACHE / "speakers" / f"{n}.json").read_text())["centroids"]) for n in numbers}
    flips = dict.fromkeys(numbers, False)
    reference = centroids[numbers[0]]
    for _ in range(3):
        flips = {n: float((c[::-1] * reference).sum()) > float((c * reference).sum()) for n, c in centroids.items()}
        reference = np.mean([c[::-1] if flips[n] else c for n, c in centroids.items()], axis=0)
        reference /= np.linalg.norm(reference, axis=1, keepdims=True)
    votes = np.zeros((2, 2))
    for n in numbers:
        claims = json.loads((CACHE / "summary" / f"{n}.json").read_text()).get("speakers", {})
        for label, name in claims.items():
            if name in HOSTS and label in ("A", "B"):
                votes["AB".index(label) ^ flips[n], HOSTS.index(name)] += 1
    agree, disagree = votes[0, 0] + votes[1, 1], votes[0, 1] + votes[1, 0]
    if agree == disagree:
        raise RuntimeError(f"cannot tell the hosts apart, votes {votes.tolist()}")
    group_names = HOSTS if agree > disagree else HOSTS[::-1]
    print(f"  speaker votes {votes.tolist()}, voice group 0 is {group_names[0]}", file=sys.stderr)
    names = {n: {"A": group_names[flips[n]], "B": group_names[not flips[n]]} for n in numbers}
    for n in numbers:
        claims = json.loads((CACHE / "summary" / f"{n}.json").read_text()).get("speakers", {})
        conflicts = [label for label, name in claims.items() if name in HOSTS and names[n][label] != name]
        if conflicts:
            print(f"  EP{n}: summary names {claims} but voices say {names[n]}, check this episode", file=sys.stderr)
    return names


def export(episode: Episode, lines: list[dict], summary: dict, names: dict[str, str]) -> None:
    transcript = Transcript(
        episode=episode.number,
        speakers=list(HOSTS),
        summary=Summary(overview=summary["overview"], points=summary["points"], chapters=summary["chapters"]),
        lines=[Line(**{**line, "speaker": names[line["speaker"]]}) for line in lines if line["text"]],
    )
    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / f"{episode.number}.json").write_text(
        json.dumps(transcript.model_dump(), ensure_ascii=False, indent=1) + "\n"
    )


def gpu_idle() -> bool:
    readings = []
    for _ in range(6):
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.free", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
        ).stdout.split(",")
        readings.append((int(out[0]), int(out[1])))
        time.sleep(10)
    return all(util < 15 and free > 4500 for util, free in readings)


def claim(n: int) -> bool:
    path = CACHE / "claims" / str(n)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        owner = int(path.read_text())
        os.kill(owner, 0)
        return owner == os.getpid()
    except (FileNotFoundError, ValueError, ProcessLookupError):
        path.unlink(missing_ok=True)
    try:
        with open(path, "x") as file:
            file.write(str(os.getpid()))
        return True
    except FileExistsError:
        return False


def process(episode: Episode, device: str) -> None:
    n = episode.number
    print(f"EP{n} {episode.title} on {device}", file=sys.stderr)
    audio = None

    def audio_once():
        nonlocal audio
        if audio is None:
            audio = load_audio(episode)
        return audio

    asr = cached(CACHE / "asr" / f"{n}.json", lambda: transcribe(audio_once(), device))
    speakers = cached(CACHE / "speakers" / f"{n}.json", lambda: diarize(audio_once(), asr))
    corrected = cached(CACHE / "corrected" / f"{n}.json", lambda: correct(episode, speakers["lines"]))
    cached(CACHE / "summary" / f"{n}.json", lambda: summarize(episode, corrected))


def main():
    parser = argparse.ArgumentParser(description="Transcribe 八百屋 Boys episodes with Breeze-ASR-25")
    parser.add_argument("episodes", nargs="*", type=int, help="episode numbers, all when omitted")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    parser.add_argument("--no-wait", action="store_true", help="use the GPU even when other work is running on it")
    args = parser.parse_args()

    episodes = {e.number: e for e in read_feed()}
    for n in args.episodes or sorted(episodes, reverse=True):
        if (CACHE / "summary" / f"{n}.json").exists():
            continue
        while args.device == "cuda" and not args.no_wait and not (CACHE / "asr" / f"{n}.json").exists() and not gpu_idle():
            print("  GPU busy, waiting", file=sys.stderr)
            time.sleep(240)
        if not claim(n):
            continue
        try:
            process(episodes[n], args.device)
        except Exception as error:
            print(f"EP{n} failed: {error!r}", file=sys.stderr)
        finally:
            (CACHE / "claims" / str(n)).unlink(missing_ok=True)

    done = sorted(n for n in episodes if (CACHE / "summary" / f"{n}.json").exists())
    names = name_speakers(done)
    for n in done:
        corrected = json.loads((CACHE / "corrected" / f"{n}.json").read_text())
        summary = json.loads((CACHE / "summary" / f"{n}.json").read_text())
        export(episodes[n], corrected, summary, names[n])
        print(f"EP{n}: wrote {OUTPUT / f'{n}.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
