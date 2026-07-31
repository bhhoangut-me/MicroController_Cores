import config_wifi
import network
import socket
import utime
class WIFI:
    def __init__(self,ssid,passwd):
        self._ssid = ssid
        self._passwd = passwd
        self._wifi=network.WLAN(network.AP_IF)
        self._socket= None
        self._client_sock = None
       
    def connect(self):
        # Buoc 1: Bat AP len truoc
        self._wifi.active(1)
        utime.sleep_ms(200)  # Cho AP on dinh
        # Buoc 2: Config SSID/passwd SAU KHI da active
        self._wifi.config(essid=self._ssid, password=self._passwd)
        utime.sleep_ms(500)  
        self._ip=self._wifi.ifconfig()
        print(f"[WIFI]  AP bat len | SSID='{self._ssid}' | IP={self._ip[0]} | Subnet={self._ip[1]}")
        print(f"[WIFI]  AuthMode=WPA2 | Channel=6")
        self._socket=socket.socket()
        self._socket.bind((self._ip[0],80))
        self._socket.listen(1)
        self._socket.settimeout(0.01)
        print(f"[WIFI]  Socket lang nghe tai {self._ip[0]}:80 - Cho client ket noi...")
    def update(self):
        if self._client_sock is None:
            if self._socket is not None:
                try:
                    self._client_sock, self._client_addr = self._socket.accept()
                    self._client_sock.settimeout(0.01) # Timeout ngắn để đọc recv
                    print(f"[WIFI]  CLIENT KET NOI THANH CONG tu: {self._client_addr}")
                    print(f"[WIFI]  San sang nhan/gui du lieu")
                except OSError:
                    pass
        else:
            try:
                self._data_receive = self._client_sock.recv(1024).decode('utf-8').strip()
                if self._data_receive:
                    print(f"[WIFI]  Nhan du lieu: '{self._data_receive}'")
                if self._data_receive == "DISCONNECT_WIFI":
                    print("[WIFI]  Nhan lenh DISCONNECT_WIFI -> Ngat ket noi")
                    self.disconnect()
            except OSError:
                pass
    def send(self,value):
        if self._client_sock is not None:
            try:
                self._client_sock.sendall(f"{value}\n".encode('utf-8'))
                print(f"[WIFI]  Gui: {value}", end='\r')        
            except OSError:
                # Nếu rớt mạng khi đang gửi -> Tự xả client để chờ kết nối lại
                print(f"[WIFI]  LOI khi gui! Client co the da ngat -> Xoa client, cho ket noi lai")
                if self._client_sock:
                    self._client_sock.close()
                self._client_sock = None
    def disconnect(self):
        print("[WIFI]  Bat dau qua trinh DISCONNECT...")
        if self._client_sock:
            try:
                self._client_sock.close()
                print("[WIFI]  Da dong client socket")
            except:
                pass
            self._client_sock = None
            
        if self._socket:
            try:
                self._socket.close()
                print("[WIFI]  Da dong server socket")
            except:
                pass
            self._socket = None

        self._wifi.active(0)
        print("[WIFI]  AP da tat. WiFi hoan toan OFF")