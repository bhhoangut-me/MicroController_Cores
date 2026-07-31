import config_wifi
import network
import socket
class WIFI:
    def __init__(self,ssid,passwd):
        self._ssid = ssid
        self._passwd = passwd
        self._wifi=network.WLAN(network.AP_IF)
        self._socket= None
        self._client_sock = None
        self._wifi.config(essid=self._ssid,password=self._passwd)
    def connect(self):
        self._wifi.active(1)
        self._ip=self._wifi.ifconfig()
        self._socket=socket.socket()
        self._socket.bind((self._ip[0],80))
        self._socket.listen(1)
        self._socket.settimeout(0.01)
    def update(self):
        if self._client_sock is None:
            if self._socket is not None:
                try:
                    self._client_sock, self._client_addr = self._socket.accept()
                    self._client_sock.settimeout(0.01) # Timeout ngắn để đọc recv
                    print(f"CONNECT SUCCESS from: {self._client_addr}")
                except OSError:
                    pass
        else:
            try:
                self._data_receive = self._client_sock.recv(1024).decode('utf-8').strip()
                if self._data_receive == "DISCONNECT_WIFI":
                    print("DISCONNECT SUCCESS.....")
                    self.disconnect()
            except OSError:
                pass
    def send(self,value):
        if self._client_sock is not None:
            try:
                self._client_sock.sendall(f"{value}\n".encode('utf-8'))
                print(f"Dang gui ADC: {value}", end='\r')        
            except OSError:
                # Nếu rớt mạng khi đang gửi -> Tự xả client để chờ kết nối lại
                if self._client_sock:
                    self._client_sock.close()
                self._client_sock = None
    def disconnect(self):
        if self._client_sock:
            try:
                self._client_sock.close()
            except:
                pass
            self._client_sock = None
            
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None

        self._wifi.active(0)