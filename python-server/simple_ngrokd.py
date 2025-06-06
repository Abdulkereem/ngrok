#!/usr/bin/env python3
"""Simplified tunnel server in Python.

This is a minimal proof-of-concept implementation of an ngrok-like server.
It allows a client to register a tunnel via WebSocket and forwards HTTP
requests to that client. It is **not** a full replacement for the Go server
and lacks many security features. Use for testing only.
"""

import asyncio
import json
from aiohttp import web
import websockets

# Map of client_id -> websocket connection
clients = {}

async def register_handler(websocket):
    try:
        msg = await websocket.recv()
        data = json.loads(msg)
        client_id = data.get("client_id")
        if not client_id:
            await websocket.close()
            return
        clients[client_id] = websocket
        print(f"client registered: {client_id}")
        while True:
            # keep connection alive
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"client connection error: {e}")
    finally:
        if client_id in clients and clients[client_id] is websocket:
            del clients[client_id]
        await websocket.close()
        print(f"client disconnected: {client_id}")

async def ws_server(websocket, path):
    if path == "/register":
        await register_handler(websocket)
    else:
        await websocket.close()

async def handle_request(request):
    host = request.headers.get('Host', '')
    client_id = host.split('.', 1)[0]
    if client_id not in clients:
        return web.Response(status=502, text='no tunnel')

    websocket = clients[client_id]
    body = await request.read()
    req_data = {
        'method': request.method,
        'path': request.path_qs,
        'headers': dict(request.headers),
        'body': body.decode('latin1')
    }
    try:
        await websocket.send(json.dumps(req_data))
        resp_msg = await websocket.recv()
        resp_data = json.loads(resp_msg)
    except Exception as e:
        return web.Response(status=502, text='tunnel error')

    return web.Response(status=resp_data.get('status', 502),
                        headers=resp_data.get('headers', {}),
                        text=resp_data.get('body', ''))

async def main():
    app = web.Application()
    app.router.add_route('*', '/{tail:.*}', handle_request)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8080)
    await site.start()

    ws_srv = await websockets.serve(ws_server, '0.0.0.0', 4443)
    print('Server listening on http://0.0.0.0:8080 and websocket port 4443')
    await asyncio.Future()  # run forever

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
