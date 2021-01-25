#! /usr/bin/python3

import tkinter as tk
from tkinter import simpledialog, messagebox
from PIL import ImageTk, Image
from session import Session, SessionListener
from os.path import expanduser, join

class SelectServerDialog(simpledialog.Dialog):
    def body(self, master):
        lbl = tk.Label(master, text="Server:")
        lbl.grid(row=0, column=0)
        self.ent_server = tk.Entry(master)
        self.ent_server.insert(tk.END, "localhost")
        self.ent_server.grid(row=0, column=1)
        
        lbl = tk.Label(master, text="Port:")
        lbl.grid(row=1, column=0)
        self.ent_port = tk.Entry(master)
        self.ent_port.insert(tk.END, "455")
        self.ent_port.grid(row=1, column=1)

        try:
            with open(join(expanduser("~"), '.rtp.client.txt')) as saved:
                server = saved.readline().strip()
                port = saved.readline().strip()
                self.ent_server.delete(0, tk.END)
                self.ent_server.insert(tk.END, server)
                self.ent_port.delete(0, tk.END)
                self.ent_port.insert(tk.END, port)
        except:
            pass
        
        return self.ent_server

    def validate(self):
        try:
            address = (self.ent_server.get(), self.ent_port.get())
            self.result = Session(address)
            return True
        except Exception as exception:
            messagebox.showerror("Error", str(exception))
            return False

    def apply(self):
        try:
            with open(join(expanduser("~"), '.rtp.client.txt'), 'w') as saved:
                saved.write(f'{self.ent_server.get()}\n{self.ent_port.get()}\n')
        except:
            pass
                
        
class VideoControlToolbar(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.master = master
        self.pack()
        
        self.btn_open = tk.Button(self, text="Open", command=master.open_file)
        self.btn_open.pack(side=tk.LEFT)
        
        self.btn_play = tk.Button(self, text="Play", command=master.play)
        self.btn_play.pack(side=tk.LEFT)
        
        self.btn_pause = tk.Button(self, text="Pause", command=master.pause)
        self.btn_pause.pack(side=tk.LEFT)
        
        self.btn_close = tk.Button(self, text="Close", command=master.close_file)
        self.btn_close.pack(side=tk.LEFT)
        
        self.btn_disconnect = tk.Button(self, text="Disconnect", command=master.connect)
        self.btn_disconnect.pack(side=tk.LEFT)

class MainWindow(tk.Tk, SessionListener):
    def __init__(self):
        super().__init__()
        self.session = None
        self.title("RTSP Client")

        self.toolbar = VideoControlToolbar(self)

        self.lbl_image = tk.Label(self)
        self.lbl_image.pack(fill=tk.BOTH, expand=True)
        
        self.lbl_video_name = tk.Label(self)
        self.video_name_changed(None)
        self.lbl_video_name.pack()
        
        self.connect()

    def open_file(self):
        file_name = simpledialog.askstring("File Name", "File Name", parent=self)
        if file_name is not None:
            self.session.open(file_name)

    def play(self):
        return self.session.play()
    
    def pause(self):
        return self.session.pause()
    
    def close_file(self):
        return self.session.teardown()
    
    def exception_thrown(self, exception):
        messagebox.showerror("Error", str(exception))

    def frame_received(self, frame):
        self.lbl_image['image'] = self.image = frame.get_image() if frame else None

    def video_name_changed(self, name):
        self.lbl_video_name['text'] = f'Video: {name}' if name else 'No video open'

    def connect(self):
        if self.session: self.session.close()
        self.session = SelectServerDialog(self).result
        if self.session is None:
            self.destroy()
        else:
            self.session.add_listener(self)
                
    def destroy(self):
        if self.session: self.session.close()
        super().destroy()

window = MainWindow()
window.mainloop()

