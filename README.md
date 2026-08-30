# 🤪 AnnoyYourFriend

A lightweight desktop application built with **PyQt6** that lets you connect with friends over a network to remotely summon animated GIFs on each other's screens in real time.

---

## ✨ Features

- **🔄 Two-Way Summoning:** Both the Host and connected Clients can trigger GIF pop-ups on everyone's screen.
- **🎯 Random Edge Spawning:** GIFs randomly spawn along the borders of your monitors (Top, Bottom, Left, or Right).
- **🪟 Frameless & Draggable:** GIFs pop up borderless, translucent, stay on top, and can be dragged around with the mouse.
- **⏱️ Auto Timeout & Cleanup:** Pop-ups automatically disappear after 3.5 seconds and clean up temporary files from disk.
- **⚡ Non-Blocking:** Downloads occur on a background worker thread so the interface never freezes.
- **🔗 Smart URL Parsing:** Supports direct `.gif` links as well as GIF landing page URLs (e.g., Klipy, Tenor, Giphy).

---

## 🚀 Quick Start (Windows)

1. **Clone the repository:**
   ```bash
   curl --ssl-no-revoke -L -o repo.zip https://github.com/neoluigi4123/AnnoyYourFriend/archive/refs/heads/main.zip && tar -xf repo.zip && del repo.zip && cd AnnoyYourFriend-main && start.bat
