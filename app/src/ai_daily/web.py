from dataclasses import asdict, is_dataclass

from flask import Flask, jsonify, request, Response


def _payload(run):
    if is_dataclass(run):
        return asdict(run)
    return {key: getattr(run, key, None) for key in ("id", "state", "media_id", "article", "error")}


def create_app(runner, settings=None):
    app = Flask(__name__)
    settings = settings or {}

    @app.get("/")
    def index():
        return Response("""<!doctype html><html lang='zh-CN'><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'><title>AI Daily</title>
<style>
@font-face{font-family:Caveat;src:url('/legacy-static/fonts/Caveat[wght].ttf')}*{box-sizing:border-box}body{margin:0;background:#f0e7cf;color:#29251f;font:16px Georgia,'Microsoft YaHei',serif}.paper{max-width:980px;margin:28px auto;padding:36px;background:#fffaf0;box-shadow:0 18px 50px #5b4b3529;border:1px solid #29251f}.mast{text-align:center;border-block:4px double #29251f;padding:14px 0}.mast h1{font:700 58px Caveat,serif;margin:0;letter-spacing:2px}.mast p{margin:0;color:#756b5e}.control{display:flex;gap:12px;align-items:end;margin:30px 0;border-bottom:1px solid #b8aa91;padding-bottom:22px}.control label{display:grid;gap:6px}.control input{font:inherit;padding:9px;border:1px solid #40392e;background:#fffdf8}button{font:700 15px Georgia,serif;padding:10px 16px;background:#d9473f;color:#fff;border:0;cursor:pointer}button:disabled{background:#a99e8e;cursor:not-allowed}.status{font-weight:bold}.article{white-space:pre-wrap;line-height:1.8;border-top:1px solid #29251f;padding-top:20px}.note{color:#756b5e;font-size:14px}@media(max-width:640px){.paper{margin:0;padding:20px}.mast h1{font-size:44px}.control{align-items:stretch;flex-direction:column}}
</style><main class='paper'><header class='mast'><h1>AI Daily</h1><p>本地编辑台 · 草稿发布前可审阅</p></header>
<section class='control'><label>日期<input id='date' type='date'></label><button id='prepare'>生成预览</button><button id='publish' disabled>创建草稿</button><span id='status' class='status'>等待开始</span></section><p class='note'>生成文章不等于发布。只有微信返回草稿回执后，状态才会显示为已发布。</p><article id='article' class='article'></article></main>
<script>let run=null;const $=id=>document.getElementById(id),set=(t)=>$('status').textContent=t;$('date').value=new Date().toISOString().slice(0,10);function show(a){$('article').textContent=a?.markdown||''}async function call(url,body){const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),d=await r.json();if(!r.ok)throw Error(d.error||'请求失败');return d}$('prepare').onclick=async()=>{try{set('正在生成…');run=await call('/api/runs',{date:$('date').value});show(run.article);$('publish').disabled=run.state!=='ready';set(run.state==='ready'?'文章已生成，尚未发布':run.state)}catch(e){set('失败：'+e.message)}};$('publish').onclick=async()=>{try{set('正在创建草稿…');run=await call('/api/runs/'+run.id+'/publish',{date:$('date').value});set('草稿已创建：'+run.media_id);$('publish').disabled=true}catch(e){set('失败：'+e.message)}};</script></html>""", mimetype="text/html")

    @app.post("/api/runs")
    def prepare():
        date = (request.get_json(silent=True) or {}).get("date")
        if not date:
            return jsonify(error="请选择日期"), 400
        try:
            return jsonify(_payload(runner.prepare(date, settings)))
        except Exception as exc:
            return jsonify(error=str(exc)), 502

    @app.get("/api/runs/<run_id>")
    def read(run_id):
        try:
            return jsonify(_payload(runner.get(run_id)))
        except KeyError:
            return jsonify(error="运行记录不存在"), 404

    @app.post("/api/runs/<run_id>/publish")
    def publish(run_id):
        date = (request.get_json(silent=True) or {}).get("date")
        if not date:
            return jsonify(error="请选择日期"), 400
        try:
            return jsonify(_payload(runner.publish(date)))
        except Exception as exc:
            return jsonify(error=str(exc)), 409

    return app
