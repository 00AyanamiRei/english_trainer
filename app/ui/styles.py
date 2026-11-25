STYLESHEET = """
* { font-family: "Segoe UI", "Noto Sans", "Helvetica Neue", Arial, sans-serif; font-size: 14px; }
QMainWindow, QDialog, QMessageBox { background: #f3f4f6; }
QLabel { color: #1f2937; }
QLabel#title { font-size: 26px; font-weight: 700; }
QLabel#h2 { font-size: 18px; font-weight: 600; }
QLabel#muted { color: #6b7280; }
QLabel#logo { color: white; font-size: 20px; font-weight: 700; }
QLabel#prompt { font-size: 32px; font-weight: 700; }
QLabel#second { font-size: 22px; font-weight: 600; color: #2563eb; }

QFrame#card, QGroupBox { background: white; border: 1px solid #e5e7eb; border-radius: 10px; }
QGroupBox { margin-top: 14px; padding: 14px 12px 12px 12px; font-weight: 600; color: #1f2937; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; }
QFrame#sidebar { background: #111827; }

QLineEdit, QSpinBox, QComboBox {
    background: white; color: #1f2937; border: 1px solid #d1d5db; border-radius: 6px; padding: 6px 8px;
    selection-background-color: #bfdbfe; selection-color: #1e3a8a;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #2563eb; }
QLineEdit#answer { font-size: 18px; padding: 8px 10px; }
QComboBox QAbstractItemView { background: white; color: #1f2937; selection-background-color: #dbeafe; selection-color: #1e3a8a; }

QPushButton {
    background: #2563eb; color: white; border: none; border-radius: 6px; padding: 8px 18px; font-weight: 600;
}
QPushButton:hover { background: #1d4ed8; }
QPushButton:disabled { background: #cbd5e1; color: #f8fafc; }
QPushButton#secondary { background: white; color: #1f2937; border: 1px solid #d1d5db; }
QPushButton#secondary:hover { background: #f3f4f6; }
QPushButton#danger { background: #dc2626; }
QPushButton#danger:hover { background: #b91c1c; }
QPushButton#nav {
    text-align: left; background: transparent; color: #e5e7eb; padding: 12px 16px; border-radius: 8px; font-size: 15px;
}
QPushButton#nav:hover { background: #374151; }
QPushButton#nav:checked { background: #2563eb; color: white; }
QPushButton#choice {
    background: white; color: #1f2937; border: 1px solid #d1d5db; text-align: left;
    padding: 12px 16px; font-size: 16px; font-weight: 500;
}
QPushButton#choice:hover { border-color: #2563eb; background: #eff6ff; }
QPushButton#cardBtn {
    background: white; color: #1f2937; border: 1px solid #e5e7eb; border-radius: 12px;
    text-align: left; padding: 22px 24px; font-size: 16px; font-weight: 500;
}
QPushButton#cardBtn:hover { border-color: #2563eb; background: #eff6ff; }

QTableWidget, QListWidget {
    background: white; color: #1f2937; border: 1px solid #e5e7eb; border-radius: 8px;
    gridline-color: #eef0f3; alternate-background-color: #f9fafb;
    selection-background-color: #dbeafe; selection-color: #1e3a8a;
}
QListWidget::item { padding: 4px 2px; }
QHeaderView::section {
    background: #f3f4f6; color: #374151; padding: 6px; border: none; border-bottom: 1px solid #e5e7eb; font-weight: 600;
}
QProgressBar { border: none; background: #e5e7eb; border-radius: 4px; max-height: 8px; }
QProgressBar::chunk { background: #2563eb; border-radius: 4px; }
QTextBrowser { background: white; color: #1f2937; border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px; font-size: 15px; }
QCheckBox, QRadioButton { color: #1f2937; spacing: 8px; }
QStatusBar { background: #f3f4f6; color: #6b7280; }
"""
