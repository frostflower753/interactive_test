import subprocess
import asyncio
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI()

@app.get("/")
async def get():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    process = None
    
    try:
        data = await websocket.receive_json()
        lang = data.get("lang")
        code = data.get("code")
        
        # 1. コードの実行準備（C++のコンパイル / Pythonのファイル生成）
        if lang == "cpp":
            with open("temp.cpp", "w", encoding="utf-8") as f:
                f.write(code)
            
            # AtCoder仕様のコンパイルコマンド
            compile_cmd = [
                "g++",
                "-std=c++17",  # C++17 (C++20が良い場合は -std=c++20)
                "-O2",         # 最適化
                "-I.",         # カレントフォルダの atcoder/ をインクルード参照させる
                "temp.cpp",
                "-o", "temp.exe" if sys.platform == "win32" else "./temp"
            ]

            compile_res = subprocess.run(
                compile_cmd,
                capture_output=True, text=True
            )
            if compile_res.returncode != 0:
                await websocket.send_json({"type": "sys", "msg": f"[Compile Error]\n{compile_res.stderr}"})
                await websocket.close()
                return
            cmd = ["temp.exe" if sys.platform == "win32" else "./temp"]
            
        elif lang == "python":
            with open("temp.py", "w", encoding="utf-8") as f:
                f.write(code)
            cmd = [sys.executable, "-u", "temp.py"] # -u でアンバッファ化
        else:
            await websocket.close()
            return

        # 2. サブプロセスの起動
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await websocket.send_json({"type": "sys", "msg": "[Process Started]"})

        # 3. 標準出力を監視してブラウザへ送信
        async def read_stdout():
            while True:
                line = await process.stdout.readline()
                if not line:
                    break
                await websocket.send_json({"type": "stdout", "msg": line.decode("utf-8")})
            
            return_code = await process.wait()
            await websocket.send_json({"type": "sys", "msg": f"[Process Finished (Exit Code: {return_code})]"})

        read_task = asyncio.create_task(read_stdout())

        # 4. ブラウザからの入力を受け取って stdin へ流し込む
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "stdin" and process.returncode is None:
                user_input = msg.get("msg") + "\n"
                process.stdin.write(user_input.encode("utf-8"))
                await process.stdin.drain()

    except WebSocketDisconnect:
        pass
    finally:
        if process and process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
