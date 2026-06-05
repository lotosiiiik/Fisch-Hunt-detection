import sys
import time
import threading
import json
import re
import os
import html
import requests
import pytesseract
import mss
import numpy as np
import cv2

from pynput import keyboard
from PyQt5.QtCore import pyqtSignal, Qt, QRect, QPoint
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QVBoxLayout,
    QLabel, QTextEdit, QTabWidget, QCheckBox, QLineEdit,
    QHBoxLayout, QMessageBox, QScrollArea, QComboBox, QFileDialog
)

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

CONFIG_FILE = "config.json"
STORAGE_FILE = "storage.json"
DEFAULT_TESSERACT = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
monitor = None
running = False


class App(QWidget):
    log_signal = pyqtSignal(str)
    detection_signal = pyqtSignal(str)
    control_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Fisch Hunt Detector")
        self.setGeometry(300, 200, 560, 520)
        self.setMinimumSize(520, 480)

        self.setStyleSheet("""
            QWidget { background-color: #10121a; color: #e8eef9; font-family: Segoe UI, Arial, sans-serif; }
            QTabWidget::pane { border: 1px solid #2e3a55; border-radius: 10px; background: #141b2c; }
            QTabBar::tab { background: #1d283f; color: #d8e3ff; padding: 10px 18px; border: 1px solid #2e3a55; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px; }
            QTabBar::tab:selected { background: #2f4d8b; color: white; }
            QPushButton { background-color: #253055; border: 1px solid #3f5aa3; border-radius: 8px; padding: 10px; color: #f0f4ff; }
            QPushButton:hover { background-color: #3352a2; }
            QPushButton:pressed { background-color: #1b2f68; }
            QTextEdit, QLineEdit { background-color: #172038; border: 1px solid #2f4b86; border-radius: 8px; color: #f3f8ff; padding: 8px; }
            QLabel { font-size: 13px; }
            QCheckBox { padding: 4px; }
        """)

        self.webhook = ""
        self.ping_user = ""
        self.toggle_key = "f1"
        self.preview_key = "f2"
        self.tesseract_path = ""
        self.always_on_top = False
        self.last_ocr_snippet = None
        self.ocr_repeat_count = 0
        self.hunt_names = [
            "cookiecutter shark",
            "venom maw",
            "mycotide serpent",
            "great white shark",
            "great hammerhead shark",
            "whale shark",
            "ancient depth serpent",
            "megalodon",
            "ancient megalodon",
            "the kraken",
            "kraken",
            "orca",
            "blue whale",
            "lobster king",
            "leviathan",
            "mossjaw",
            "colossal blue dragon",
            "colossal ancient dragon",
            "baby bloop fish",
            "frostwyrm",
            "reef titan",
            "omnithal",
            "pliosaur",
            "goldwraith",
            "plesiosaur",
            "skeletal leviathan",
            "wyvern",
            "rotbloom",
            "flower guardian",
            "queen bee serpent",
            "legionnaire lamprey",
            "helios sunray",
            "tidecrasher archon",
            "kerauno wyrm",
            "styx angler",
            "ancient kraken",
            "ancient orca",
            "moby",
            "scylla",
            "profane leviathan",
            "elder mossjaw",
            "colossal ethereal dragon",
            "colossus reef titan",
            "awakened omnithal",
            "ancestral pliosaur",
            "ancient goldwraith",
            "witherbloom",
            "toxic guardian",
            "olympian devil",
            "mosslurker",
            "beluga",
            "narwhal",
            "magical narwhal",
            "charybdis",
            "lusca",
            "akkorokamui",
            "ashclaw",
            "bloop fish",
            "dreadfin",
            "phantom megalodon",
            "forbidden plesiosaur",
            "sea leviathan",
            "apex leviathan",
            "sunken chests",
            "brine storm",
            "luminous event",
            "megamouth shark"
        ]
        self.hunts = {name: False for name in self.hunt_names}
        self.custom_hunts = []
        self.storage = {"detections": [], "counts": {}}

        self.init_ui()

        self.log_signal.connect(self.log_msg)
        self.detection_signal.connect(self.handle_detection)
        self.control_signal.connect(self.handle_control)

        self.load_config()
        self.load_storage()
        self.setup_hotkeys()

    # ================= UI =================
    def init_ui(self):
        layout = QVBoxLayout()
        self.tabs = QTabWidget()

        main_tab = QWidget()
        main_layout = QVBoxLayout()

        self.status = QLabel("🔴 Stopped")
        self.status.setStyleSheet("font-size: 14px; color: #ff6b6b;")
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setAcceptRichText(True)

        btn_select = QPushButton("Select Area")
        btn_select.clicked.connect(self.select_area)

        self.toggle_button = QPushButton("Start / Stop")
        self.toggle_button.clicked.connect(self.toggle_run)

        main_layout.addWidget(self.status)
        main_layout.addWidget(btn_select)
        main_layout.addWidget(self.toggle_button)

        self.hotkey_label = QLabel("Toggle key: F1 | Preview key: F3")
        self.hotkey_label.setStyleSheet("font-size: 12px; color: #a0c8ff;")

        self.zone_label = QLabel("Zone: none")
        self.zone_label.setStyleSheet("font-size: 13px; color: #a0c8ff;")
        btn_preview = QPushButton("Preview Zone")
        btn_preview.clicked.connect(self.preview_zone)
        btn_clear_log = QPushButton("Clear Log")
        btn_clear_log.clicked.connect(self.clear_log)

        main_layout.addWidget(self.hotkey_label)
        main_layout.addWidget(self.zone_label)
        main_layout.addWidget(btn_preview)
        main_layout.addWidget(btn_clear_log)
        main_layout.addWidget(self.log)
        main_tab.setLayout(main_layout)

        target_tab = QWidget()
        target_layout = QVBoxLayout()
        target_layout.addWidget(QLabel("Select hunts to track:"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search hunt fishes...")
        self.search_input.textChanged.connect(self.filter_hunt_list)
        target_layout.addWidget(self.search_input)

        self.select_all_button = QPushButton("Select All")
        self.select_all_button.clicked.connect(self.toggle_select_all)
        target_layout.addWidget(self.select_all_button)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(300)
        scroll_area.setStyleSheet("QScrollArea { border: 1px solid #2f4b86; border-radius: 8px; }")

        self.hunt_container = QWidget()
        self.hunt_layout = QVBoxLayout()
        self.hunt_layout.setAlignment(Qt.AlignTop)
        self.hunt_container.setLayout(self.hunt_layout)

        self.checkbox_widgets = []
        for name in self.hunt_names:
            label = self.get_hunt_label(name)
            cb = QCheckBox(label)
            cb.stateChanged.connect(self.on_hunt_checkbox_changed)
            self.checkbox_widgets.append((name, cb))
            self.hunt_layout.addWidget(cb)

        scroll_area.setWidget(self.hunt_container)
        target_layout.addWidget(scroll_area)

        target_layout.addWidget(QLabel("Custom hunt keywords (comma separated):"))
        self.custom_input = QLineEdit()
        self.custom_input.setPlaceholderText("e.g. rockfish, redbone, shadow shark")
        self.custom_input.textChanged.connect(self.update_targets)
        target_layout.addWidget(self.custom_input)
        target_tab.setLayout(target_layout)

        storage_tab = QWidget()
        storage_layout = QVBoxLayout()
        storage_layout.addWidget(QLabel("Detected hunt history:"))

        self.storage_display = QTextEdit()
        self.storage_display.setReadOnly(True)

        btn_refresh = QPushButton("Refresh Storage")
        btn_refresh.clicked.connect(self.update_storage_ui)
        btn_clear = QPushButton("Clear Storage")
        btn_clear.clicked.connect(self.clear_storage)

        button_row = QHBoxLayout()
        button_row.addWidget(btn_refresh)
        button_row.addWidget(btn_clear)

        storage_layout.addWidget(self.storage_display)
        storage_layout.addLayout(button_row)
        storage_tab.setLayout(storage_layout)

        settings_tab = QWidget()
        settings_layout = QVBoxLayout()

        self.webhook_input = QLineEdit()
        self.webhook_input.setPlaceholderText("Discord webhook")

        self.ping_user_input = QLineEdit()
        self.ping_user_input.setPlaceholderText("Discord user ID to ping")

        self.tesseract_input = QLineEdit()
        self.tesseract_input.setPlaceholderText("Path to tesseract.exe")
        self.browse_tesseract_button = QPushButton("Browse")
        self.browse_tesseract_button.clicked.connect(self.browse_tesseract)

        self.always_on_top_checkbox = QCheckBox("Always on top")
        self.always_on_top_checkbox.stateChanged.connect(self.toggle_always_on_top)

        self.toggle_combo = QComboBox()
        self.preview_combo = QComboBox()
        for key in [f"F{i}" for i in range(1, 13)]:
            self.toggle_combo.addItem(key)
            self.preview_combo.addItem(key)
        self.toggle_combo.setCurrentText(self.toggle_key.upper())
        self.preview_combo.setCurrentText(self.preview_key.upper())
        self.toggle_combo.currentTextChanged.connect(lambda _: self.update_hotkey_label())
        self.preview_combo.currentTextChanged.connect(lambda _: self.update_hotkey_label())
        self.update_hotkey_label()

        btn_save = QPushButton("Save Config")
        btn_save.clicked.connect(self.save_config)

        btn_reset = QPushButton("Reset keybinds")
        btn_reset.clicked.connect(self.reset_keybinds)

        settings_layout.addWidget(QLabel("Webhook:"))
        settings_layout.addWidget(self.webhook_input)
        settings_layout.addWidget(QLabel("Ping user ID:"))
        settings_layout.addWidget(self.ping_user_input)
        settings_layout.addWidget(QLabel("Tesseract path:"))
        path_row = QHBoxLayout()
        path_row.addWidget(self.tesseract_input)
        path_row.addWidget(self.browse_tesseract_button)
        settings_layout.addLayout(path_row)
        settings_layout.addWidget(self.always_on_top_checkbox)
        settings_layout.addWidget(QLabel("Toggle key:"))
        settings_layout.addWidget(self.toggle_combo)
        settings_layout.addWidget(QLabel("Preview key:"))
        settings_layout.addWidget(self.preview_combo)
        settings_layout.addWidget(btn_save)
        settings_layout.addWidget(btn_reset)
        settings_tab.setLayout(settings_layout)

        self.tabs.addTab(main_tab, "Main")
        self.tabs.addTab(target_tab, "Hunts")
        self.tabs.addTab(storage_tab, "Storage")
        self.tabs.addTab(settings_tab, "Settings")

        layout.addWidget(self.tabs)
        self.setLayout(layout)

    # ================= LOG =================
    def log_msg(self, msg):
        self.log.append(msg)

    # ================= CONFIG =================
    def save_config(self):
        data = {
            "webhook": self.webhook_input.text(),
            "ping_user": self.ping_user_input.text().strip(),
            "toggle_key": self.toggle_combo.currentText().strip().lower(),
            "preview_key": self.preview_combo.currentText().strip().lower(),
            "tesseract_path": self.tesseract_input.text().strip(),
            "always_on_top": self.always_on_top_checkbox.isChecked(),
            "hunts": {name: cb.isChecked() for name, cb in self.checkbox_widgets},
            "custom_hunts": self.custom_input.text(),
            "monitor": monitor
        }
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(data, f, indent=2)
            self.update_hotkey_label()
            self.log_msg("Saved config")
        except Exception as exc:
            self.log_msg(f"Failed to save config: {exc}")

    def load_config(self):
        global monitor
        try:
            with open(CONFIG_FILE, "r") as f:
                data = json.load(f)

            self.webhook = data.get("webhook", "")
            self.webhook_input.setText(self.webhook)
            self.ping_user = data.get("ping_user", "")
            self.ping_user_input.setText(self.ping_user)
            self.toggle_key = data.get("toggle_key", "f1")
            self.preview_key = data.get("preview_key", "f3")
            self.toggle_combo.setCurrentText(self.toggle_key.upper())
            self.preview_combo.setCurrentText(self.preview_key.upper())
            self.tesseract_path = data.get("tesseract_path", "")
            self.tesseract_input.setText(self.tesseract_path)
            self.always_on_top = data.get("always_on_top", False)
            self.always_on_top_checkbox.setChecked(self.always_on_top)
            self.setWindowFlag(Qt.WindowStaysOnTopHint, self.always_on_top)
            self.show()
            self.update_hotkey_label()
            self.ensure_tesseract_path()

            saved_hunts = data.get("hunts", {})
            for name, cb in self.checkbox_widgets:
                cb.setChecked(saved_hunts.get(name, False))

            self.custom_input.setText(data.get("custom_hunts", ""))
            monitor = data.get("monitor", monitor)
            self.update_zone_label()
            self.update_targets()
            self.log_msg("Config loaded")
        except FileNotFoundError:
            self.save_config()
            self.log_msg("No config found; created blank config")
        except Exception as exc:
            self.log_msg(f"Failed to load config: {exc}")

    # ================= STORAGE =================
    def load_storage(self):
        try:
            with open(STORAGE_FILE, "r") as f:
                self.storage = json.load(f)
            self.storage.setdefault("detections", [])
            self.storage.setdefault("counts", {})
        except FileNotFoundError:
            self.storage = {"detections": [], "counts": {}}
        except Exception as exc:
            self.log_msg(f"Failed to load storage: {exc}")
            self.storage = {"detections": [], "counts": {}}
        self.update_storage_ui()

    def save_storage(self):
        try:
            with open(STORAGE_FILE, "w") as f:
                json.dump(self.storage, f, indent=2)
        except Exception as exc:
            self.log_msg(f"Failed to save storage: {exc}")

    def update_storage_ui(self):
        lines = []
        counts = self.storage.get("counts", {})
        if counts:
            lines.append("Counts:")
            for hunt, count in sorted(counts.items(), key=lambda item: -item[1]):
                lines.append(f"  {hunt}: {count}")
            lines.append("")

        lines.append("Last detections:")
        for entry in self.storage.get("detections", [])[:20]:
            lines.append(f"[{entry['time']}] {entry['hunt']}")

        self.storage_display.setText("\n".join(lines))

    def clear_storage(self):
        confirm = QMessageBox.question(
            self, "Clear storage",
            "Clear all stored hunt detections?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.storage = {"detections": [], "counts": {}}
            self.save_storage()
            self.update_storage_ui()
            self.log_msg("Storage cleared")

    def update_zone_label(self):
        if monitor:
            self.zone_label.setText(f"Zone: {monitor['left']}x{monitor['top']} {monitor['width']}x{monitor['height']}")
        else:
            self.zone_label.setText("Zone: none")

    # ================= TARGETS =================
    def update_targets(self):
        self.hunts = {name: cb.isChecked() for name, cb in self.checkbox_widgets}
        self.custom_hunts = [term.strip().lower() for term in self.custom_input.text().split(",") if term.strip()]
        self.save_config()
        self.update_select_all_button()

    def on_hunt_checkbox_changed(self):
        self.update_targets()

    def zone_to_str(self, zone):

        if not zone:
            return "none"
        return f"{zone['left']}x{zone['top']} {zone['width']}x{zone['height']}"

    def select_region_from_screen(self, title):
        old_opacity = self.windowOpacity()
        old_flags = self.windowFlags()
        old_state = self.windowState()
        self.setWindowOpacity(0)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.setWindowState(Qt.WindowMinimized)
        self.hide()
        QApplication.processEvents()
        time.sleep(0.4)
        try:
            with mss.MSS() as sct:
                screen = np.array(sct.grab(sct.monitors[0]))
            screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
            r = self.select_roi_from_image(screen, title)
            cv2.destroyAllWindows()
        except Exception as exc:
            self.setWindowState(old_state)
            self.setWindowFlags(old_flags)
            self.show()
            self.setWindowOpacity(old_opacity)
            QApplication.processEvents()
            self.log_msg(f"Area selection failed: {exc}")
            return None

        self.setWindowState(old_state)
        self.setWindowFlags(old_flags)
        self.setWindowOpacity(old_opacity)
        self.show()
        self.raise_()
        QApplication.processEvents()
        if r is None:
            return None

        x, y, w, h = r
        return {
            "top": int(y),
            "left": int(x),
            "width": int(w),
            "height": int(h)
        }

    def parse_int(self, text, default):
        try:
            return int(text)
        except Exception:
            return default

    def toggle_select_all(self):
        select_all = any(not cb.isChecked() for _, cb in self.checkbox_widgets)
        for _, cb in self.checkbox_widgets:
            cb.setChecked(select_all)
        self.update_targets()

    def update_select_all_button(self):
        any_unchecked = any(not cb.isChecked() for _, cb in self.checkbox_widgets)
        self.select_all_button.setText("Select All" if any_unchecked else "Unselect All")

    def get_hunt_label(self, name):
        emoji = "🐟"
        lower = name.lower()
        if "shark" in lower or "kraken" in lower or "leviathan" in lower or "orca" in lower:
            emoji = "🦈"
        elif "whale" in lower or "narwhal" in lower or "beluga" in lower:
            emoji = "🐳"
        elif "chest" in lower or "event" in lower or "sunken" in lower:
            emoji = "✨"
        elif "dragon" in lower or "wyrm" in lower or "wyvern" in lower:
            emoji = "🐉"
        elif "bee" in lower or "serpent" in lower or "crab" in lower:
            emoji = "🐙"
        return f"{emoji} {name.title()}"

    def filter_hunt_list(self, text):
        text = text.lower().strip()
        for name, cb in self.checkbox_widgets:
            cb.setVisible(text in name.lower() or not text)

    # ================= CLEAN TEXT =================
    def clean_text(self, text):
        text = text.lower()
        text = text.replace("\n", " ")
        text = re.sub(r"[^a-z0-9\s]", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def perform_ocr(self, img):
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        adaptive = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 15, 3)

        try:
            text_otsu = pytesseract.image_to_string(otsu)
            text_adaptive = pytesseract.image_to_string(adaptive)
        except Exception:
            text_otsu = pytesseract.image_to_string(gray)
            text_adaptive = ""

        return (text_otsu + "\n" + text_adaptive).strip()

    # ================= FILTER =================
    def extract_matches(self, text):
        text = self.clean_text(text)
        compact_text = re.sub(r"[^a-z0-9]", "", text)
        keywords = [name for name, enabled in self.hunts.items() if enabled] + self.custom_hunts

        matched = []
        matched_spans = []
        for keyword in sorted(keywords, key=lambda k: len(k or ""), reverse=True):
            if not keyword:
                continue
            keyword = keyword.lower().strip()
            
            # Skip if this keyword is a substring of an already matched hunt
            if any(keyword in m for m in matched):
                continue
            
            pattern = r"\b" + re.escape(keyword) + r"\b"
            exact_matches = list(re.finditer(pattern, text))
            added = False
            for match in exact_matches:
                span = match.span()
                if any(start <= span[0] and span[1] <= end for start, end in matched_spans):
                    continue
                matched.append(keyword)
                matched_spans.append(span)
                added = True
                break
            if added:
                continue

            compact_keyword = re.sub(r"[^a-z0-9]", "", keyword)
            if compact_keyword and compact_keyword in compact_text:
                if keyword not in matched:
                    # Skip if substring of already matched hunt
                    if not any(keyword in m for m in matched):
                        matched.append(keyword)

        return matched

    def check_text(self, text):
        return bool(self.extract_matches(text))

    def add_detection(self, text):
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = {"time": now, "hunt": text}
        self.storage["detections"].insert(0, entry)
        self.storage["detections"] = self.storage["detections"][:100]
        self.storage["counts"][text] = self.storage["counts"].get(text, 0) + 1
        self.save_storage()
        self.update_storage_ui()

    def handle_detection(self, text):
        self.add_detection(text)
        escaped = html.escape(text.title())
        self.log_msg(f"{escaped} <b>Found!!</b>")

    def clear_log(self):
        self.log.clear()

    def handle_control(self, command):
        if command == "toggle":
            self.toggle_run()
        elif command == "preview":
            self.preview_zone()

    def update_hotkey_label(self):
        self.hotkey_label.setText(
            f"Toggle key: {self.toggle_combo.currentText()} | Preview key: {self.preview_combo.currentText()}"
        )

    def update_status(self, state):
        if state == "Running":
            self.status.setText("🟢 Running")
            self.status.setStyleSheet("font-size: 14px; color: #7fff7f;")
        else:
            self.status.setText("🔴 Stopped")
            self.status.setStyleSheet("font-size: 14px; color: #ff6b6b;")

    def set_tesseract_path(self, path):
        if os.path.isfile(path):
            self.tesseract_path = path
            pytesseract.pytesseract.tesseract_cmd = path
            self.tesseract_input.setText(path)
            self.log_msg(f"Tesseract path set to: {path}")
            return True
        return False

    def browse_tesseract(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Locate tesseract.exe", "", "Tesseract Executable (tesseract.exe);;All Files (*)"
        )
        if file_path:
            if self.set_tesseract_path(file_path):
                self.save_config()
            else:
                self.log_msg("Selected file is not valid Tesseract executable.")

    def ensure_tesseract_path(self):
        if self.tesseract_path and os.path.isfile(self.tesseract_path):
            pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
            return True
        if os.path.isfile(DEFAULT_TESSERACT):
            return self.set_tesseract_path(DEFAULT_TESSERACT)

        self.log_msg("Tesseract not found. Please choose the executable path.")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Locate tesseract.exe", "", "Tesseract Executable (tesseract.exe);;All Files (*)"
        )
        if file_path and self.set_tesseract_path(file_path):
            self.save_config()
            return True

        QMessageBox.warning(
            self, "Tesseract Missing",
            "Tesseract is required for OCR. Please install it or choose the executable location."
        )
        return False

    def toggle_always_on_top(self, state):
        enabled = state == Qt.Checked
        self.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
        self.show()
        self.save_config()

    def reset_keybinds(self):
        self.toggle_combo.setCurrentText("F1")
        self.preview_combo.setCurrentText("F3")
        self.update_hotkey_label()
        self.save_config()
        self.log_msg("Keybinds reset to default")

    def toggle_run(self):
        if running:
            self.stop()
        else:
            self.start()

    # ================= HOTKEYS =================
    def normalize_key_name(self, key):
        return str(key).strip().lower().replace(" ", "")

    def setup_hotkeys(self):
        def on_press(key):
            try:
                raw_name = key.char.lower() if hasattr(key, "char") and key.char else key.name
            except AttributeError:
                return
            name = self.normalize_key_name(raw_name)
            if name == self.toggle_combo.currentText().strip().lower():
                self.control_signal.emit("toggle")
            elif name == self.preview_combo.currentText().strip().lower():
                self.control_signal.emit("preview")

        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

    # ================= SELECT AREA =================
    def select_area(self):
        global monitor
        old_opacity = self.windowOpacity()
        old_flags = self.windowFlags()
        old_state = self.windowState()
        self.setWindowOpacity(0)
        self.setWindowFlag(Qt.WindowStaysOnTopHint, False)
        self.setWindowState(Qt.WindowMinimized)
        self.hide()
        QApplication.processEvents()
        time.sleep(0.4)
        try:
            with mss.MSS() as sct:
                screen = np.array(sct.grab(sct.monitors[0]))
            screen = cv2.cvtColor(screen, cv2.COLOR_BGRA2BGR)
            r = self.select_roi_from_image(screen)
            cv2.destroyAllWindows()
        except Exception as exc:
            self.setWindowState(old_state)
            self.setWindowFlags(old_flags)
            self.show()
            self.setWindowOpacity(old_opacity)
            QApplication.processEvents()
            self.log_msg(f"Area selection failed: {exc}")
            return

        self.setWindowState(old_state)
        self.setWindowFlags(old_flags)
        self.setWindowOpacity(old_opacity)
        self.show()
        self.raise_()
        QApplication.processEvents()
        if r is None:
            self.log_msg("Area selection cancelled")
            return

        x, y, w, h = r
        monitor = {
            "top": int(y),
            "left": int(x),
            "width": int(w),
            "height": int(h)
        }
        self.update_zone_label()
        self.save_config()
        self.log_msg(f"Area selected: {monitor}")

    def select_roi_from_image(self, image, title="Select Area"):
        roi_start = None
        roi_end = None
        selecting = False

        def mouse_callback(event, x, y, flags, param):
            nonlocal roi_start, roi_end, selecting
            if event == cv2.EVENT_LBUTTONDOWN:
                roi_start = (x, y)
                roi_end = (x, y)
                selecting = True
            elif event == cv2.EVENT_MOUSEMOVE and selecting:
                roi_end = (x, y)
            elif event == cv2.EVENT_LBUTTONUP and selecting:
                roi_end = (x, y)
                selecting = False

        window_name = title
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(window_name, mouse_callback)

        while True:
            display = image.copy()
            if roi_start and roi_end:
                cv2.rectangle(display, roi_start, roi_end, (0, 255, 0), 2)

            instructions = "Drag to select area. ENTER/SPACE to confirm, C to cancel."
            cv2.putText(display, instructions, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.imshow(window_name, display)

            key = cv2.waitKey(20) & 0xFF
            if key in (13, 32):
                if roi_start and roi_end:
                    x0, y0 = roi_start
                    x1, y1 = roi_end
                    left = min(x0, x1)
                    top = min(y0, y1)
                    width = abs(x1 - x0)
                    height = abs(y1 - y0)
                    if width > 0 and height > 0:
                        return left, top, width, height
            elif key == ord('c') or key == 27:
                return None

    def preview_zone(self):
        if not monitor:
            self.log_msg("No zone selected to preview")
            return
        try:
            with mss.MSS() as sct:
                shot = sct.grab(monitor)
            img = np.array(shot)
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            cv2.namedWindow("Zone Preview", cv2.WINDOW_NORMAL)
            cv2.imshow("Zone Preview", img)
            cv2.waitKey(1)
            self.log_msg("Preview opened. Close the window to continue.")
        except Exception as exc:
            self.log_msg(f"Preview failed: {exc}")

    # ================= START =================
    def start(self):
        global running
        if not monitor:
            self.log_msg("Select area first")
            return

        if not any(self.hunts.values()) and not self.custom_hunts:
            self.log_msg("Select at least one hunt or add custom keywords")
            return

        if not self.ensure_tesseract_path():
            return

        running = True
        self.toggle_button.setText("Stop")
        self.update_status("Running")
        webhook = self.webhook_input.text().strip()
        ping_line = f"<@{self.ping_user_input.text().strip()}> " if self.ping_user_input.text().strip() else ""

        def loop():
            global running
            seen_matches = set()
            with mss.MSS() as sct:
                while running:
                    shot = sct.grab(monitor)
                    img = np.array(shot)
                    try:
                        text = self.perform_ocr(img)
                    except Exception as exc:
                        self.log_signal.emit(f"[DEBUG OCR ERROR] {exc}")
                        text = ""

                    snippet = (text[:100] if text else "")
                    if snippet == self.last_ocr_snippet:
                        self.ocr_repeat_count += 1
                    else:
                        if self.ocr_repeat_count > 0:
                            self.log_signal.emit(f"[DEBUG OCR] (previous snippet repeated {self.ocr_repeat_count}×)")
                        if snippet:
                            self.log_signal.emit(f"[DEBUG OCR] {snippet}...")
                        self.last_ocr_snippet = snippet
                        self.ocr_repeat_count = 0
                    matches = self.extract_matches(text)
                    matches_set = {m.strip() for m in matches if m.strip()}
                    new_hunts = matches_set - seen_matches

                    if new_hunts:
                        match_text = ", ".join(sorted(new_hunts))
                        self.detection_signal.emit(match_text)
                        seen_matches.update(new_hunts)
                        if webhook:
                            try:
                                requests.post(
                                    webhook,
                                    json={
                                        "username": "Fisch Hunt Detector",
                                        "content": (
                                            f"{ping_line}**🎣 Fisch Hunt Detected!**\n"
                                            f"**Hunt(s):** {match_text}"
                                        )
                                    },
                                    timeout=10,
                                )
                            except Exception as exc:
                                self.log_signal.emit(f"Webhook error: {exc}")

                    time.sleep(2)

        threading.Thread(target=loop, daemon=True).start()

    # ================= STOP =================
    def stop(self):
        global running
        running = False
        self.update_status("Stopped")
        self.toggle_button.setText("Start / Stop")


app = QApplication(sys.argv)
window = App()
window.show()
sys.exit(app.exec_())