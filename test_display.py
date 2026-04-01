#!/usr/bin/env python3
import sys
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

app = QApplication(sys.argv)

window = QWidget()
window.setWindowTitle("PyQt Test")
layout = QVBoxLayout()
label = QLabel("Test Display\nIf you see this, PyQt6 works!")
label.setAlignment(Qt.AlignmentFlag.AlignCenter)
label.setStyleSheet("color: white; background: #081433; font: bold 20px; padding: 20px;")
layout.addWidget(label)
window.setLayout(layout)
window.setStyleSheet("background: #081433;")
window.showFullScreen()

print("Window shown. Press Ctrl+C to exit.")
sys.exit(app.exec())
