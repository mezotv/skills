import { closeSync, existsSync, openSync, writeSync } from "node:fs";
import { basename, join } from "node:path";

const token = process.env.PHONE_TOKEN;
const uploadDir = process.env.UPLOAD_DIR ?? ".";
const serveDir = process.env.SERVE_DIR;
if (!token || token.length < 16) throw new Error("PHONE_TOKEN (16+ random chars) is required");

const page = `<!doctype html><meta name=viewport content="width=device-width,initial-scale=1"><body style="font:18px system-ui;padding:24px">
<h2>Upload video</h2><input type=file id=f accept="video/*"><br><br><button id=b style="font-size:18px;padding:12px 24px">Upload</button>
<p id=s></p><progress id=p max=100 value=0 style="width:100%"></progress><script>
b.onclick=async()=>{const file=f.files[0];if(!file)return;b.disabled=true;const C=20*1024*1024,id=Date.now();
for(let o=0;o<file.size;o+=C){for(let t=0;;t++){try{const r=await fetch(location.pathname+'?id='+id+'&offset='+o+'&name='+encodeURIComponent(file.name),{method:'POST',body:file.slice(o,o+C)});if(r.ok)break;throw 0}catch(e){if(t>4){s.textContent='Failed, try again';b.disabled=false;return}}}
p.value=Math.min(100,(o+C)/file.size*100);s.textContent=Math.round(p.value)+'%'}
await fetch(location.pathname+'?id='+id+'&done=1&size='+file.size+'&name='+encodeURIComponent(file.name),{method:'POST'});s.textContent='Done! You can close this.'}
</script>`;

Bun.serve({
  port: Number(process.env.PORT ?? 8787),
  hostname: "0.0.0.0",
  maxRequestBodySize: 64 * 1024 ** 2,
  async fetch(req) {
    const url = new URL(req.url);
    const prefix = `/${token}`;
    if (serveDir && url.pathname.startsWith(`${prefix}/f/`)) {
      const file = Bun.file(join(serveDir, basename(decodeURIComponent(url.pathname.slice(prefix.length + 3)))));
      if (!(await file.exists())) return new Response("not found", { status: 404 });
      return new Response(file, { headers: { "content-disposition": `attachment; filename="${basename(file.name ?? "video.mp4")}"` } });
    }
    if (url.pathname !== prefix) return new Response("not found", { status: 404 });
    if (req.method === "GET") return new Response(page, { headers: { "content-type": "text/html" } });
    const name = (url.searchParams.get("name") ?? "video.mp4").replace(/[^\w.-]/g, "_");
    const out = join(uploadDir, `${(url.searchParams.get("id") ?? "0").replace(/\D/g, "")}-${name}`);
    if (url.searchParams.get("done")) {
      console.log("saved", out, Bun.file(out).size, "expected", url.searchParams.get("size"));
      return new Response("ok");
    }
    const body = new Uint8Array(await req.arrayBuffer());
    const fd = openSync(out, existsSync(out) ? "r+" : "w+");
    try {
      writeSync(fd, body, 0, body.length, Number(url.searchParams.get("offset")));
    } finally {
      closeSync(fd);
    }
    return new Response("ok");
  },
});
