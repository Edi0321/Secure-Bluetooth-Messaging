import socket

blue_Server_MAC = "XX:XX:XX:XX:XX:XX"  #Your PCs Bluetooth MAC goes here

server_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
server_sock.bind((blue_Server_MAC, 4))
server_sock.listen(1)

print("Waiting to connect")

blue_sock, mac_address = server_sock.accept()
print("Connected to: ", mac_address)

while True:
    data = blue_sock.recv(1024).decode() # The 1024 is number of bytes to recieve so we can change that if we want messages to be longer on arrival
    print("Client: ", data)
    
    msg = input("You: ")
    blue_sock.send(msg.encode())