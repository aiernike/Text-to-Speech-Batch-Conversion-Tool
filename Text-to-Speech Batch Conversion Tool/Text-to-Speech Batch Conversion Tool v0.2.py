import sys
import os
import subprocess
import threading
import time
import tempfile
from datetime import datetime

# 抑制 libpng 警告
os.environ['QT_LOGGING_RULES'] = '*.debug=false;qt.*.debug=false'

# PySide2 导入
from PySide2 import QtWidgets, QtCore, QtGui


class ConversionThread(QtCore.QThread):
    """转换线程，避免界面卡顿"""
    progress_signal = QtCore.Signal(str)
    progress_update = QtCore.Signal(int, int)  # 当前进度，总文件数
    finished_signal = QtCore.Signal()
    error_signal = QtCore.Signal(str)

    def __init__(self, folder_path, voice, file_filter="*.txt"):
        super().__init__()
        self.folder_path = folder_path
        self.voice = voice
        self.file_filter = file_filter
        self._is_running = True
        self.total_files = 0
        self.processed_files = 0

    def run(self):
        """执行转换任务"""
        try:
            # 自动更新 edge-tts
            self.progress_signal.emit("正在检查并更新 edge-tts...")
            update_msg = self.ensure_edge_tts_updated()
            self.progress_signal.emit(update_msg)

            # 首先统计符合条件的文件总数
            self.total_files = 0
            for (dirpath, dirnames, filenames) in os.walk(self.folder_path):
                for fn in filenames:
                    if self.matches_filter(fn):
                        self.total_files += 1

            self.processed_files = 0
            self.progress_update.emit(0, self.total_files)

            # 开始转换
            for (dirpath, dirnames, filenames) in os.walk(self.folder_path):
                if not self._is_running:
                    break

                for fn in filenames:
                    if not self._is_running:
                        break

                    if self.matches_filter(fn):
                        fpath = os.path.join(dirpath, fn)
                        mp3Path = os.path.join(dirpath, fn.replace('.txt', '.mp3'))

                        # 记录进度
                        self.progress_signal.emit(f"正在转换: {fn}")

                        # 读取文件内容
                        try:
                            with open(fpath, 'r', encoding='utf-8') as f:
                                content = f.read().strip()

                            if not content:
                                self.progress_signal.emit(f"⚠ 跳过空文件: {fn}")
                                self.processed_files += 1
                                self.progress_update.emit(self.processed_files, self.total_files)
                                continue

                            # 使用临时文件存储内容
                            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False,
                                                             encoding='utf-8') as tmp:
                                tmp.write(content)
                                tmp_path = tmp.name

                            # 执行转换命令 - 使用文件方式更可靠
                            cmd = [
                                'edge-tts',
                                '--voice', self.voice,
                                '--file', tmp_path,
                                '--write-media', mp3Path
                            ]

                            try:
                                result = subprocess.run(
                                    cmd,
                                    capture_output=True,
                                    text=True,
                                    encoding='utf-8',
                                    timeout=60  # 60秒超时
                                )

                                # 删除临时文件
                                try:
                                    os.unlink(tmp_path)
                                except:
                                    pass

                                if result.returncode == 0:
                                    self.progress_signal.emit(f"✓ 已转换: {fn} -> {fn.replace('.txt', '.mp3')}")
                                else:
                                    error_msg = result.stderr or result.stdout or "未知错误"
                                    self.progress_signal.emit(f"✗ 转换失败: {fn} - {error_msg[:100]}")
                            except subprocess.TimeoutExpired:
                                self.progress_signal.emit(f"✗ 转换超时: {fn}")
                            except Exception as e:
                                self.progress_signal.emit(f"✗ 错误: {fn} - {str(e)}")

                        except Exception as e:
                            self.progress_signal.emit(f"✗ 读取文件失败: {fn} - {str(e)}")

                        self.processed_files += 1
                        self.progress_update.emit(self.processed_files, self.total_files)

        except Exception as e:
            self.error_signal.emit(f"程序错误: {str(e)}")
        finally:
            self.finished_signal.emit()

    @staticmethod
    def ensure_edge_tts_updated():
        """确保 edge-tts 是最新版本"""
        try:
            # 尝试更新 edge-tts
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--upgrade', 'edge-tts'],
                capture_output=True,
                text=True,
                encoding='utf-8',
                timeout=120  # 给更新过程更多时间
            )
            if result.returncode == 0:
                # 检查输出中是否包含 "Requirement already satisfied"，这表示已是最新版
                if "Requirement already satisfied" in result.stdout:
                    return "edge-tts 已是最新版本。"
                else:
                    return "edge-tts 已成功更新。"
            else:
                # 如果更新失败，返回错误信息
                return f"尝试更新 edge-tts 时出错，但不影响后续转换: {result.stderr[:100]}"
        except subprocess.TimeoutExpired:
            return "更新 edge-tts 超时，但不影响后续转换。"
        except Exception as e:
            return f"检查更新时发生错误，但不影响后续转换: {str(e)}"

    def matches_filter(self, filename):
        """检查文件是否匹配过滤器"""
        if self.file_filter == "*.*":
            return True
        elif "*." in self.file_filter:
            # 处理多个扩展名的情况
            filters = [f.strip() for f in self.file_filter.split(';')]
            for filter_ext in filters:
                if "*." in filter_ext:
                    ext = filter_ext.replace("*.", ".")
                    if filename.endswith(ext):
                        return True
            return False
        else:
            return False

    def stop(self):
        """停止转换"""
        self._is_running = False


