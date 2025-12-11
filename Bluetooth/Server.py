import socket, asyncio, websockets, requests

blue_Server_MAC = "XX:XX:XX:XX:XX:XX"  # Your PCs Bluetooth MAC goes here
CRYPTO = "http://localhost:1919"

key = requests.get(f"{CRYPTO}/key").text.strip()

server_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
server_sock.bind((blue_Server_MAC, 4))
server_sock.listen(1)
print("Waiting for Bluetooth...")
blue_sock, mac_address = server_sock.accept()
print(f"Connected: {mac_address}")

async def handle(ws):
    print("Browser connected")
    while True:
        msg = await ws.recv()

        enc = requests.post(f"{CRYPTO}/encrypt", data=f"{key},{msg}".encode()).text.strip()
        
        blue_sock.send(enc.encode())
        print(f"Sent: {msg}")
        
        
        enc_data = blue_sock.recv(4096).decode()
        
        dec = requests.post(f"{CRYPTO}/decrypt", data=f"{key},{enc_data}".encode()).text.strip()
        
        await ws.send(dec)
        print(f"Received: {dec}")

async def main():
    async with websockets.serve(handle, "localhost", 10000):
        print("Ready! Open index.html")
        await asyncio.Future()

asyncio.run(main())