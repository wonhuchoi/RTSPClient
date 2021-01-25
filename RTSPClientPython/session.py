import io
from PIL import Image, ImageTk

from rtsp import Connection

class SessionListener:
    '''Interface for listener methods for session events.'''
    def exception_thrown(self, exception):
        pass

    def frame_received(self, frame):
        pass

    def video_name_changed(self, name):
        pass

class VideoFrame:
    def __init__(self, payload_type, marker, sequence_number, timestamp, payload):
        '''Creates a new frame.
	- payload_type: The numeric type of payload found in the frame. The most
	  common type is 26 (JPEG).
	- marker: An indication if the frame is an important frame when compared
	  to other frames in the stream.
	- sequence_number: A sequential number corresponding to the ordering of the
	  frame. This number is expected to start at 0 (zero) and increase by one
          for each frame following that.
	- timestamp: The number of milliseconds after the logical start of the
	  stream when this frame is expected to be played.
	- payload: A byte array containing the payload (contents) of the frame.
        '''
        self.payload_type = payload_type
        self.marker = marker
        self.sequence_number = sequence_number
        self.timestamp = timestamp
        self.payload = payload

    def get_image(self):
        '''Creates an Image based on the payload of the frame.'''
        image = Image.open(io.BytesIO(self.payload))
        return ImageTk.PhotoImage(image)
    
class Session:
    def __init__(self, address):
        '''Creates a new RTSP session. This constructor will also create a
        new network connection with the server. No stream setup is
        established at this point.
        '''
        self.connection = Connection(self, address)
        self.video_name = None
        self.listeners = []

    def add_listener(self, listener):
        '''Adds a new listener interface to be called every time a session
	event (such as a change in video name or a new frame)
	happens. Any interaction with user interfaces is done through
	these listeners.
        '''
        self.listeners.append(listener)
        listener.video_name_changed(self.video_name)

    def open(self, video_name):
        '''Opens a new video file in the interface.'''
        try:
            self.video_name = video_name
            self.connection.setup()
            for l in self.listeners:
                l.video_name_changed(video_name)
        except Exception as exception:
            self.handle_exception(exception)

    def play(self):
        '''Starts to play the existing file. It should only be called once a
	file has been opened. This function will return immediately
	after the request was responded. Frames will be received in
	the background and will be handled by the process_frame
	method. If the video has been paused previously, playback will
	resume where it stopped.
        '''
        try:
            self.connection.play()
        except Exception as exception:
            self.handle_exception(exception)

    def pause(self):
        '''Pauses the playback the existing file. It should only be called
	once a file has started playing. This function will return
	immediately after the request was responded. The server might
	still send a few frames before stopping the playback
	completely.
        '''
        try:
            self.connection.pause()
        except Exception as exception:
            self.handle_exception(exception)

    def teardown(self):
        '''Closes the currently open file. It should only be called once a
	file has been open.
        '''
        try:
            self.connection.teardown()
            self.video_name = None
            for l in self.listeners:
                l.frame_received(None)
                l.video_name_changed(None)
        except Exception as exception:
            self.handle_exception(exception)

    def close(self):
        '''Closes the connection with the current server. This session element
	should not be used anymore after this point.
        '''
        try:
            self.connection.close()
            for l in self.listeners:
                l.video_name_changed(None)
                l.frame_received(None)
        except Exception as exception:
            self.handle_exception(exception)

    def handle_exception(self, exception):
        '''Helper function that notifies the main window that an exception has
        happened.
        '''
        for l in self.listeners:
            l.exception_thrown(exception)
        
    def process_frame(self, payload_type, marker, sequence_number, timestamp, payload):
        '''Creates and processes a frame received from the RTSP server. This
	method will direct the frame to the user interface to be
	processed and presented to the user. A description of the
	parameters can be found on the VideoFrame class comments.
        '''
        frame = VideoFrame(payload_type, marker, sequence_number, timestamp, payload)
        if (self.video_name):
            for l in self.listeners:
                l.frame_received(frame)
