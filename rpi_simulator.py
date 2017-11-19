from threading import Thread, Lock
import socket
import time
from config_loader import CONFIG

# Pin mapping for simulator
_pin_map = {}

simulatorConn = None

# We require a lock since there will be 2 threads that need to read/write access the pin_map variable
# The two threads are
# 1. Main Thread for GPIO class
# 2. Server Run Thread for Simulator connection
_pin_map_lock = Lock()


class GPIO:
    """
    Simulates (stub for) GPIO module on raspberry pi
    """

    BCM = 1
    IN = 1
    BOTH = 1

    @staticmethod
    def add_event_detect(pin, rf_type, callback, bouncetime):
        global _pin_map
        global _pin_map_lock

        with _pin_map_lock:

            (curState, old_call) = _pin_map[pin]
            _pin_map[pin] = (curState, callback)

    @staticmethod
    def input(pin):
        global _pin_map
        global _pin_map_lock

        with _pin_map_lock:
            if pin in _pin_map:
                return _pin_map[pin][0]

    @staticmethod
    def output(pin, value):
        global _pin_map
        global _pin_map_lock
        global simulatorConn

        # Define the callback outside the Crit. section so that it doesnt cause a deadlock
        callback = None

        with _pin_map_lock:
            if pin in _pin_map:
                (old_val, callback) = _pin_map[pin]
                _pin_map[pin] = (value, callback)

        if callback is not None:
            callback(pin)

        if simulatorConn:
            simulatorConn.set_should_sync()

    @staticmethod
    def setup(pin, dir):
        global _pin_map
        global _pin_map_lock

        print("[Simulator]: Set up pin", pin)
        with _pin_map_lock:
            _pin_map[pin] = (0, None)

    @staticmethod
    def setmode(mode):
        print("[Simulator] Set board mode to", mode)

    @staticmethod
    def cleanup():
        print("[Simulator]: Cleaned up!")

        if simulatorConn:
            simulatorConn.shutdown()


class SimulatorConnection:
    """
    Sets up a server
    """
    serverSocket = None
    clientSocket = None
    thread = None
    lock = Lock()
    sync_client_lock = Lock()
    should_sync = False
    run_thread = False

    def __init__(self):
        # Create socket & bind
        self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serverSocket.bind(("127.0.0.1", CONFIG.debug_config.simulator_config.port))
        self.serverSocket.listen(1)

        self.thread = Thread(target=self.server_run_thread)
        self.run_thread = True

        print("[Simulator] Waiting for simulator client. Connect to:", self.serverSocket.getsockname())
        self.thread.start()

    def server_run_thread(self):
        """
        Run server thread that accepts incoming connections for simulator,
        and sends / receives messages for updating GPIO
        :return: None
        """

        # Accept the simulator client
        res = self.accept_client()

        # Check that the server thread should still run.
        # Its possible that it needs to stop after making the above call
        if not self.can_run_thread():
            return

        (client, caddr) = res
        self.clientSocket = client

        print("Simulator Client Connected:", caddr)

        # Set socket options with the client
        self.clientSocket.settimeout(30)
        self.clientSocket.setblocking(False)

        # First, we want to send the current state of the pins
        self.sync_with_client()

        while self.can_run_thread():

            try:
                chunk = self.clientSocket.recv(1024)
                self.process_message(chunk)

                if self.should_sync_client():
                    self.sync_with_client()
            except socket.error as serror:
                # Check errno, if EAGAIN, then it just means that no data was available and
                # we should ignore the error and try again. This is a result of the non-blocking recv call
                if serror.errno == socket.errno.EAGAIN:
                    pass
                else:
                    print(serror)

            # Rest
            time.sleep(0.1)

    def set_should_sync(self, val=True):
        """
        Sets whether or not we need to sync with the client
        :param val: True if client needs to sync
        :return: None
        """

        with self.sync_client_lock:
            self.should_sync = val

    def should_sync_client(self):
        """
        Synchronized method to see if the simulator client needs to sync up with pin map
        :return: Whether client needs sync
        """
        with self.sync_client_lock:
            return self.should_sync

    def can_run_thread(self):
        """
        Synchronized method that checks to see if the thread should still be running
        :return: True if the thread can run
        """
        with self.lock:
            return self.run_thread

    def sync_with_client(self):
        """
        Synchronize pin map with GPIO simulator
        :return: None
        """
        global _pin_map
        global _pin_map_lock

        # Need sync access to pin map
        with _pin_map_lock:

            send_b = bytearray()

            for pin, (state, callback) in _pin_map.items():
                send_b.append(0x35)
                send_b.append(pin)
                send_b.append(state)

            # Send all GPIO pins to simulator
            self.clientSocket.send(send_b)

            # No longer needs to sync with client
            self.set_should_sync(False)

    def accept_client(self):
        """
        Accepts a simulator client.
        Will only return if a client gets accepted.
        :return: socket.accept tuple
        """
        self.serverSocket.setblocking(False)

        while self.can_run_thread():

            try:
                res = self.serverSocket.accept()
                return res
            except socket.error as serror:
                # Check errno, if EAGAIN, then it just means that no data was available and
                # we should ignore the error and try again. This is a result of the non-blocking recv call
                if serror.errno == socket.errno.EAGAIN:
                    pass

            # Rest
            time.sleep(0.1)

    '''
    Process a message received by the simulator client
    '''
    def process_message(self, chunk):
        if len(chunk) < 1 or len(chunk) > 3:
            return

        cmd_num = chunk[0]

        # Cmd is updating GPIO pin, requires two more arguments
        if cmd_num == 0x35:
            arg_1 = chunk[1]
            arg_2 = chunk[2]

            GPIO.output(arg_1, arg_2)

        elif cmd_num == 0x10:
            print("Syncing")
            self.sync_with_client()

    def shutdown(self):
        with self.lock:
            self.run_thread = False

        self.thread.join()

        if self.serverSocket:
            self.serverSocket.close()

        if self.clientSocket:
            self.clientSocket.close()

        print("[Simulator] Server Thread stopped!")


if CONFIG.debug_config.simulator_config.enabled:
    simulatorConn = SimulatorConnection()
else:
    print("[Simulator]: Remote simulator not enabled")
