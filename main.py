import json
import os
import random
import re
import sys
import tempfile
import requests
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, QThread, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QImageReader, QMovie
from PyQt6.QtNetwork import QTcpServer, QTcpSocket, QHostAddress
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QRadioButton, QGroupBox, QSpinBox
)

DEFAULT_PORT = 45454
DEFAULT_GIF_URL = "https://static2.klipy.com/ii/e293a233a303a98e471f78d04e13a1b0/a0/86/58Y6YqlV.gif"


# -------------------------------------------------------------
# Background Worker for Downloading GIFs
# -------------------------------------------------------------
class GifDownloadWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        try:
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            resp = session.get(self.url, timeout=15)
            resp.raise_for_status()
            data = resp.content

            # Extract direct GIF link if an HTML landing page was provided
            if not data.startswith(b"GIF"):
                html = resp.text
                match = re.search(r'<meta[^>]+(?:property|content)=["\']og:image["\'][^>]+(?:content|property)=["\']([^"\']+)["\']', html, re.I)
                direct_link = match.group(1) if match else None
                if not direct_link:
                    direct_link = re.search(r'https?://[^\s"\'<>]+\.gif', html, re.I)
                    direct_link = direct_link.group(0) if direct_link else None

                if direct_link:
                    img_resp = session.get(direct_link, timeout=15)
                    img_resp.raise_for_status()
                    data = img_resp.content

            temp_file = tempfile.NamedTemporaryFile(suffix=".gif", delete=False)
            temp_file.write(data)
            temp_file.close()

            self.finished.emit(temp_file.name)
        except Exception as e:
            self.error.emit(str(e))


