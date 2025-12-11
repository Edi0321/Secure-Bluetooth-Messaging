import socket

Server_MAC = ""  # We would need to input the Bluetooth MAC address of the PC we are trying to connect to here

blue_sock = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)

blue_sock.connect((Server_MAC, 4))

print("Connected to server!!")

while True:
    msg = input("You: ")
    blue_sock.send(msg.encode())
    
    data = blue_sock.recv(1024).decode() # # The 1024 is number of bytes to recieve so we can change that if we want messages to be longer on arrival
    print("Server: ", data)