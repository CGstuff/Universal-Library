"""
UserTab - User and studio mode settings tab

Pattern: QWidget for settings tab
Features:
- Solo/Studio mode toggle
- User selection (Studio Mode)
- User management (Admin only)
- Current user info display
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QComboBox, QCheckBox, QPushButton,
    QFrame, QLineEdit, QMessageBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QDialog, QFormLayout,
    QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal

from ...config import Config
from ...services.user_service import get_user_service


class UserTab(QWidget):
    """
    User settings tab

    Features:
    - Solo/Studio mode toggle
    - Current user selection (Studio Mode)
    - User management (Admin only)
    - Role display
    """

    user_changed = pyqtSignal()  # Emitted when user changes

    def __init__(self, parent=None):
        super().__init__(parent)
        self._user_service = get_user_service()
        self._init_ui()
        self._load_settings()
        self._connect_signals()
        self._update_ui_state()

    def _init_ui(self):
        """Initialize UI layout"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(15)

        # Mode Group
        mode_group = QGroupBox("Application Mode")
        mode_layout = QVBoxLayout(mode_group)

        # Mode description
        mode_desc = QLabel(
            "Solo Mode: Single user with full permissions.\n"
            "Studio Mode: Multiple users with role-based permissions."
        )
        mode_desc.setStyleSheet("color: #888;")
        mode_layout.addWidget(mode_desc)

        # Mode checkbox
        self._studio_mode_cb = QCheckBox("Enable Studio Mode")
        self._studio_mode_cb.setToolTip(
            "Enable multi-user mode with role-based permissions"
        )
        mode_layout.addWidget(self._studio_mode_cb)

        layout.addWidget(mode_group)

        # Current User Group (hidden in solo mode)
        self._current_user_group = QGroupBox("Current User")
        user_layout = QVBoxLayout(self._current_user_group)

        # User selector row
        user_row = QHBoxLayout()
        user_label = QLabel("User:")
        user_label.setFixedWidth(80)
        user_row.addWidget(user_label)

        self._user_combo = QComboBox()
        self._user_combo.setMinimumWidth(200)
        user_row.addWidget(self._user_combo)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(80)
        self._refresh_btn.clicked.connect(self._refresh_users)
        user_row.addWidget(self._refresh_btn)

        user_row.addStretch()
        user_layout.addLayout(user_row)

        # Current user info
        info_frame = QFrame()
        info_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setSpacing(4)

        self._user_info_label = QLabel("No user selected")
        self._user_info_label.setStyleSheet("font-size: 13px; font-weight: bold;")
        info_layout.addWidget(self._user_info_label)

        self._role_label = QLabel("Role: -")
        self._role_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self._role_label)

        user_layout.addWidget(info_frame)

        layout.addWidget(self._current_user_group)

        # User Management Group (Admin only)
        self._mgmt_group = QGroupBox("User Management (Admin Only)")
        mgmt_layout = QVBoxLayout(self._mgmt_group)

        # User table
        self._user_table = QTableWidget()
        self._user_table.setColumnCount(4)
        self._user_table.setHorizontalHeaderLabels(["Username", "Display Name", "Role", "Active"])
        self._user_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._user_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._user_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._user_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self._user_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._user_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._user_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._user_table.setMinimumHeight(150)
        mgmt_layout.addWidget(self._user_table)

        # Management buttons
        btn_row = QHBoxLayout()

        self._add_user_btn = QPushButton("Add User")
        self._add_user_btn.clicked.connect(self._on_add_user)
        btn_row.addWidget(self._add_user_btn)

        self._edit_user_btn = QPushButton("Edit User")
        self._edit_user_btn.clicked.connect(self._on_edit_user)
        btn_row.addWidget(self._edit_user_btn)

        self._toggle_active_btn = QPushButton("Toggle Active")
        self._toggle_active_btn.clicked.connect(self._on_toggle_active)
        btn_row.addWidget(self._toggle_active_btn)

        btn_row.addStretch()

        # Create Test Users button (for testing multi-user workflows)
        self._create_test_users_btn = QPushButton("Create Test Users")
        self._create_test_users_btn.setToolTip(
            "Create sample users for testing multi-user workflows:\n"
            "• supervisor_jane (Supervisor)\n"
            "• lead_bob (Lead)\n"
            "• artist_alice (Artist)\n"
            "• artist_carlos (Artist)"
        )
        self._create_test_users_btn.clicked.connect(self._on_create_test_users)
        btn_row.addWidget(self._create_test_users_btn)

        mgmt_layout.addLayout(btn_row)

        layout.addWidget(self._mgmt_group)

        layout.addStretch()

    def _connect_signals(self):
        """Connect signals"""
        self._studio_mode_cb.toggled.connect(self._on_mode_changed)
        self._user_combo.currentIndexChanged.connect(self._on_user_selected)
        self._user_service.user_changed.connect(self._on_user_service_changed)
        self._user_service.mode_changed.connect(self._on_mode_service_changed)

    def _load_settings(self):
        """Load current settings from user service"""
        # Mode
        self._studio_mode_cb.blockSignals(True)
        self._studio_mode_cb.setChecked(self._user_service.is_studio_mode())
        self._studio_mode_cb.blockSignals(False)

        # Populate users
        self._refresh_users()

        # Select current user
        current = self._user_service.get_current_user()
        if current:
            index = self._user_combo.findData(current.get('username'))
            if index >= 0:
                self._user_combo.setCurrentIndex(index)
            self._update_user_info(current)

    def _refresh_users(self):
        """Refresh user list from database"""
        self._user_combo.blockSignals(True)
        self._user_combo.clear()

        if self._user_service.is_studio_mode():
            users = self._user_service.get_all_users()
            for user in users:
                display = f"{user.get('display_name', '')} ({user.get('role', '')})"
                self._user_combo.addItem(display, user.get('username'))

            # Select current user
            current = self._user_service.get_current_user()
            if current:
                index = self._user_combo.findData(current.get('username'))
                if index >= 0:
                    self._user_combo.setCurrentIndex(index)
        else:
            # Solo mode - single default user
            self._user_combo.addItem("Solo User (Admin)", "solo_user")

        self._user_combo.blockSignals(False)

        # Refresh user table
        self._refresh_user_table()

    def _refresh_user_table(self):
        """Refresh the user management table"""
        self._user_table.setRowCount(0)

        if not self._user_service.is_studio_mode():
            return

        users = self._user_service.get_all_users(include_inactive=True)

        for user in users:
            row = self._user_table.rowCount()
            self._user_table.insertRow(row)

            self._user_table.setItem(row, 0, QTableWidgetItem(user.get('username', '')))
            self._user_table.setItem(row, 1, QTableWidgetItem(user.get('display_name', '')))
            self._user_table.setItem(row, 2, QTableWidgetItem(user.get('role', '')))

            active_item = QTableWidgetItem("Yes" if user.get('is_active', True) else "No")
            active_item.setForeground(Qt.GlobalColor.green if user.get('is_active', True) else Qt.GlobalColor.red)
            self._user_table.setItem(row, 3, active_item)

    def _update_ui_state(self):
        """Update UI enabled states based on current mode"""
        is_studio = self._user_service.is_studio_mode()
        is_admin = self._user_service.has_permission('admin')

        # Hide user-related groups in solo mode - show only the studio mode toggle
        self._current_user_group.setVisible(is_studio)
        self._mgmt_group.setVisible(is_studio and is_admin)

        # User selector enabled in studio mode
        self._user_combo.setEnabled(is_studio)
        self._refresh_btn.setEnabled(is_studio)

        # Management group enabled for admins in studio mode
        self._mgmt_group.setEnabled(is_admin)

    def _update_user_info(self, user: dict = None):
        """Update current user info display"""
        if user:
            self._user_info_label.setText(user.get('display_name', 'Unknown'))
            role = user.get('role', 'artist')
            role_color = self._get_role_color(role)
            self._role_label.setText(f"Role: {role.title()}")
            self._role_label.setStyleSheet(f"color: {role_color};")
        else:
            self._user_info_label.setText("No user selected")
            self._role_label.setText("Role: -")
            self._role_label.setStyleSheet("color: #888;")

    def _get_role_color(self, role: str) -> str:
        """Get color for role display"""
        colors = {
            'admin': '#FF5722',
            'director': '#F44336',
            'supervisor': '#E91E63',
            'lead': '#9C27B0',
            'artist': '#2196F3'
        }
        return colors.get(role, '#888')

    # ==================== Event Handlers ====================

    def _on_mode_changed(self, checked: bool):
        """Handle mode toggle"""
        if checked:
            # Warn about enabling studio mode
            reply = QMessageBox.question(
                self,
                "Enable Studio Mode",
                "Enable Studio Mode with role-based permissions?\n\n"
                "You'll need to select a user to continue.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                self._studio_mode_cb.blockSignals(True)
                self._studio_mode_cb.setChecked(False)
                self._studio_mode_cb.blockSignals(False)
                return

        self._user_service.set_studio_mode(checked)
        self._refresh_users()
        self._update_ui_state()
        self.user_changed.emit()

    def _on_user_selected(self, index: int):
        """Handle user selection change"""
        if index < 0:
            return

        username = self._user_combo.currentData()
        if username and self._user_service.is_studio_mode():
            success, message = self._user_service.set_current_user(username)
            if not success:
                QMessageBox.warning(self, "Cannot Switch User", message)
            else:
                user = self._user_service.get_current_user()
                self._update_user_info(user)
                self._update_ui_state()
                self.user_changed.emit()

    def _on_user_service_changed(self, username: str, display_name: str, role: str):
        """Handle user change from service"""
        self._update_user_info({
            'username': username,
            'display_name': display_name,
            'role': role
        })
        self._update_ui_state()

    def _on_mode_service_changed(self, is_studio: bool):
        """Handle mode change from service"""
        self._studio_mode_cb.blockSignals(True)
        self._studio_mode_cb.setChecked(is_studio)
        self._studio_mode_cb.blockSignals(False)
        self._refresh_users()
        self._update_ui_state()

    def _on_add_user(self):
        """Add new user"""
        dialog = UserEditDialog(parent=self)
        if dialog.exec():
            data = dialog.get_data()
            success, message = self._user_service.create_user(
                data['username'],
                data['display_name'],
                data['role']
            )
            if success:
                self._refresh_users()
                QMessageBox.information(self, "Success", message)
            else:
                QMessageBox.warning(self, "Failed", message)

    def _on_edit_user(self):
        """Edit selected user"""
        row = self._user_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a user to edit.")
            return

        username = self._user_table.item(row, 0).text()
        display_name = self._user_table.item(row, 1).text()
        role = self._user_table.item(row, 2).text()

        dialog = UserEditDialog(
            username=username,
            display_name=display_name,
            role=role,
            parent=self
        )
        if dialog.exec():
            data = dialog.get_data()
            success, message = self._user_service.update_user(
                username,
                display_name=data['display_name'],
                role=data['role']
            )
            if success:
                self._refresh_users()
                QMessageBox.information(self, "Success", message)
            else:
                QMessageBox.warning(self, "Failed", message)

    def _on_toggle_active(self):
        """Toggle selected user's active status"""
        row = self._user_table.currentRow()
        if row < 0:
            QMessageBox.warning(self, "No Selection", "Please select a user.")
            return

        username = self._user_table.item(row, 0).text()
        is_active = self._user_table.item(row, 3).text() == "Yes"

        success, message = self._user_service.update_user(
            username,
            is_active=not is_active
        )
        if success:
            self._refresh_users()
        else:
            QMessageBox.warning(self, "Failed", message)

    def _on_create_test_users(self):
        """Create test users for multi-user workflow testing"""
        # Test users to create
        test_users = [
            {'username': 'supervisor_jane', 'display_name': 'Jane Smith', 'role': 'supervisor'},
            {'username': 'lead_bob', 'display_name': 'Bob Johnson', 'role': 'lead'},
            {'username': 'artist_alice', 'display_name': 'Alice Wong', 'role': 'artist'},
            {'username': 'artist_carlos', 'display_name': 'Carlos Rivera', 'role': 'artist'},
        ]

        # Confirm creation
        reply = QMessageBox.question(
            self,
            "Create Test Users",
            "This will create the following test users:\n\n"
            "• Jane Smith (Supervisor)\n"
            "• Bob Johnson (Lead)\n"
            "• Alice Wong (Artist)\n"
            "• Carlos Rivera (Artist)\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        created = 0
        skipped = 0
        errors = []

        for user in test_users:
            success, message = self._user_service.create_user(
                user['username'],
                user['display_name'],
                user['role']
            )
            if success:
                created += 1
            elif "already exist" in message.lower():
                skipped += 1
            else:
                errors.append(f"{user['username']}: {message}")

        # Refresh UI
        self._refresh_users()

        # Report results
        if errors:
            QMessageBox.warning(
                self,
                "Test Users Created",
                f"Created: {created}\n"
                f"Skipped (existing): {skipped}\n\n"
                f"Errors:\n" + "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self,
                "Test Users Created",
                f"Created: {created}\n"
                f"Skipped (existing): {skipped}\n\n"
                "You can now switch between users to test multi-user workflows."
            )

    def save_settings(self):
        """Save settings - called by dialog"""
        # Settings are saved immediately by user service
        pass


class UserEditDialog(QDialog):
    """Dialog for adding/editing users"""

    def __init__(
        self,
        username: str = '',
        display_name: str = '',
        role: str = 'artist',
        parent=None
    ):
        super().__init__(parent)
        self._is_edit = bool(username)
        self._original_username = username

        self.setWindowTitle("Edit User" if self._is_edit else "Add User")
        self.setModal(True)
        self.resize(350, 200)

        self._init_ui(username, display_name, role)

    def _init_ui(self, username: str, display_name: str, role: str):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        # Username
        self._username_input = QLineEdit()
        self._username_input.setText(username)
        self._username_input.setEnabled(not self._is_edit)  # Can't change username
        form.addRow("Username:", self._username_input)

        # Display name
        self._display_name_input = QLineEdit()
        self._display_name_input.setText(display_name)
        form.addRow("Display Name:", self._display_name_input)

        # Role
        self._role_combo = QComboBox()
        self._role_combo.addItem("Artist", "artist")
        self._role_combo.addItem("Lead", "lead")
        self._role_combo.addItem("Supervisor", "supervisor")
        self._role_combo.addItem("Director", "director")
        self._role_combo.addItem("Admin", "admin")

        index = self._role_combo.findData(role)
        if index >= 0:
            self._role_combo.setCurrentIndex(index)
        form.addRow("Role:", self._role_combo)

        layout.addLayout(form)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self._validate_and_accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _validate_and_accept(self):
        """Validate input before accepting"""
        username = self._username_input.text().strip()
        display_name = self._display_name_input.text().strip()

        if not username:
            QMessageBox.warning(self, "Invalid Input", "Username is required.")
            return

        if not display_name:
            QMessageBox.warning(self, "Invalid Input", "Display name is required.")
            return

        self.accept()

    def get_data(self) -> dict:
        """Get the form data"""
        return {
            'username': self._username_input.text().strip(),
            'display_name': self._display_name_input.text().strip(),
            'role': self._role_combo.currentData()
        }


__all__ = ['UserTab']
