import fs from "node:fs/promises";
import { createReadStream, createWriteStream } from "node:fs";
import { pipeline, finished } from "node:stream/promises";
import { once } from "node:events";
import http from "node:http";
import path from "node:path";

export async function openRecordingServer({ root, partial }) {
  let sink,
    finalized = false;
  const server = http.createServer(async (req, res) => {
    try {
      const url = new URL(req.url, "http://localhost");
      if (req.method === "GET" && url.pathname === "/__record/controller") {
        res.setHeader("Content-Type", "text/html");
        res.end(
          '<!doctype html><html><meta charset="utf-8"><title>Recording controller</title><body></body></html>',
        );
        return;
      }
      if (req.method === "POST" && url.pathname === "/__record/chunk") {
        if (finalized) throw Error("Recording already finalized");
        if (!sink) {
          sink = createWriteStream(partial, { flags: "wx" });
          sink.on("error", (error) =>
            console.error(`Video write failed: ${error.message}`),
          );
        }
        // A chunk is acknowledged after its bytes reach the file stream.
        for await (const data of req) {
          if (!sink.write(data)) await once(sink, "drain");
        }
        if (sink.errored) throw sink.errored;
        res.end("OK");
        return;
      }
      if (req.method === "POST" && url.pathname === "/__record/finish") {
        if (!sink || finalized) throw Error("No active recording");
        sink.end();
        await finished(sink);
        finalized = true;
        res.end("OK");
        return;
      }
      if (req.method !== "GET") {
        res.writeHead(405);
        res.end();
        return;
      }
      const file = path.resolve(
        root,
        "." +
          decodeURIComponent(
            url.pathname === "/" ? "/index.html" : url.pathname,
          ),
      );
      if (!file.startsWith(root + path.sep)) {
        res.writeHead(403);
        res.end();
        return;
      }
      await fs.access(file);
      res.setHeader(
        "Content-Type",
        {
          ".html": "text/html",
          ".mjs": "text/javascript",
          ".js": "text/javascript",
          ".css": "text/css",
          ".json": "application/json",
          ".png": "image/png",
          ".ttf": "font/ttf",
        }[path.extname(file)] || "application/octet-stream",
      );
      await pipeline(createReadStream(file), res);
    } catch (error) {
      if (!res.headersSent) res.writeHead(500);
      res.end(error.message);
    }
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  return {
    url: `http://127.0.0.1:${server.address().port}/`,
    async close() {
      if (sink && !sink.closed) sink.destroy();
      await new Promise((resolve) => server.close(resolve));
    },
  };
}
