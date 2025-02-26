    def init_ui(self):
        central_widget = QWidget()
        main_layout = QVBoxLayout()

        # Input Section
        self.input_label = QLabel("Enter phrases (semicolon-separated - max 300 chars):")

        # Create horizontal layout for input + button
        input_row = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setMaxLength(300)
        self.input_field.setPlaceholderText("Example: Hello; Goodbye")

        self.translate_btn = QPushButton("Translate")
        self.translate_btn.setFixedWidth(120)  # Fixed button width

        # Add to horizontal layout with stretch factors
        input_row.addWidget(self.input_field, 1)  # Input field expands
        input_row.addWidget(self.translate_btn, 0)  # Button stays fixed
        input_row.setContentsMargins(0, 0, 0, 10)  # Add bottom margin

        # Add components to main layout
        main_layout.addWidget(self.input_label)
        main_layout.addLayout(input_row)  # Add the horizontal row
        main_layout.addWidget(self.progress_bar)
        main_layout.addWidget(self.output_area)

        # ... rest of the code remains unchanged ...
