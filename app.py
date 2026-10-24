"""BeastRecon desktop media converter."""
from dataclasses import replace
import importlib.metadata
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from urllib.parse import urlsplit
import webbrowser
from tkinter import filedialog, messagebox, ttk
from converter import FORMATS, ConversionCancelled, convert_to_folder, inspect_media, prepare_runtime
from preferences import Preferences, load_preferences, preferences_path, save_preferences

APP_VERSION = "1.1"


def open_result(path, folder=False):
    """Open a saved result in the operating system's media player or file manager."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError('The saved file has been moved or deleted.')
    if os.name == 'nt':
        if folder:
            subprocess.Popen(['explorer.exe', '/select,', str(path)])
        else:
            os.startfile(str(path))
    else:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path.parent if folder else path)])


class ConverterApp:
    def __init__(self, root, preferences_file=None):
        self.root = root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.result = None
        self.last_error = ''
        self.preferences_file = Path(preferences_file) if preferences_file is not None else preferences_path()
        self.preferences, preference_warning = load_preferences(self.preferences_file)
        self.settings_window = None
        self.preview_generation = 0
        self.preview_timer = None
        self.preview_running = False
        self.preview_pending = False
        self.preview_cancel = threading.Event()
        root.title(f'BeastRecon V{APP_VERSION} • Media Converter')
        root.geometry('800x740')
        root.minsize(760, 700)
        icon = Path(__file__).with_name('BeastRecon.ico')
        if os.name == 'nt' and icon.exists():
            root.iconbitmap(str(icon))
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(12, weight=1)
        ttk.Label(frame, text=f'BeastRecon V{APP_VERSION}', font=('', 22, 'bold')).grid(row=0, column=0, sticky='w')
        self.settings_button = ttk.Button(frame, text='Preferences / About', command=self.show_settings)
        self.settings_button.grid(row=0, column=1, sticky='e')
        ttk.Label(frame, text='Paste a YouTube or media link, or choose a local file.').grid(row=1, column=0, columnspan=2, sticky='w', pady=(4, 20))
        self.source = tk.StringVar()
        self.output_format = tk.StringVar(value=self.preferences.default_format)
        ttk.Label(frame, text='Media URL or file path').grid(row=2, column=0, sticky='w')
        self.input = ttk.Entry(frame, textvariable=self.source)
        self.input.grid(row=3, column=0, sticky='ew', pady=6)
        self.browse_button = ttk.Button(frame, text='Browse…', command=self.browse)
        self.browse_button.grid(row=3, column=1, padx=(10, 0))
        self.preview = tk.StringVar(value='Preview: paste a link or choose a file to see its title.')
        ttk.Label(frame, textvariable=self.preview, wraplength=550).grid(row=4, column=0, sticky='w', pady=(4, 6))
        self.preview_button = ttk.Button(frame, text='Preview', command=self.begin_preview)
        self.preview_button.grid(row=4, column=1, sticky='e')
        ttk.Label(frame, text='Output format • MP3 downloads audio without the video where available').grid(row=5, column=0, columnspan=2, sticky='w', pady=(10, 4))
        self.formats = ttk.Combobox(frame, values=FORMATS, state='readonly', textvariable=self.output_format, width=12)
        self.formats.grid(row=6, column=0, sticky='w')
        self.formats.bind('<<ComboboxSelected>>', self.remember_format)
        controls = ttk.Frame(frame)
        controls.grid(row=6, column=1)
        self.convert_button = ttk.Button(controls, text='Download', command=self.start)
        self.convert_button.pack(side='left')
        self.cancel_button = ttk.Button(controls, text='Cancel', command=self.stop, state='disabled')
        self.cancel_button.pack(side='left', padx=(8, 0))
        self.save_folder = tk.StringVar(value='Save to: ' + self.preferences.download_directory)
        ttk.Label(frame, textvariable=self.save_folder, wraplength=700).grid(row=7, column=0, columnspan=2, sticky='w', pady=(10, 0))
        self.status = tk.StringVar(value='Ready. Choose MP3 to save audio you can play in your usual media player.')
        ttk.Label(frame, textvariable=self.status, wraplength=700).grid(row=8, column=0, columnspan=2, sticky='w', pady=(20, 6))
        self.bar = ttk.Progressbar(frame)
        self.bar.grid(row=9, column=0, columnspan=2, sticky='ew', pady=8)
        actions = ttk.Frame(frame)
        actions.grid(row=10, column=0, columnspan=2, sticky='w', pady=6)
        self.play_button = ttk.Button(actions, text='Play file', command=lambda: self.open_saved(False), state='disabled')
        self.play_button.pack(side='left')
        self.folder_button = ttk.Button(actions, text='Open folder', command=lambda: self.open_saved(True), state='disabled')
        self.folder_button.pack(side='left', padx=8)
        ttk.Button(actions, text='Copy details', command=self.copy_details).pack(side='left')
        ttk.Label(frame, text='Activity and error details').grid(row=11, column=0, sticky='w', pady=(10, 4))
        self.details = tk.Text(frame, height=7, wrap='word', state='disabled')
        self.details.grid(row=12, column=0, columnspan=2, sticky='nsew')
        ttk.Label(frame, text='One video at a time. Live streams and DRM-protected media are unsupported.\nUse media you own or have permission to download.', wraplength=700).grid(row=13, column=0, columnspan=2, sticky='w', pady=(10, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        if preference_warning:
            self.log(preference_warning)
        self.source.trace_add('write', self.source_changed)
        self.poll_id = root.after(100, self.poll)

    def cancel_preview_timer(self):
        if self.preview_timer is not None:
            self.root.after_cancel(self.preview_timer)
            self.preview_timer = None

    def source_changed(self, *args):
        self.cancel_preview_timer()
        self.preview_generation += 1
        self.preview_cancel.set()
        self.preview_pending = False
        self.preview.set('Preview: paste a link or choose a file to see its title.')
        if self.preferences.auto_preview and self.source.get().strip() and not self.busy:
            self.preview_timer = self.root.after(800, self.begin_preview)

    def begin_preview(self):
        self.cancel_preview_timer()
        if self.busy:
            return
        value = self.source.get().strip()
        if not value:
            return
        try:
            parsed = urlsplit(value)
            valid = (parsed.scheme in ('http', 'https') and parsed.hostname) or Path(value).expanduser().is_file()
        except (ValueError, OSError):
            valid = False
        if not valid:
            self.preview.set('Preview: enter a complete media URL or choose a file.')
            return
        if self.preview_running:
            self.preview_pending = True
            return
        generation = self.preview_generation
        self.preview_running = True
        self.preview_pending = False
        cancel = self.preview_cancel = threading.Event()
        self.preview.set('Preview: reading title…')
        def worker():
            info, error = None, None
            try:
                info = inspect_media(value, cancel)
            except ConversionCancelled:
                pass
            except Exception as exception:
                error = str(exception)
            self.events.put(('preview_result', (generation, value, info, error)))
        threading.Thread(target=worker, daemon=True).start()

    def finish_preview(self, generation, source, info, error):
        self.preview_running = False
        if generation == self.preview_generation and source == self.source.get().strip() and not self.busy:
            if info is not None:
                self.show_media_info(info)
            elif error:
                self.preview.set('Preview unavailable. You can still try Download; details are below.')
                self.log('Preview: ' + error)
        if self.preview_pending and not self.busy:
            self.preview_pending = False
            self.begin_preview()

    def show_media_info(self, info):
        details = [info.creator] if info.creator else []
        if info.duration is not None and info.duration >= 0:
            seconds = int(info.duration)
            minutes, seconds = divmod(seconds, 60)
            hours, minutes = divmod(minutes, 60)
            duration = f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'
            details.append(duration)
        title = info.title[:200] + ('…' if len(info.title) > 200 else '')
        self.preview.set('Title: ' + title + ('\n' + ' • '.join(details) if details else ''))

    def apply_preferences(self, preferences):
        save_preferences(preferences, self.preferences_file)
        self.preferences = preferences
        self.output_format.set(preferences.default_format)
        self.save_folder.set('Save to: ' + preferences.download_directory)

    def remember_format(self, event=None):
        try:
            self.apply_preferences(replace(self.preferences, default_format=self.output_format.get()))
        except OSError as error:
            self.log('Could not remember the output format: ' + str(error))

    def show_settings(self):
        if self.settings_window is not None and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        window = self.settings_window = tk.Toplevel(self.root)
        window.title(f'BeastRecon V{APP_VERSION} • Preferences / About')
        window.geometry('680x520')
        window.minsize(600, 460)
        window.transient(self.root)
        notebook = self.settings_notebook = ttk.Notebook(window)
        notebook.pack(fill='both', expand=True, padx=16, pady=16)
        preferences = ttk.Frame(notebook, padding=16)
        about = ttk.Frame(notebook, padding=16)
        changelog = ttk.Frame(notebook, padding=12)
        for tab, label in ((preferences, 'Preferences'), (about, 'About'), (changelog, 'Changelog')):
            notebook.add(tab, text=label)
        preferences.columnconfigure(0, weight=1)
        self.pref_directory = tk.StringVar(value=self.preferences.download_directory)
        self.pref_format = tk.StringVar(value=self.preferences.default_format)
        self.pref_preview = tk.BooleanVar(value=self.preferences.auto_preview)
        self.pref_message = tk.StringVar()
        ttk.Label(preferences, text='Permanent download folder').grid(row=0, column=0, columnspan=2, sticky='w')
        ttk.Entry(preferences, textvariable=self.pref_directory).grid(row=1, column=0, sticky='ew', pady=8)
        def choose_folder():
            directory = filedialog.askdirectory(parent=window, title='Choose download folder',
                                                initialdir=self.pref_directory.get(), mustexist=False)
            if directory:
                self.pref_directory.set(directory)
        ttk.Button(preferences, text='Browse…', command=choose_folder).grid(row=1, column=1, padx=(8, 0))
        ttk.Label(preferences, text='Default output format').grid(row=2, column=0, sticky='w', pady=(12, 6))
        ttk.Combobox(preferences, values=FORMATS, textvariable=self.pref_format, state='readonly', width=12).grid(row=3, column=0, sticky='w')
        ttk.Checkbutton(preferences, text='Automatically preview links when typing stops', variable=self.pref_preview).grid(row=4, column=0, columnspan=2, sticky='w', pady=16)
        ttk.Label(preferences, text='Downloads use the video/song title. Existing files receive numbered names.\nYour preferences are kept when the app updates.', wraplength=550).grid(row=5, column=0, columnspan=2, sticky='w', pady=8)
        ttk.Button(preferences, text='Save preferences', command=self.save_preference_changes).grid(row=6, column=0, sticky='w', pady=12)
        ttk.Label(preferences, textvariable=self.pref_message, wraplength=550).grid(row=7, column=0, columnspan=2, sticky='w')
        ttk.Label(about, text=f'BeastRecon V{APP_VERSION}', font=('', 20, 'bold')).pack(anchor='w', pady=(0, 12))
        ttk.Label(about, text='Desktop media downloader and converter.\n\nConvert supported media links and local files to MP3, M4A, WAV, FLAC, MP4 or WebM.\n\nPowered by FFmpeg, yt-dlp, its JavaScript solver and Deno.\n\nUse media you own or have permission to download. Live streams, playlists, DRM and account verification are not supported.', wraplength=540, justify='left').pack(anchor='w')
        ttk.Button(about, text='Project on GitHub', command=lambda: webbrowser.open('https://github.com/NoLifeeSSJ/BeastRecon')).pack(anchor='w', pady=16)
        text = tk.Text(changelog, wrap='word', padx=8, pady=8)
        scrollbar = ttk.Scrollbar(changelog, command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        text.pack(fill='both', expand=True)
        try:
            history = Path(__file__).with_name('CHANGELOG.md').read_text(encoding='utf-8')
        except OSError:
            history = 'Changelog unavailable. Rerun Install.ps1 to restore the app files.'
        text.insert('1.0', re.sub(r'^#+ ', '', history, flags=re.MULTILINE))
        text.config(state='disabled')

    def save_preference_changes(self):
        if self.busy:
            self.pref_message.set('Wait until the current download finishes before changing preferences.')
            return
        try:
            folder = Path(self.pref_directory.get().strip()).expanduser()
            if not folder.is_absolute():
                raise ValueError('Choose a full folder path, such as C:\\BeastRecon\\Downloads.')
            if folder.exists() and not folder.is_dir():
                raise ValueError('Choose a folder rather than a file.')
            preferences = Preferences(str(folder), self.pref_format.get(), self.pref_preview.get())
            self.apply_preferences(preferences)
            self.source_changed()
            self.pref_message.set('Preferences saved. Downloads will use this folder automatically.')
        except (OSError, ValueError) as error:
            self.pref_message.set('Could not save preferences: ' + str(error))

    def log(self, message):
        self.details.config(state='normal')
        self.details.insert('end', str(message) + '\n')
        # Bound memory even for long conversions.
        if int(self.details.index('end-1c').split('.')[0]) > 200:
            self.details.delete('1.0', '2.0')
        self.details.see('end')
        self.details.config(state='disabled')

    def browse(self):
        path = filedialog.askopenfilename(title='Choose media')
        if path:
            self.source.set(path)

    def set_busy(self, busy):
        self.busy = busy
        state = 'disabled' if busy else 'normal'
        for control in (self.input, self.browse_button, self.convert_button, self.preview_button, self.settings_button):
            control.config(state=state)
        self.formats.config(state='disabled' if busy else 'readonly')
        self.cancel_button.config(state='normal' if busy else 'disabled')
        result_state = 'normal' if self.result and not busy else 'disabled'
        self.play_button.config(state=result_state)
        self.folder_button.config(state=result_state)

    def start(self):
        value = self.source.get().strip()
        if not value:
            messagebox.showerror('Missing input', 'Choose a media file or enter a URL.')
            return
        extension = self.output_format.get()
        directory = self.preferences.download_directory
        self.preview_cancel.set()
        self.preview_pending = False
        self.cancel_preview_timer()
        self.preview_generation += 1
        self.cancel.clear()
        self.last_error = ''
        self.set_busy(True)
        self.status.set('Starting…')
        self.bar.config(mode='indeterminate')
        self.bar.start(12)
        self.log('Starting ' + extension.upper() + ' conversion…')
        def worker():
            try:
                result = convert_to_folder(value, directory, extension,
                                           lambda message: self.events.put(('status', message)), self.cancel,
                                           lambda info: self.events.put(('metadata', info)))
                self.events.put(('success', result))
            except ConversionCancelled:
                self.events.put(('cancelled', 'Conversion cancelled. No output file was saved.'))
            except Exception as error:
                self.events.put(('error', str(error)))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=worker, daemon=True).start()

    def stop(self):
        self.cancel.set()
        self.cancel_button.config(state='disabled')
        self.status.set('Cancelling… waiting for the current network request to finish.')

    def open_saved(self, folder):
        try:
            open_result(self.result, folder)
        except Exception as error:
            messagebox.showerror('Could not open file', str(error))

    def copy_details(self):
        try:
            version = importlib.metadata.version('yt-dlp')
        except importlib.metadata.PackageNotFoundError:
            version = 'not installed'
        text = f'BeastRecon V{APP_VERSION} | Python {sys.version.split()[0]} | yt-dlp {version}\n'
        text += self.details.get('1.0', 'end').strip()
        if self.last_error:
            text += '\n\nLast error:\n' + self.last_error
        self.root.clipboard_clear()
        self.root.clipboard_append(text)

    def close(self):
        if self.busy:
            if messagebox.askyesno('Stop conversion?', 'Cancel this conversion and close BeastRecon?'):
                self.closing = True
                self.stop()
        else:
            self.destroy()

    def destroy(self):
        self.preview_cancel.set()
        self.cancel_preview_timer()
        self.root.after_cancel(self.poll_id)
        self.bar.stop()
        self.root.destroy()

    def poll(self):
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == 'preview_result':
                    self.finish_preview(*message)
                elif kind == 'metadata':
                    self.show_media_info(message)
                elif kind == 'status':
                    self.log(message)
                    if not self.cancel.is_set():
                        self.status.set(message)
                        match = re.search(r'(\d+)%', message)
                        if match:
                            self.bar.stop()
                            self.bar.config(mode='determinate', value=int(match.group(1)))
                        elif not message.startswith('Download notice:'):
                            self.bar.stop()
                            self.bar.config(mode='indeterminate')
                            self.bar.start(12)
                elif kind == 'success':
                    self.result = message
                    self.status.set(f'Saved: {message}. Use Play file to listen.')
                    self.bar.stop()
                    self.bar.config(mode='determinate', value=100)
                elif kind == 'error':
                    self.last_error = message
                    self.log(message)
                    self.status.set('Conversion failed. See the details below, or use Copy details for help.')
                    self.bar.stop()
                    self.bar.config(mode='determinate', value=0)
                    messagebox.showerror('Conversion failed', message)
                elif kind == 'cancelled':
                    self.log(message)
                    self.status.set(message)
                    self.bar.stop()
                    self.bar.config(mode='determinate', value=0)
                elif kind == 'done':
                    self.set_busy(False)
                    if self.closing:
                        self.destroy()
                        return
        except queue.Empty:
            pass
        self.poll_id = self.root.after(100, self.poll)


def main():
    prepare_runtime()
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('BeastRecon.MediaConverter')
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
