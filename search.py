import os, time, threading
from queue import Queue
from concurrent.futures import ThreadPoolExecutor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QLineEdit, 
    QListWidget, QListWidgetItem, QCheckBox, QProgressBar, QHBoxLayout, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, QUrl, QTimer, pyqtSignal
from PyQt5.QtGui import QDesktopServices, QFont

# Global parameters
NUM_THREADS = os.cpu_count() * 2  # Maximum threads for speed
OUTPUT_FILE = "found_files_doc.txt"

# Thread-safe queues and sets
drive_queue = Queue()
found_files = set()
lock = threading.Lock()
stop_event = threading.Event()

# A simple clickable label class.
class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    def mousePressEvent(self, event):
        self.clicked.emit()

class FileSearcher(QWidget):
    # Signal to safely send new file results to the UI thread
    new_files_signal = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Really Deep File Search Tool")
        self.setGeometry(100, 100, 800, 1000)
        
        self.total_drives = 0
        self.drives_completed = 0
        self.start_time = 0
        self.progress_bars = {}  # Keyed by drive letter

        main_layout = QVBoxLayout()
        
        # --- Header Section ---
        header_layout = QVBoxLayout()
        header_layout.setAlignment(Qt.AlignCenter)
        
        header_tagline = QLabel("made by sunshine vendetta because windows search is slow and dumb as fuck")
        header_tagline.setFont(QFont("Arial", 12, QFont.Bold))
        header_tagline.setAlignment(Qt.AlignCenter)
        
        # Clickable link label using rich text
        header_link = QLabel('<a href="https://x.com/sunshinevndetta">https://x.com/sunshinevndetta</a>')
        header_link.setFont(QFont("Arial", 12))
        header_link.setAlignment(Qt.AlignCenter)
        header_link.setTextFormat(Qt.RichText)
        header_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        header_link.setOpenExternalLinks(True)
        
        # Donation address label - clicking copies address to clipboard
        self.donate_label = ClickableLabel("donate: 0xD320699029B09bEA3380EB22dE59C3030d70f278")
        self.donate_label.setFont(QFont("Arial", 12))
        self.donate_label.setAlignment(Qt.AlignCenter)
        self.donate_label.setStyleSheet("color: #00ff00;")  # Neon green
        self.donate_label.clicked.connect(self.copy_donation_address)
        
        header_layout.addWidget(header_tagline)
        header_layout.addWidget(header_link)
        header_layout.addWidget(self.donate_label)
        
        main_layout.addLayout(header_layout)
        # --- End Header Section ---

        # Status Label for messages and estimated time left
        self.status_label = QLabel("")
        self.status_label.setFont(QFont("Arial", 10))
        self.status_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_label)
        
        # Drive Selection
        self.all_drives_checkbox = QCheckBox("Select All Drives")
        self.all_drives_checkbox.stateChanged.connect(self.select_all_drives)
        main_layout.addWidget(self.all_drives_checkbox)
        
        self.drive_checkboxes = []
        for drive in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            if os.path.exists(f"{drive}:\\"):
                checkbox = QCheckBox(f"{drive}:\\")
                main_layout.addWidget(checkbox)
                self.drive_checkboxes.append(checkbox)
        
        # Input for file extension or keyword
        self.extension_input = QLineEdit()
        self.extension_input.setPlaceholderText("Enter file extension or keyword (e.g., .pdf, photo, hot)")
        main_layout.addWidget(self.extension_input)
        
        # Start Search Button
        self.search_button = QPushButton("Start Search")
        self.search_button.clicked.connect(self.start_search)
        main_layout.addWidget(self.search_button)

        # Stop Search Button
        self.stop_button = QPushButton("Stop Search")
        self.stop_button.clicked.connect(self.stop_search)
        self.stop_button.setEnabled(False)
        main_layout.addWidget(self.stop_button)
        
        # Dynamic results list with inner search functionality
        self.result_list = QListWidget()
        # Make the result list widget resizable
        self.result_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.result_list.itemClicked.connect(self.open_file)
        main_layout.addWidget(self.result_list)
        
        # Inner Search Bar for Results
        self.inner_search_box = QLineEdit()
        self.inner_search_box.setPlaceholderText("Search within results...")
        self.inner_search_box.textChanged.connect(self.inner_search)
        main_layout.addWidget(self.inner_search_box)
        
        # Hint label for clicking on results
        click_hint = QLabel("Click on a result to open the folder. Yeah, it’s that easy.")
        click_hint.setFont(QFont("Arial", 9))
        click_hint.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(click_hint)
        
        self.setLayout(main_layout)
        
        # Timer for UI updates (progress, time left, etc.)
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_ui)
        
        # Connect our custom signal to the UI update slot
        self.new_files_signal.connect(self.batch_update)
        
        # Apply Frutiger Aero Dark Mode Styles
        self.setStyleSheet("""
            QWidget {
                background-color: #1e1e1e;
                color: #cfcfcf;
            }
            QLineEdit {
                background-color: #2e2e2e;
                color: #cfcfcf;
                border: 1px solid #444;
                padding: 5px;
            }
            QPushButton {
                background-color: #3a3a3a;
                color: #00ff00;
                border: 1px solid #555;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #444;
                color: #ff0000;
            }
            QProgressBar {
                background-color: #2e2e2e;
                color: #cfcfcf;
                border: 1px solid #555;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #00ff00;
            }
            QListWidget {
                background-color: #1e1e1e;
                color: #cfcfcf;
                border: 1px solid #444;
            }
        """)

    def copy_donation_address(self):
        # Copy donation address to clipboard
        clipboard = QApplication.clipboard()
        address = "0xD320699029B09bEA3380EB22dE59C3030d70f278"
        clipboard.setText(address)
        QMessageBox.information(self, "Donation Copied", "Donation address copied to clipboard! Send some meme coins over.")

    def select_all_drives(self):
        state = self.all_drives_checkbox.isChecked()
        for checkbox in self.drive_checkboxes:
            checkbox.setChecked(state)
    
    def inner_search(self):
        search_term = self.inner_search_box.text().lower()
        matches = 0
        for i in range(self.result_list.count()):
            item = self.result_list.item(i)
            visible = search_term in item.text().lower()
            item.setHidden(not visible)
            if visible:
                matches += 1
        self.status_label.setText(f"{matches} matches found.")
    
    def batch_update(self, file_paths):
        for file_path in file_paths:
            item = QListWidgetItem(file_path)
            item.setToolTip(file_path)
            self.result_list.addItem(item)
    
    def open_file(self, item):
        folder = os.path.dirname(item.text())
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        QMessageBox.information(self, "File Opened", "Clicked, opening in Windows Explorer. You're welcome.")
    
    def start_search(self):
        # Reset previous search data
        selected_drives = [cb.text() for cb in self.drive_checkboxes if cb.isChecked()]
        if not selected_drives:
            self.result_list.addItem("❌ No drives selected.")
            return
        self.result_list.clear()
        with lock:
            found_files.clear()
        self.drives_completed = 0
        self.total_drives = len(selected_drives)
        self.start_time = time.time()
        
        self.status_label.setText("I'm working bitch, don't move, do not close me, it's working ok?")
        
        # Write header to output file
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("Search Results:\n")
        
        stop_event.clear()
        self.stop_button.setEnabled(True)
        
        # Populate drive queue with (drive, query) tuples
        query = self.extension_input.text().lower()
        for drive in selected_drives:
            drive_queue.put((drive, query))
        
        # Create and add progress bars for each drive
        for drive in selected_drives:
            progress_bar = QProgressBar()
            progress_bar.setAlignment(Qt.AlignCenter)
            progress_bar.setMaximum(100)
            progress_bar.setValue(0)
            self.progress_bars[drive] = progress_bar
            progress_layout = QHBoxLayout()
            label = QLabel(f"Searching {drive}")
            label.setFont(QFont("Arial", 10))
            progress_layout.addWidget(label)
            progress_layout.addWidget(progress_bar)
            self.layout().addLayout(progress_layout)
        
        # Start worker threads
        self.executor = ThreadPoolExecutor(max_workers=NUM_THREADS)
        for _ in range(NUM_THREADS):
            self.executor.submit(self.worker)
        
        self.timer.start(100)
    
    def stop_search(self):
        stop_event.set()  # Signal workers to stop
        self.executor.shutdown(wait=False)
        self.stop_button.setEnabled(False)
        self.status_label.setText("Search stopped. Results saved.")
        QMessageBox.information(self, "Search Stopped", 
            "You found it already? Cool, enjoy baby. I saved your life, right?")
    
    def worker(self):
        while not drive_queue.empty() and not stop_event.is_set():
            drive, query = drive_queue.get()
            self.search_drive(drive, query)
            drive_queue.task_done()
            with lock:
                self.drives_completed += 1
    
    def search_drive(self, drive, query):
        try:
            total_files = 0
            matched_files = 0
            for root, dirs, files in os.walk(drive, topdown=True):
                total_files += len(files)
                for file in files:
                    if stop_event.is_set():
                        return
                    if query in file.lower():
                        full_path = os.path.join(root, file)
                        with lock:
                            if full_path not in found_files:
                                found_files.add(full_path)
                                self.new_files_signal.emit([full_path])
                        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
                            f.write(full_path + "\n")
                    matched_files += 1
                    if total_files > 0:
                        progress = int((matched_files / total_files) * 100)
                        QTimer.singleShot(0, lambda d=drive, p=progress: self.progress_bars[d].setValue(p))
        except Exception as e:
            print(f"Error in search_drive({drive}): {e}")
    
    def update_ui(self):
        elapsed = time.time() - self.start_time
        if self.drives_completed > 0:
            estimated_total = elapsed / self.drives_completed * self.total_drives
            time_left = max(0, estimated_total - elapsed)
            hrs, rem = divmod(time_left, 3600)
            mins, secs = divmod(rem, 60)
            time_left_str = f"{int(hrs):02d}:{int(mins):02d}:{int(secs):02d}"
        else:
            time_left_str = "calculating..."
        self.status_label.setText(f"I'm working bitch, don't move, do not close me, it's working ok? | Time left: {time_left_str}")
        
        if self.drives_completed >= self.total_drives:
            self.timer.stop()
            self.stop_button.setEnabled(False)
            self.status_label.setText("All done, baby. Your treasure map (aka results) is in found_files_doc.txt inside the folder where you put this .exe. Thank me later.")
            QMessageBox.information(self, "Search Complete", 
                "All done, baby. Your treasure map (aka results) is in found_files_doc.txt inside the folder where you put this .exe, Thank me later.")

def main():
    app = QApplication([])
    window = FileSearcher()
    window.show()
    app.exec_()

if __name__ == "__main__":
    main()
