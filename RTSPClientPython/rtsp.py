import io, socket, time
from threading import Thread, Event, Timer
import _thread

MESSAGE_ENDLINE = '\r\n\r\n'
RTP_HEADER_SIZE = 12

class RTSPException(Exception):
    def __init__(self, response):
        super().__init__(f'Server error: {response.message} (error code: {response.response_code})')

class Response:
    def __init__(self, reader):
        '''Reads and parses the data associated to an RTSP response'''
        print('parsing')
        first_line = reader.readline().split(' ', 2)
        print(first_line)
        if len(first_line) != 3:
            raise Exception('Invalid response format. Expected first line with version, code and message')
        self.version, _, self.message = first_line
        if self.version != 'RTSP/1.0':
            raise Exception('Invalid response version. Expected RTSP/1.0')
        self.response_code = int(first_line[1])
        self.headers = {}
        
        while True:
            line = reader.readline().strip()
            if not line or ':' not in line: break
            hdr_name, hdr_value = line.split(':', 1)
            self.headers[hdr_name.lower()] = hdr_value
            if hdr_name.lower() == 'cseq':
                self.cseq = int(hdr_value)
            elif hdr_name.lower() == 'session':
                self.session_id = int(hdr_value)
        
        if self.response_code != 200:
            print('raise exception')
            raise RTSPException(self)

        print(self.cseq)
        print(self.session_id)
    
