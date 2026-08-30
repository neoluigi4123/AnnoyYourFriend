import base64
import json
import os
import random
import re
import sys
import tempfile
import requests
from PyQt6.QtCore import Qt, QPoint, QSize, QTimer, QThread, pyqtSignal, QBuffer, QByteArray, QIODevice
from PyQt6.QtGui import QGuiApplication, QImageReader, QMovie, QPixmap, QImage, QKeySequence
from PyQt6.QtNetwork import QTcpServer, QTcpSocket, QHostAddress
from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QTextEdit, QRadioButton, QGroupBox, QSpinBox,
    QFileDialog, QFrame
)

DEFAULT_PORT = 45454
DEFAULT_GIF_URL = "https://static2.klipy.com/ii/e293a233a303a98e471f78d04e13a1b0/a0/86/58Y6YqlV.gif"
MAX_IMAGE_DIM = 500  # Max dimension (longest side) for static images


# -------------------------------------------------------------
# Background Worker for Downloading GIFs from URL
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

            # Extract direct link if an HTML landing page was provided
            if not data.startswith(b"GIF") and not data.startswith(b"\x89PNG") and not data.startswith(b"\xff\xd8"):
                html = resp.text
                match = re.search(r'<meta[^>]+(?:property|content)=["\']og:image["\'][^>]+(?:content|property)=["\']([^"\']+)["\']', html, re.I)
                direct_link = match.group(1) if match else None
                if not direct_link:
                    direct_link = re.search(r'https?://[^\s"\'<>]+\.(?:gif|png|jpe?g|webp)', html, re.I)
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
# Edge-Spawning Draggable Media Window (GIF & Static Images)
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

        # 1. Calculate dimensions relative to screen size
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

        # 3. Position randomly along the screen edges
        spawn_pos = self.get_random_edge_position(screen, new_w, new_h)
        self.move(spawn_pos)

        # 4. Animated GIF or Static Pixmap Label
        self.label = QLabel(self)
        self.label.setFixedSize(new_w, new_h)
        self.label.setScaledContents(True)

        self.movie = QMovie(self.temp_path)
        if self.movie.isValid() and self.movie.frameCount() > 1:
            self.movie.setScaledSize(QSize(new_w, new_h))
            self.label.setMovie(self.movie)
            self.movie.start()
        else:
            pixmap = QPixmap(self.temp_path).scaled(
                new_w, new_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.label.setPixmap(pixmap)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.label)

    def get_random_edge_position(self, screen_rect, w, h) -> QPoint:
        sx, sy, sw, sh = screen_rect.x(), screen_rect.y(), screen_rect.width(), screen_rect.height()
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
        if hasattr(self, 'movie') and self.movie:
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
# Main Control Panel
# -------------------------------------------------------------
class SyncGifController(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sync GIF & Image Overlay (Bidirectional)")
        self.resize(560, 620)

        self.active_popups = []
        self.workers = []

        # Staged Media Data: dict(type="url"|"base64", data=..., ext="gif"|"png")
        self.staged_media = None

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

        # 2. Connection config
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

        # 3. Media Picker & Summon Section
        media_group = QGroupBox("3. Choose Media to Summon (URL, Upload, or Paste)")
        media_layout = QVBoxLayout(media_group)

        # URL Input
        url_layout = QHBoxLayout()
        self.input_url = QLineEdit()
        self.input_url.setPlaceholderText("Enter GIF/Image URL or pick a file / paste image below...")
        self.input_url.textChanged.connect(self.on_url_changed)
        url_layout.addWidget(self.input_url)
        media_layout.addLayout(url_layout)

        # File & Paste Action Buttons
        btn_action_layout = QHBoxLayout()
        self.btn_browse = QPushButton("📁 Browse File (GIF/PNG/JPG)...")
        self.btn_browse.clicked.connect(self.choose_file)
        self.btn_paste = QPushButton("📋 Paste Clipboard Image (Ctrl+V)")
        self.btn_paste.clicked.connect(self.paste_from_clipboard)
        btn_action_layout.addWidget(self.btn_browse)
        btn_action_layout.addWidget(self.btn_paste)
        media_layout.addLayout(btn_action_layout)

        # Staged Media Preview
        preview_container = QHBoxLayout()
        self.lbl_preview_thumb = QLabel()
        self.lbl_preview_thumb.setFixedSize(64, 64)
        self.lbl_preview_thumb.setFrameShape(QFrame.Shape.Box)
        self.lbl_preview_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_preview_thumb.setText("No\nMedia")

        self.lbl_preview_info = QLabel("No media currently selected.")
        self.lbl_preview_info.setWordWrap(True)

        preview_container.addWidget(self.lbl_preview_thumb)
        preview_container.addWidget(self.lbl_preview_info, stretch=1)
        media_layout.addLayout(preview_container)

        # Summon Button
        self.btn_summon = QPushButton("🎉 Summon Media on EVERYONE'S Screen!")
        self.btn_summon.setFixedHeight(40)
        self.btn_summon.setEnabled(False)
        self.btn_summon.clicked.connect(self.request_summon_media)
        media_layout.addWidget(self.btn_summon)

        layout.addWidget(media_group)

        # 4. Activity log
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        layout.addWidget(QLabel("Activity Log:"))
        layout.addWidget(self.log_area)

        # Set default initial URL
        self.input_url.setText(DEFAULT_GIF_URL)

    def log(self, text: str):
        self.log_area.append(text)

    # ------------------ Media Helpers & Resizing ------------------
    def resize_qimage_if_needed(self, img: QImage, max_dim: int = MAX_IMAGE_DIM) -> QImage:
        """Scales the image down so its longest side is at most max_dim."""
        if img.width() > max_dim or img.height() > max_dim:
            return img.scaled(
                max_dim, max_dim,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        return img

    def qimage_to_base64(self, img: QImage) -> str:
        """Converts a QImage to base64-encoded PNG."""
        ba = QByteArray()
        buffer = QBuffer(ba)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buffer, "PNG")
        return base64.b64encode(ba.data()).decode("utf-8")

    def stage_base64_image(self, b64_str: str, ext: str, desc: str, thumb_pixmap: QPixmap):
        self.staged_media = {
            "type": "base64",
            "data": b64_str,
            "ext": ext
        }
        self.lbl_preview_thumb.setPixmap(thumb_pixmap.scaled(
            64, 64, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        ))
        self.lbl_preview_info.setText(f"Ready: {desc}")

    def on_url_changed(self, text: str):
        text = text.strip()
        if text:
            self.staged_media = {"type": "url", "data": text, "ext": "gif"}
            self.lbl_preview_thumb.setText("URL")
            self.lbl_preview_info.setText(f"URL: {text[:45]}..." if len(text) > 45 else f"URL: {text}")

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Image or GIF", "",
            "Media Files (*.gif *.png *.jpg *.jpeg *.webp *.bmp);;All Files (*)"
        )
        if not path:
            return

        self.input_url.blockSignals(True)
        self.input_url.clear()
        self.input_url.blockSignals(False)

        ext = os.path.splitext(path)[1].lower().replace(".", "")
        if ext == "gif":
            with open(path, "rb") as f:
                raw_bytes = f.read()
            b64_data = base64.b64encode(raw_bytes).decode("utf-8")
            pixmap = QPixmap(path)
            self.stage_base64_image(b64_data, "gif", f"GIF File ({os.path.basename(path)})", pixmap)
            self.log(f"📁 Loaded GIF: {os.path.basename(path)}")
        else:
            img = QImage(path)
            if img.isNull():
                self.log("❌ Could not load image file.")
                return
            img = self.resize_qimage_if_needed(img, MAX_IMAGE_DIM)
            b64_data = self.qimage_to_base64(img)
            pixmap = QPixmap.fromImage(img)
            self.stage_base64_image(b64_data, "png", f"Image ({img.width()}x{img.height()})", pixmap)
            self.log(f"📁 Loaded & resized image: {os.path.basename(path)} ({img.width()}x{img.height()})")

    def paste_from_clipboard(self):
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        if mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                self.input_url.blockSignals(True)
                self.input_url.clear()
                self.input_url.blockSignals(False)

                img = self.resize_qimage_if_needed(img, MAX_IMAGE_DIM)
                b64_data = self.qimage_to_base64(img)
                pixmap = QPixmap.fromImage(img)
                self.stage_base64_image(b64_data, "png", f"Clipboard Image ({img.width()}x{img.height()})", pixmap)
                self.log(f"📋 Pasted image from clipboard (resized to {img.width()}x{img.height()})")
                return

        if mime.hasText():
            text = clipboard.text().strip()
            if text.startswith("http://") or text.startswith("https://"):
                self.input_url.setText(text)
                self.log(f"📋 Pasted URL from clipboard: {text}")
                return

        self.log("⚠️ Clipboard does not contain an image or valid URL.")

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.StandardKey.Paste) or (
            event.key() == Qt.Key.Key_V and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.paste_from_clipboard()
        else:
            super().keyPressEvent(event)

    # ------------------ Mode & Network Controls ------------------
    def on_mode_toggled(self):
        is_host = self.radio_host.isChecked()
        self.input_ip.setEnabled(not is_host)
        self.btn_toggle_network.setText("Start Server" if is_host else "Connect to Host")
        self.btn_summon.setEnabled(False)

    def toggle_network(self):
        if self.radio_host.isChecked():
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
        while sock.canReadLine():
            raw_line = sock.readLine().data().decode("utf-8").strip()
            if not raw_line:
                continue
            try:
                msg = json.loads(raw_line)
                if msg.get("action") == "summon_media":
                    sender = msg.get("sender", "A friend")
                    self.log(f"📥 {sender} summoned media! Broadcasting to all...")
                    self.broadcast_media(msg.get("media"), sender=sender)
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
        while self.client_socket.canReadLine():
            raw_line = self.client_socket.readLine().data().decode("utf-8").strip()
            if not raw_line:
                continue
            try:
                msg = json.loads(raw_line)
                if msg.get("action") == "show_media":
                    sender = msg.get("sender", "Someone")
                    self.log(f"✨ Incoming media from {sender}!")
                    self.handle_incoming_media(msg.get("media"))
            except Exception as e:
                self.log(f"Error parsing broadcast: {e}")

    # ------------------ Summon & Broadcast Logic ------------------
    def request_summon_media(self):
        if not self.staged_media:
            self.log("⚠️ No media selected to summon.")
            return

        if self.radio_host.isChecked():
            self.broadcast_media(self.staged_media, sender="Host")
        else:
            if self.client_socket and self.client_socket.state() == QTcpSocket.SocketState.ConnectedState:
                req = json.dumps({
                    "action": "summon_media",
                    "media": self.staged_media,
                    "sender": "Client"
                }) + "\n"
                self.client_socket.write(req.encode("utf-8"))
                self.client_socket.flush()
                self.log("🚀 Sent summon request to host...")

    def broadcast_media(self, media_payload: dict, sender: str = "Host"):
        payload = json.dumps({
            "action": "show_media",
            "media": media_payload,
            "sender": sender
        }) + "\n"
        data = payload.encode("utf-8")

        for sock in list(self.clients):
            if sock.state() == QTcpSocket.SocketState.ConnectedState:
                sock.write(data)
                sock.flush()

        # Display on host screen
        self.handle_incoming_media(media_payload)

    def handle_incoming_media(self, media_payload: dict):
        if not media_payload:
            return

        media_type = media_payload.get("type")
        if media_type == "url":
            url = media_payload.get("data")
            worker = GifDownloadWorker(url)
            worker.finished.connect(self.display_media_file)
            worker.error.connect(lambda err: self.log(f"❌ Failed to download GIF: {err}"))
            self.workers.append(worker)
            worker.start()
        elif media_type == "base64":
            try:
                b64_data = media_payload.get("data")
                ext = media_payload.get("ext", "png")
                raw_bytes = base64.b64decode(b64_data.encode("utf-8"))

                temp_file = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
                temp_file.write(raw_bytes)
                temp_file.close()

                self.display_media_file(temp_file.name)
            except Exception as e:
                self.log(f"❌ Error displaying base64 media: {e}")

    def display_media_file(self, file_path: str):
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
