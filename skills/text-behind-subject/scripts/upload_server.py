"""Tiny token-protected upload page for getting the user's video onto this machine.

usage: python3 upload_server.py OUT_DIR [--port 8765]
Prints the secret path. Expose with:  cloudflared tunnel --url http://localhost:PORT
Uploads go in 32 MB chunks because Cloudflare quick tunnels reject request bodies over 100 MB.
"""
import argparse, html, os, re, secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PAGE = """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Video Upload</title><style>
body{font-family:-apple-system,system-ui,sans-serif;background:#111;color:#eee;margin:0;padding:32px 16px;display:flex;justify-content:center}
main{max-width:480px;width:100%}h1{font-size:22px}
input{display:block;width:100%;padding:24px 12px;border:2px dashed #555;border-radius:12px;box-sizing:border-box;color:#eee}
button{margin-top:16px;width:100%;padding:16px;font-size:18px;font-weight:600;border:0;border-radius:12px;background:#fff;color:#111}
button:disabled{opacity:.4}progress{width:100%;height:14px;margin-top:20px}#s{margin-top:12px;color:#aaa;word-break:break-all}
</style></head><body><main><h1>Upload your video</h1>
<input id="f" type="file" accept="video/*" multiple>
<button id="b">Upload</button>
<progress id="p" value="0" max="1"></progress><div id="s"></div></main><script>
const CH=32*1024*1024, s=document.getElementById('s'), p=document.getElementById('p');
const BASE=__BASE__, f=document.getElementById('f'), b=document.getElementById('b');
b.onclick=async()=>{
  if(!f.files.length){s.textContent='Choose a video first.';return}
  b.disabled=true;
  try{await up()}catch(err){s.textContent='Failed: '+err}
  b.disabled=false;
};
async function up(){
  for(const file of f.files){
    const name=Date.now()+'_'+file.name.replace(/[^\\w.-]/g,'_');
    for(let off=0;off<file.size;off+=CH){
      const r=await fetch(`${BASE}/upload?name=${encodeURIComponent(name)}&offset=${off}`,{method:'POST',body:file.slice(off,off+CH)});
      if(!r.ok){s.textContent='Failed: '+await r.text();return}
      p.value=Math.min(1,(off+CH)/file.size);
      s.textContent=`${file.name}: ${Math.round(100*p.value)}%`;
    }
    const r=await fetch(`${BASE}/upload?name=${encodeURIComponent(name)}&done=1&size=${file.size}`,{method:'POST'});
    s.textContent=r.ok?`Done: ${file.name} (${(file.size/1e6).toFixed(1)} MB) - you can close this page.`:'Failed: '+await r.text();
  }
}</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--token", help="reuse a secret path (keeps the URL stable across restarts)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    token = a.token or secrets.token_urlsafe(12)

    class H(BaseHTTPRequestHandler):
        def _ok(self, body, ctype="text/plain", code=200):
            b = body.encode()
            self.send_response(code); self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

        def do_GET(self):
            if urlparse(self.path).path.rstrip("/") == "/" + token:
                return self._ok(PAGE.replace("__BASE__", '"/%s"' % token), "text/html; charset=utf-8")
            self._ok("not found", code=404)

        def do_POST(self):
            u = urlparse(self.path)
            if u.path != "/%s/upload" % token:
                return self._ok("not found", code=404)
            q = {k: v[0] for k, v in parse_qs(u.query).items()}
            name = re.sub(r"[^\w.-]", "_", q.get("name", ""))[:200]
            if not name or name.startswith("."):
                return self._ok("bad name", code=400)
            path = os.path.join(a.out, name + ".part")
            if "done" in q:
                if not os.path.exists(path) or os.path.getsize(path) != int(q.get("size", -1)):
                    return self._ok("size mismatch", code=400)
                os.rename(path, os.path.join(a.out, name))
                print("UPLOADED %s" % os.path.join(a.out, name), flush=True)
                return self._ok("ok")
            off, n = int(q.get("offset", 0)), int(self.headers.get("Content-Length", 0))
            cur = os.path.getsize(path) if os.path.exists(path) else 0
            if off != cur:
                return self._ok("offset mismatch (have %d)" % cur, code=409)
            with open(path, "ab") as f:
                while n > 0:
                    chunk = self.rfile.read(min(n, 1 << 20))
                    if not chunk:
                        break
                    f.write(chunk); n -= len(chunk)
            self._ok("ok")

        def log_message(self, *args):
            pass

    print("TOKEN_PATH /%s" % token, flush=True)
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