class Connection:

    def __init__(self, session, address):
        '''Establishes a new connection with an RTSP server. No message is
	sent at this point, and no stream is set up.
        '''
        self.BUFFER_LENGTH = 0x10000
        self.BUFFER_THRESHOLD = 120 # one second for now
        self.PLAYBACK_RATE = 1/25
        self.session = session
        self.cseq = None
        self.buffer = []
        self.playback_buffer = []
        self.state = 'INIT'
        self.is_rtp_running = False
        self.address = address[0]
        self.port = int(address[1])

        # statistics counters
        self.out_of_order_pkts = 0
        self.total_pkts = 0
        self.lost_pkts = 0
        self.frame_seqnum = -1
        self.max_seqnum = 0
        self.playback_seq_no = -1
        self.early_packets = 0
        self.late_packets = 0
        self.start_time = 0
        self.end_time = 0
    
        self.stat_flag = 1
        self.enable_buffer_playout = False
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection = (self.address, self.port)
        self.socket.connect(connection)
        

    def send_request(self, command, include_session=True, extra_headers=None):
        '''Helper function that generates an RTSP request and sends it to the
        RTSP connection.
        '''
        if self.cseq is None:
            req = command[0]
            self.cseq = 1
            transport = command[1]
            port = command[2]
            if req != "SETUP":
                # error handling
                return
            request = req + " " + self.session.video_name + " " + "RTSP/1.0\n" + "CSeq: " + str(self.cseq) + "\nTransport: " + transport + "; client_port= " + str(port) + "\n\n"
            print(request + 'sent')
            self.socket.send(request.encode())
            return
        else:
            req = command
            self.cseq = self.cseq + 1
            session = self.session_id
            request = req + " " + self.session.video_name + " " + "RTSP/1.0\n" + "Cseq: " + str(self.cseq) + "\nSession: " + str(session) + "\n\n"
            print(request + 'sent')
            self.socket.send(request.encode())
            return

    def start_rtp_timer(self):
        '''Starts a thread that reads RTP packets repeatedly and process the
	corresponding frame (method ). The data received from the
	datagram socket is assumed to be no larger than BUFFER_LENGTH
	bytes. This data is then parsed into its useful components,
	and the method `self.session.process_frame()` is called with
	the resulting data. In case of timeout no exception should be
	thrown.
        '''
        self.playEvent = Event()
        Thread(target=self.listen_for_rtp).start()
        Timer(1.0, self.process_frames).start()
        self.playEvent.clear()

    def listen_for_rtp(self):
        while True:
            try:
                data, addr = self.rtp_socket.recvfrom(self.BUFFER_LENGTH)
                if data:
                    rtp_header = bytearray(data[:RTP_HEADER_SIZE])
                    rtp_payload = data[RTP_HEADER_SIZE:]
                    
                    marker = int(rtp_header[1] >> 7)
                    payload_type = int(rtp_header[1] & 0x7F)
                    seq_num = int(rtp_header[2] << 8 | rtp_header[3])
                    timestamp = int(rtp_header[4] << 24 | rtp_header[5] << 16 | rtp_header[6] << 8 | rtp_header[7])
                    if seq_num < self. playback_seq_no:
                        continue
                    frame = (payload_type, marker, seq_num, timestamp, rtp_payload)
                    self.insert_frame(frame)
                    # # self.buffer.append(frame)
                    # self.total_pkts += 1
                    # if self.frame_seqnum + 1 != seq_num:
                    #     self.out_of_order_pkts += 1
                    #     print('out of order')
                    #     print(self.frame_seqnum)
                    #     print(seq_num)
                    #     if self.frame_seqnum + 1 > seq_num:
                    #         self.late_packets += 1
                    #     else:
                    #         self.early_packets += 1

                    # self.frame_seqnum = seq_num
                    # if seq_num > self.max_seqnum:
                    #     self.max_seqnum = seq_num
                
                    # self.session.process_frame(payload_type, marker, seq_num, timestamp, rtp_payload)
            except Exception as e:
                print(e)
                self.end_time = time.time()
                total_time = int(self.end_time - self.start_time) - 1

                pkts_lost = (self.max_seqnum + 1) - self.total_pkts
                frame_rate = self.total_pkts / (total_time)
                pkt_lost_rate = pkts_lost / (total_time)

                print('Total Frame Rate: ' + str(frame_rate))
                print('Packet Loss Rate: ' + str(pkt_lost_rate))
                print('Number of Out Of Order Packets: ' + str(self.out_of_order_pkts))
                print('Number of Early Packets: ' + str(self.early_packets))
                print('Number of Late Packets: ' + str(self.late_packets))

                self.stat_flag = 0

                if self.signalTeardown == True:
                    self.rtp_socket.shutdown(socket.SHUT_RDWR)
                    self.rtp_socket.close()
                    break
                if self.playEvent.is_set():
                    break
                
    def insert_frame(self, frame):
        seq_no = frame[2]
        for e in range(len(self.buffer)):
            if self.buffer[e][2] > seq_no:
                self.buffer.insert(e, frame)
                return
        self.buffer.insert(len(self.buffer) - 1, frame)
        return

    def process_frames(self):
        start_time = time.time()
        while True:
            if self.playEvent.is_set() or self.signalTeardown == True:
                self.buffer = []
                break
            if self.enable_buffer_playout == False and len(self.buffer) > self.BUFFER_THRESHOLD / 2:
                self.start_time = time.time()
                self.enable_buffer_playout = True
            if len(self.buffer) == 0:
                self.enable_buffer_playout = False
            if self.enable_buffer_playout:
                frame = self.buffer[0]
                while (frame[2] < self.playback_seq_no) and (len(self.buffer) != 0):
                    frame = self.buffer.pop(0)
                if frame[2] != self.playback_seq_no:
                    self.playback_seq_no += 1
                    time.sleep(self.PLAYBACK_RATE)
                    continue

                payload_type = frame[0]
                marker = frame[1]
                seq_num = frame[2]
                timestamp = frame[3]
                rtp_payload = frame[4]
                self.playback_seq_no += 1
                self.session.process_frame(payload_type, marker, seq_num, timestamp, rtp_payload)

                time.sleep(self.PLAYBACK_RATE)
                self.total_pkts += 1
                if self.frame_seqnum + 1 != seq_num:
                    self.out_of_order_pkts += 1
                    print('out of order')
                    print(self.frame_seqnum)
                    print(seq_num)
                    if self.frame_seqnum + 1 > seq_num:
                        self.late_packets += 1
                    else:
                        self.early_packets += 1

                self.frame_seqnum = seq_num
                if seq_num > self.max_seqnum:
                    self.max_seqnum = seq_num

    def stop_rtp_timer(self):
        '''Stops the thread that reads RTP packets'''

        self.playEvent.set()

    def recv_response(self):
        resp_string = self.socket.recv(2048)
        resp_string = resp_string.decode()
        while not MESSAGE_ENDLINE in resp_string:
            recv_buf = self.socket.recv(2048)
            if not recv_buf: break
            resp_string += recv_buf
        return resp_string

    def setup(self):
        '''Sends a SETUP request to the server. This method is responsible for
	sending the SETUP request, receiving the response and
	retrieving the session identification to be used in future
	messages. It is also responsible for establishing an RTP
	datagram socket to be used for data transmission by the
	server. The datagram socket should be created with a random
	UDP port number, and the port number used in that connection
	has to be sent to the RTSP server for setup. This datagram
	socket should also be defined to timeout after 1 second if no
	packet is received.
        '''
        print(self.state)
        if self.state == 'INIT':
            self.signalTeardown = False
            self.cseq = None

            self.rtp_socket = socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
            self.rtp_socket.settimeout(1)
            self.rtp_socket.bind((self.address, 0))
            self.rtp_port = self.rtp_socket.getsockname()[1]
            print(self.rtp_port)

            command_input = ('SETUP', 'RTP/UDP', self.rtp_port)
            self.send_request(command_input)

            resp = Response(self.socket.makefile("r"))
            self.session_id = resp.session_id
            self.state = 'READY'
            self.out_of_order_pkts = 0
            self.total_pkts = 0
            self.playback_seq_no = 0
            self.lost_pkts = 0
            self.frame_seqnum = -1
            self.max_seqnum = 0
            self.early_packets = 0
            self.late_packets = 0
            self.start_time = 0
            self.end_time = 0


    def play(self):
        '''Sends a PLAY request to the server. This method is responsible for
	sending the request, receiving the response and, in case of a
	successful response, starting the RTP timer responsible for
	receiving RTP packets with frames.
        '''
        if self.state == 'READY':
            self.start_rtp_timer()
            self.send_request('PLAY')
            
            resp = Response(self.socket.makefile("r"))
            self.state = 'PLAYING'

    def pause(self):
        '''Sends a PAUSE request to the server. This method is responsible for
	sending the request, receiving the response and, in case of a
	successful response, cancelling the RTP thread responsible for
	receiving RTP packets with frames.
        '''

        if self.state == 'PLAYING':
            self.stop_rtp_timer()
            self.send_request('PAUSE')

            resp = Response(self.socket.makefile("r"))
            self.state = 'READY'

    def teardown(self):
        '''Sends a TEARDOWN request to the server. This method is responsible
	for sending the request, receiving the response and, in case
	of a successful response, closing the RTP socket. This method
	does not close the RTSP connection, and a further SETUP in the
	same connection should be accepted. Also this method can be
	called both for a paused and for a playing stream, so the
	timer responsible for receiving RTP packets will also be
	cancelled.
        '''
        if self.state == 'READY' or self.state == 'PLAYING':
            self.send_request('TEARDOWN')
            resp = Response(self.socket.makefile("r"))
            if self.state == 'PLAYING':
                self.signalTeardown = True
            else:
                print("Closing the RTP socket here")
                self.rtp_socket.shutdown(socket.SHUT_RDWR)
                self.rtp_socket.close()
            self.state = 'INIT'


    def close(self):
        '''Closes the connection with the RTSP server. This method should also
	close any open resource associated to this connection, such as
	the RTP connection, if it is still open.
        '''
        self.signalTeardown = True
        self.socket.shutdown(socket.SHUT_RDWR)
        self.socket.close()
        
