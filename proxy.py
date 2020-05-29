from sys import argv, exit
import socket
import threading
import re

LOCAL_HOST = "127.0.0.1"

class BrowserThread(threading.Thread):
    def __init__(self,browserSock, browserAddr):
        threading.Thread.__init__(self)
        self.bSock = browserSock
        self.bAddr = browserAddr
        
    def run(self):
        currLine = ""
        request = ""
        header = ""
        serverName = ""
        serverPort = 80

        while True:
            if header[-4:] == "\r\n\r\n" or header[-3:-1] == "\n\r\n":
                # If header end with "\r\n\r\n" or "\n\r\n", we've got the whole header
                break
            try:
                currLine += self.bSock.recv(1).decode()
            except socket.timeout:
                print("Didn't receive any data from this socket")
                print(currLine, request, header)
                self.bSock.close()
                return
            except socket.error:
                # If the socket is good, but we got a non fatal error indicating
                # that we've received nothing, we should try again.
                continue
            if currLine[-1:] == "\n":
                # if we still haven't proccess the first line
                if len(request) == 0:
                    # Change http version to 1.0
                    lineSplit = re.split('HTTP/', currLine)
                    currLine = lineSplit[0] + "HTTP/1.0\r\n"
                    request = currLine

                    # print out request line
                    print(">>> " + request[:-2])

                    # assign initial server's port number based on the request line
                    reqSplit = re.split(' |:', request)
                    if len(reqSplit) == 5:
                        serverPort = int(reqSplit[3])
                    elif len(reqSplit) == 4 and reqSplit[0] == "CONNECT":
                        serverPort = int(reqSplit[2])
                    elif reqSplit[1].lower() is "https":
                        serverPort = 443

                # if this line has the host keyword, we want to get the domain and port of the server
                elif "host" in currLine.lower():
                    lineSplit = re.split(' :|: |:', currLine)
                    if len(lineSplit) == 3:
                        # Enters here if we have a port number in the Host line.
                        serverName = lineSplit[1]
                        port = int(lineSplit[2][:-2])
                    else:
                        serverName = lineSplit[1][:-2]

                # if this line has the keep-alive keyword
                elif "keep-alive" in currLine.lower():
                    lineSplit = re.split(' :|: |:', currLine)
                    currLine = lineSplit[0] + ": " + "close\r\n"

                # Don't add request to header
                if currLine is not request:
                    header += currLine
                currLine = ""
        
        # Uncomment to print header, server name and server port
        #print(header)
        #print(serverName, serverPort)

        # Establish connection between proxy and server
        serverSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        try:
            serverSock.connect((serverName, serverPort))
        except Exception:
            print("error connecting from proxy to server, sending 502 Bad Gateway")
            self.bSock.send("HTTP/1.0 502 Bad Gateway\r\n\r\n".encode())
            serverSock.close()
            self.bSock.close()
            return
        
        isConnect = "CONNECT" in request

        if isConnect:
            # Send back 200 OK for successful CONNECT
            self.bSock.send("HTTP/1.0 200 OK\r\n\r\n".encode())
        
        if not isConnect:
            serverSock.send(request.encode())
            serverSock.send(header.encode())
            while True:
                try:
                    data = self.bSock.recv(256)
                except socket.error:
                    break
                if len(data) == 0:
                    break
                serverSock.send(data)
            
            # Get server's header
            header = ""
            currLine = ""
            while True:
                if header[-4:] == "\r\n\r\n" or header[-3:-1] == "\n\r\n":
                    # We got the whole header
                    break
                currLine += serverSock.recv(1).decode()
                if currLine[-1:] == "\n":
                    if "keep-alive" in currLine.lower():
                        lineSplit = re.split(' :|: |:', currLine)
                        currLine = lineSplit[0] + ": " + "close\r\n"
                    header += currLine
                    currLine = ""
            self.bSock.send(header.encode())

            # send rest of server's data
            while True:
                data = serverSock.recv(256)
                if len(data) == 0:
                    break
                self.bSock.send(data)
            serverSock.close()
            self.bSock.close()
        else:
            self.bSock.settimeout(30)
            serverSock.settimeout(30)
            sendThread = connectThread(self.bSock, serverSock)
            recvThread = connectThread(serverSock, self.bSock)
            sendThread.start()
            recvThread.start()

class connectThread(threading.Thread):
    def __init__(self, srcSock, dstSock):
        threading.Thread.__init__(self)
        self.src = srcSock
        self.dst = dstSock
        
    def run(self):
        sent = False
        while True:
            try:
                data = self.src.recv(256)
            except socket.timeout:
                continue
            except (OSError, ConnectionAbortedError):
                break
            if data == 0:
                break
            sent = True
            try:
                self.dst.send(data)
            except (OSError, ConnectionAbortedError):
                break

def Main():
    port = int(argv[1])
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((LOCAL_HOST, port))
    try:
        while True:
            sock.listen()
            browserSock, browserAddr = sock.accept()
            browserSock.setblocking(0)
            newThread = BrowserThread(browserSock, browserAddr)
            newThread.daemon = True  # Allows us to kill all threads when main thread exits
            newThread.start()
    except (KeyboardInterrupt, SystemExit):  # Catch ctrl + c
        sock.close()
        exit()
        


if __name__ == '__main__':
    Main()