import { afterEach, describe, expect, it, vi } from "vitest";

import { sendFile } from "./StageUploads";

type Answer = { status: number; headers?: Record<string, string> } | "break";
type Sent = { headers: Record<string, string>; size: number | null };

/** Google's upload session, scripted: each PUT gets the next answer. */
function session(answers: Answer[]) {
  const sent: Sent[] = [];
  class Xhr {
    upload: { onprogress?: (event: { loaded: number }) => void } = {};
    status = 0;
    onload?: () => void;
    onerror?: () => void;
    private headers: Record<string, string> = {};
    private answer: Answer = "break";
    open() {}
    setRequestHeader(name: string, value: string) {
      this.headers[name] = value;
    }
    getResponseHeader(name: string) {
      return this.answer !== "break" ? (this.answer.headers?.[name] ?? null) : null;
    }
    send(body: Blob | null) {
      sent.push({ headers: this.headers, size: body ? body.size : null });
      this.answer = answers.shift() ?? "break";
      const answer = this.answer;
      setTimeout(() => {
        if (answer === "break") return this.onerror?.();
        this.upload.onprogress?.({ loaded: body?.size ?? 0 });
        this.status = answer.status;
        this.onload?.();
      });
    }
  }
  vi.stubGlobal("XMLHttpRequest", Xhr);
  return sent;
}

const file = () => new File(["0123456789"], "Planta.pdf", { type: "application/pdf" });
const NO_WAIT = [0, 0, 0];

afterEach(() => vi.unstubAllGlobals());

describe("sending a file to its upload session", () => {
  it("after a lost connection, asks what arrived and sends only the rest", async () => {
    const sent = session(["break", { status: 308, headers: { Range: "bytes=0-3" } }, { status: 200 }]);
    const progress: number[] = [];
    await sendFile("https://upload.example/s", file(), (p) => progress.push(p), NO_WAIT);
    expect(sent).toEqual([
      { headers: { "Content-Type": "application/pdf" }, size: 10 },
      { headers: { "Content-Range": "bytes */10" }, size: null },
      { headers: { "Content-Range": "bytes 4-9/10" }, size: 6 },
    ]);
    expect(progress.at(-1)).toBe(1);
  });

  it("after Google's 5xx, starts over when nothing arrived", async () => {
    const sent = session([{ status: 503 }, { status: 308 }, { status: 201 }]);
    await sendFile("https://upload.example/s", file(), () => {}, NO_WAIT);
    expect(sent[2]).toEqual({ headers: { "Content-Type": "application/pdf" }, size: 10 });
  });

  it("is done when the session already has it all", async () => {
    const sent = session(["break", { status: 200 }]);
    await sendFile("https://upload.example/s", file(), () => {}, NO_WAIT);
    expect(sent).toHaveLength(2);
  });

  it("gives up on a refusal at once, and after a few breaks", async () => {
    session([{ status: 403 }]);
    await expect(sendFile("https://upload.example/s", file(), () => {}, NO_WAIT)).rejects.toMatchObject({
      code: "unexpected",
    });
    const sent = session(["break", "break", "break", "break", "break", "break", "break"]);
    await expect(sendFile("https://upload.example/s", file(), () => {}, NO_WAIT)).rejects.toMatchObject({
      code: "network",
    });
    expect(sent.length).toBe(4); // the first try, then one question per wait
  });

  it("stops when the session itself is gone", async () => {
    session(["break", { status: 404 }]);
    await expect(sendFile("https://upload.example/s", file(), () => {}, NO_WAIT)).rejects.toMatchObject({
      status: 404,
    });
  });
});