class TestThread(QtCore.QThread):
    """测试语音线程"""
    finished_signal = QtCore.Signal(str, bool)  # 消息, 是否成功
    progress_signal = QtCore.Signal(str)

    def __init__(self, voice, text=""):
        super().__init__()
        self.voice = voice
        self.text = text if text else "你好，这是一个语音测试。欢迎使用文本转语音批量转换工具。"

    def run(self):
        """执行测试"""
        try:
            # 自动更新 edge-tts
            self.progress_signal.emit("正在检查并更新 edge-tts...")
            update_msg = ConversionThread.ensure_edge_tts_updated()
            self.progress_signal.emit(update_msg)

            # 创建临时文件
            test_file = os.path.join(tempfile.gettempdir(),
                                     f"test_voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3")

            # 创建临时文本文件
            temp_text_file = os.path.join(tempfile.gettempdir(),
                                          f"test_text_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

            try:
                # 将文本写入临时文件
                with open(temp_text_file, 'w', encoding='utf-8') as f:
                    f.write(self.text)

                self.progress_signal.emit("正在生成测试音频...")

                # 使用列表形式传递参数，避免shell解析问题
                cmd = [
                    'edge-tts',
                    '--voice', self.voice,
                    '--file', temp_text_file,
                    '--write-media', test_file
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=30  # 添加超时
                )

                # 清理临时文本文件
                try:
                    os.remove(temp_text_file)
                except:
                    pass

                if result.returncode == 0:
                    if os.path.exists(test_file) and os.path.getsize(test_file) > 0:
                        self.progress_signal.emit("测试音频生成成功，正在播放...")

                        # 播放音频
                        if sys.platform == "win32":
                            # Windows: 使用start命令更可靠
                            subprocess.Popen(['start', '', test_file], shell=True)
                        elif sys.platform == "darwin":  # macOS
                            subprocess.Popen(["afplay", test_file])
                        else:  # Linux
                            subprocess.Popen(["xdg-open", test_file])

                        self.finished_signal.emit(f"✓ 测试音频已生成并播放: {os.path.basename(test_file)}", True)
                    else:
                        self.finished_signal.emit("✗ 测试音频文件生成失败或为空", False)
                else:
                    error_msg = result.stderr or result.stdout or "未知错误"
                    self.finished_signal.emit(f"✗ 测试失败: {error_msg[:200]}", False)

            except Exception as e:
                # 清理临时文件
                try:
                    os.remove(temp_text_file)
                except:
                    pass
                self.finished_signal.emit(f"✗ 测试过程出错: {str(e)}", False)

        except Exception as e:
            self.finished_signal.emit(f"✗ 测试错误: {str(e)}", False)


class ProgressEstimator:
    """进度估计器"""

    def __init__(self):
        self.start_time = None
        self.total_files = 0
        self.completed_files = 0

    def start(self, total_files):
        self.start_time = time.time()
        self.total_files = total_files
        self.completed_files = 0

    def update(self):
        self.completed_files += 1
        if self.completed_files > 0 and self.start_time:
            elapsed = time.time() - self.start_time
            if self.completed_files > 0:
                avg_time_per_file = elapsed / self.completed_files
                remaining_files = self.total_files - self.completed_files
                estimated_time_remaining = remaining_files * avg_time_per_file

                hours = int(estimated_time_remaining // 3600)
                minutes = int((estimated_time_remaining % 3600) // 60)
                seconds = int(estimated_time_remaining % 60)

                if hours > 0:
                    return f"预计剩余时间: {hours}小时{minutes}分钟"
                elif minutes > 0:
                    return f"预计剩余时间: {minutes}分钟{seconds}秒"
                else:
                    return f"预计剩余时间: {seconds}秒"
        return "计算中..."


class Window(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.conversion_thread = None
        self.test_thread = None
        self.progress_estimator = ProgressEstimator()
        self.setup_ui()

    def setup_ui(self):
        """设置界面"""
        self.setWindowTitle("文本转语音批量转换工具 v2.0")

        # 设置窗口图标（可选）- 可以注释掉这行以避免图标问题
        # self.setWindowIcon(QtGui.QIcon())

        # 创建控件
        btn_chooseFolder = QtWidgets.QPushButton('选择目录', self)
        btn_chooseFolder.setFixedSize(100, 30)

        self.label_path = QtWidgets.QLabel('未选择目录', self)
        self.label_path.setStyleSheet("""
            QLabel {
                color: #666;
                padding: 5px;
                border: 1px solid #ddd;
                border-radius: 3px;
                background-color: #f9f9f9;
            }
        """)
        self.label_path.setMinimumHeight(30)

        # 文件筛选
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("文件筛选:"))
        self.file_filter = QtWidgets.QLineEdit("*.txt", self)
        self.file_filter.setPlaceholderText("如: *.txt;*.md;*.html")
        self.file_filter.setFixedWidth(150)
        filter_layout.addWidget(self.file_filter)
        filter_layout.addStretch()

        # 语音选择
        self.voice_combo = QtWidgets.QComboBox(self)
        self.voice_combo.addItems([
            "zh-CN-YunjianNeural (云健)",
            "zh-CN-XiaoxiaoNeural (晓晓)",
            "zh-CN-XiaoyiNeural (晓伊)",
            "zh-CN-YunxiNeural (云希)",
            "zh-CN-YunxiaNeural (云夏)",
            "zh-CN-YunyangNeural (云扬)",
            "en-US-JennyNeural (英文-Jenny)",
            "en-US-GuyNeural (英文-Guy)"
        ])
        self.voice_combo.setFixedHeight(30)

        # 测试按钮
        self.btn_test = QtWidgets.QPushButton('测试语音', self)
        self.btn_test.setFixedSize(80, 30)
        self.btn_test.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
        """)

        # 控制按钮
        self.btn_run = QtWidgets.QPushButton('开始转换', self)
        self.btn_run.setFixedSize(100, 30)
        self.btn_run.setEnabled(False)
        self.btn_run.setStyleSheet("""
            QPushButton:enabled {
                background-color: #4CAF50;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:enabled:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        self.btn_stop = QtWidgets.QPushButton('停止', self)
        self.btn_stop.setFixedSize(80, 30)
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet("""
            QPushButton:enabled {
                background-color: #f44336;
                color: white;
                border: none;
                border-radius: 3px;
            }
            QPushButton:enabled:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)

        # 进度条
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_bar.setVisible(False)

        # 进度标签
        self.progress_label = QtWidgets.QLabel("就绪", self)
        self.progress_label.setStyleSheet("""
            QLabel {
                color: #2196F3;
                padding: 5px;
                font-weight: bold;
            }
        """)

        # 时间估计标签
        self.time_label = QtWidgets.QLabel("", self)
        self.time_label.setStyleSheet("color: #666; padding: 2px;")

        # 文本编辑框
        self.textEdit = QtWidgets.QPlainTextEdit(self)
        self.textEdit.setReadOnly(True)
        self.textEdit.setStyleSheet("""
            QPlainTextEdit {
                font-family: Consolas, 'Courier New', monospace;
                font-size: 10pt;
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 3px;
            }
        """)

        # 创建布局 - 顶部工具栏
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(btn_chooseFolder)
        top_layout.addWidget(self.label_path, 1)  # 设置伸展因子为1

        # 工具栏第二行
        toolbar_layout = QtWidgets.QHBoxLayout()
        toolbar_layout.addLayout(filter_layout)
        toolbar_layout.addWidget(self.voice_combo)
        toolbar_layout.addWidget(self.btn_test)
        toolbar_layout.addWidget(self.btn_run)
        toolbar_layout.addWidget(self.btn_stop)

        # 进度布局
        progress_layout = QtWidgets.QVBoxLayout()
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.time_label)

        # 创建主布局
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.addLayout(top_layout)
        main_layout.addLayout(toolbar_layout)
        main_layout.addLayout(progress_layout)
        main_layout.addWidget(self.textEdit)

        # 连接信号槽
        btn_chooseFolder.clicked.connect(self.chooseFolder)
        self.btn_run.clicked.connect(self.start_conversion)
        self.btn_stop.clicked.connect(self.stop_conversion)
        self.btn_test.clicked.connect(self.test_voice)

    def chooseFolder(self):
        """选择文件夹"""
        folder_path = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "选择包含文本文件的目录",
            "",
            QtWidgets.QFileDialog.ShowDirsOnly
        )

        if folder_path:
            self.label_path.setText(folder_path)
            self.folderPath = folder_path
            self.btn_run.setEnabled(True)

            # 统计符合条件的文件数量
            file_filter = self.file_filter.text().strip()
            if not file_filter:
                file_filter = "*.txt"

            file_count = 0
            for (dirpath, dirnames, filenames) in os.walk(folder_path):
                for fn in filenames:
                    if self.matches_filter(fn, file_filter):
                        file_count += 1

            self.progress_label.setText(f"找到 {file_count} 个符合条件的文件")
            self.progress_bar.setVisible(False)
            self.time_label.clear()
            self.textEdit.clear()
            self.textEdit.appendPlainText(f"已选择目录: {folder_path}")
            self.textEdit.appendPlainText(f"文件筛选: {file_filter}")
            self.textEdit.appendPlainText(f"发现 {file_count} 个符合条件的文件\n")

    def matches_filter(self, filename, file_filter):
        """检查文件是否匹配过滤器"""
        if file_filter == "*.*":
            return True
        elif "*." in file_filter:
            # 处理多个扩展名的情况
            filters = [f.strip() for f in file_filter.split(';')]
            for filter_ext in filters:
                if "*." in filter_ext:
                    ext = filter_ext.replace("*.", ".")
                    if filename.endswith(ext):
                        return True
            return False
        else:
            return False

    def start_conversion(self):
        """开始转换"""
        if not hasattr(self, 'folderPath') or not self.folderPath:
            QtWidgets.QMessageBox.warning(self, "警告", "请先选择目录！")
            return

        # 检查 edge-tts 是否可用
        if not self.check_edge_tts():
            return

        # 获取选中的语音
        selected_voice = self.voice_combo.currentText().split(' ')[0]
        file_filter = self.file_filter.text().strip()
        if not file_filter:
            file_filter = "*.txt"

        # 禁用开始按钮，启用停止按钮
        self.btn_run.setEnabled(False)
        self.btn_test.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_label.setText("正在转换中...")

        # 清空之前的输出
        self.textEdit.clear()
        self.textEdit.appendPlainText(f"开始批量转换...\n")
        self.textEdit.appendPlainText(f"语音: {self.voice_combo.currentText()}\n")
        self.textEdit.appendPlainText(f"文件筛选: {file_filter}\n")
        self.textEdit.appendPlainText("=" * 50 + "\n")

        # 创建并启动转换线程
        self.conversion_thread = ConversionThread(self.folderPath, selected_voice, file_filter)
        self.conversion_thread.progress_signal.connect(self.update_progress)
        self.conversion_thread.progress_update.connect(self.update_progress_bar)
        self.conversion_thread.finished_signal.connect(self.conversion_finished)
        self.conversion_thread.error_signal.connect(self.show_error)
        self.conversion_thread.start()

        # 初始化进度估计器
        self.progress_estimator.start(self.conversion_thread.total_files)

    def stop_conversion(self):
        """停止转换"""
        if self.conversion_thread and self.conversion_thread.isRunning():
            reply = QtWidgets.QMessageBox.question(
                self, '确认停止',
                '确定要停止转换吗？',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )

            if reply == QtWidgets.QMessageBox.Yes:
                self.conversion_thread.stop()
                self.conversion_thread.wait()
                self.progress_label.setText("已停止")
                self.time_label.clear()
                self.textEdit.appendPlainText("\n转换已停止")

    def update_progress(self, message):
        """更新进度显示"""
        self.textEdit.appendPlainText(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

        # 滚动到底部
        scrollbar = self.textEdit.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

        # 更新进度估计器
        if "正在转换" in message:
            self.time_label.setText(self.progress_estimator.update())

    def update_progress_bar(self, current, total):
        """更新进度条"""
        if total > 0:
            progress = int((current / total) * 100)
            self.progress_bar.setValue(progress)
            self.progress_bar.setFormat(f"{current}/{total} ({progress}%)")

    def conversion_finished(self):
        """转换完成"""
        self.btn_run.setEnabled(True)
        self.btn_test.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress_label.setText("转换完成")
        self.time_label.clear()
        self.textEdit.appendPlainText("\n" + "=" * 50)
        self.textEdit.appendPlainText("所有文件转换完成！")

        # 显示完成提示
        QtWidgets.QMessageBox.information(self, "完成", "所有文件转换完成！")

    def test_voice(self):
        """测试语音效果"""
        # 获取选中的语音
        selected_voice = self.voice_combo.currentText().split(' ')[0]

        # 先检查 edge-tts 是否可用
        if not self.check_edge_tts():
            return

        # 弹出对话框输入测试文本
        text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, '测试语音',
            '请输入测试文本:',
            '你好，这是一个语音测试。欢迎使用文本转语音批量转换工具。'
        )

        if ok and text.strip():
            self.btn_test.setEnabled(False)
            self.progress_label.setText("正在测试语音...")
            self.textEdit.appendPlainText(f"\n[测试] 开始测试语音: {self.voice_combo.currentText()}")
            self.textEdit.appendPlainText(f"[测试] 语音代码: {selected_voice}")

            # 创建并启动测试线程
            self.test_thread = TestThread(selected_voice, text)
            self.test_thread.finished_signal.connect(self.test_finished)
            self.test_thread.progress_signal.connect(self.update_progress)
            self.test_thread.start()

    def test_finished(self, message, success):
        """测试完成"""
        self.btn_test.setEnabled(True)
        self.progress_label.setText("测试完成" if success else "测试失败")
        self.textEdit.appendPlainText(f"[测试] {message}")

    def check_edge_tts(self):
        """检查 edge-tts 是否可用"""
        try:
            # 尝试运行 edge-tts --version
            result = subprocess.run(['edge-tts', '--version'],
                                    capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                reply = QtWidgets.QMessageBox.warning(self, "警告",
                                                      "edge-tts 可能未正确安装或不在系统PATH中。\n是否尝试自动安装？",
                                                      QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                                                      QtWidgets.QMessageBox.Yes)

                if reply == QtWidgets.QMessageBox.Yes:
                    self.textEdit.appendPlainText("[系统] 正在尝试安装 edge-tts...")
                    try:
                        subprocess.run([sys.executable, '-m', 'pip', 'install', 'edge-tts'],
                                       capture_output=True, text=True, timeout=60)
                        self.textEdit.appendPlainText("[系统] edge-tts 安装完成，请重新测试。")
                    except Exception as e:
                        self.textEdit.appendPlainText(f"[系统] 安装失败: {str(e)}")
                return False
            return True
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "警告",
                                          f"无法找到 edge-tts: {str(e)}\n请确保已安装 edge-tts (pip install edge-tts)。")
            return False

    def show_error(self, error_msg):
        """显示错误信息"""
        self.textEdit.appendPlainText(f"\n✗ 错误: {error_msg}")
        QtWidgets.QMessageBox.critical(self, "错误", error_msg)

    def closeEvent(self, event):
        """关闭窗口时停止线程"""
        if self.conversion_thread and self.conversion_thread.isRunning():
            self.conversion_thread.stop()
            self.conversion_thread.wait()
        event.accept()


def main():
    app = QtWidgets.QApplication([])
    app.setStyle('Fusion')  # 使用Fusion样式，更现代

    # 设置应用信息
    app.setApplicationName("文本转语音批量转换工具")
    app.setOrganizationName("EdgeTTS Converter")

    window = Window()
    window.resize(900, 600)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()