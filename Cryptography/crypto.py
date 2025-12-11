import random
import base64
from http.server import BaseHTTPRequestHandler, HTTPServer
from Crypto.Cipher import AES

def encrypt(message, key):
    cipher = AES.new(key, AES.MODE_GCM)

    nonce = bytes(cipher.nonce)
    ciphertext, tag = cipher.encrypt_and_digest(message)
    return [nonce, ciphertext, tag]

def encryptString(message, key):
    b = bytearray()
    b.extend(map(ord, message))
    return encrypt(b, key)

def decrypt(key, nonce, ciphertext, tag):
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt(ciphertext)

    try:
        cipher.verify(tag)
        print("the message is authentic")
    except ValueError:
        print("Bad message")

    return plaintext

def decryptString(key, nonce, ciphertext, tag):
    return decrypt(key, nonce, ciphertext, tag).decode("utf-8")

def encodeString(s):
    return base64.b32encode(s).decode('utf-8')

def decodeString(s):
    return base64.b32decode(s).decode('utf-8')

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()
        print(self.path)
        print(self.request)
        if self.path.endswith("key"):
            global shared_key
            if 'shared_key' not in globals():
                shared_key = bytearray(16)
                for i in range(16):
                   shared_key[i] = random.randint(0, 255)
            encoded = base64.b32encode(shared_key)
            self.wfile.write(encoded)
            return

        self.wfile.write(bytes("Please use the following endpoint: /key", "utf8"))

    def do_POST(self):
        self.send_response(200)
        self.send_header('Content-type','text/html')
        self.end_headers()
        byts = self.rfile.read1()

        if self.path.endswith("encrypt"):
            # input is key (base32 encoded) and message separated by a comma
            encoded = bytearray(0) + byts
            [key, msg] = encoded.split(bytes(',', 'utf-8'), 1)
            key = base64.b32decode(key)
            msg = msg.decode('utf-8')

            [n, c, t] = encryptString(msg, key)
            res = encodeString(n) + ',' + encodeString(c) + ',' + encodeString(t) + '\n'
            self.wfile.write(bytes(res, 'utf-8'))
            return

        if self.path.endswith("decrypt"):
            # input is key, nonce, ciphertext, tag separated by commas (each base32 encoded)
            encoded = bytearray(0) + byts
            [key, nonce, ciphertext, tag] = encoded.split(bytes(',', 'utf-8'), 3)
            key = base64.b32decode(key)
            nonce = base64.b32decode(nonce)
            ciphertext = base64.b32decode(ciphertext)
            tag = base64.b32decode(tag)

            plaintext = decryptString(key, nonce, ciphertext, tag)
            self.wfile.write(bytes(plaintext, "utf8"))
            return

        self.wfile.write(bytes("Please use one of the following endpoints: /encrypt or /decrypt", "utf8"))

with HTTPServer(('0.0.0.0', 1919), handler) as server:
    server.serve_forever()
