"""BeastRecon desktop media converter."""
import importlib.metadata
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from converter import FORMATS, ConversionCancelled, convert, prepare_runtime


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
    def __init__(self, root):
        self.root = root
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.closing = False
        self.result = None
        self.last_error = ''
        root.title('BeastRecon • Media Converter')
        root.geometry('800x620')
        root.minsize(640, 580)
        icon = Path(__file__).with_name('BeastRecon.ico')
        if os.name == 'nt' and icon.exists():
            root.iconbitmap(str(icon))
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(10, weight=1)
        ttk.Label(frame, text='BeastRecon', font=('', 22, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(frame, text='Paste a YouTube or media link, or choose a local file.').grid(row=1, column=0, columnspan=2, sticky='w', pady=(4, 20))
        self.source = tk.StringVar()
        self.output_format = tk.StringVar(value='mp3')
        ttk.Label(frame, text='Media URL or file path').grid(row=2, column=0, sticky='w')
        self.input = ttk.Entry(frame, textvariable=self.source)
        self.input.grid(row=3, column=0, sticky='ew', pady=6)
        self.browse_button = ttk.Button(frame, text='Browse…', command=self.browse)
        self.browse_button.grid(row=3, column=1, padx=(10, 0))
        ttk.Label(frame, text='Output format • MP3 downloads audio without the video where available').grid(row=4, column=0, columnspan=2, sticky='w', pady=(10, 4))
        self.formats = ttk.Combobox(frame, values=FORMATS, state='readonly', textvariable=self.output_format, width=12)
        self.formats.grid(row=5, column=0, sticky='w')
        controls = ttk.Frame(frame)
        controls.grid(row=5, column=1)
        self.convert_button = ttk.Button(controls, text='Convert and save…', command=self.start)
        self.convert_button.pack(side='left')
        self.cancel_button = ttk.Button(controls, text='Cancel', command=self.stop, state='disabled')
        self.cancel_button.pack(side='left', padx=(8, 0))
        self.status = tk.StringVar(value='Ready. Choose MP3 to save audio you can play in your usual media player.')
        ttk.Label(frame, textvariable=self.status, wraplength=700).grid(row=6, column=0, columnspan=2, sticky='w', pady=(20, 6))
        self.bar = ttk.Progressbar(frame)
        self.bar.grid(row=7, column=0, columnspan=2, sticky='ew', pady=8)
        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, columnspan=2, sticky='w', pady=6)
        self.play_button = ttk.Button(actions, text='Play file', command=lambda: self.open_saved(False), state='disabled')
        self.play_button.pack(side='left')
        self.folder_button = ttk.Button(actions, text='Open folder', command=lambda: self.open_saved(True), state='disabled')
        self.folder_button.pack(side='left', padx=8)
        ttk.Button(actions, text='Copy details', command=self.copy_details).pack(side='left')
        ttk.Label(frame, text='Activity and error details').grid(row=9, column=0, sticky='w', pady=(10, 4))
        self.details = tk.Text(frame, height=7, wrap='word', state='disabled')
        self.details.grid(row=10, column=0, columnspan=2, sticky='nsew')
        ttk.Label(frame, text='One video at a time. Live streams and DRM-protected media are unsupported.\nUse media you own or have permission to download.', wraplength=700).grid(row=11, column=0, columnspan=2, sticky='w', pady=(10, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.poll_id = root.after(100, self.poll)

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
        for control in (self.input, self.browse_button, self.convert_button):
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
        destination = filedialog.asksaveasfilename(title='Save converted media', defaultextension='.' + extension,
                                                   initialfile='BeastRecon.' + extension,
                                                   filetypes=[(extension.upper(), '*.' + extension)])
        if not destination:
            return
        if not destination.lower().endswith('.' + extension):
            messagebox.showerror('Output format', f'Choose a filename ending in .{extension}.')
            return
        if Path(destination).exists():
            messagebox.showerror('Choose a new filename', 'This file already exists. Choose another filename to keep it safe.')
            return
        self.cancel.clear()
        self.last_error = ''
        self.set_busy(True)
        self.status.set('Starting…')
        self.bar.config(mode='indeterminate')
        self.bar.start(12)
        self.log('Starting ' + extension.upper() + ' conversion…')
        def worker():
            try:
                result = convert(value, destination, lambda message: self.events.put(('status', message)), self.cancel)
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
        text = f'BeastRecon | Python {sys.version.split()[0]} | yt-dlp {version}\n'
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
        self.root.after_cancel(self.poll_id)
        self.bar.stop()
        self.root.destroy()

    def poll(self):
        try:
            while True:
                kind, message = self.events.get_nowait()
                if kind == 'status':
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
