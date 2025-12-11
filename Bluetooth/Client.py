import socket, asyncio, websockets, requests

blue_Server_MAC = "XX:XX:XX:XX:XX:XX"  # Your PCs Bluetooth MAC goes here
CRYPTO = "http://localhost:1919"

key = requests.get(f"{CRYPTO}/key").text.strip()

blue_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
blue_sock.connect((blue_Server_MAC, 4))
print("Connected to server")

async def handle(ws):
    print("Browser connected")
    while True:
        
        enc_data = blue_sock.recv(4096).decode()

        dec = requests.post(f"{CRYPTO}/decrypt", data=f"{key},{enc_data}".encode()).text.strip()

        await ws.send(dec)
        print(f"Received: {dec}")

        msg = await ws.recv()
        
        enc = requests.post(f"{CRYPTO}/encrypt", data=f"{key},{msg}".encode()).text.strip()
        
        blue_sock.send(enc.encode())
        print(f"Sent: {msg}")
        

async def main():
    async with websockets.serve(handle, "localhost", 10000):
        print("Ready! Open index.html")
        await asyncio.Future()

asyncio.run(main())