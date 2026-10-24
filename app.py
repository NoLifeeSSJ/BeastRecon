"""BeastRecon desktop media converter."""
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from converter import FORMATS, convert


def main():
    if os.name == 'nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('BeastRecon.MediaConverter')
        # winget links may not be inherited by Explorer until the next login.
        links = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft/WinGet/Links'
        os.environ['PATH'] = str(links) + os.pathsep + os.environ.get('PATH', '')
    root = tk.Tk()
    icon = Path(__file__).with_name('BeastRecon.ico')
    if os.name == 'nt' and icon.exists():
        root.iconbitmap(str(icon))
    root.title('BeastRecon • Media Converter')
    root.geometry('740x360')
    root.minsize(600, 360)
    frame = ttk.Frame(root, padding=24)
    frame.pack(fill='both', expand=True)
    frame.columnconfigure(0, weight=1)
    ttk.Label(frame, text='Media Converter', font=('', 22, 'bold')).grid(row=0, column=0, sticky='w')
    ttk.Label(frame, text='Convert a local file or download media from a supported URL.').grid(row=1, column=0, columnspan=2, sticky='w', pady=(4, 20))
    source = tk.StringVar()
    output_format = tk.StringVar(value='mp3')
    ttk.Label(frame, text='Media URL or file path').grid(row=2, column=0, sticky='w')
    ttk.Entry(frame, textvariable=source).grid(row=3, column=0, sticky='ew', pady=6)
    def browse():
        path = filedialog.askopenfilename(title='Choose media')
        if path:
            source.set(path)
    ttk.Button(frame, text='Browse…', command=browse).grid(row=3, column=1, padx=(10, 0))
    ttk.Label(frame, text='Output format').grid(row=4, column=0, sticky='w', pady=(10, 4))
    ttk.Combobox(frame, values=FORMATS, state='readonly', textvariable=output_format, width=12).grid(row=5, column=0, sticky='w')
    status = tk.StringVar(value='Ready. MP3 → MP4 creates a video with a black background.')
    events = queue.Queue()
    def start():
        value = source.get().strip()
        if not value:
            messagebox.showerror('Missing input', 'Choose a media file or enter a URL.')
            return
        extension = output_format.get()
        destination = filedialog.asksaveasfilename(title='Save converted media', defaultextension='.' + extension,
                                                   filetypes=[(extension.upper(), '*.' + extension)])
        if not destination:
            return
        if not destination.lower().endswith('.' + extension):
            messagebox.showerror('Output format', f'Choose a filename ending in .{extension}.')
            return
        button.config(state='disabled')
        status.set('Starting…')
        def worker():
            try:
                convert(value, destination, lambda message: events.put(('status', message)))
            except Exception as error:
                events.put(('error', str(error)))
            finally:
                events.put(('done', ''))
        threading.Thread(target=worker, daemon=True).start()
    button = ttk.Button(frame, text='Convert and save…', command=start)
    button.grid(row=5, column=1)
    ttk.Label(frame, textvariable=status, wraplength=660).grid(row=6, column=0, columnspan=2, sticky='w', pady=(20, 6))
    ttk.Label(frame, text='Use media you own or have permission to download. DRM-protected media is unsupported.', wraplength=660).grid(row=7, column=0, columnspan=2, sticky='w')
    def poll():
        try:
            while True:
                kind, message = events.get_nowait()
                if kind == 'status':
                    status.set(message)
                elif kind == 'error':
                    status.set('Conversion failed.')
                    messagebox.showerror('Conversion failed', message)
                else:
                    button.config(state='normal')
        except queue.Empty:
            pass
        root.after(100, poll)
    poll()
    root.mainloop()


if __name__ == '__main__':
    main()
