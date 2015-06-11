import django
import time
from collections import deque
from twisted.internet import reactor
from channels import Channel, channel_backends, DEFAULT_CHANNEL_BACKEND
from autobahn.twisted.websocket import WebSocketServerProtocol, WebSocketServerFactory


class InterfaceProtocol(WebSocketServerProtocol):
    """
    Protocol which supports WebSockets and forwards incoming messages to
    the django.websocket channels.
    """

    def onConnect(self, request):
        self.channel_backend = channel_backends[DEFAULT_CHANNEL_BACKEND]
        self.request = request

    def onOpen(self):
        # Make sending channel
        self.send_channel = Channel.new_name("django.websocket.send")
        self.factory.protocols[self.send_channel] = self
        # Send news that this channel is open
        Channel("django.websocket.connect").send(
            send_channel = self.send_channel,
        )

    def onMessage(self, payload, isBinary):
        if isBinary:
            Channel("django.websocket.receive").send(
                send_channel = self.send_channel,
                content = payload,
                binary = True,
            )
        else:
            Channel("django.websocket.receive").send(
                send_channel = self.send_channel,
                content = payload.decode("utf8"),
                binary = False,
            )

    def onChannelSend(self, content, binary=False, **kwargs):
        self.sendMessage(content, binary)

    def onClose(self, wasClean, code, reason):
        del self.factory.protocols[self.send_channel]
        Channel("django.websocket.disconnect").send(
            send_channel = self.send_channel,
        )


class InterfaceFactory(WebSocketServerFactory):
    """
    Factory which keeps track of its open protocols' receive channels
    and can dispatch to them.
    """

    # TODO: Clean up dead protocols if needed?

    def __init__(self, *args, **kwargs):
        super(InterfaceFactory, self).__init__(*args, **kwargs)
        self.protocols = {}

    def send_channels(self):
        return self.protocols.keys()

    def dispatch_send(self, channel, message):
        self.protocols[channel].onChannelSend(**message)


class WebsocketTwistedInterface(object):
    """
    Easy API to run a WebSocket interface server using Twisted.
    Integrates the channel backend by running it in a separate thread, as we don't
    know if the backend is Twisted-compliant.
    """

    def __init__(self, channel_backend, port=9000):
        self.channel_backend = channel_backend
        self.port = port

    def run(self):
        self.factory = InterfaceFactory("ws://localhost:%i" % self.port, debug=False)
        self.factory.protocol = InterfaceProtocol
        reactor.listenTCP(self.port, self.factory)
        reactor.callInThread(self.backend_reader)
        reactor.run()

    def backend_reader(self):
        """
        Run in a separate thread; reads messages from the backend.
        """
        while True:
            channels = self.factory.send_channels()
            # Don't do anything if there's no channels to listen on
            if channels:
                channel, message = self.channel_backend.receive_many(channels)
            else:
                time.sleep(0.1)
                continue
            # Wait around if there's nothing received
            if channel is None:
                time.sleep(0.05)
                continue
            # Deal with the message
            self.factory.dispatch_send(channel, message)