# -------------------------------------------------------------
# Edge-Spawning Draggable GIF Window
# -------------------------------------------------------------
class DraggableGifWindow(QWidget):
    def __init__(self, file_path: str, duration_ms: int = 3500):
        super().__init__()
        self.temp_path = file_path
        self.drag_position = QPoint()
        self.duration_ms = duration_ms

        reader = QImageReader(self.temp_path)
        orig_size = reader.size()
        orig_w, orig_h = orig_size.width(), orig_size.height()

        if orig_w <= 0 or orig_h <= 0:
            self.close()
            return

        # 1. Calculate dimensions (scaled to screen size)
        screen = QGuiApplication.primaryScreen().availableGeometry()
        target_longest = max(screen.width(), screen.height()) / 4.5

        if orig_w >= orig_h:
            new_w = int(target_longest)
            new_h = int(orig_h * (target_longest / orig_w))
        else:
            new_h = int(target_longest)
            new_w = int(orig_w * (target_longest / orig_h))

        # 2. Window flags for borderless on-top display
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(new_w, new_h)

        # 3. Position randomly along the edges of the primary screen
        spawn_pos = self.get_random_edge_position(screen, new_w, new_h)
        self.move(spawn_pos)

        # 4. Animated GIF label
        self.label = QLabel(self)
        self.label.setFixedSize(new_w, new_h)
        self.label.setScaledContents(True)

        self.movie = QMovie(self.temp_path)
        self.movie.setScaledSize(QSize(new_w, new_h))
        self.label.setMovie(self.movie)
        self.movie.start()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

    def get_random_edge_position(self, screen_rect, w, h) -> QPoint:
        """Picks a random coordinate strictly along the outer borders/edges."""
        sx = screen_rect.x()
        sy = screen_rect.y()
        sw = screen_rect.width()
        sh = screen_rect.height()

        edge = random.choice(["top", "bottom", "left", "right"])

        if edge == "top":
            x = random.randint(sx, max(sx, sx + sw - w))
            y = sy
        elif edge == "bottom":
            x = random.randint(sx, max(sx, sx + sw - w))
            y = max(sy, sy + sh - h)
        elif edge == "left":
            x = sx
            y = random.randint(sy, max(sy, sy + sh - h))
        else:  # right
            x = max(sx, sx + sw - w)
            y = random.randint(sy, max(sy, sy + sh - h))

        return QPoint(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(self.duration_ms, self.close)

    def closeEvent(self, event):
        if hasattr(self, 'movie'):
            self.movie.stop()
        if hasattr(self, 'temp_path') and os.path.exists(self.temp_path):
            try:
                os.remove(self.temp_path)
            except OSError:
                pass
        super().closeEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()


# -------------------------------------------------------------
# Main Control Panel (Bidirectional Host & Client)
# -------------------------------------------------------------
class SyncGifController(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sync GIF Overlay (Two-Way)")
        self.resize(520, 460)

        self.active_popups = []
        self.workers = []

        # Networking
        self.tcp_server = None
        self.clients = []
        self.client_socket = None

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # 1. Mode selection
        mode_group = QGroupBox("1. Select Mode")
        mode_layout = QHBoxLayout(mode_group)
        self.radio_host = QRadioButton("Host (Server)")
        self.radio_client = QRadioButton("Client (Friend)")
        self.radio_host.setChecked(True)
        self.radio_host.toggled.connect(self.on_mode_toggled)
        mode_layout.addWidget(self.radio_host)
        mode_layout.addWidget(self.radio_client)
        layout.addWidget(mode_group)

        # 2. Network config
        conn_group = QGroupBox("2. Connection Settings")
        conn_layout = QHBoxLayout(conn_group)

        self.lbl_ip = QLabel("Host IP:")
        self.input_ip = QLineEdit("127.0.0.1")
        self.input_ip.setEnabled(False)

        self.lbl_port = QLabel("Port:")
        self.input_port = QSpinBox()
        self.input_port.setRange(1024, 65535)
        self.input_port.setValue(DEFAULT_PORT)

        self.btn_toggle_network = QPushButton("Start Server")
        self.btn_toggle_network.clicked.connect(self.toggle_network)

        conn_layout.addWidget(self.lbl_ip)
        conn_layout.addWidget(self.input_ip)
        conn_layout.addWidget(self.lbl_port)
        conn_layout.addWidget(self.input_port)
        conn_layout.addWidget(self.btn_toggle_network)
        layout.addWidget(conn_group)

        # 3. Summon GIF Controls (Active for both Host and connected Clients)
        self.summon_group = QGroupBox("3. Summon GIF (Available for Everyone)")
        summon_layout = QVBoxLayout(self.summon_group)

        self.input_url = QLineEdit(DEFAULT_GIF_URL)
        self.input_url.setPlaceholderText("Enter direct GIF URL...")

        self.btn_summon = QPushButton("🎉 Summon GIF on EVERYONE'S Screen!")
        self.btn_summon.setFixedHeight(38)
        self.btn_summon.setEnabled(False)  # Enabled once connected / started
        self.btn_summon.clicked.connect(self.request_summon_gif)

        summon_layout.addWidget(QLabel("GIF URL:"))
        summon_layout.addWidget(self.input_url)
        summon_layout.addWidget(self.btn_summon)
        layout.addWidget(self.summon_group)

        # 4. Activity log
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(QLabel("Activity Log:"))
        layout.addWidget(self.log_area)

    def log(self, text: str):
        self.log_area.append(text)

    def on_mode_toggled(self):
        is_host = self.radio_host.isChecked()
        self.input_ip.setEnabled(not is_host)
        self.btn_toggle_network.setText("Start Server" if is_host else "Connect to Host")
        self.btn_summon.setEnabled(False)

    def toggle_network(self):
        if self.radio_host.isChecked():
            # --- HOST MODE ---
            if self.tcp_server and self.tcp_server.isListening():
                self.tcp_server.close()
                self.tcp_server = None
                self.btn_toggle_network.setText("Start Server")
                self.btn_summon.setEnabled(False)
                self.log("🛑 Server stopped.")
            else:
                self.tcp_server = QTcpServer(self)
                self.tcp_server.newConnection.connect(self.on_new_client)
                port = self.input_port.value()
                if self.tcp_server.listen(QHostAddress.SpecialAddress.Any, port):
                    self.log(f"✅ Server running on port {port}. Ready for friends to join!")
                    self.btn_toggle_network.setText("Stop Server")
                    self.btn_summon.setEnabled(True)
                else:
                    self.log(f"❌ Failed to start server: {self.tcp_server.errorString()}")
        else:
            # --- CLIENT MODE ---
            if self.client_socket and self.client_socket.state() == QTcpSocket.SocketState.ConnectedState:
                self.client_socket.disconnectFromHost()
                self.btn_toggle_network.setText("Connect to Host")
                self.btn_summon.setEnabled(False)
            else:
                self.client_socket = QTcpSocket(self)
                self.client_socket.connected.connect(self.on_client_connected)
                self.client_socket.readyRead.connect(self.on_client_ready_read)
                self.client_socket.disconnected.connect(self.on_client_disconnected)

                ip = self.input_ip.text().strip()
                port = self.input_port.value()
                self.log(f"Connecting to {ip}:{port}...")
                self.client_socket.connectToHost(ip, port)

    # ------------------ Server Handlers ------------------
    def on_new_client(self):
        sock = self.tcp_server.nextPendingConnection()
        self.clients.append(sock)
        peer = f"{sock.peerAddress().toString()}:{sock.peerPort()}"
        self.log(f"👤 Friend connected: {peer}")

        sock.readyRead.connect(lambda: self.on_server_receive_data(sock))
        sock.disconnected.connect(lambda: self.on_server_client_disconnected(sock))

    def on_server_client_disconnected(self, sock):
        if sock in self.clients:
            self.clients.remove(sock)
        self.log("👤 A friend disconnected.")

    def on_server_receive_data(self, sock):
        """Processes messages sent by any connected client to the host."""
        while sock.canReadLine():
            raw_line = sock.readLine().data().decode("utf-8").strip()
            if not raw_line:
                continue
            try:
                msg = json.loads(raw_line)
                if msg.get("action") == "summon_gif":
                    sender = msg.get("sender", "A friend")
                    url = msg.get("url")
                    self.log(f"📥 {sender} summoned a GIF! Broadcasting to all...")
                    self.broadcast_gif_to_all(url, sender=sender)
            except Exception as e:
                self.log(f"Error handling client request: {e}")

    # ------------------ Client Handlers ------------------
    def on_client_connected(self):
        self.log("✅ Successfully connected to Host!")
        self.btn_toggle_network.setText("Disconnect")
        self.btn_summon.setEnabled(True)

    def on_client_disconnected(self):
        self.log("❌ Disconnected from host.")
        self.btn_toggle_network.setText("Connect to Host")
        self.btn_summon.setEnabled(False)

    def on_client_ready_read(self):
        """Client reads broadcast messages dispatched by the host."""
        while self.client_socket.canReadLine():
            raw_line = self.client_socket.readLine().data().decode("utf-8").strip()
            if not raw_line:
                continue
            try:
                msg = json.loads(raw_line)
                if msg.get("action") == "show_gif":
                    sender = msg.get("sender", "Someone")
                    self.log(f"✨ GIF incoming from {sender}!")
                    self.trigger_popup(msg.get("url"))
            except Exception as e:
                self.log(f"Error parsing broadcast: {e}")

    # ------------------ Summon & Broadcast Logic ------------------
    def request_summon_gif(self):
        """Triggered when pressing the summon button on either Host or Client."""
        url = self.input_url.text().strip()
        if not url:
            return

        if self.radio_host.isChecked():
            # Host directly broadcasts to everyone
            self.broadcast_gif_to_all(url, sender="Host")
        else:
            # Client sends a summon request up to the Host
            if self.client_socket and self.client_socket.state() == QTcpSocket.SocketState.ConnectedState:
                req = json.dumps({"action": "summon_gif", "url": url, "sender": "Client"}) + "\n"
                self.client_socket.write(req.encode("utf-8"))
                self.client_socket.flush()
                self.log("🚀 Sent summon request to host...")

    def broadcast_gif_to_all(self, url: str, sender: str = "Host"):
        """Host forwards the GIF signal to all clients and spawns it locally."""
        payload = json.dumps({"action": "show_gif", "url": url, "sender": sender}) + "\n"
        data = payload.encode("utf-8")

        for sock in list(self.clients):
            if sock.state() == QTcpSocket.SocketState.ConnectedState:
                sock.write(data)
                sock.flush()

        # Display on host screen too
        self.trigger_popup(url)

    def trigger_popup(self, url: str):
        worker = GifDownloadWorker(url)
        worker.finished.connect(self.display_gif)
        worker.error.connect(lambda err: self.log(f"❌ Failed to download GIF: {err}"))
        self.workers.append(worker)
        worker.start()

    def display_gif(self, file_path: str):
        try:
            popup = DraggableGifWindow(file_path, duration_ms=3500)
            self.active_popups.append(popup)
            popup.destroyed.connect(lambda: self.active_popups.remove(popup) if popup in self.active_popups else None)
            popup.show()
            popup.raise_()
            popup.activateWindow()
        except Exception as e:
            self.log(f"❌ Display error: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = SyncGifController()
    window.show()
    sys.exit(app.exec())
